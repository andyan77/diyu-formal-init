from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from email.utils import parsedate_to_datetime
from typing import Any, cast

import httpx

from src.ports.content_generator import ContentGenerator
from src.ports.reviewer_provider import ReviewerProvider
from src.shared.clause_license import (
    CLAUSE_LICENSE_REVIEW_VERSION,
    CLAUSE_LICENSE_TOOL_NAME,
    ClauseLicenseReviewsV1,
    ClauseLicenseReviewV1,
    ClauseLicenseV1,
    UnitClauseLicensePolicyV1,
    clause_license_review_json_schema,
    materialize_clause_licenses_v1,
    parse_clause_license_reviews_v1,
    prohibited_binding_question_v1,
    reconcile_clause_license_reviews_v1,
    unsupported_quote_candidates_v1,
)
from src.shared.closed_review import (
    CLOSED_REVIEW_TOOL_NAME,
    CLOSED_REVIEW_VERSION,
    ClosedReviewAnswers,
    ClosedReviewQuestion,
    closed_review_json_schema,
    parse_closed_review_answers,
)
from src.shared.content_origin import aigc_disclosure
from src.shared.creative_kernel import (
    DRAMATIZATION_DISCLOSURE,
    HYPOTHESIS_DISCLOSURE,
    KERNEL_VERSION,
    MAX_PRODUCT_FACT_BLOCKS,
    CreativeKernelV1,
    build_kernel_skeleton,
    compiler_owned_unit_source,
    compiler_owned_unit_texts,
    creative_units_digest,
    freeze_prior_revision_units,
    kernel_digest,
    kernel_document,
    parse_writer_kernel,
    select_kernel_program,
)
from src.shared.creative_plan import (
    creative_plan_document,
    creative_plan_from_document,
    validate_creative_plan,
)
from src.shared.delivery_compiler import (
    DELIVERY_COMPILER_VERSION,
    DeliveryCompileInput,
    assert_compiled_delivery,
    compile_delivery,
)
from src.shared.errors import DomainError, GenerationFailed
from src.shared.factual_basis import (
    FrozenFactRecord,
    ImmutableFactBlock,
    ProductFactPacket,
    brand_fact_records,
    build_product_fact_packet,
    immutable_fact_blocks_document,
    immutable_product_fact_blocks,
    product_fact_literal_spans,
    product_fact_packet_document,
    product_fact_records,
    registered_product_claims,
    select_product_fact_block_ids,
)
from src.shared.narrative import (
    NarrativeBlock,
    NarrativeBlockType,
    NarrativeFrame,
    NarrativeIssue,
    NarrativeMode,
    legacy_frame,
    parse_observation,
    reconcile_observations,
    visible_digest,
)
from src.shared.review_evidence import (
    ClauseContextV2,
    UnitContractV2,
    build_clause_contexts_v2,
    unit_contracts_v2,
    validate_server_owned_contexts_v2,
    writer_clause_contexts_v2,
)
from src.shared.types import (
    ContentProduct,
    ContentProductionBundle,
    ContentSemanticContract,
    ConversationDecision,
    ConversationInput,
    FactRepairReceipt,
    GeneratedArtifact,
    GenerationInput,
    GraphicProductionBundle,
    P1SemanticContract,
    P2SemanticContract,
    P3SemanticContract,
    P4SemanticContract,
    P5SemanticContract,
    ProductFact,
    RoutingInput,
    VideoProductionBundle,
)

_LOGGER = logging.getLogger(__name__)
_SPEAKER_ID = "speaker:brand_account"
_CREATOR_ACTOR_ID = "actor:creator"
_CREATOR_EXPRESSION_RESOURCE_ID = "resource:creator_expression"
_ORIGINAL_COMPOSITION_RESOURCE_ID = "resource:original_composition"
_SPOKEN_SLOT = "spoken"
_COVER_PURPOSE = "cover"
_SCENE_PURPOSE = "scene"
_REVIEW_TOKEN_BASE = 1024
_REVIEW_TOKEN_PER_QUESTION = 160
_LICENSE_REVIEW_TOKEN_PER_CLAUSE = 640
_REVIEW_TOKEN_HARD_LIMIT = 16384
_CLOSED_REVIEW_BATCH_CLAUSES = 8

_CONTRACT_FIELDS: dict[ContentProduct, tuple[str, str, str]] = {
    "dressing_decision": ("choice", "boundary", "next_action"),
    "product_truth": (
        "product_insight",
        "tradeoff_or_limit",
        "validity_condition",
    ),
    "brand_life_narrative": (
        "persona_observation",
        "audience_return",
        "brand_account_link",
    ),
    "local_response": (
        "local_reality_or_signal",
        "legitimate_account_response",
        "public_relationship_return",
    ),
    "visual_styling_story": (
        "real_product_anchor",
        "visible_styling_proposition",
        "visual_dependency",
    ),
}
_PRODUCT_VALUE: dict[ContentProduct, str] = {
    "dressing_decision": "帮助受众完成有条件、有边界的穿衣选择",
    "product_truth": "解释一件商品能确认什么、不能确认什么",
    "brand_life_narrative": "让受众认识这个账号怎样观察、判断和待人",
    "local_response": "从近场信号给未参与者一份关系回应",
    "visual_styling_story": "用真实商品与画面动作创造可见的穿着可能",
}
_MODE_BLOCK_TYPE: dict[NarrativeMode, NarrativeBlockType] = {
    "actuality_reflection": "general_observation",
    "general_observation": "general_observation",
    "hypothesis": "hypothesis",
    "dramatization": "dramatization",
}


@dataclass(frozen=True)
class SceneStep:
    step_id: str
    purpose: str
    actor_refs: tuple[str, ...]
    resource_refs: tuple[str, ...]
    action_text: str
    sound_text: str
    production_note: str
    block_refs: tuple[str, ...]


@dataclass(frozen=True)
class NarrativeCore:
    speaker_ref: str
    blocks: tuple[NarrativeBlock, ...]
    spoken_order: tuple[str, ...]
    scene_steps: tuple[SceneStep, ...]

    def block(self, block_id: str) -> NarrativeBlock:
        for block in self.blocks:
            if block.block_id == block_id:
                return block
        raise KeyError(block_id)

    @property
    def target_ids(self) -> tuple[str, ...]:
        return tuple(block.block_id for block in self.blocks) + tuple(scene.step_id for scene in self.scene_steps)


@dataclass(frozen=True)
class BlockSkeleton:
    block_id: str
    block_type: NarrativeBlockType
    slot: str
    fact_refs: tuple[str, ...]
    constraint_refs: tuple[str, ...]
    linked_scene_ids: tuple[str, ...]


@dataclass(frozen=True)
class SceneSkeleton:
    scene_id: str
    purpose: str
    block_refs: tuple[str, ...]
    allowed_resource_refs: tuple[str, ...]


@dataclass(frozen=True)
class NarrativeSkeleton:
    blocks: tuple[BlockSkeleton, ...]
    service_actuality_blocks: tuple[NarrativeBlock, ...]
    scenes: tuple[SceneSkeleton, ...]
    spoken_order: tuple[str, ...]


@dataclass(frozen=True)
class BoundaryContext:
    fact_registry: tuple[FrozenFactRecord, ...]
    product_fact_packet: ProductFactPacket
    product_fact_blocks: tuple[ImmutableFactBlock, ...]
    constraint_registry: tuple[tuple[str, str], ...]
    resource_registry: tuple[tuple[str, str], ...]
    actor_registry: tuple[tuple[str, str], ...]
    product_facts_text: str
    brand_text: str
    method_text: str

    @property
    def fact_text_by_id(self) -> dict[str, str]:
        return {record.fact_id: record.exact_text for record in self.fact_registry}

    @property
    def brand_fact_ids(self) -> frozenset[str]:
        return frozenset(record.fact_id for record in self.fact_registry if record.fact_kind == "brand")

    @property
    def constraint_ids(self) -> frozenset[str]:
        return frozenset(identifier for identifier, _ in self.constraint_registry)

    @property
    def resource_ids(self) -> frozenset[str]:
        return frozenset(identifier for identifier, _ in self.resource_registry)

    @property
    def actor_ids(self) -> frozenset[str]:
        return frozenset(identifier for identifier, _ in self.actor_registry)

    @classmethod
    def from_request(
        cls,
        request: GenerationInput,
        frame: NarrativeFrame,
    ) -> BoundaryContext:
        if request.creative_plan is None:
            raise GenerationFailed("生成请求缺少冻结的 CreativePlanV2")
        product_records = tuple(
            record
            for product in request.products
            for record in product_fact_records(product)
            if record.fact_id in frame.allowed_product_fact_ids
        )
        product_fact_packet = build_product_fact_packet(
            request.products,
            allowed_fact_ids=frame.allowed_product_fact_ids,
        )
        product_fact_blocks = immutable_product_fact_blocks(product_fact_packet)
        brand_records = tuple(
            record
            for record in brand_fact_records(request.brand.brand_reference_context)
            if record.fact_id in frame.allowed_brand_fact_ids
        )
        if {record.fact_id for record in product_records} != set(frame.allowed_product_fact_ids) or {
            record.fact_id for record in brand_records
        } != set(frame.allowed_brand_fact_ids):
            raise GenerationFailed("冻结事实标识无法解析到当前精确原句")
        user_records = tuple(
            FrozenFactRecord(
                fact_id=fact.source_id,
                exact_text=fact.exact_text,
                fact_kind="user_actuality",
            )
            for fact in frame.user_facts
        )
        fact_registry = (*user_records, *product_records, *brand_records)
        product_facts_text = "\n".join(f"- {record.fact_id}：{record.exact_text}" for record in product_records)
        constraint_registry = (
            ("source:brand_baseline", "当前品牌定位、判断顺序与语气"),
            ("source:role_boundary", "当前发布账号的表达身份与资格边界"),
            (
                "source:organization",
                "当前组织与账号作用域；只限制表达资格，不证明机构立场",
            ),
            ("constraint:creative-plan-v2", "冻结 CreativePlanV2"),
            ("constraint:platform-shape", "目标平台与内容形式"),
            *((tone_id, "用户显式选择或账号合法基线语气") for tone_id in request.creative_plan.tone_ids),
            *(
                ((request.creative_plan.mechanism_id, "既有内容机制"),)
                if request.creative_plan.mechanism_id is not None
                else ()
            ),
        )
        resource_registry = (
            (
                _CREATOR_EXPRESSION_RESOURCE_ID,
                "创作者本人可选择口播、旁白、手势或不出镜表达；不证明其具有题材中的家庭、职业或经历身份",
            ),
            (
                _ORIGINAL_COMPOSITION_RESOURCE_ID,
                "本次原创的抽象构图、排版、留白、色块、符号、文字和声音组织；"
                "不包含现实人物、场地、家具、照片、商品或外部素材",
            ),
            *(
                (
                    f"resource:product:{product.sku}",
                    f"本次已确认可用商品样衣 {product.sku}",
                )
                for product in request.products
            ),
        )
        method_parts = [
            "冻结 CreativePlanV2："
            + json.dumps(
                creative_plan_document(request.creative_plan),
                ensure_ascii=False,
                sort_keys=True,
            ),
            *(
                (
                    (
                        "用户本次明确选择的创作控制（只调整表达方法，不证明现实事实）："
                        + "；".join(
                            f"{selection.axis}：{selection.applied_label}"
                            for selection in request.creative_direction.selections
                        )
                    ),
                    (
                        "用户本次自然补充的创作控制（只调整表达方法，成品不得讨论这段"
                        "控制说明本身）：" + request.creative_direction.custom_text
                    ),
                )
                if request.creative_direction is not None
                else ()
            ),
            *(
                ("本次选用的参考材料（只作为表达参考，不证明现实对象或事件存在）：" + material.text_body)
                for material in request.reference_materials
                if material.text_body
            ),
            *(
                ("本次参考材料使用说明（只调整创作方法，不是成品素材）：" + material.reference_note)
                for material in request.reference_materials
                if material.reference_note
            ),
            *(
                (
                    (
                        "私人协作偏好说明只调整协作方式与表达取舍，成品中不得出现它的"
                        "原文、转述或对它的解释：" + request.collaboration_note
                    ),
                )
                if request.collaboration_note
                else ()
            ),
            *("方法资料（不证明现实对象存在）：" + asset.body for asset in request.active_domain_assets),
        ]
        brand_text = (
            f"品牌：{request.brand.brand_name}；组织：{request.brand.organization_name}；"
            f"账号：{request.brand.account_name}；表达身份：{request.brand.content_role_name}；"
            f"资格边界：{request.brand.content_role_boundary}；"
            f"定位：{request.brand.positioning}；判断顺序：{request.brand.decision_order}；"
            f"语气：{request.brand.tone}。这些只支持当前立场，不证明任何经历、案例、"
            "门店做法或经营历史已经发生。"
        )
        return cls(
            fact_registry=fact_registry,
            product_fact_packet=product_fact_packet,
            product_fact_blocks=product_fact_blocks,
            constraint_registry=constraint_registry,
            resource_registry=resource_registry,
            actor_registry=(
                (
                    _CREATOR_ACTOR_ID,
                    "当前创作者，仅以拍摄者／表达者身份出现，不扮演题材人物",
                ),
            ),
            product_facts_text=product_facts_text or "（本次没有冻结商品事实。）",
            brand_text=brand_text,
            method_text="\n".join(part for part in method_parts if part),
        )


class DeepSeekGenerator(ContentGenerator):
    """DeepSeek intake and typed Writer for the server-owned dual-track runtime."""

    def __init__(
        self,
        api_base_url: str,
        api_key: str,
        model: str,
        reviewer_provider: ReviewerProvider | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._reviewer_provider = reviewer_provider
        self._reviewer_model = reviewer_provider.model_name if reviewer_provider is not None else None
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._review_timeout_seconds = max(timeout_seconds, 60.0)

    @property
    def model_name(self) -> str:
        return self._model

    def route(self, request: RoutingInput) -> ContentProduct | None:
        payload, _ = self._request(
            "你是笛语内容任务路由器。只返回 JSON，不解释。",
            self._routing_prompt(request),
            700,
        )
        try:
            document = json.loads(self._json_content(str(payload["choices"][0]["message"]["content"])))
            value = document.get("primary_value")
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise GenerationFailed("模型路由返回格式不完整") from exc
        mapping: dict[str, ContentProduct | None] = {
            "普通交流": None,
            "帮助选择": "dressing_decision",
            "解释商品": "product_truth",
            "建立人格": "brand_life_narrative",
            "经营关系": "local_response",
            "视觉造型": "visual_styling_story",
        }
        if not isinstance(value, str) or value not in mapping:
            raise GenerationFailed("模型路由返回了不支持的内容产品")
        return mapping[value]

    def collaborate(self, request: ConversationInput) -> ConversationDecision:
        payload, _ = self._request(
            "你是笛语内容工作台的自然协作入口。只返回 JSON，不展示推理或内部规则。",
            self._conversation_prompt(request),
            1800,
        )
        try:
            document = json.loads(self._json_content(str(payload["choices"][0]["message"]["content"])))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise GenerationFailed("这次还没能可靠理解你的意思，请继续补充一句。") from exc
        if not isinstance(document, dict):
            raise GenerationFailed("这次还没能可靠理解你的意思，请继续补充一句。")
        kind = document.get("kind")
        message = document.get("message")
        if kind not in {"chat", "question", "ready"} or not isinstance(message, str) or not message.strip():
            raise GenerationFailed("这次还没能可靠理解你的意思，请继续补充一句。")
        creation_proposal = bool(document.get("creation_proposal", kind == "ready"))
        raw_intent_span = document.get("intent_span")
        proposed_intent_span = raw_intent_span.strip() if isinstance(raw_intent_span, str) else ""
        if kind == "chat":
            return ConversationDecision(
                "chat",
                message.strip(),
                creation_proposal=creation_proposal,
                proposed_intent_span=proposed_intent_span,
            )
        available_user_turns = tuple(turn.content for turn in request.history if turn.role == "user") + (
            request.message,
        )
        if kind == "question":
            missing_span = document.get("missing_fact_span")
            if (
                not isinstance(missing_span, str)
                or not missing_span
                or not any(missing_span in user_turn for user_turn in available_user_turns)
            ):
                raise GenerationFailed("模型追问没有绑定用户的不可替代事实")
            return ConversationDecision(
                "question",
                message.strip(),
                creation_proposal=creation_proposal,
                proposed_intent_span=proposed_intent_span,
            )
        raw_premises = document.get("user_premises")
        raw_facts = document.get("user_fact_spans")
        raw_plan = document.get("creative_plan")
        if not isinstance(raw_premises, list) or not isinstance(raw_facts, list):
            raise GenerationFailed("模型协作返回格式不完整")
        premises = self._exact_string_list(raw_premises)
        facts = self._exact_string_list(raw_facts)
        if request.message not in premises or any(premise not in available_user_turns for premise in premises):
            raise GenerationFailed("模型没有逐字保留本次用户前提")
        premise_text = "\n".join(premises)
        if any(fact not in premise_text for fact in facts):
            raise GenerationFailed("模型返回的用户事实跨度不存在")
        explicit_mode = request.explicit_narrative_mode
        if explicit_mode is not None:
            if (explicit_mode == "actuality_reflection") != bool(facts):
                raise GenerationFailed("用户显式叙事形式与事实跨度不一致")
            narrative_mode = explicit_mode
        else:
            narrative_mode = "actuality_reflection" if facts else "general_observation"
        try:
            plan = creative_plan_from_document(raw_plan)
            validate_creative_plan(
                plan,
                user_turns=available_user_turns,
                allowed_tone_ids=request.allowed_tone_ids,
                allowed_mechanism_ids=request.allowed_mechanism_ids,
                expected_primary_value=plan.primary_value,
                expected_platform_shape=request.platform_shape,
            )
        except DomainError as exc:
            raise GenerationFailed("模型返回的 CreativePlanV2 超出冻结边界") from exc
        return ConversationDecision(
            "ready",
            message.strip(),
            user_premises=premises,
            user_fact_spans=facts,
            narrative_mode=narrative_mode,
            creative_plan=plan,
            primary_product=plan.primary_value,
            creation_proposal=creation_proposal,
            proposed_intent_span=proposed_intent_span,
        )

    def generate(self, request: GenerationInput) -> GeneratedArtifact:
        if request.delivery_compiler_version is None:
            raise GenerationFailed("新内容生成缺少确定性成品编译合同")
        if request.delivery_compiler_version != DELIVERY_COMPILER_VERSION:
            raise GenerationFailed("不支持的确定性成品编译版本")
        return self._generate_kernel(request)

    def _generate_kernel(
        self,
        request: GenerationInput,
    ) -> GeneratedArtifact:
        started = time.monotonic()
        retries = 0
        provider_payloads: list[dict[str, Any]] = []
        if request.narrative_frame is None or request.creative_plan is None:
            raise GenerationFailed("CreativeKernelV1 缺少冻结计划或叙事框架")
        frame = request.narrative_frame
        context = BoundaryContext.from_request(request, frame)
        program_id = select_kernel_program(
            frame=frame,
            prior_kernel=request.prior_creative_kernel,
            revision_instruction=request.revision_instruction,
        )
        skeleton = build_kernel_skeleton(
            frame=frame,
            fact_registry=context.fact_registry,
            constraint_refs=tuple(identifier for identifier, _ in context.constraint_registry),
            program_id=program_id,
            allowed_resource_ids=tuple(sorted(context.resource_ids)),
        )
        skeleton = freeze_prior_revision_units(
            skeleton,
            request.prior_creative_kernel,
        )
        required_fact_block_ids = (
            self._prior_fact_block_ids(
                request.prior_creative_kernel,
                context.product_fact_blocks,
            )
            if request.prior_creative_kernel is not None
            else None
        )
        selected_fact_block_ids = (
            required_fact_block_ids
            or select_product_fact_block_ids(
                context.product_fact_packet,
                limit=MAX_PRODUCT_FACT_BLOCKS,
            )
        )
        if context.product_fact_blocks:
            skeleton = replace(
                skeleton,
                selected_fact_block_ids=selected_fact_block_ids,
            )
        compiler_texts = compiler_owned_unit_texts(request.primary_product)
        writer_payload, writer_retries = self._request(
            "你是笛语 CreativeKernel Writer。只返回服务端既定 unit 的创作文字 JSON，不展示推理或内部规则。",
            self._kernel_writer_prompt(
                request,
                skeleton,
                compiler_texts,
            ),
            4096,
        )
        provider_payloads.append(writer_payload)
        retries += writer_retries
        try:
            kernel = parse_writer_kernel(
                json.loads(self._json_content(str(writer_payload["choices"][0]["message"]["content"]))),
                skeleton,
                fact_blocks=context.product_fact_blocks,
                allowed_claim_ids=context.product_fact_packet.fact_ids,
                required_fact_block_ids=required_fact_block_ids,
                compiler_owned_text_by_id=compiler_texts,
            )
            self._validate_product_fact_selection(
                request,
                context,
                kernel,
            )
        except (
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise GenerationFailed("CreativeKernelV1 Writer 返回格式不完整") from exc
        receipts: tuple[FactRepairReceipt, ...] = ()
        if request.revision_instruction and request.prior_creative_kernel:
            before = tuple(unit.text for unit in request.prior_creative_kernel.writable_units)
            after = tuple(unit.text for unit in kernel.writable_units)
            if before == after:
                raise GenerationFailed("本次修改没有实质改变允许修改的创作单元")
        reviewed_kernel_digest = kernel_digest(kernel)
        reviewed_creative_digest = creative_units_digest(kernel)
        compiled = compile_delivery(
            DeliveryCompileInput(
                primary_product=request.primary_product,
                media_format=request.media_format,
                products=request.products,
                production_conditions=request.brand.production_conditions,
                allowed_resource_ids=context.resource_ids,
                immutable_fact_blocks=context.product_fact_blocks,
                trusted_fact_texts=tuple(sorted(context.fact_text_by_id.items())),
            ),
            kernel,
        )
        assert_compiled_delivery(
            DeliveryCompileInput(
                primary_product=request.primary_product,
                media_format=request.media_format,
                products=request.products,
                production_conditions=request.brand.production_conditions,
                allowed_resource_ids=context.resource_ids,
                immutable_fact_blocks=context.product_fact_blocks,
                trusted_fact_texts=tuple(sorted(context.fact_text_by_id.items())),
            ),
            kernel,
            compiled,
        )
        digest = visible_digest(compiled.outline, compiled.body)
        return GeneratedArtifact(
            outline=compiled.outline,
            body=compiled.body,
            model=self._model,
            latency_ms=int((time.monotonic() - started) * 1000),
            retry_count=retries,
            provider_usage=self._provider_usage_receipt(provider_payloads),
            primary_product=request.primary_product,
            semantic_contract=compiled.semantic_contract,
            production=compiled.production,
            fact_repair_receipts=receipts,
            reviewed_digest=digest,
            completion_snapshot_patch={
                "creative_kernel_v2": kernel_document(kernel),
                "expression_plan_version": "expression-plan-v1",
                "expression_plan_digest": reviewed_kernel_digest,
                "delivery_compiler_version": DELIVERY_COMPILER_VERSION,
                "writer_model": self._model,
                "version_authorization": "deterministic-dual-track-v1",
                "claim_inventory_v1": [],
                "reviewed_kernel_digest": reviewed_kernel_digest,
                "reviewed_creative_digest": reviewed_creative_digest,
                "product_fact_packet": product_fact_packet_document(context.product_fact_packet),
                "immutable_product_fact_blocks": (
                    immutable_fact_blocks_document(
                        tuple(
                            block
                            for block_id in kernel.selected_fact_block_ids
                            for block in context.product_fact_blocks
                            if block.fact_block_id == block_id
                        )
                    )
                ),
                "used_product_fact_ids": [
                    block.fact_id
                    for block_id in kernel.selected_fact_block_ids
                    for block in context.product_fact_blocks
                    if block.fact_block_id == block_id
                ],
                "used_product_fact_block_ids": list(kernel.selected_fact_block_ids),
                "product_fact_renderer_version": (
                    context.product_fact_blocks[0].renderer_version if context.product_fact_blocks else None
                ),
                "visible_provenance": {field: list(sources) for field, sources in compiled.visible_provenance.items()},
                "delivery_resource_refs": list(compiled.resource_refs),
            },
        )

    def _generate_legacy(self, request: GenerationInput) -> GeneratedArtifact:
        started = time.monotonic()
        retries = 0
        provider_payloads: list[dict[str, Any]] = []
        frame = request.narrative_frame or legacy_frame(
            tuple(record.fact_id for product in request.products for record in product_fact_records(product))
        )
        context = BoundaryContext.from_request(request, frame)
        skeleton = self._narrative_skeleton(request, frame, context)
        writer_payload, writer_retries = self._request(
            "你是笛语类型化内容 Writer。只返回一个完整 JSON，不展示推理、规则或内部审查。",
            self._writer_prompt(request, frame, context, skeleton),
            8192,
        )
        provider_payloads.append(writer_payload)
        retries += writer_retries
        try:
            core = self._parse_core(
                request,
                frame,
                context,
                skeleton,
                json.loads(self._json_content(str(writer_payload["choices"][0]["message"]["content"]))),
            )
        except (
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise GenerationFailed("模型返回的类型化成品不完整") from exc

        title, contract, production, body = self._compile_core(request, core)
        issues, review_payload, review_retries = self._review_candidate(
            request,
            frame,
            context,
            core,
            body,
        )
        provider_payloads.append(review_payload)
        retries += review_retries
        receipts: tuple[FactRepairReceipt, ...] = ()
        if issues:
            self._assert_review_can_repair(core, issues)
            _LOGGER.warning(
                "narrative blocks selected for one repair: %s",
                ",".join(f"{issue.target_id}:{issue.reason}" for issue in issues),
            )
            repair_payload, repair_retries = self._request(
                "你是笛语类型化内容 Writer。只返回一次完整块级修复 JSON，不展示推理或审查。",
                self._repair_prompt(request, frame, context, core, issues),
                8192,
            )
            provider_payloads.append(repair_payload)
            retries += repair_retries
            try:
                repaired = self._merge_block_repair(
                    request,
                    frame,
                    context,
                    skeleton,
                    core,
                    issues,
                    json.loads(self._json_content(str(repair_payload["choices"][0]["message"]["content"]))),
                )
            except (
                KeyError,
                IndexError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                raise GenerationFailed("模型块级修复返回格式不完整") from exc
            title, contract, production, body = self._compile_core(request, repaired)
            final_issues, review_payload, review_retries = self._review_candidate(
                request,
                frame,
                context,
                repaired,
                body,
            )
            provider_payloads.append(review_payload)
            retries += review_retries
            if final_issues:
                _LOGGER.warning(
                    "narrative repair remained invalid: %s",
                    ",".join(f"{issue.target_id}:{issue.reason}" for issue in final_issues),
                )
                raise GenerationFailed("内容边界无法在一次叙事块修复内满足")
            receipts = self._repair_receipts(issues)
            core = repaired
        if request.revision_instruction and request.prior_saved_body:
            without_facts = body
            prior_without_facts = request.prior_saved_body
            for fact in frame.user_facts:
                without_facts = without_facts.replace(fact.exact_text, "")
                prior_without_facts = prior_without_facts.replace(fact.exact_text, "")
            if self._semantic_text(without_facts) == self._semantic_text(prior_without_facts):
                raise GenerationFailed("本次修改没有实质改变允许修改的表达块")
        digest = visible_digest(title, body)
        return GeneratedArtifact(
            outline=title,
            body=body,
            model=self._model,
            latency_ms=int((time.monotonic() - started) * 1000),
            retry_count=retries,
            provider_usage=self._provider_usage_receipt(provider_payloads),
            primary_product=request.primary_product,
            semantic_contract=contract,
            production=production,
            fact_repair_receipts=receipts,
            reviewed_digest=digest,
        )

    def _review_kernel(
        self,
        request: GenerationInput,
        context: BoundaryContext,
        kernel: CreativeKernelV1,
        license_policies: tuple[UnitClauseLicensePolicyV1, ...],
    ) -> tuple[
        tuple[NarrativeIssue, ...],
        tuple[ClauseLicenseV1, ...],
        ClauseLicenseReviewsV1,
        dict[str, Any],
        int,
    ]:
        clause_contexts = self._kernel_clause_contexts(
            request,
            context,
            kernel,
        )
        source_issues = validate_server_owned_contexts_v2(
            contexts=clause_contexts,
            fact_text_by_id=context.fact_text_by_id,
        )
        if source_issues:
            raise GenerationFailed("CreativeKernelV1 服务端来源合同不完整")
        writer_contexts = writer_clause_contexts_v2(clause_contexts)
        if not writer_contexts:
            raise GenerationFailed("CreativeKernelV1 缺少可审查的 Writer clause")
        try:
            licenses = materialize_clause_licenses_v1(
                contexts=clause_contexts,
                policies=license_policies,
            )
        except ValueError as exc:
            raise GenerationFailed("CreativeKernelV1 服务端 clause 许可不完整") from exc
        payloads: list[dict[str, Any]] = []
        all_reviews: list[ClauseLicenseReviewV1] = []
        retries = 0
        for batch in self._clause_license_batches(licenses):
            reviewer_provider = self._reviewer_provider
            if reviewer_provider is None:
                raise GenerationFailed("历史 Reviewer 回放路径没有配置审查提供方")
            provider_result = reviewer_provider.review(
                system_prompt=(
                    "你是独立 CreativeKernel clause 许可证支持核对器。只核对文字是否完全符合"
                    "服务端既定许可，不决定事实许可、通过失败、保存、重试、修复或制作资源，"
                    "只调用指定函数一次。"
                ),
                user_prompt=self._kernel_license_reviewer_prompt(
                    licenses=batch,
                    contexts=writer_contexts,
                    actuality_facts=tuple(
                        (fact_id, fact_text)
                        for fact_id, fact_text in (context.fact_text_by_id.items())
                        if fact_id.startswith("source:user_actuality:")
                    ),
                    protected_subjects=tuple(
                        dict.fromkeys(
                            name
                            for name in (
                                request.brand.brand_name,
                                request.brand.organization_name,
                                request.brand.account_name,
                            )
                            if name
                        )
                    ),
                    product_fact_packet=context.product_fact_packet,
                ),
                licenses=batch,
                timeout_seconds=self._review_timeout_seconds,
            )
            payloads.append(cast(dict[str, Any], provider_result.raw_payload))
            retries += provider_result.retry_count
            all_reviews.extend(provider_result.reviews.reviews)
        reviews = ClauseLicenseReviewsV1(
            review_version=CLAUSE_LICENSE_REVIEW_VERSION,
            reviews=tuple(all_reviews),
        )
        result = reconcile_clause_license_reviews_v1(
            contexts=clause_contexts,
            policies=license_policies,
            licenses=licenses,
            reviews=reviews,
            fact_text_by_id=context.fact_text_by_id,
            product_fact_packet=context.product_fact_packet,
        )
        return (
            result.issues,
            licenses,
            reviews,
            self._review_payload_envelope(payloads),
            retries,
        )

    @staticmethod
    def _kernel_clause_contexts(
        request: GenerationInput,
        context: BoundaryContext,
        kernel: CreativeKernelV1,
    ) -> tuple[ClauseContextV2, ...]:
        if request.narrative_frame is None:
            raise GenerationFailed("CreativeKernelV1 缺少冻结叙事框架")
        try:
            return build_clause_contexts_v2(
                kernel=kernel,
                frame=request.narrative_frame,
                fact_registry=context.fact_registry,
                allowed_constraint_ids=context.constraint_ids,
                speaker_kind=request.brand.speaker_kind,
            )
        except ValueError as exc:
            raise GenerationFailed("CreativeKernelV1 服务端 clause 合同不完整") from exc

    @staticmethod
    def _kernel_repair_scope(
        kernel: CreativeKernelV1,
        issues: tuple[NarrativeIssue, ...],
    ) -> frozenset[str]:
        nonrepairable = {
            "review_evidence_coverage",
            "review_evidence_span",
            "review_evidence_uncertain",
            "review_question_coverage",
            "review_answer_coverage",
            "review_answer_quote",
            "claim_inventory_drift",
            "license_assignment_drift",
            "license_review_coverage",
            "license_review_quote",
            "insufficient_evidence",
            "frozen_fact_changed",
            "server_wrapper_drift",
            "hypothesis_not_visible",
            "dramatization_not_visible",
            "kernel_program_drift",
        }
        if any(issue.reason in nonrepairable for issue in issues):
            raise GenerationFailed("CreativeKernel Reviewer 证据不完整或事实单元不一致")
        writable_ids = {
            unit.unit_id
            for unit in kernel.writable_units
            if compiler_owned_unit_source(
                unit.unit_id,
                unit.text,
            )
            is None
        }
        product_fact_ownership_issues = {
            "unsupported_product_claim",
            "product_fact_must_use_immutable_block",
            "unsupported_product_inference",
        }
        if any(issue.reason in product_fact_ownership_issues for issue in issues):
            return frozenset(writable_ids)
        affected = frozenset(issue.target_id for issue in issues if issue.target_id in writable_ids)
        if not affected:
            raise GenerationFailed("CreativeKernel 缺陷不属于可写单元")
        return affected

    @staticmethod
    def _prior_fact_block_ids(
        prior_kernel: CreativeKernelV1,
        fact_blocks: tuple[ImmutableFactBlock, ...],
    ) -> tuple[str, ...]:
        available = {block.fact_id: block.fact_block_id for block in fact_blocks}
        inferred = tuple(
            available[unit.fact_refs[0]]
            for unit in prior_kernel.units
            if unit.purpose == "frozen_fact" and len(unit.fact_refs) == 1 and unit.fact_refs[0] in available
        )
        selected = prior_kernel.selected_fact_block_ids or inferred
        if any(block_id not in {block.fact_block_id for block in fact_blocks} for block_id in selected):
            raise GenerationFailed("历史商品事实块无法在当前 Packet 重放")
        return selected

    @staticmethod
    def _validate_product_fact_selection(
        request: GenerationInput,
        context: BoundaryContext,
        kernel: CreativeKernelV1,
    ) -> None:
        packet = context.product_fact_packet
        if not packet.facts:
            if kernel.selected_fact_block_ids:
                raise ValueError("non-product kernel selected product facts")
            return
        block_by_id = {block.fact_block_id: block for block in context.product_fact_blocks}
        selected_fact_ids = {block_by_id[block_id].fact_id for block_id in kernel.selected_fact_block_ids}
        display_name_ids = {item.fact_id for item in packet.facts if item.fact_key == "display_name"}
        if (
            request.primary_product in {"product_truth", "visual_styling_story"}
            and display_name_ids
            and not selected_fact_ids & display_name_ids
        ):
            raise ValueError("product content omitted identity fact block")
        substantive_ids = {item.fact_id for item in packet.facts if item.fact_key not in {"sku", "display_name"}}
        if (
            request.primary_product in {"product_truth", "visual_styling_story"}
            and substantive_ids
            and not selected_fact_ids & substantive_ids
        ):
            raise ValueError("product content omitted substantive fact block")
        for unit in kernel.writable_units:
            if (
                compiler_owned_unit_source(
                    unit.unit_id,
                    unit.text,
                )
                is not None
            ):
                continue
            if product_fact_literal_spans(packet, unit.text):
                raise ValueError("writer repeated an immutable product fact")

    def _kernel_writer_prompt(
        self,
        request: GenerationInput,
        skeleton: CreativeKernelV1,
        compiler_texts: Mapping[str, str] | None = None,
    ) -> str:
        if request.creative_plan is None:
            raise GenerationFailed("CreativeKernelV1 缺少 CreativePlanV2")
        if request.narrative_frame is None:
            raise GenerationFailed("CreativeKernelV1 缺少冻结叙事框架")
        fact_units = [
            {
                "unit_id": unit.unit_id,
                "text": unit.text,
            }
            for unit in skeleton.units
            if unit.track == "trusted_fact"
            and (
                request.narrative_frame is None
                or not any(
                    fact_ref
                    in {
                        *request.narrative_frame.allowed_brand_fact_ids,
                        *request.narrative_frame.allowed_product_fact_ids,
                    }
                    for fact_ref in unit.fact_refs
                )
            )
        ]
        product_fact_packet = build_product_fact_packet(
            request.products,
            allowed_fact_ids=(request.narrative_frame.allowed_product_fact_ids),
        )
        packet_document = product_fact_packet_document(product_fact_packet)
        fact_blocks = immutable_product_fact_blocks(product_fact_packet)
        server_selected_product_facts = bool(
            fact_blocks and skeleton.selected_fact_block_ids
        )
        resolved_compiler_texts = dict(compiler_texts or compiler_owned_unit_texts(request.primary_product))
        writer_units = tuple(unit for unit in skeleton.writable_units if unit.unit_id not in resolved_compiler_texts)
        writable = [
            {
                "unit_id": unit.unit_id,
                "purpose": unit.purpose,
                "track": unit.track,
                "mode": unit.mode,
                "scope_id": unit.scope_id,
                "visible_order": unit.visible_order,
                "expression_requirement": (
                    "写成完整虚构情境，包含场景推进、角色行动或对白以及可见收束；不能写成观点文章。"
                    if unit.mode == "disclosed_dramatization"
                    else "写成带条件语气的推演片段，不能写成已经发生。"
                    if unit.mode == "hypothesis"
                    else "写成不绑定当前真人、品牌或门店经历的一般观察。"
                    if unit.mode == "general_observation"
                    else "写成明确建议，不能写成已经执行过的做法。"
                ),
            }
            for unit in writer_units
        ]
        template: dict[str, object] = {
            "units": [
                {
                    "unit_id": unit.unit_id,
                    "text": f"填写 {unit.purpose} 的完整可见文字",
                    **(
                        {"claim_refs": []}
                        if fact_blocks and not server_selected_product_facts
                        else {}
                    ),
                }
                for unit in writer_units
            ]
        }
        if fact_blocks and not server_selected_product_facts:
            blocks_by_fact_id = {block.fact_id: block for block in fact_blocks}
            example_fact_ids = (
                *(item.fact_id for item in product_fact_packet.facts if item.fact_key == "display_name"),
                *(item.fact_id for item in product_fact_packet.facts if item.fact_key not in {"sku", "display_name"}),
            )
            template["fact_block_refs"] = [
                blocks_by_fact_id[fact_id].fact_block_id for fact_id in example_fact_ids[:MAX_PRODUCT_FACT_BLOCKS]
            ]
        prior = (
            [
                {
                    "unit_id": unit.unit_id,
                    "text": unit.text,
                    "claim_refs": list(unit.claim_refs),
                }
                for unit in request.prior_creative_kernel.writable_units
                if unit.unit_id not in resolved_compiler_texts
            ]
            if request.prior_creative_kernel is not None
            else []
        )
        controls = self._deidentified_writer_controls(request)
        product_creative_rule = (
            """本篇的可信商品事实块已经由服务端选择并将在编译时原样插入；你看不到也
不能选择、引用、复述或推导这些事实。title 与 body 只负责一个不指向当前具体商品的
选购观察：帮助读者区分“已经确认的信息”和“仍需本人判断的选择”，不得出现 SKU、商品名、
品类、颜色、数字、结构、性能、用途、效果、价格、库存、设计动机、比较结论、手感或实际
体验。title 应短而自然，body 提供独立观看价值；不能写成事实审计、资料说明或免责声明。"""
            if fact_blocks
            else ""
        )
        topic_projection: object = (
            ["如何在已确认信息与个人选择之间保留判断"]
            if server_selected_product_facts
            else request.creative_plan.topic_spans
        )
        packet_projection: object = (
            {
                "service_selected": True,
                "selected_fact_block_count": len(
                    skeleton.selected_fact_block_ids
                ),
            }
            if server_selected_product_facts
            else packet_document
        )
        blocks_projection: object = (
            []
            if server_selected_product_facts
            else immutable_fact_blocks_document(fact_blocks)
        )
        output_contract = (
            """根对象必须恰好只有 units；每个 unit 必须恰好只有 unit_id、text。商品事实块
已由服务端冻结，禁止返回 fact_block_refs、claim_refs 或任何商品事实正文。"""
            if server_selected_product_facts
            else f"""没有 ProductFactPacket 时，根对象只能有 units，每个 unit 只能有
unit_id、text。有商品 Packet 的旧证据回放中，根对象必须恰好有 fact_block_refs、units；
每个 unit 必须恰好有 unit_id、text、claim_refs。fact_block_refs 只能选择服务端候选 ID
并用数组顺序表达最终事实块顺序；首次至少选择商品名称身份块和一个与本篇切口直接相关的
事实块，最多选择 {MAX_PRODUCT_FACT_BLOCKS} 个。claim_refs 只是审查线索，只能引用本次
Packet 的 fact_id；不能把硬属性、数字或 canonical_text 写进 creative text。"""
        )
        return f"""完成一个可直接交付的 CreativeKernel。你只负责“说什么、怎样表达”，不负责
scene、actor、resource、action、sound、production_note、发布结构、自然导读、发布配文
或语义合同；自然导读和发布配文由 DeliveryCompiler 使用版本化中性短语生成。

用户 topic 精确跨度：
{json.dumps(topic_projection, ensure_ascii=False)}
服务端逐字事实单元（只读；不要在输出中返回、改写、概括或扩展）：
{json.dumps(fact_units, ensure_ascii=False)}
服务端商品事实选择状态（不包含事实正文，也不授权 Writer 选择或引用事实）：
{json.dumps(packet_projection, ensure_ascii=False)}
旧证据兼容用 ImmutableFactBlock 候选（新双轨主链为空；正文始终由服务端原样插入）：
{json.dumps(blocks_projection, ensure_ascii=False)}
本篇受众价值：{_PRODUCT_VALUE[request.primary_product]}
平台与形式：{request.target} / {request.media_format}
去标识化表达控制：{controls}
本次修改要求：{request.revision_instruction or "（首次生成）"}
此前可写内核（首次生成时为空；只用于修改，不是事实来源）：
{json.dumps(prior, ensure_ascii=False)}

服务端可写 unit skeleton：
{json.dumps(writable, ensure_ascii=False)}

{product_creative_rule}

topic_spans 是用户原话证据，可能同时包含创作命令、控制要求或“尚未想到题材”的状态，不等于
必须逐字充当成品题目。若其中没有面向受众的实际题材，系统应根据本篇受众价值、账号边界与
平台自主选择一个安全、可直接发布的生活观察主线；不得把“如何找选题、如何发内容、缺少
灵感”本身写成面向受众的元内容，也不得要求用户补交观点或结构。

只返回：
{json.dumps(template, ensure_ascii=False)}

{output_contract}
必须恰好一次覆盖全部既定可写 unit_id，不得增加、遗漏、重复或修改 id，不得输出任何制作
字段、来源、事实正文、约束、类型或内部规则。商品硬事实正文始终由服务端原样插入。
title 是自然标题；按可见顺序排列的一个或多个 body 单元共同组成完整核心正文。
track 与 mode 是服务端在写作前冻结的唯一表达轨；你不能返回、改变或根据准备填写的文字
重新解释它们。general_observation 可以表达一般判断、观点、比喻和幽默，但不是当前用户、
品牌、员工、顾客或门店的事实。它必须写成不落到某次已完成经过的一般命题，不得以第一人称
观察履历、具体人物动作链、对白、事后心理、原因或结果代替抽象观察；需要具体场景时，只能
填写服务端已分配的 hypothesis 或 disclosed_dramatization 单元。hypothesis 可以写推演但
不要自行添加“假设”标识，Compiler 会为整个单元及独立传播出口保留范围；它不能绑定真实
用户、员工、顾客、门店或已经发生的历史。disclosed_dramatization 必须写成完整虚构情境，
但不要自行添加演绎声明，Compiler
会提供不可编辑的可见范围。recommendation 必须写清楚这是可以怎样做的建议，不得伪装成
已执行做法。actuality_reflection 对应的用户现实原文
已由服务端 frozen fact 单元逐字插入；Writer 只能写不复述该事实的抽象关系反思，或带清楚
建议／条件语态的泛指做法，不能复制、概括或扩写人物、动作、对白、动机、原因、结果、时间、
地点与现实细节。修订时，未出现在可写 skeleton 中的 prior_version 单元已经由服务端冻结，
不得索取、复述或改写。
title 也属于服务端预分配的 creative_expression，Compiler 会为标题添加与整篇一致的自然
范围。由 Compiler 生成的 natural_guide 与 release_caption 不属于 Writer 输出。
不要把 topic 写成用户亲历；除 hypothesis/dramatization 既定单元外，不要创造人物微事件。
不要写品牌、公司、门店或账号相信、坚持、倡导、承诺、长期做法或历史。不要讨论拍摄资源或
制作方式。Writer-owned clause 不得让当前表达者或第一人称复数承担谓语、做法、经历或承诺；
介绍本文时使用中性的“这篇内容／这个角度”，不能用机构性“我们”。abstract_observation
只写状态、判断、关系理解或比喻，不给泛指人物安排动作、对白或建议。"""

    @staticmethod
    def _kernel_license_reviewer_prompt(
        *,
        licenses: tuple[ClauseLicenseV1, ...],
        contexts: tuple[ClauseContextV2, ...],
        actuality_facts: tuple[tuple[str, str], ...],
        protected_subjects: tuple[str, ...],
        product_fact_packet: ProductFactPacket,
    ) -> str:
        context_by_clause = {context.clause_id: context for context in contexts}
        clauses = [
            {
                "clause_id": license_.clause_id,
                "license_id": license_.license_id,
                "exact_text": context_by_clause[license_.clause_id].exact_text,
                "discourse_contract": license_.discourse_contract,
                "subject_scope": license_.subject_scope,
                "allowed_expression_types": list(license_.allowed_expression_types),
                "allowed_fact_refs": list(license_.allowed_fact_refs),
                "prohibited_binding_checks": [
                    {
                        "binding_id": binding,
                        "question": (prohibited_binding_question_v1(binding)),
                    }
                    for binding in license_.prohibited_bindings
                ],
                "unsupported_quote_candidates": list(
                    unsupported_quote_candidates_v1(context_by_clause[license_.clause_id].exact_text)
                ),
            }
            for license_ in licenses
        ]
        return f"""逐条核对 writer-owned clause 是否完整受到服务端唯一 ClauseLicenseV1 支持。
你只提许可证支持证据，不决定事实许可、最终通过／失败、保存、持久化、重试、修复或资源。

冻结用户现实事实仅用于识别当前真人绑定，不是 Writer 改写许可证：
{json.dumps(actuality_facts, ensure_ascii=False)}
受保护的当前品牌／组织／账号精确名：
{json.dumps(protected_subjects, ensure_ascii=False)}
服务端只读 ProductFactPacket（只用于识别商品越界，不能许可 Writer 复述或推导）：
{json.dumps(product_fact_packet_document(product_fact_packet), ensure_ascii=False)}

待核对 clause 与许可：
{json.dumps(clauses, ensure_ascii=False)}

逐 clause 使用同一套稳定核对顺序：
1. 先读取 discourse_contract、subject_scope、allowed_expression_types、allowed_fact_refs
   和 prohibited_binding_checks；每个 check 都是当前 clause 必须独立回答的闭合问题，不得
   因为文字和 topic／冻结事实谈的是相近生活主题，就推定新增含义已获事实许可。
2. subject_scope=generic_only 时，只允许不指向当前真人或受保护主体的泛指人数、普遍心理
   观察、一般因果、关系题材讨论和清楚建议；具体社会关系身份不是泛指人数。只讨论“婆媳
   关系／家庭关系”等关系类别或抽象关系理解可以受 generic 许可，但不能在没有服务端
   hypothesis／dramatization scope 时实例化一组人物的同住、亲属身份、现实对白、动作或
   其他具体关系处境。
3. 检查整条 clause 是否建立亲属、伴侣、家庭、同住、同事、员工、顾客或文字明确建立的
   其他社会关系；文字把该关系绑定为当前真人／现实个案，或在 abstract／audience_guidance
   clause 中把一组泛指人物实例化为具有具体关系处境，且 prohibited_binding_checks 包含
   specific_social_relation_to_actuality 时必须 unsupported。一般关系题材与抽象关系理解，
   以及 generic_or_fictional / fictional_only scope 内被服务端包裹的虚构关系可以受许可。
4. 检查当前真人／机构、现实对白、已发生事件或结果、机构／商品事实；命中相应
   prohibited_binding_checks 且没有精确 allowed_fact_refs 时必须 unsupported。
   ProductFactPacket 中的硬属性、数字和 canonical_text 只能由服务端 ImmutableFactBlock
   原样插入；writer-owned clause 即使准确复述也必须 unsupported_product_fact。根据 Packet
   推导性能、功效、用途／穿着结果、设计动机、价格、库存、比较结论或实际体验，同样必须
   unsupported_product_fact。资料来源或制作资源被当成商品事实时必须
   source_or_resource_as_fact。Packet 只帮助识别边界，不使 claim_refs 或相近表述获得许可。
5. 按 prohibited_binding_checks 的给定顺序逐项阅读 question，并为每个 binding_id
   恰好返回一个 binding_check，不得遗漏、重复、增加或改名：absent 表示该问题所述绑定
   不存在，present 表示存在，uncertain 表示无法确定。不能用对其他问题的回答代替当前
   question。服务端只在 expression_type 属于 allowed_expression_types 且全部
   binding_check=absent 时派生 supported；只要一个含义越界就不能用其他泛指或建议含义
   抵消。

稳定语义边界：
- generic_observation 可以创造不绑定当前真人或受保护主体的一般观察、观点、比喻、泛指心理
  需要和一般因果；“两个人／人与人／一些人”等泛指人数本身不是具体社会关系。
- recommendation 可以提出清楚的泛指建议，但不得把建议写成当前真人已经做过的事。
- non_situated_metaphor 可以使用夸张、反差、幽默和荒诞比喻，但不能出现人物对白、具体
  场景／地点、人物动作链或事件结果。写了“想象一下”不等于获得服务端 hypothesis 或
  dramatization 许可。
- hypothetical_example 和 disclosed_dramatization 只在服务端既定 scope 内成立，不能绑定
  当前用户、品牌、员工、顾客、门店历史或商品事实。
- specific_social_relation 只指亲属、伴侣、家庭、同住、同事、员工、顾客或文字明确建立
  的其他社会关系被主张为当前现实身份，或在未披露的 abstract／audience_guidance 中被
  实例化成具体关系处境。若许可禁止该绑定，不能把一种具体关系换成另一种；若 clause 只
  讨论一种关系题材、抽象关系理解，或处于服务端许可的 fictional scope，不得仅因出现关系
  类别就拒绝。
- current person／institution、受保护主体、现实对白、已发生事件或结果、机构和商品事实，
  没有 allowed_fact_refs 时均不受许可支持。
- frozen fact、服务端 wrapper 和商品 ImmutableFactBlock 不在本次 writer-owned 输入中，
  不能把资料来源、表达约束或制作资源当事实许可证。上方冻结用户事实仅用于判断文字是否
  把新增含义绑定当前现实；除非 allowed_fact_refs 精确列出 fact_id，否则它不支持 Writer
  新增或推断关系身份、对白、动机、原因、结果或其他现实细节。

每个 clause 恰好返回一次，顺序、clause_id 与 license_id 必须完全一致：
- 每条只返回 expression_type、完整 binding_checks 和 unsupported_quote；不要再返回
  verdict 或 reason_code，最终状态完全由服务端从这份证明派生。
- expression_type 必须从给定枚举选择；全部 binding_check=absent 时必须属于本条
  allowed_expression_types。
- 每条都返回 binding_checks，且必须对本条 prohibited_binding_checks 中的每个 binding_id
  恰好返回一次 status；顺序不构成语义，服务端会按 ID 规范化。
- 全部 absent：整条 clause 的全部可见含义均在许可证内，unsupported_quote 为空字符串。
- 至少一个 present：至少一个含义越界；unsupported_quote 必须逐字来自当前 clause、
  至少两个字符且在该 clause 中只出现一次。优先从 unsupported_quote_candidates 选择；
  只有候选过长时才可返回同一 clause 内更短但仍唯一的精确片段。不得拼接、改写或返回含
  ASCII 双引号的片段。所有实际命中的 prohibited_binding_checks 都必须为 present；
  其他能够确定不存在的检查返回 absent。
- 确实无法判断主体绑定或许可支持：至少一个对应 binding_check=uncertain，
  unsupported_quote 为空字符串，且不得同时返回 present。若没有候选能准确指向越界含义，
  也返回 uncertain；清楚样本不得用 uncertain 逃避。

不要返回 offset、occurrence、全文风险枚举、事实许可、pass/fail 或修复建议。只调用指定
函数并返回 review_version={CLAUSE_LICENSE_REVIEW_VERSION}。tool arguments 必须是合法
JSON。"""

    @staticmethod
    def _kernel_reviewer_prompt(
        *,
        questions: tuple[ClosedReviewQuestion, ...],
        contexts: tuple[ClauseContextV2, ...],
        actuality_facts: tuple[tuple[str, str], ...],
        protected_subjects: tuple[str, ...],
    ) -> str:
        context_by_clause = {context.clause_id: context for context in contexts}
        descriptions = {
            "subject_binding": (
                "这条主张是否绑定当前说话者/用户、受保护主体、泛指角色、虚构角色或其他具体人物/机构/商品？"
                "判断 clause 自身主张实际指向，不只看语法主语：只有 clause 以第一人称、当前指代"
                "或省略但可唯一回指冻结事件的主体，断言当前用户的关系、经历、心理或因果时才是"
                " current_user；如果标题、导读或正文把同一条冻结事实中的多个具体细节重新组合成"
                "一件事件，即使没有第一人称，也属于 current_user。仅仅与冻结事实题材相同、没有"
                "重新组合其具体细节、用于其后的泛指反思，不能据此绑定 current_user。"
                "面向不特定受众的第二人称阅读邀请、选择建议或内容观看回报属于 generic；只有文字"
                "断言当前用户已经具有某段具体关系、经历、心理或事件时才是 current_user。"
                "明确泛称、一般条件或倾向且没有回指当前个案时属于 generic；两种读法都成立时必须"
                " uncertain。只有当前账号／表达方自己承担主张时才属于 current_speaker；"
                "“这篇内容／这个角度”作为被介绍的内容对象，不是 current_speaker。"
            ),
            "relationship_claim": (
                "是否建立亲属、伴侣、家庭、同住、同事、员工、顾客或其他具体社会关系？"
                "“亲密关系”也属于关系主张；纯粹的‘人与人’等无具体关系可 absent。"
            ),
            "actual_event": (
                "是否声称动作、反应、事件或状态在现实中已经发生、正在发生或确实存在？"
                "泛指观察、建议、明确条件推演和披露演绎中的动作不算 actuality，应 absent。"
                "文章向不特定读者提供观看回报、理解路径或选择建议，也不是已经发生的现实事件。"
            ),
            "dialogue_attribution": ("是否出现直接对白、转述或作为例子给出的具体话语？"),
            "motive_or_mental_state": ("是否推断愿望、期待、害怕、需要、意图、信念、情绪或其他心理原因？"),
            "cause_or_result": ("是否建立前因、结果或因果联系？泛指因果也要 present，最终是否允许由服务端决定。"),
            "time_location_possession": ("是否绑定现实时间、地点、持有/所有关系或经营条件？纯条件语气不算现实时间。"),
            "institutional_or_product_claim": (
                "是否形成品牌、公司、门店、账号或商品的事实、历史、做法、承诺、性能主张？"
                "商品名称或编号作为主体只在 subject_binding 使用 named_product；本题若存在"
                "商品事实主张必须使用 product_fact，若声称性能则使用 product_performance，"
                "不得把其他维度的 operand 搬到本题。"
            ),
            "statement_mode": (
                "整条 clause 的可见语态是什么？uncertain=false 时必须只选一个：actuality、"
                "generic_observation、recommendation、hypothesis、dramatization；无法可靠"
                "唯一判断时 uncertain=true。recommendation 必须是在建议、请求或指示某人"
                "采取行动；只向受众征询观点、经验或选择而不指示其行动的互动问句属于"
                "generic_observation。比喻、类比或拟人本身不构成 dramatization；只有文字实际"
                "铺陈虚构角色与情境动作时才是 dramatization。"
            ),
            "disclosure": (
                "这条 writer 文字是否逃逸或抵触服务端给定的 hypothesis/dramatization 范围，"
                "或在需要披露时转而声称现实？只有存在冲突才 present；无冲突 absent。"
            ),
            "product_attribute_claim": (
                "这条 creative clause 是否重新陈述、改写或新增商品名称、品类、材质、结构、"
                "轮廓、颜色、可观察特征、重量、数字或其他硬属性？商品硬事实即使正确也只能"
                "由服务端 ImmutableFactBlock 承载；creative clause 出现即 present。"
            ),
            "product_performance_or_efficacy": (
                "是否新增商品性能、功效、耐用性、兼容性、保护性、舒适性或其他能力结论？"
            ),
            "product_use_or_wear_result": ("是否声称商品会产生具体使用、穿着、上身、显瘦、保暖、场景适用或普遍结果？"),
            "product_design_motive": ("是否推断商品为什么这样设计、设计者意图或结构形成原因？"),
            "product_price_or_inventory": ("是否新增或暗示商品价格、折扣、库存、稀缺性、在售状态或供应情况？"),
            "product_comparison_conclusion": ("是否给出商品优于、替代、等同、性价比更高或基于对照数据得出的比较结论？"),
            "product_actual_experience": ("是否冒充用户、顾客、员工或当前表达方已经使用、穿着、购买或验证过该商品？"),
            "source_or_resource_as_fact": (
                "是否把资料来源、品牌表达约束、拍摄样衣、制作资源或参考材料本身当成商品事实许可证？"
            ),
        }
        grouped: list[dict[str, object]] = []
        clause_ids = tuple(dict.fromkeys(question.clause_id for question in questions))
        for clause_id in clause_ids:
            context = context_by_clause[clause_id]
            clause_questions = tuple(question for question in questions if question.clause_id == clause_id)
            server_scope = (
                "hypothesis"
                if context.unit_contract == "hypothetical_example"
                else "dramatization"
                if context.unit_contract == "disclosed_dramatization"
                else "none"
            )
            grouped.append(
                {
                    "clause_id": clause_id,
                    "exact_text": context.exact_text,
                    "visible_order": context.visible_order,
                    "server_scope": server_scope,
                    "questions": [
                        {
                            "question_id": question.question_id,
                            "dimension": question.dimension,
                            "question": descriptions[question.dimension],
                            "allowed_operands": list(question.allowed_operands),
                        }
                        for question in clause_questions
                    ],
                }
            )
        return f"""逐条阅读服务端 writer-owned clause，并对服务端给出的每个固定风险问题恰好
回答一次。你只回答“文字里有没有该风险主张、证据是否覆盖本 clause、属于哪个允许 operand”；
不要决定事实许可、source_ref、unit contract、通过/失败、修复或制作资源。

冻结用户现实事实仅用于判断 writer 文字是否在绑定、概括或扩展当前用户现实，不是 Writer
事实许可证：
{json.dumps(actuality_facts, ensure_ascii=False)}
受保护的当前品牌／组织／账号精确名：
{json.dumps(protected_subjects, ensure_ascii=False)}

闭合问题：
{json.dumps(grouped, ensure_ascii=False)}

严格规则：
- 必须按给定顺序一题不少地回答全部 question_id；不得重复、增加或改名。
- 每题只返回 uncertain 和 operands；present／absent 状态与 evidence_scope 均由服务端
  确定性派生，不得返回这些字段。uncertain=false 且 operands 非空表示 present；
  uncertain=false 且 operands 为空表示 absent；uncertain=true 表示确实无法可靠判断。
- `generic`、`current_user`、`recommendation` 等类别只能放在 operands。某个
  subject_binding 类别存在时必须把该类别放入 operands。
- present 语义下 operands 至少一个，且只能从该题 allowed_operands 选择。该 question
  已由服务端唯一绑定到可信 clause，完整 clause 原文、Unicode offset 与审计 quote 都由
  服务端从 ClauseContext 确定性生成；不要回传正文片段。
- 每题 JSON 中的 allowed_operands 是该 question_id 的封闭集合；即使同批另一题允许某个
  operand，也不得跨 question 借用。
- absent 语义下 uncertain=false、operands 必须是空数组。不能通过省略整个问题表达
  absent。
- uncertain=true 时 operands 可为空或只包含该题允许的相关类别。不要猜测，也不要把
  uncertain 当 absent。
- statement_mode 在 uncertain=false 时必须恰好有一个 operand；无法唯一判断时必须
  uncertain=true。
- server_scope 只说明服务端已有的可见范围，不是让你决定许可；disclosure 题只报告 writer
  clause 是否与该范围冲突。
- 正文和证据地址均由服务端持有；不要返回 quote、start、end、occurrence 或任何正文副本／
  数字地址。
- 同一 clause 的全部问题彼此独立。即使某个表达看起来合法，也必须如实回答关系、对白、
  动机、因果等问题；合法性由服务端组合判断。
- 每个 clause 只按自身文字、明确的服务端 scope 和必要的冻结事实回指判断，不得因为同批
  其他 clause 的写法改变其主体或语态答案；题材相似不是现实主体绑定。

只调用指定函数并返回：
{{"evidence_version":"{CLOSED_REVIEW_VERSION}","answers":[{{
"question_id":"既定 id","uncertain":false,
"operands":["该题允许 operand"]
}}]}}
根对象和 answer 不得增加、遗漏或重命名字段。"""

    def _kernel_repair_prompt(
        self,
        request: GenerationInput,
        kernel: CreativeKernelV1,
        affected: frozenset[str],
        issues: tuple[NarrativeIssue, ...],
    ) -> str:
        if request.narrative_frame is None:
            raise GenerationFailed("CreativeKernelV1 缺少冻结叙事框架")
        trusted_contracts = unit_contracts_v2(
            kernel,
            request.narrative_frame,
        )
        product_issue_reasons = {
            "unsupported_product_claim",
            "product_fact_must_use_immutable_block",
            "unsupported_product_inference",
        }
        product_fact_repair = any(
            issue.target_id in affected and issue.reason in product_issue_reasons for issue in issues
        )
        product_contract = bool(request.products)
        product_packet = build_product_fact_packet(
            request.products,
            allowed_fact_ids=(
                request.narrative_frame.allowed_product_fact_ids if request.narrative_frame is not None else None
            ),
        )
        if product_fact_repair:
            return self._product_fact_repair_prompt(
                kernel=kernel,
                affected=affected,
                trusted_contracts=trusted_contracts,
                expression_controls=self._deidentified_writer_controls(request),
                platform=request.target,
                media_format=request.media_format,
            )
        if request.narrative_frame.narrative_mode == "actuality_reflection" and not product_contract:
            return self._actuality_repair_prompt(
                request=request,
                affected=affected,
                issues=issues,
                trusted_contracts=trusted_contracts,
            )
        units: list[dict[str, object]] = []
        for unit in kernel.units:
            if unit.unit_id not in affected:
                continue
            contract = trusted_contracts[unit.unit_id]
            current_text = unit.text
            disclosure = (
                HYPOTHESIS_DISCLOSURE
                if contract == "hypothetical_example"
                else DRAMATIZATION_DISCLOSURE
                if contract == "disclosed_dramatization"
                else None
            )
            if disclosure is not None:
                prefix = f"{disclosure}\n"
                if kernel.kernel_version != KERNEL_VERSION and not current_text.startswith(prefix):
                    raise GenerationFailed("CreativeKernelV1 服务端披露结构漂移")
                if current_text.startswith(prefix):
                    current_text = current_text[len(prefix) :]
            units.append(
                {
                    "unit_id": unit.unit_id,
                    "purpose": unit.purpose,
                    "unit_contract": contract,
                    "allowed_observation_types": list(unit.allowed_observation_types),
                    "claim_refs": list(unit.claim_refs),
                    "current_text": current_text,
                }
            )
        findings = [
            {
                "unit_id": issue.target_id,
                "reason": issue.reason,
                "fragment": issue.fragment,
            }
            for issue in issues
            if issue.target_id in affected
        ]
        result_template: dict[str, object] = {
            "units": [
                {
                    "unit_id": "只使用列出的既定 id",
                    "text": "完整替换文字",
                    **({"claim_refs": ["只引用本次 Packet 的 fact_id"]} if product_contract else {}),
                }
            ]
        }
        claim_rule = (
            "有 ProductFactPacket 时，每个返回 unit 必须保留 claim_refs 字段且只引用"
            "上述 fact_id；claim_refs 只是审查线索，不构成商品事实许可。"
            if product_contract
            else "没有 ProductFactPacket 时不得返回 claim_refs。"
        )
        return f"""只修复这一次列出的完整可写 unit。不得修改、返回或概括事实单元，不得改变
CreativePlanV2、NarrativeFrame、资源集合、compiler version 或任何 unit_id。

用户 topic：{
            json.dumps(
                request.creative_plan.topic_spans if request.creative_plan is not None else (),
                ensure_ascii=False,
            )
        }
本次修改要求：{request.revision_instruction or "（首次生成）"}
本次只读 ProductFactPacket 的 fact_id：
{json.dumps(list(product_packet.fact_ids), ensure_ascii=False)}
既有 fact_block_refs 已由服务端冻结，修复不得返回、增删、换序或替换。
受影响 unit：{json.dumps(units, ensure_ascii=False)}
当前问题：{json.dumps(findings, ensure_ascii=False)}

修复后仍只写创作文字，不得返回 scene、actor、resource、action、sound、production_note、
来源、约束或语义合同。hypothesis/dramatization 的可见包裹由服务端加入，修复文字不得重复
这些包裹。recommendation unit 的每个 clause 都必须带显式建议、条件或意愿语态，
不得写具体时间、地点、对白、情境例子或抽象收束。按以下稳定含义修复全部 findings：
- situated_event_in_observation / recommendation_in_observation：把完整 unit 重写为其冻结
  contract 允许的抽象状态、关系判断或观看回报，不保留、换写或搬运具体情境与建议；
- situated_event_in_reflection / unsupported_actuality_expansion：只对服务端已经逐字插入的
  事实作抽象反思，不复述或扩写人物、动作、对白、动机、原因、结果、时间或地点；
- unsupported_actuality_binding：删除 Writer unit 中复制、概括或改写的现实事实，现实原文
  已由服务端 frozen fact 单元独立保留；
- unsupported_institutional_assertion：删除当前机构或第一人称复数承担的观点、做法与经历；
- unsupported_product_claim / product_fact_must_use_immutable_block /
  unsupported_product_inference：删除 Writer unit 对商品名称、编号、硬属性、数字、性能、
  功效、用途、穿着结果、价格、库存、比较、设计动机或实际体验的复述、概括、推断和改写；
  已登记商品事实由服务端 frozen fact 单元逐字保留，并由 ImmutableFactBlock 原样插入。
  重新从对应 unit 的表达职责出发写面向受众的标题、观看回报、抽象视角或选择建议；这些
  创意文字即使脱离所有商品标识与硬事实也必须独立成立。不得把内部资料边界、审查规则或
  “哪些信息可以确认”写成面向用户的内容主题；
- unsupported_actuality_binding 出现在 hypothesis/dramatization 时，改为不绑定现实身份的
  泛指虚构角色。
这是本成品唯一修复。若受影响 unit 的冻结 contract 是 abstract_observation，或
actuality_reflection 已因现实扩写／具体情境失败，本次不要再选择边界较宽的建议或示例路径：
只写一至两句纯状态、关系或价值判断，不写任何人物／关系角色、动作、建议、条件、对白、动机、
原因、结果、时间或地点。用户事实中没有逐字出现的亲属、伴侣、同住、员工、顾客等关系角色，
不得在任何受影响 unit 中新增；泛称也不得被用来暗示具体身份或共同家庭。
每个返回 unit 的文字都必须与 current_text 实质不同，并同时消除该 unit 的全部 findings；
不得原样返回、只换标点或把问题句移动到另一个 unit。只返回：
{json.dumps(result_template, ensure_ascii=False)}
{claim_rule}"""

    @staticmethod
    def _actuality_repair_prompt(
        *,
        request: GenerationInput,
        affected: frozenset[str],
        issues: tuple[NarrativeIssue, ...],
        trusted_contracts: Mapping[str, UnitContractV2],
    ) -> str:
        prior = request.prior_creative_kernel
        if request.narrative_frame is None or request.narrative_frame.narrative_mode != "actuality_reflection":
            raise GenerationFailed("真人事实内容修复缺少冻结叙事作用域")
        prior_by_id = {unit.unit_id: unit for unit in (prior.writable_units if prior is not None else ())}
        if prior is not None and any(unit_id not in prior_by_id for unit_id in affected):
            raise GenerationFailed("真人事实修改修复无法回放已审单元")
        units = [
            {
                "unit_id": unit_id,
                "purpose": (
                    prior_by_id[unit_id].purpose
                    if unit_id in prior_by_id
                    else (
                        "title"
                        if unit_id == "unit:title"
                        else "natural_guide"
                        if unit_id == "unit:natural-guide"
                        else "release_caption"
                        if unit_id == "unit:release-caption"
                        else "body"
                    )
                ),
                "unit_contract": trusted_contracts[unit_id],
                **({"prior_reviewed_text": (prior_by_id[unit_id].text)} if unit_id in prior_by_id else {}),
                "issue_reasons": sorted({issue.reason for issue in issues if issue.target_id == unit_id}),
            }
            for unit_id in sorted(affected)
        ]
        expression_request = request.revision_instruction or "保持服务端真人事实原文不变，补齐可直接发布的抽象观看主线"
        read_only_facts = (
            []
            if prior is not None
            else [
                {
                    "source_id": fact.source_id,
                    "exact_text": fact.exact_text,
                }
                for fact in request.narrative_frame.user_facts
            ]
        )
        template = {
            "units": [
                {
                    "unit_id": unit["unit_id"],
                    "text": "完整替换文字",
                }
                for unit in units
            ]
        }
        return f"""这是一次真人事实内容的唯一受影响单元修复。服务端已经逐字保留用户现实
原文；你看不到本次违规草稿，也不得复述、概括或扩写现实原文。只从上一个已审通过的创意
单元出发，按用户本次表达要求改写。

本次表达要求：{expression_request}
首次修复的服务端逐字事实投影（只用于理解主题；事实正文由服务端另行插入，禁止在返回
文字中复制、概括、换词复述或扩展）：
{json.dumps(read_only_facts, ensure_ascii=False)}
受影响单元及可用的上一个已审版本：
{json.dumps(units, ensure_ascii=False)}

必须恰好一次返回全部列出的 unit_id，且只能返回 unit_id、text。不得返回事实单元、
claim_refs、scene、actor、resource、action、sound、production_note、来源、约束或合同。
有 prior_reviewed_text 时，新 text 必须与它实质不同。所有 text 都必须遵守服务端给定的
unit_contract：
- actuality_reflection：只写一至两句抽象关系判断、价值判断或不落到现实场景的比喻；不得
  复述真人事实、安排已发生事件、现实对白、具体时间地点或任何具体关系身份。可以写明确泛指
  的原因、需要、建议或条件，但不得把它们绑定为当前用户、当前机构或冻结事实已经发生的
  心理、因果与结果。
- audience_guidance：只写中性的观看主线、阅读邀请或带清楚语态的泛指建议；不得绑定当前
  用户、机构、现实事件或任何具体关系身份。
- abstract_observation：只写抽象状态、关系理解或价值判断，不写人物微事件或建议。
- recommendation：每个 clause 都用清楚建议、条件或意愿语态，不写已经发生的事件。

同时保持完整平台成品职责：title 是自然、有张力但不改写事实的标题；natural_guide 用一句
话说明观看回报；body 用三至五个短 clause 形成一条有推进的泛指观察与可选建议，不能只写
一句安全口号；release_caption 用一至两句自然收束或互动邀请。各 unit 不得重复同一句意思。

不要使用违规草稿的替换词继续同一场景，也不要把问题内容移动到另一个 unit。只返回：
{json.dumps(template, ensure_ascii=False)}"""

    @staticmethod
    def _product_fact_repair_prompt(
        *,
        kernel: CreativeKernelV1,
        affected: frozenset[str],
        trusted_contracts: Mapping[str, UnitContractV2],
        expression_controls: str,
        platform: str,
        media_format: str,
    ) -> str:
        expression_rules: dict[UnitContractV2, str] = {
            "abstract_observation": (
                "只写一句面向不特定读者的观看角度或价值判断；不带行动指示、条件推演"
                "或具体外部对象，每个 clause 都必须是 generic_observation"
            ),
            "audience_guidance": (
                "只写一至两句与已插入事实配套的观看回报、选择视角或阅读邀请；"
                "只谈读者如何看、如何选、如何保留判断，不评价底层对象或所属品类"
            ),
            "recommendation": ("只写带清楚建议语态的泛指做法；不得写已经发生的事件"),
            "hypothetical_example": ("只写服务端假设范围内的条件推演；不得绑定任何现实主体"),
            "disclosed_dramatization": ("只写服务端演绎范围内的虚构表达；不得绑定任何现实主体"),
            "actuality_reflection": ("只写不复述或扩展现实原文的泛指反思；不得增加现实主体、事件或心理"),
            "frozen_fact": "不可写；事实单元不应进入修复范围",
        }
        units = [
            {
                "unit_id": unit.unit_id,
                "purpose": unit.purpose,
                "unit_contract": trusted_contracts[unit.unit_id],
                "required_expression": expression_rules[trusted_contracts[unit.unit_id]],
                "allowed_observation_types": list(unit.allowed_observation_types),
            }
            for unit in kernel.units
            if unit.unit_id in affected
        ]
        template = {
            "units": [
                {
                    "unit_id": unit["unit_id"],
                    "text": "完整替换文字",
                    "claim_refs": [],
                }
                for unit in units
            ]
        }
        return f"""只重写服务端列出的受影响创意 unit。相关事实正文已经由服务端不可变单元
独立插入；你看不到、也不需要复述、解释或推断这些事实。不要返回事实单元或事实块引用。

受影响创意 unit：
{json.dumps(units, ensure_ascii=False)}

平台与形式：{platform} / {media_format}
去标识化表达控制：{expression_controls}

这是面向最终读者的创意表达层，不是资料说明、方法论讲解或内部审查说明。每个 clause 的
判断对象只能是泛指读者如何看、如何选、如何保留自己的判断，或本篇能带来的阅读价值；
不得对底层对象、其所属品类、设计、结构、属性、用途、效果、形成原因或现实体验作任何
主张。底层对象、其类别以及“它／这件对象”不得成为创意文字的主语、宾语或指代对象。
使用自然第二人称直接和受众说话，不把“读者”“文章”“本文”或阅读学习过程当作表达
对象。title 用简短、有张力的选择问题或判断冲突吸引受众；natural_guide 用一句自然的话
把受众带到同一选择主线；body 用二至四个短 clause 依次帮助受众确定优先项、排除无关
干扰并保留自己的判断；release_caption 留下一个可以直接回答、且没有预设答案的选择
问题。四个 unit 必须围绕同一条具体主线、各自承担不同作用，不能重复解释文章、方法或
承诺受众会变得更明智。所有文字必须在不知道底层对象名称、类别和任何属性时仍然成立。
不得输出“抽象原则”等内部合同语言，不写举例对白、引号口号或虚构场景。每个 unit 必须
逐条服从其唯一
unit_contract 和 required_expression，不得因为 purpose 或写作习惯换成建议、假设、演绎
或现实语态。不得虚构人物、事件、对白、机构立场或第一人称经历。

必须恰好覆盖列出的 unit_id，每个 unit 只能有 unit_id、text、claim_refs，claim_refs 必须
是空数组。不得增加、遗漏、重复或改名。这是唯一修复，只返回：
{json.dumps(template, ensure_ascii=False)}"""

    @staticmethod
    def _deidentified_writer_controls(request: GenerationInput) -> str:
        parts = [
            request.brand.positioning,
            request.brand.decision_order,
            request.brand.audience_description,
            request.brand.tone,
            request.brand.content_role_boundary,
            *(
                tuple(selection.applied_label for selection in request.creative_direction.selections)
                if request.creative_direction is not None
                else ()
            ),
            *(
                (request.creative_direction.custom_text,)
                if request.creative_direction is not None and request.creative_direction.custom_text
                else ()
            ),
            *((request.collaboration_note,) if request.collaboration_note else ()),
        ]
        value = "；".join(part.strip() for part in parts if part.strip())
        for identifier in (
            request.brand.brand_name,
            request.brand.organization_name,
            request.brand.account_name,
            request.brand.operator_name,
            request.brand.content_role_name,
        ):
            if identifier:
                value = value.replace(identifier, "当前表达方")
        return value[:600] or "自然、清楚、不过度下结论"

    @staticmethod
    def _singleton_slots(
        product: ContentProduct,
        media_format: str,
    ) -> tuple[str, ...]:
        base: tuple[str, ...] = ("title", "natural_guide", "release_caption")
        if media_format == "video":
            base = (*base, "viewing_flow")
        return (*base, *_CONTRACT_FIELDS[product])

    @classmethod
    def _narrative_skeleton(
        cls,
        request: GenerationInput,
        frame: NarrativeFrame,
        context: BoundaryContext,
    ) -> NarrativeSkeleton:
        expected_type = _MODE_BLOCK_TYPE[frame.narrative_mode]
        singleton = cls._singleton_slots(request.primary_product, request.media_format)
        generated_ids = {slot: f"b-{slot}" for slot in (*singleton, _SPOKEN_SLOT)}
        scene_groups: list[tuple[str, str, tuple[str, ...]]] = [
            ("s-cover", _COVER_PURPOSE, (generated_ids["title"],)),
            (
                "s-guide",
                _SCENE_PURPOSE,
                (generated_ids["natural_guide"],),
            ),
            (
                "s-contract",
                _SCENE_PURPOSE,
                tuple(generated_ids[slot] for slot in _CONTRACT_FIELDS[request.primary_product]),
            ),
            ("s-spoken", _SCENE_PURPOSE, (generated_ids[_SPOKEN_SLOT],)),
            (
                "s-release",
                _SCENE_PURPOSE,
                (generated_ids["release_caption"],),
            ),
        ]
        if request.media_format == "video":
            scene_groups.append(
                (
                    "s-viewing",
                    _SCENE_PURPOSE,
                    (generated_ids["viewing_flow"],),
                )
            )
        actuality_scene_by_block: dict[str, str] = {}
        for index, _ in enumerate(frame.user_facts, start=1):
            block_id = f"actuality:{index}"
            scene_id = f"s-actuality-{index}"
            actuality_scene_by_block[block_id] = scene_id
            scene_groups.append((scene_id, _SCENE_PURPOSE, (block_id,)))
        scene_ids_by_block = {
            block_id: tuple(scene_id for scene_id, _, block_refs in scene_groups if block_id in block_refs)
            for block_id in (
                *generated_ids.values(),
                *actuality_scene_by_block,
            )
        }
        constraint_refs = tuple(identifier for identifier, _ in context.constraint_registry)
        product_fact_ids = tuple(frame.allowed_product_fact_ids)
        brand_fact_ids = tuple(frame.allowed_brand_fact_ids)
        blocks: list[BlockSkeleton] = []
        for slot in (*singleton, _SPOKEN_SLOT):
            fact_refs: tuple[str, ...] = ()
            if slot in _CONTRACT_FIELDS[request.primary_product]:
                fact_refs = product_fact_ids
            if slot == "brand_account_link":
                fact_refs = (*fact_refs, *brand_fact_ids)
            block_id = generated_ids[slot]
            blocks.append(
                BlockSkeleton(
                    block_id=block_id,
                    block_type=expected_type,
                    slot=slot,
                    fact_refs=tuple(dict.fromkeys(fact_refs)),
                    constraint_refs=constraint_refs,
                    linked_scene_ids=scene_ids_by_block[block_id],
                )
            )
        service_blocks = tuple(
            NarrativeBlock(
                block_id=f"actuality:{index}",
                block_type="actuality_source",
                slot=_SPOKEN_SLOT,
                text=fact.exact_text,
                fact_refs=(fact.source_id,),
                constraint_refs=(),
                linked_scene_ids=(actuality_scene_by_block[f"actuality:{index}"],),
            )
            for index, fact in enumerate(frame.user_facts, start=1)
        )
        allowed_resources = tuple(identifier for identifier, _ in context.resource_registry)
        scenes = tuple(
            SceneSkeleton(
                scene_id=scene_id,
                purpose=purpose,
                block_refs=block_refs,
                allowed_resource_refs=allowed_resources,
            )
            for scene_id, purpose, block_refs in scene_groups
        )
        return NarrativeSkeleton(
            blocks=tuple(blocks),
            service_actuality_blocks=service_blocks,
            scenes=scenes,
            spoken_order=(
                *(block.block_id for block in service_blocks),
                generated_ids[_SPOKEN_SLOT],
            ),
        )

    def _parse_core(
        self,
        request: GenerationInput,
        frame: NarrativeFrame,
        context: BoundaryContext,
        skeleton: NarrativeSkeleton,
        raw: object,
    ) -> NarrativeCore:
        if not isinstance(raw, dict) or frozenset(raw) != {
            "blocks",
            "scenes",
        }:
            raise TypeError("writer core must contain only server skeleton slots")
        raw_blocks = raw.get("blocks")
        raw_steps = raw.get("scenes")
        if not isinstance(raw_blocks, list) or not raw_blocks or not isinstance(raw_steps, list) or not raw_steps:
            raise TypeError("typed core collections are incomplete")
        skeleton_blocks = {block.block_id: block for block in skeleton.blocks}
        if {value.get("block_id") for value in raw_blocks if isinstance(value, dict)} != set(skeleton_blocks) or len(
            raw_blocks
        ) != len(skeleton_blocks):
            raise ValueError("writer block coverage drifted from server skeleton")
        generated: list[NarrativeBlock] = []
        for raw_block in raw_blocks:
            if not isinstance(raw_block, dict) or frozenset(raw_block) != {
                "block_id",
                "text",
            }:
                raise TypeError("block must be an object")
            block_id = self._required_string(raw_block.get("block_id"))
            frozen = skeleton_blocks[block_id]
            generated.append(
                NarrativeBlock(
                    block_id=block_id,
                    block_type=frozen.block_type,
                    slot=frozen.slot,
                    text=self._required_string(raw_block.get("text")),
                    fact_refs=frozen.fact_refs,
                    constraint_refs=frozen.constraint_refs,
                    linked_scene_ids=frozen.linked_scene_ids,
                )
            )
        provisional = (*skeleton.service_actuality_blocks, *generated)
        block_ids = [block.block_id for block in provisional]
        if len(set(block_ids)) != len(block_ids):
            raise ValueError("block ids must be unique")

        skeleton_scenes = {scene.scene_id: scene for scene in skeleton.scenes}
        if {value.get("scene_id") for value in raw_steps if isinstance(value, dict)} != set(skeleton_scenes) or len(
            raw_steps
        ) != len(skeleton_scenes):
            raise ValueError("writer scene coverage drifted from server skeleton")
        steps: list[SceneStep] = []
        for raw_step in raw_steps:
            if not isinstance(raw_step, dict) or frozenset(raw_step) != {
                "scene_id",
                "resource_refs",
                "action_text",
                "sound_text",
                "production_note",
            }:
                raise TypeError("scene step must be an object")
            scene_id = self._required_string(raw_step.get("scene_id"))
            frozen_scene = skeleton_scenes[scene_id]
            resource_refs = self._string_refs(raw_step.get("resource_refs") or [], allow_empty=True)
            if any(ref not in frozen_scene.allowed_resource_refs for ref in resource_refs):
                raise ValueError("scene uses an unregistered resource")
            steps.append(
                SceneStep(
                    step_id=scene_id,
                    purpose=frozen_scene.purpose,
                    actor_refs=((_CREATOR_ACTOR_ID,) if _CREATOR_EXPRESSION_RESOURCE_ID in resource_refs else ()),
                    resource_refs=resource_refs,
                    action_text=self._required_string(raw_step.get("action_text")),
                    sound_text=self._optional_string(raw_step.get("sound_text")),
                    production_note=self._optional_string(raw_step.get("production_note")),
                    block_refs=frozen_scene.block_refs,
                )
            )
        return NarrativeCore(
            speaker_ref=_SPEAKER_ID,
            blocks=tuple(provisional),
            spoken_order=skeleton.spoken_order,
            scene_steps=tuple(steps),
        )

    def _review_candidate(
        self,
        request: GenerationInput,
        frame: NarrativeFrame,
        context: BoundaryContext,
        core: NarrativeCore,
        body: str,
    ) -> tuple[tuple[NarrativeIssue, ...], dict[str, Any], int]:
        payload, retries = self._request(
            "你是独立叙事观察器。只从最终可见成品提取观察，不裁决通过，不改写成品，不展示推理，只返回一个完整 JSON。",
            self._reviewer_prompt(request, frame, context, core, body),
            8192,
            # The production-compatible JSON contract is the authority here;
            # Reviewer independence comes from a separate request/input, not
            # from enabling an incompatible provider-side thinking mode.
            thinking_disabled=True,
            timeout_seconds=self._review_timeout_seconds,
        )
        try:
            document = json.loads(self._json_content(str(payload["choices"][0]["message"]["content"])))
            raw_observations = document["observations"]
            if not isinstance(raw_observations, list):
                raise TypeError
            observations = tuple(parse_observation(value) for value in raw_observations)
        except (
            KeyError,
            IndexError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            raise GenerationFailed("独立 Reviewer 返回格式不完整") from exc
        scene_text = {step.step_id: self._scene_visible_text(step) for step in core.scene_steps}
        issues = reconcile_observations(
            frame=frame,
            blocks=core.blocks,
            scene_text=scene_text,
            scene_resource_refs={step.step_id: step.resource_refs for step in core.scene_steps},
            observations=observations,
            allowed_resource_ids=context.resource_ids,
            fact_text_by_id=context.fact_text_by_id,
            brand_fact_ids=context.brand_fact_ids,
            allowed_constraint_ids=context.constraint_ids,
        )
        return issues, payload, retries

    def _merge_block_repair(
        self,
        request: GenerationInput,
        frame: NarrativeFrame,
        context: BoundaryContext,
        skeleton: NarrativeSkeleton,
        core: NarrativeCore,
        issues: tuple[NarrativeIssue, ...],
        raw: object,
    ) -> NarrativeCore:
        if not isinstance(raw, dict):
            raise TypeError("repair must be an object")
        affected_blocks, affected_scenes = self._repair_scope(core, issues)
        if any(core.block(block_id).block_type == "actuality_source" for block_id in affected_blocks):
            raise ValueError("service-authored actuality cannot be repaired")
        raw_blocks = raw.get("blocks")
        raw_scenes = raw.get("scenes")
        if not isinstance(raw_blocks, list) or not isinstance(raw_scenes, list):
            raise TypeError("repair collections are incomplete")
        if {value.get("block_id") for value in raw_blocks if isinstance(value, dict)} != affected_blocks or {
            value.get("scene_id") for value in raw_scenes if isinstance(value, dict)
        } != affected_scenes:
            raise ValueError("repair scope drifted")
        replacement_blocks = {
            self._required_string(value.get("block_id")): value for value in raw_blocks if isinstance(value, dict)
        }
        replacement_scenes = {
            self._required_string(value.get("scene_id")): value for value in raw_scenes if isinstance(value, dict)
        }
        merged_raw = {
            "blocks": [
                replacement_blocks.get(block.block_id, self._writer_block_document(block))
                for block in core.blocks
                if block.block_type != "actuality_source"
            ],
            "scenes": [
                replacement_scenes.get(scene.step_id, self._writer_scene_document(scene)) for scene in core.scene_steps
            ],
        }
        return self._parse_core(
            request,
            frame,
            context,
            skeleton,
            merged_raw,
        )

    @staticmethod
    def _assert_review_can_repair(
        core: NarrativeCore,
        issues: tuple[NarrativeIssue, ...],
    ) -> None:
        nonrepairable_reasons = {
            "review_coverage",
            "missing_exact_span",
            "uncertain_meaning",
            "actuality_changed",
        }
        actuality_ids = {block.block_id for block in core.blocks if block.block_type == "actuality_source"}
        if any(issue.reason in nonrepairable_reasons or issue.target_id in actuality_ids for issue in issues):
            raise GenerationFailed("独立 Reviewer 观察不完整或真人事实块不一致")

    @staticmethod
    def _repair_scope(
        core: NarrativeCore,
        issues: tuple[NarrativeIssue, ...],
    ) -> tuple[set[str], set[str]]:
        block_ids = {block.block_id for block in core.blocks if block.block_type != "actuality_source"}
        affected_blocks = {issue.target_id for issue in issues if issue.target_id in block_ids}
        failed_scenes = {issue.target_id for issue in issues if issue.target_id not in block_ids}
        for scene in core.scene_steps:
            if scene.step_id in failed_scenes:
                affected_blocks.update(block_id for block_id in scene.block_refs if block_id in block_ids)
        affected_scenes = {
            scene.step_id
            for scene in core.scene_steps
            if any(block_id in scene.block_refs for block_id in affected_blocks)
        }
        return affected_blocks, affected_scenes

    def _compile_core(
        self,
        request: GenerationInput,
        core: NarrativeCore,
    ) -> tuple[
        str,
        ContentSemanticContract,
        ContentProductionBundle,
        str,
    ]:
        slot_text = {block.slot: block.text for block in core.blocks if block.slot != _SPOKEN_SLOT}
        title = self._visible_text(slot_text["title"])
        contract = self._contract(request.primary_product, slot_text)
        spoken = self._visible_text("\n\n".join(core.block(block_id).text for block_id in core.spoken_order))
        cover = next(step for step in core.scene_steps if step.purpose == _COVER_PURPOSE)
        scenes = tuple(step for step in core.scene_steps if step.purpose == _SCENE_PURPOSE)
        sounds = "\n".join(
            text for step in core.scene_steps for text in (step.sound_text, step.production_note) if text
        )
        production: ContentProductionBundle
        if request.media_format == "video":
            fixed_seconds = self._fixed_duration_seconds(request.brand.production_conditions)
            duration = (
                f"{fixed_seconds} 秒" if fixed_seconds is not None else f"约 {self._natural_spoken_seconds(spoken)} 秒"
            )
            production = VideoProductionBundle(
                natural_guide=self._visible_text(slot_text["natural_guide"]),
                spoken_lines=spoken,
                visual_actions=self._visible_text("\n".join(step.action_text for step in scenes)),
                subtitles=spoken,
                sound_and_production=self._visible_text(sounds),
                cover_or_first_frame=self._visible_text(cover.action_text),
                viewing_flow=self._visible_text(slot_text["viewing_flow"]),
                natural_duration=duration,
                release_caption_and_interaction=self._visible_text(slot_text["release_caption"]),
            )
        else:
            image_steps = (cover, *scenes)
            production = GraphicProductionBundle(
                natural_guide=self._visible_text(slot_text["natural_guide"]),
                hero_image=self._visible_text(cover.action_text),
                image_sequence=self._visible_text(
                    "\n".join(
                        ("首图：" if index == 1 else f"第{index}张：") + step.action_text
                        for index, step in enumerate(image_steps, start=1)
                    )
                ),
                full_body=spoken,
                layout_and_production=self._visible_text(
                    "\n".join(step.production_note for step in core.scene_steps if step.production_note)
                ),
                release_caption_and_interaction=self._visible_text(slot_text["release_caption"]),
            )
        return title, contract, production, self._visible_body(title, production)

    @staticmethod
    def _contract(
        product: ContentProduct,
        slot_text: dict[str, str],
    ) -> ContentSemanticContract:
        values = tuple(DeepSeekGenerator._visible_text(slot_text[field]) for field in _CONTRACT_FIELDS[product])
        if product == "dressing_decision":
            return P1SemanticContract(*values)
        if product == "product_truth":
            return P2SemanticContract(*values)
        if product == "brand_life_narrative":
            return P3SemanticContract(*values)
        if product == "local_response":
            return P4SemanticContract(*values)
        return P5SemanticContract(*values)

    @staticmethod
    def _visible_body(
        title: str,
        production: ContentProductionBundle,
    ) -> str:
        if isinstance(production, VideoProductionBundle):
            sections: tuple[tuple[str, str], ...] = (
                ("内容概要", production.natural_guide),
                ("封面/首帧", production.cover_or_first_frame),
                ("完整观看链", production.viewing_flow),
                ("完整台词/解说", production.spoken_lines),
                ("画面与动作", production.visual_actions),
                ("字幕", production.subtitles),
                ("声音与制作提示", production.sound_and_production),
                ("自然时长", production.natural_duration),
                ("发布配文与互动", production.release_caption_and_interaction),
            )
        else:
            sections = (
                ("内容概要", production.natural_guide),
                ("首图方案", production.hero_image),
                ("图序与每张职责", production.image_sequence),
                ("完整发布正文", production.full_body),
                ("拍摄/排版提示", production.layout_and_production),
                ("发布配文与互动", production.release_caption_and_interaction),
            )
        return "标题：" + title + "\n\n" + "\n\n".join(f"{heading}：{value}" for heading, value in sections)

    @staticmethod
    def _routing_prompt(request: RoutingInput) -> str:
        products = "、".join(product.sku for product in request.products) or "无"
        return f"""只判断主要受众价值。只返回：
{{"primary_value":"普通交流|帮助选择|解释商品|建立人格|经营关系|视觉造型"}}
普通交流只用于没有成品意图的交流。解释商品必须有已确认商品。开放生活题材、生活片段和安全
自主选题通常选择建立人格；只有明确近场经营信号且回报是给未参与者关系许可时选择经营关系。
不得因为题材中出现门店就自行创造经营事实。
品牌：{request.brand.brand_name}
可用商品：{products}
用户输入：{request.weak_seed}"""

    @staticmethod
    def _conversation_prompt(request: ConversationInput) -> str:
        history = (
            "\n".join(
                ("用户" if turn.role == "user" else "笛语") + "：" + turn.content for turn in request.history[-8:]
            )
            or "（无）"
        )
        products = "、".join(product.sku for product in request.products) or "无"
        forced = request.explicit_narrative_mode or "无显式模式"
        return f"""编译本轮创作条件。服务端已经独立判断是否存在创作承诺；你只能提议，不能授权
创建任务。只返回以下一种 JSON：
{{"kind":"chat","message":"自然回复","creation_proposal":false,"intent_span":""}}
{{"kind":"question","message":"一个具体事实问题","missing_fact_span":"逐字复制用户明确要求依赖的真实经历片段",
"creation_proposal":true,"intent_span":"候选用户原话跨度"}}
{{"kind":"ready","message":"一句自然承接","user_premises":["逐字复制实际使用的用户消息"],
"user_fact_spans":["逐字截取用户明确陈述的现实片段"],
"creative_plan":{{"plan_version":"creative-plan-v2","topic_spans":["只能逐字截取用户消息"],
"primary_value":"dressing_decision|product_truth|brand_life_narrative|local_response|visual_styling_story",
"tone_ids":["只选允许 id"],"mechanism_id":null,"platform_shape":"{request.platform_shape}",
"prohibited_bindings":["no_situated_event","no_institutional_assertion",
"no_user_history_expansion","no_unregistered_resource"]}},
"creation_proposal":true,"intent_span":"候选用户原话跨度"}}

责任合同：
- 服务端创作承诺={str(request.creation_committed).lower()}。为 false 时自然交流优先；即使你认为
  适合创作，也只能给自然回复并将 creation_proposal 设为 true，不能把提议当作授权。
- 服务端创作承诺为 true 时，负责形成 ready 或一次不可替代事实 question；不追问题材、观点、
  受众或结构。
- 商品编号加生成请求、开放题材加生成请求、生活流水账／抱怨／感悟加生成请求、以及“没想好
  发什么”的生成请求都直接 ready。系统自己选观点与结构，不追问创作选择。
- 只有用户明确要写某段真人既成经历且缺少会决定真假的不可替代事实，才 question；只问一个。
- “某段时间／某件事”的指称和“最困难、最难忘、最重要”等主观评价只说明用户想写哪段经历，
  本身不是可逐字插入的现实事件。若没有至少一个可观察的动作、事件、对白或结果，必须
  question；不得把时间标签或评价词填进 user_fact_spans 后直接创作。
- 只给题材且没有现实片段用 general_observation；给出真人生活／工作片段用
  actuality_reflection，并把现实片段从用户消息逐字截取，保留标点，不概括；明确条件推演
  与明确故事／短剧／情境演绎不属于现实事实，user_fact_spans 必须为空。narrative_mode 由
  服务端根据显式形式与事实跨度派生，你不得返回或选择该字段。
- 显式模式为 dramatization 时必须使用它；没有明确演绎要求不得升级为剧情。
- general_observation 不创造人物动作、对白、动机、结果、地点、持有物或生活履历。
- CreativePlanV2 只能选择上述结构字段。topic_spans 必须逐字来自用户消息；禁止写人物设定、
  事件、对白、动机、因果、品牌立场、门店事实、用户履历、标题、主张或故事梗概。
- primary_value 是本篇给受众的主要回报，不是 narrative_mode，也不能填写
  general_observation／actuality_reflection／hypothesis／dramatization。只有商品请求选
  product_truth 或其他确有商品前提的商品价值；开放题材、生活种子和“没有选题但要求生成”
  通常选 brand_life_narrative，由系统自主形成安全主线和账号观看回报。
- 商品硬事实只来自当前可用商品；没有资料不猜。
- user_premises 必须包含本轮用户消息且只能逐字复制用户消息；普通聊天不带入。
- tone_ids 只能从 {json.dumps(request.allowed_tone_ids, ensure_ascii=False)} 选择，至少一个。
- mechanism_id 只能从 {json.dumps(request.allowed_mechanism_ids, ensure_ascii=False)}
  选择或为 null；platform_shape 必须逐字为 {request.platform_shape}。

当前品牌：{request.brand.brand_name}
平台／形式：{request.brand.platform}／{request.brand.media_format}
可用商品：{products}
本次可选方向：{request.selected_direction or "无"}
显式模式：{forced}
系列：{request.prior_series_summary or "无"}
此前交流：
{history}
用户本轮：{request.message}"""

    def _writer_prompt(
        self,
        request: GenerationInput,
        frame: NarrativeFrame,
        context: BoundaryContext,
        skeleton: NarrativeSkeleton,
    ) -> str:
        actual_text = (
            "\n".join(
                f"- actuality:{index} = {fact.exact_text}" for index, fact in enumerate(frame.user_facts, start=1)
            )
            or "（无服务端真人事实块）"
        )
        fact_registry = (
            "\n".join(f"- {record.fact_id}：{record.exact_text}" for record in context.fact_registry)
            or "（没有可引用的冻结事实。）"
        )
        constraint_registry = "\n".join(
            f"- {identifier}：{description}" for identifier, description in context.constraint_registry
        )
        resource_registry = "\n".join(
            f"- {identifier}：{description}" for identifier, description in context.resource_registry
        )
        mode_rule = {
            "actuality_reflection": (
                "服务端已逐字冻结 actuality_source。你不能输出、改写、概括或安排该块；"
                "只填写一般观察槽位，不能把原文扩写成新的现实细节。"
            ),
            "general_observation": (
                "全部槽位都是 general_observation。可以写抽象原则、观点、比喻、幽默和节奏；"
                "不能写 situated_event，也不能写无精确品牌事实支持的 institutional_assertion。"
            ),
            "hypothesis": ("全部块为 hypothesis，最终可见文字自然保留条件和可能性，不能写成已经发生。"),
            "dramatization": (
                "全部块为 dramatization。可以创造角色和情节，但每个独立可见块都要自然显出这是"
                "情境演绎，不能绑定用户、真实员工、顾客、品牌案例或门店现场。"
            ),
        }[frame.narrative_mode]
        prior = request.prior_saved_body or "（首次生成）"
        revision = request.revision_instruction or "（首次生成）"
        block_template = [
            {
                "block_id": block.block_id,
                "text": f"填写 {block.slot} 的完整可见文字",
            }
            for block in skeleton.blocks
        ]
        scene_template = [
            {
                "scene_id": scene.scene_id,
                "resource_refs": [],
                "action_text": "填写完整可见画面与动作",
                "sound_text": "",
                "production_note": "",
            }
            for scene in skeleton.scenes
        ]
        frozen_skeleton = {
            "speaker_ref": _SPEAKER_ID,
            "blocks": [
                {
                    "block_id": block.block_id,
                    "block_type": block.block_type,
                    "slot": block.slot,
                    "fact_refs": list(block.fact_refs),
                    "constraint_refs": list(block.constraint_refs),
                    "linked_scene_ids": list(block.linked_scene_ids),
                }
                for block in skeleton.blocks
            ],
            "service_actuality_blocks": [self._block_document(block) for block in skeleton.service_actuality_blocks],
            "scenes": [
                {
                    "scene_id": scene.scene_id,
                    "purpose": scene.purpose,
                    "block_refs": list(scene.block_refs),
                    "allowed_resource_refs": list(scene.allowed_resource_refs),
                }
                for scene in skeleton.scenes
            ],
            "spoken_order": list(skeleton.spoken_order),
        }
        plan = creative_plan_document(request.creative_plan) if request.creative_plan is not None else {}
        output_shape = {"blocks": block_template, "scenes": scene_template}
        return f"""生成一个完整结构化成品。只返回 JSON，且只填服务端给出的文字与资源槽位。
用户原始前提：{request.weak_seed}
CreativePlanV2：{json.dumps(plan, ensure_ascii=False)}
本次修改：{revision}
旧成品（只用于修改对比，不是事实来源）：{prior}
叙事模式：{frame.narrative_mode}
模式合同：{mode_rule}
服务端真人事实块：
{actual_text}

品牌与账号表达约束：
{context.brand_text}
方法约束：
{context.method_text}
精确冻结事实（只有这些原句能证明现实事实或机构主张）：
{fact_registry}
表达约束（只限制怎么说，不能证明发生过什么或机构相信什么）：
{constraint_registry}
允许的拍摄／制作资源：
{resource_registry}

受众价值：{_PRODUCT_VALUE[request.primary_product]}
平台／形式：{request.brand.platform}／{request.media_format}
平台方向：{request.platform_direction.direction}

服务端冻结骨架（只读，不能在输出中重述或修改）：
{json.dumps(frozen_skeleton, ensure_ascii=False)}

只返回以下结构：
{json.dumps(output_shape, ensure_ascii=False)}

输出必须恰好覆盖模板中的每个 block_id 与 scene_id，不能增加或删除字段、id 或条目。
不要输出 block_type、slot、fact_refs、constraint_refs、linked_scene_ids、purpose、block_refs、
speaker_ref 或 spoken_order；这些均由服务端冻结。
资源只能从对应 scene 的 allowed_resource_refs 中选择。用户事实不是拍摄资源。
fact_refs 指向精确事实；constraint_refs 只能约束语气、角色、方法和平台，不能作为事实许可证。
general_observation 只写 abstract_principle；situated_event 不因省略人物称谓而成为抽象观点。
institutional_assertion 必须逐字等于该块允许的精确品牌事实，否则不要写。
confirmed_fact 必须逐字等于该块允许的精确事实，不得改写。
hypothesis 必须在每个可见槽位保持条件语气。dramatization 必须在每个可见槽位自然表明演绎，
且不能绑定真实用户、员工、顾客、品牌历史或未登记资源。
所有标题、正文、口播、字幕、画面、动作、声音、制作提示和发布配文都来自这些槽位；
不要暴露内部 id、类型、来源、约束、规则或审查说明。"""

    def _reviewer_prompt(
        self,
        request: GenerationInput,
        frame: NarrativeFrame,
        context: BoundaryContext,
        core: NarrativeCore,
        body: str,
    ) -> str:
        targets = [{"id": block.block_id, "target_kind": "block", "text": block.text} for block in core.blocks] + [
            {
                "id": scene.step_id,
                "target_kind": "scene",
                "text": self._scene_visible_text(scene),
            }
            for scene in core.scene_steps
        ]
        frame_input = {
            "frame_version": frame.frame_version,
            "narrative_mode": frame.narrative_mode,
            "user_facts": [{"source_id": fact.source_id, "exact_text": fact.exact_text} for fact in frame.user_facts],
            "allowed_brand_fact_ids": list(frame.allowed_brand_fact_ids),
            "allowed_product_fact_ids": list(frame.allowed_product_fact_ids),
        }
        resources = [
            {"id": identifier, "description": description} for identifier, description in context.resource_registry
        ]
        aigc_label, aigc_reminder = aigc_disclosure(self._model)
        aigc_visible = f"{aigc_label}；{aigc_reminder}" if aigc_label and aigc_reminder else "（无 AIGC 展示字段）"
        return f"""独立阅读最终完整可见成品，然后对每个 block 和 scene 逐一提取实际语义。
这里不提供 Writer 的任何事实自报或事实标签；只读实际可见文本。不要返回 pass/fail 布尔裁决。

用户原始要求：{request.weak_seed}
本次修改：{request.revision_instruction or "（首次生成）"}
NarrativeFrame：{json.dumps(frame_input, ensure_ascii=False)}
允许资源：{json.dumps(resources, ensure_ascii=False)}
冻结商品事实：
{context.product_facts_text}

最终完整可见成品：
{body}

最终展示的 AIGC 提醒：
{aigc_visible}

逐项目标：
{json.dumps(targets, ensure_ascii=False)}

对每个 id 恰好返回一份观察，id 和 target_kind 必须原样。text_spans 至少一项，逐字复制该目标
真实存在、足以承载观察的精确跨度；不能抄别的目标。claims 是统一观察列表，每项只含 category
和 span；span 必须逐字存在于该目标。每个 observation 的 text_spans 必须恰好是只含该
block 或 scene 完整可见原文的单元素数组，不得截短、拆分或概括。category 只选 people、relationships、
actions_or_events、dialogue、motives、causes、results、times、locations、possessions。
同一跨度承载多类观察时分别列出，不能改写或概括跨度。

observation_type 只选：
- abstract_principle：抽象原则、观点、价值判断或一般关系理解，不声称一件具体事情已经发生；
- situated_event：具体或隐含人物在某个情境中的动作、对白、反应、原因或结果；即使省略人物称谓，
  只要存在一件情境化微事件也选它；
- institutional_assertion：品牌、公司、门店、账号或组织声称其相信、坚持、倡导、承诺、已实施
  做法或形成历史；
- user_actuality：逐字用户真人事实；
- hypothesis：可见保留条件／可能性的推演；
- dramatization：可见自然表明是创作演绎；
- confirmed_fact：冻结品牌／组织／商品状态；
- uncertain：无法确定。
这里的类型判断的是文字语义，不是画面采用了什么制作形式。“抽象构图”“色块”
“排版”本身不是 dramatization；只要没有把具体事件演成已发生事实，应按
abstract_principle 或 hypothesis 判断。possessions 只提取文字主张现实人物持有、或制作确实
需要的实体物件；原创抽象构成中的线条、色块、标点、文字和明确的图形符号不是现实持有物。
一般题材里只要出现具体人物做事、对白、动机、结果、时间地点或持有物，必须如实提取，不能因
语气温和而归为空。演绎只有在目标自身存在自然可见提示时才填 dramatization，并把提示逐字放入
dramatization_disclosure_spans；删掉提示会像现实叙述时不能留空。resource_refs 填该 scene
实际需要的登记资源 id；若需要未登记人物、家、店、厨房、家具、照片、现场声音或道具，填
unregistered:加简短名称。用户事实来源不是资源。instruction_conflicts 逐字列出与用户要求冲突
的目标片段；没有则空。任何语义无法确定时 uncertain=true。

只返回：
{{"observations":[{{"id":"…","target_kind":"block|scene","text_spans":["…"],
"claims":[{{"category":"relationships","span":"目标内精确子串"}}],
"observation_type":"…","resource_refs":[],"dramatization_disclosure_spans":[],
"instruction_conflicts":[],"uncertain":false}}]}}

严格类型：text_spans、resource_refs、dramatization_disclosure_spans 和
instruction_conflicts 必须是纯字符串 JSON 数组；claims 必须是上述统一对象数组；没有观察就
返回 []。不得增加 category，不得嵌套数组，不得返回 null。每个逐项目标恰好一个 observation，
所有字段都必须出现。"""

    def _repair_prompt(
        self,
        request: GenerationInput,
        frame: NarrativeFrame,
        context: BoundaryContext,
        core: NarrativeCore,
        issues: tuple[NarrativeIssue, ...],
    ) -> str:
        affected_blocks, affected_scenes = self._repair_scope(core, issues)
        if any(core.block(block_id).block_type == "actuality_source" for block_id in affected_blocks):
            raise GenerationFailed("服务端真人事实块无法修改")
        blocks = [self._writer_block_document(block) for block in core.blocks if block.block_id in affected_blocks]
        scenes = [self._writer_scene_document(scene) for scene in core.scene_steps if scene.step_id in affected_scenes]
        findings = [
            {
                "id": issue.target_id,
                "reason": issue.reason,
                "fragment": issue.fragment,
            }
            for issue in issues
        ]
        return f"""只进行这一次完整叙事块修复。不得改变 NarrativeFrame、narrative_mode、服务端真人
事实块、事实来源集合或用户核心要求。修复每个列出的完整 block，并同时修复它关联的全部 scene；
不得返回未列出的 id，也不得只改一句／一个字段。

NarrativeFrame：{frame.narrative_mode}
用户要求：{request.weak_seed}
修改要求：{request.revision_instruction or "（首次生成）"}
CreativePlanV2：{
            json.dumps(
                creative_plan_document(request.creative_plan) if request.creative_plan is not None else {},
                ensure_ascii=False,
            )
        }
品牌边界：{context.brand_text}
冻结商品事实：{context.product_facts_text}
可用资源：{json.dumps(context.resource_registry, ensure_ascii=False)}
问题：{json.dumps(findings, ensure_ascii=False)}
必须完整替换的 blocks：{json.dumps(blocks, ensure_ascii=False)}
必须完整替换的 scenes：{json.dumps(scenes, ensure_ascii=False)}

保持每个 block_id 和 scene_id 不变。类型、slot、事实、约束、关联和模式均由服务端冻结，
不得在输出中声明或修改。
一般观察出现具体真人事件时，重建整个观察块和关联画面，不把失败句塞到别处；真人原文只由
服务端块承担。资源越界时重建整个相关块与画面，不固定回退手机、字卡或室内。演绎必须在每个
相关块自然可见为演绎。商品硬事实只能逐字使用冻结登记句。
一般观察修复不得换成“比如她／你……”的人物微场景，也不得暗示受众经历过某件事；抽象画面
只用色块、线条、留白、标点、文字与原创声音组织。账号链接不得新写品牌信念、历史或承诺。

只返回：
{{"blocks":[只含 block_id 与 text 的完整对象],
"scenes":[只含 scene_id、resource_refs、action_text、sound_text、production_note 的完整对象]}}"""

    @staticmethod
    def _block_document(block: NarrativeBlock) -> dict[str, object]:
        return {
            "block_id": block.block_id,
            "block_type": block.block_type,
            "slot": block.slot,
            "text": block.text,
            "fact_refs": list(block.fact_refs),
            "constraint_refs": list(block.constraint_refs),
            "linked_scene_ids": list(block.linked_scene_ids),
        }

    @staticmethod
    def _writer_block_document(
        block: NarrativeBlock,
    ) -> dict[str, object]:
        return {"block_id": block.block_id, "text": block.text}

    @staticmethod
    def _writer_scene_document(scene: SceneStep) -> dict[str, object]:
        return {
            "scene_id": scene.step_id,
            "resource_refs": list(scene.resource_refs),
            "action_text": scene.action_text,
            "sound_text": scene.sound_text,
            "production_note": scene.production_note,
        }

    @staticmethod
    def _scene_visible_text(scene: SceneStep) -> str:
        return "\n".join(
            part
            for part in (
                scene.action_text,
                scene.sound_text,
                scene.production_note,
            )
            if part
        )

    @staticmethod
    def _repair_receipts(
        issues: tuple[NarrativeIssue, ...],
    ) -> tuple[FactRepairReceipt, ...]:
        grouped: dict[str, list[str]] = {}
        for issue in issues:
            grouped.setdefault(issue.target_id, []).append(issue.fragment)
        return tuple(
            FactRepairReceipt(
                field=target_id,
                fragments=tuple(dict.fromkeys(fragments)),
            )
            for target_id, fragments in grouped.items()
        )

    @staticmethod
    def _registered_product_claims(
        product: ProductFact,
    ) -> tuple[str, ...]:
        return registered_product_claims(product)

    @staticmethod
    def _review_max_tokens(question_count: int) -> int:
        if question_count < 1:
            raise ValueError("review question count must be positive")
        return min(
            _REVIEW_TOKEN_HARD_LIMIT,
            _REVIEW_TOKEN_BASE + _REVIEW_TOKEN_PER_QUESTION * question_count,
        )

    @staticmethod
    def _license_review_max_tokens(clause_count: int) -> int:
        if clause_count < 1:
            raise ValueError("review clause count must be positive")
        return min(
            _REVIEW_TOKEN_HARD_LIMIT,
            _REVIEW_TOKEN_BASE + _LICENSE_REVIEW_TOKEN_PER_CLAUSE * clause_count,
        )

    def _strict_review_api_url(self) -> str:
        base_url = self._api_base_url
        if base_url.endswith("/beta"):
            beta_url = base_url
        elif base_url.endswith("/v1"):
            beta_url = f"{base_url[:-3]}/beta"
        else:
            beta_url = f"{base_url}/beta"
        return f"{beta_url}/chat/completions"

    @staticmethod
    def _strict_license_review_tool(
        licenses: tuple[ClauseLicenseV1, ...],
    ) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": CLAUSE_LICENSE_TOOL_NAME,
                "description": (
                    "Check whether every writer clause is fully supported by its server-assigned ClauseLicenseV1."
                ),
                "strict": True,
                "parameters": clause_license_review_json_schema(licenses),
            },
        }

    @staticmethod
    def _strict_license_review_answers(
        payload: dict[str, Any],
        *,
        licenses: tuple[ClauseLicenseV1, ...],
    ) -> ClauseLicenseReviewsV1:
        choices = payload.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise TypeError("strict license review choice count is invalid")
        choice = choices[0]
        if not isinstance(choice, dict) or choice.get("finish_reason") != "tool_calls":
            raise TypeError("strict license review finish reason is invalid")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise TypeError("strict license review message is invalid")
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list) or len(tool_calls) != 1:
            raise TypeError("strict license review tool call count is invalid")
        tool_call = tool_calls[0]
        if not isinstance(tool_call, dict) or tool_call.get("type") != "function":
            raise TypeError("strict license review tool call is invalid")
        function = tool_call.get("function")
        if not isinstance(function, dict) or function.get("name") != CLAUSE_LICENSE_TOOL_NAME:
            raise TypeError("strict license review function name is invalid")
        arguments = function.get("arguments")
        if not isinstance(arguments, str):
            raise TypeError("strict license review arguments are invalid")
        usage = payload.get("usage")
        if isinstance(usage, dict):
            completion_tokens = usage.get("completion_tokens")
            if isinstance(completion_tokens, int) and completion_tokens > _REVIEW_TOKEN_HARD_LIMIT:
                raise TypeError("strict license review output exceeded hard limit")
        return parse_clause_license_reviews_v1(
            json.loads(arguments),
            licenses=licenses,
        )

    def _request_strict_license_review(
        self,
        system: str,
        prompt: str,
        *,
        license_count: int,
        licenses: tuple[ClauseLicenseV1, ...],
        timeout_seconds: float | None = None,
    ) -> tuple[dict[str, Any], int]:
        request_payload: dict[str, Any] = {
            "model": self._reviewer_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "max_tokens": self._license_review_max_tokens(license_count),
            "thinking": {"type": "disabled"},
            "tools": [self._strict_license_review_tool(licenses)],
            "tool_choice": {
                "type": "function",
                "function": {"name": CLAUSE_LICENSE_TOOL_NAME},
            },
        }
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout_seconds or self._timeout_seconds)) as client:
                response = client.post(
                    self._strict_review_api_url(),
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=request_payload,
                )
        except httpx.TransportError as exc:
            raise GenerationFailed("Reviewer strict 模型网络请求失败") from exc
        if response.status_code >= 400:
            _LOGGER.warning(
                "strict license review request rejected: status=%s",
                response.status_code,
            )
            raise GenerationFailed("Reviewer strict 模型服务拒绝当前请求")
        try:
            result = response.json()
        except (TypeError, ValueError) as exc:
            raise GenerationFailed("Reviewer strict 模型返回无效") from exc
        if not isinstance(result, dict):
            raise GenerationFailed("Reviewer strict 模型返回无效")
        return result, 0

    @staticmethod
    def _strict_review_tool(
        questions: tuple[ClosedReviewQuestion, ...],
    ) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": CLOSED_REVIEW_TOOL_NAME,
                "description": (
                    "Answer every server-provided closed review question with a clause scope and bounded operands."
                ),
                "strict": True,
                "parameters": closed_review_json_schema(questions),
            },
        }

    @staticmethod
    def _strict_review_answers(
        payload: dict[str, Any],
        *,
        questions: tuple[ClosedReviewQuestion, ...],
    ) -> ClosedReviewAnswers:
        choices = payload.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise TypeError("strict review choice count is invalid")
        choice = choices[0]
        if not isinstance(choice, dict) or choice.get("finish_reason") != "tool_calls":
            raise TypeError("strict review finish reason is invalid")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise TypeError("strict review message is invalid")
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list) or len(tool_calls) != 1:
            raise TypeError("strict review tool call count is invalid")
        tool_call = tool_calls[0]
        if not isinstance(tool_call, dict) or tool_call.get("type") != "function":
            raise TypeError("strict review tool call is invalid")
        function = tool_call.get("function")
        if not isinstance(function, dict) or function.get("name") != CLOSED_REVIEW_TOOL_NAME:
            raise TypeError("strict review function name is invalid")
        arguments = function.get("arguments")
        if not isinstance(arguments, str):
            raise TypeError("strict review arguments are invalid")
        usage = payload.get("usage")
        if isinstance(usage, dict):
            completion_tokens = usage.get("completion_tokens")
            if isinstance(completion_tokens, int) and completion_tokens > _REVIEW_TOKEN_HARD_LIMIT:
                raise TypeError("strict review output exceeded hard limit")
        return parse_closed_review_answers(
            json.loads(arguments),
            questions=questions,
        )

    def _request_strict_review(
        self,
        system: str,
        prompt: str,
        *,
        question_count: int,
        questions: tuple[ClosedReviewQuestion, ...],
        timeout_seconds: float | None = None,
    ) -> tuple[dict[str, Any], int]:
        request_payload: dict[str, Any] = {
            "model": self._reviewer_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "max_tokens": self._review_max_tokens(question_count),
            "thinking": {"type": "disabled"},
            "tools": [self._strict_review_tool(questions)],
            "tool_choice": {
                "type": "function",
                "function": {"name": CLOSED_REVIEW_TOOL_NAME},
            },
        }
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout_seconds or self._timeout_seconds)) as client:
                response = client.post(
                    self._strict_review_api_url(),
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=request_payload,
                )
        except httpx.TransportError as exc:
            raise GenerationFailed("Reviewer strict 模型网络请求失败") from exc
        if response.status_code >= 400:
            _LOGGER.warning(
                "strict review request rejected: status=%s",
                response.status_code,
            )
            raise GenerationFailed("Reviewer strict 模型服务拒绝当前请求")
        try:
            result = response.json()
        except (TypeError, ValueError) as exc:
            raise GenerationFailed("Reviewer strict 模型返回无效") from exc
        if not isinstance(result, dict):
            raise GenerationFailed("Reviewer strict 模型返回无效")
        return result, 0

    @staticmethod
    def _closed_review_batches(
        questions: tuple[ClosedReviewQuestion, ...],
    ) -> tuple[tuple[ClosedReviewQuestion, ...], ...]:
        clause_ids = tuple(dict.fromkeys(question.clause_id for question in questions))
        if not clause_ids:
            raise ValueError("closed review questions cannot be empty")
        batches: list[tuple[ClosedReviewQuestion, ...]] = []
        for start in range(0, len(clause_ids), _CLOSED_REVIEW_BATCH_CLAUSES):
            selected = frozenset(clause_ids[start : start + _CLOSED_REVIEW_BATCH_CLAUSES])
            batch = tuple(question for question in questions if question.clause_id in selected)
            if not batch:
                raise ValueError("closed review batch cannot be empty")
            batches.append(batch)
        return tuple(batches)

    @staticmethod
    def _clause_license_batches(
        licenses: tuple[ClauseLicenseV1, ...],
    ) -> tuple[tuple[ClauseLicenseV1, ...], ...]:
        if not licenses:
            raise ValueError("clause licenses cannot be empty")
        return tuple(
            licenses[start : start + _CLOSED_REVIEW_BATCH_CLAUSES]
            for start in range(0, len(licenses), _CLOSED_REVIEW_BATCH_CLAUSES)
        )

    def _review_payload_envelope(
        self,
        payloads: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if self._reviewer_provider is None:
            raise GenerationFailed("历史 Reviewer 回放路径没有配置审查提供方")
        return {
            "clause_license_review_batches": payloads,
            "reviewer_model": self._reviewer_model,
            "reviewer_provider": self._reviewer_provider.provider_name,
            "usage": self._combined_usage(payloads),
        }

    def _request(
        self,
        system: str,
        prompt: str,
        max_tokens: int,
        *,
        thinking_disabled: bool = True,
        timeout_seconds: float | None = None,
    ) -> tuple[dict[str, Any], int]:
        retries = 0
        request_payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if thinking_disabled:
            request_payload["thinking"] = {"type": "disabled"}
        with httpx.Client(timeout=httpx.Timeout(timeout_seconds or self._timeout_seconds)) as client:
            while True:
                try:
                    response = client.post(
                        f"{self._api_base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json=request_payload,
                    )
                    if response.status_code < 400:
                        result = response.json()
                        if not isinstance(result, dict):
                            raise GenerationFailed("模型返回无效")
                        return result, retries
                    if response.status_code != 429 and not 500 <= response.status_code < 600:
                        error_code = ""
                        error_category = "unavailable"
                        try:
                            error_body = response.json()
                            if isinstance(error_body, dict):
                                raw_error = error_body.get("error")
                                if isinstance(raw_error, dict):
                                    raw_code = raw_error.get("code")
                                    if isinstance(raw_code, str):
                                        error_code = raw_code
                                    raw_message = raw_error.get("message")
                                    if isinstance(raw_message, str):
                                        lowered_message = raw_message.casefold()
                                        for category, markers in (
                                            ("max_tokens", ("max_tokens", "maximum tokens")),
                                            ("context_length", ("context length", "context_length")),
                                            ("input_length", ("input length", "prompt length")),
                                            ("thinking", ("thinking",)),
                                            ("response_format", ("response_format",)),
                                            ("content_filter", ("sensitive", "content filter")),
                                            ("parameter", ("parameter", "invalid value")),
                                        ):
                                            if any(marker in lowered_message for marker in markers):
                                                error_category = category
                                                break
                        except (TypeError, ValueError):
                            pass
                        _LOGGER.warning(
                            "model request rejected: status=%s code=%s category=%s",
                            response.status_code,
                            error_code or "unavailable",
                            error_category,
                        )
                        raise GenerationFailed("模型服务拒绝当前请求")
                    if retries >= self._max_retries:
                        raise GenerationFailed("模型服务暂时不可用")
                    delay = self._retry_delay(response.headers.get("Retry-After"), retries)
                except httpx.TransportError as exc:
                    if retries >= self._max_retries:
                        raise GenerationFailed("模型网络请求失败") from exc
                    delay = min(4.0, 0.5 * (2**retries))
                retries += 1
                time.sleep(delay)

    @staticmethod
    def _combined_usage(
        payloads: list[dict[str, Any]],
    ) -> dict[str, int] | None:
        totals: dict[str, int] = {}
        for payload in payloads:
            usage = payload.get("usage")
            if not isinstance(usage, dict):
                continue
            for key, value in usage.items():
                if isinstance(value, int):
                    totals[str(key)] = totals.get(str(key), 0) + value
        return totals or None

    def _provider_usage_receipt(
        self,
        payloads: list[dict[str, Any]],
    ) -> dict[str, int | str]:
        if self._reviewer_provider is None:
            return {
                **(self._combined_usage(payloads) or {}),
                "writer_model": self._model,
                "version_authorization": "deterministic-dual-track-v1",
            }
        writer_payloads = [
            payload
            for payload in payloads
            if not isinstance(
                payload.get("clause_license_review_batches"),
                list,
            )
        ]
        reviewer_payloads = [
            batch
            for payload in payloads
            if isinstance(
                payload.get("clause_license_review_batches"),
                list,
            )
            for batch in cast(
                list[dict[str, Any]],
                payload["clause_license_review_batches"],
            )
        ]
        combined = self._combined_usage(payloads) or {}
        receipt: dict[str, int | str] = {
            **combined,
            "writer_model": self._model,
            "reviewer_model": self._reviewer_model or "",
            "reviewer_provider": self._reviewer_provider.provider_name,
        }
        for role, role_payloads in (("writer", writer_payloads), ("reviewer", reviewer_payloads)):
            for key, value in (self._combined_usage(role_payloads) or {}).items():
                receipt[f"{role}_{key}"] = value
        return receipt

    @staticmethod
    def _retry_delay(retry_after: str | None, retries: int) -> float:
        if retry_after:
            try:
                return min(8.0, max(0.0, float(retry_after)))
            except ValueError:
                try:
                    return min(
                        8.0,
                        max(
                            0.0,
                            parsedate_to_datetime(retry_after).timestamp() - time.time(),
                        ),
                    )
                except (TypeError, ValueError):
                    pass
        return float(min(4.0, 0.5 * (2**retries)))

    @staticmethod
    def _json_content(content: str) -> str:
        stripped = content.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            stripped = re.sub(
                r"^```(?:json)?\s*",
                "",
                stripped,
                count=1,
                flags=re.IGNORECASE,
            )
            stripped = re.sub(r"\s*```$", "", stripped, count=1)
        return stripped

    @staticmethod
    def _required_string(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise TypeError("field must be a non-empty string")
        return value.strip()

    @staticmethod
    def _optional_string(value: object) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise TypeError("field must be a string")
        return value.strip()

    @staticmethod
    def _string_refs(
        value: object,
        *,
        allow_empty: bool = False,
    ) -> tuple[str, ...]:
        if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
            if allow_empty and value == []:
                return ()
            raise TypeError("references must be a string list")
        result = tuple(dict.fromkeys(item.strip() for item in value))
        if not allow_empty and not result:
            raise TypeError("references must not be empty")
        return result

    @staticmethod
    def _exact_string_list(value: list[object]) -> tuple[str, ...]:
        if any(not isinstance(item, str) or not item for item in value):
            raise GenerationFailed("模型返回的原文数组无效")
        return tuple(dict.fromkeys(cast(list[str], value)))

    @staticmethod
    def _visible_text(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise TypeError("visible content must be a non-empty string")
        visible = value.strip()
        if not re.search(r"[\w一-鿿]", visible):
            raise TypeError("visible content must contain readable text")
        return visible

    @staticmethod
    def _semantic_text(value: str) -> str:
        return re.sub(r"\s+", "", value)

    @staticmethod
    def _natural_spoken_seconds(spoken: str) -> int:
        readable = len(re.findall(r"[一-鿿]|[A-Za-z0-9]+", spoken))
        pauses = len(re.findall(r"[。！？!?；;\n]", spoken))
        return max(1, (readable + 3) // 4 + (pauses + 1) // 2)

    @staticmethod
    def _fixed_duration_seconds(
        production_conditions: str,
    ) -> int | None:
        match = re.search(r"(?<!\d)(\d{1,3})\s*秒", production_conditions)
        return int(match.group(1)) if match else None
