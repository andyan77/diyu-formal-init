from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, replace
from email.utils import parsedate_to_datetime
from typing import Any, cast

import httpx

from src.ports.content_generator import ContentGenerator
from src.shared.errors import GenerationFailed
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
_NARRATIVE_MODES = frozenset(_MODE_BLOCK_TYPE)


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
        return tuple(block.block_id for block in self.blocks) + tuple(
            scene.step_id for scene in self.scene_steps
        )


@dataclass(frozen=True)
class BoundaryContext:
    source_registry: tuple[tuple[str, str], ...]
    resource_registry: tuple[tuple[str, str], ...]
    actor_registry: tuple[tuple[str, str], ...]
    exact_product_facts: dict[str, frozenset[str]]
    product_facts_text: str
    brand_text: str
    method_text: str

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
        exact_product_facts = {
            f"source:product:{product.sku}": frozenset(
                DeepSeekGenerator._registered_product_claims(product)
            )
            for product in request.products
        }
        product_facts_text = "\n".join(
            f"- {source_id}：{statement}"
            for source_id, statements in exact_product_facts.items()
            for statement in sorted(statements)
        )
        source_registry = (
            ("source:brand_baseline", "当前品牌定位、判断顺序与语气"),
            ("source:role_boundary", "当前发布账号的表达身份与资格边界"),
            ("source:organization", "当前品牌、组织与发布账号在册事实"),
            *(
                (fact.source_id, f"用户本轮原文：{fact.exact_text}")
                for fact in frame.user_facts
            ),
            *(
                (source_id, "当前冻结商品登记事实")
                for source_id in frame.allowed_product_fact_ids
            ),
        )
        resource_registry = (
            (
                _CREATOR_EXPRESSION_RESOURCE_ID,
                "创作者本人可选择口播、旁白、手势或不出镜表达；"
                "不证明其具有题材中的家庭、职业或经历身份",
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
            (
                "系统创作计划（只决定主题、切口、观点、结构、风格和平台组织，"
                "不是事实来源）："
                + request.system_creative_plan
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
                        "控制说明本身）："
                        + request.creative_direction.custom_text
                    ),
                )
                if request.creative_direction is not None
                else ()
            ),
            *(
                (
                    "本次选用的参考材料（只作为表达参考，不证明现实对象或事件存在）："
                    + material.text_body
                )
                for material in request.reference_materials
                if material.text_body
            ),
            *(
                (
                    "本次参考材料使用说明（只调整创作方法，不是成品素材）："
                    + material.reference_note
                )
                for material in request.reference_materials
                if material.reference_note
            ),
            *(
                (
                    (
                        "私人协作偏好说明只调整协作方式与表达取舍，成品中不得出现它的"
                        "原文、转述或对它的解释："
                        + request.collaboration_note
                    ),
                )
                if request.collaboration_note
                else ()
            ),
            *(
                "方法资料（不证明现实对象存在）：" + asset.body
                for asset in request.active_domain_assets
            ),
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
            source_registry=source_registry,
            resource_registry=resource_registry,
            actor_registry=(
                (
                    _CREATOR_ACTOR_ID,
                    "当前创作者，仅以拍摄者／表达者身份出现，不扮演题材人物",
                ),
            ),
            exact_product_facts=exact_product_facts,
            product_facts_text=product_facts_text
            or "（本次没有冻结商品事实。）",
            brand_text=brand_text,
            method_text="\n".join(part for part in method_parts if part),
        )


class DeepSeekGenerator(ContentGenerator):
    """One provider: intake, typed writer, independent extractor, one block repair."""

    def __init__(
        self,
        api_base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
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
            document = json.loads(
                self._json_content(
                    str(payload["choices"][0]["message"]["content"])
                )
            )
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
            document = json.loads(
                self._json_content(
                    str(payload["choices"][0]["message"]["content"])
                )
            )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise GenerationFailed("这次还没能可靠理解你的意思，请继续补充一句。") from exc
        if not isinstance(document, dict):
            raise GenerationFailed("这次还没能可靠理解你的意思，请继续补充一句。")
        kind = document.get("kind")
        message = document.get("message")
        if kind not in {"chat", "question", "ready"} or not isinstance(
            message, str
        ) or not message.strip():
            raise GenerationFailed("这次还没能可靠理解你的意思，请继续补充一句。")
        if kind == "chat":
            return ConversationDecision("chat", message.strip())
        available_user_turns = tuple(
            turn.content for turn in request.history if turn.role == "user"
        ) + (request.message,)
        if kind == "question":
            missing_span = document.get("missing_fact_span")
            if (
                not isinstance(missing_span, str)
                or not missing_span
                or not any(
                    missing_span in user_turn for user_turn in available_user_turns
                )
            ):
                raise GenerationFailed("模型追问没有绑定用户的不可替代事实")
            return ConversationDecision("question", message.strip())
        raw_premises = document.get("user_premises")
        raw_facts = document.get("user_fact_spans")
        raw_mode = document.get("narrative_mode")
        raw_plan = document.get("system_creative_plan")
        raw_value = document.get("primary_value")
        if (
            not isinstance(raw_premises, list)
            or not isinstance(raw_facts, list)
            or not isinstance(raw_mode, str)
            or raw_mode not in _NARRATIVE_MODES
            or not isinstance(raw_plan, str)
            or not raw_plan.strip()
        ):
            raise GenerationFailed("模型协作返回格式不完整")
        premises = self._exact_string_list(raw_premises)
        facts = self._exact_string_list(raw_facts)
        if (
            request.message not in premises
            or any(premise not in available_user_turns for premise in premises)
        ):
            raise GenerationFailed("模型没有逐字保留本次用户前提")
        premise_text = "\n".join(premises)
        if any(fact not in premise_text for fact in facts):
            raise GenerationFailed("模型返回的用户事实跨度不存在")
        if (raw_mode == "actuality_reflection") != bool(facts):
            raise GenerationFailed("模型叙事模式与用户事实跨度不一致")
        if (
            request.explicit_narrative_mode is not None
            and raw_mode != request.explicit_narrative_mode
        ):
            raise GenerationFailed("模型没有遵守用户显式叙事形式")
        mapping: dict[str, ContentProduct] = {
            "帮助选择": "dressing_decision",
            "解释商品": "product_truth",
            "建立人格": "brand_life_narrative",
            "经营关系": "local_response",
            "视觉造型": "visual_styling_story",
        }
        if not isinstance(raw_value, str) or raw_value not in mapping:
            raise GenerationFailed("模型没有形成一个受众价值")
        return ConversationDecision(
            "ready",
            message.strip(),
            user_premises=premises,
            user_fact_spans=facts,
            narrative_mode=raw_mode,
            system_creative_plan=raw_plan.strip(),
            primary_product=mapping[raw_value],
        )

    def generate(self, request: GenerationInput) -> GeneratedArtifact:
        started = time.monotonic()
        retries = 0
        provider_payloads: list[dict[str, Any]] = []
        frame = request.narrative_frame or legacy_frame(
            tuple(f"source:product:{product.sku}" for product in request.products)
        )
        context = BoundaryContext.from_request(request, frame)
        writer_payload, writer_retries = self._request(
            "你是笛语类型化内容 Writer。只返回一个完整 JSON，不展示推理、规则或内部审查。",
            self._writer_prompt(request, frame, context),
            8192,
        )
        provider_payloads.append(writer_payload)
        retries += writer_retries
        try:
            core = self._parse_core(
                request,
                frame,
                context,
                json.loads(
                    self._json_content(
                        str(writer_payload["choices"][0]["message"]["content"])
                    )
                ),
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
                ",".join(
                    f"{issue.target_id}:{issue.reason}" for issue in issues
                ),
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
                    core,
                    issues,
                    json.loads(
                        self._json_content(
                            str(
                                repair_payload["choices"][0]["message"][
                                    "content"
                                ]
                            )
                        )
                    ),
                )
            except (
                KeyError,
                IndexError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                raise GenerationFailed("模型块级修复返回格式不完整") from exc
            title, contract, production, body = self._compile_core(
                request, repaired
            )
            final_issues, review_payload, review_retries = (
                self._review_candidate(
                    request,
                    frame,
                    context,
                    repaired,
                    body,
                )
            )
            provider_payloads.append(review_payload)
            retries += review_retries
            if final_issues:
                raise GenerationFailed("内容边界无法在一次叙事块修复内满足")
            receipts = self._repair_receipts(issues)
            core = repaired
        if request.revision_instruction and request.prior_saved_body:
            without_facts = body
            prior_without_facts = request.prior_saved_body
            for fact in frame.user_facts:
                without_facts = without_facts.replace(fact.exact_text, "")
                prior_without_facts = prior_without_facts.replace(
                    fact.exact_text, ""
                )
            if self._semantic_text(without_facts) == self._semantic_text(
                prior_without_facts
            ):
                raise GenerationFailed("本次修改没有实质改变允许修改的表达块")
        digest = visible_digest(title, body)
        return GeneratedArtifact(
            outline=title,
            body=body,
            model=self._model,
            latency_ms=int((time.monotonic() - started) * 1000),
            retry_count=retries,
            provider_usage=self._combined_usage(provider_payloads),
            primary_product=request.primary_product,
            semantic_contract=contract,
            production=production,
            fact_repair_receipts=receipts,
            reviewed_digest=digest,
        )

    @staticmethod
    def _singleton_slots(
        product: ContentProduct,
        media_format: str,
    ) -> tuple[str, ...]:
        base: tuple[str, ...] = ("title", "natural_guide", "release_caption")
        if media_format == "video":
            base = (*base, "viewing_flow")
        return (*base, *_CONTRACT_FIELDS[product])

    def _parse_core(
        self,
        request: GenerationInput,
        frame: NarrativeFrame,
        context: BoundaryContext,
        raw: object,
    ) -> NarrativeCore:
        if not isinstance(raw, dict) or raw.get("speaker_ref") != _SPEAKER_ID:
            raise TypeError("typed core must use the registered speaker")
        raw_blocks = raw.get("blocks")
        raw_order = raw.get("spoken_order")
        raw_steps = raw.get("scene_steps")
        if (
            not isinstance(raw_blocks, list)
            or not raw_blocks
            or not isinstance(raw_order, list)
            or not raw_order
            or not isinstance(raw_steps, list)
            or not raw_steps
        ):
            raise TypeError("typed core collections are incomplete")
        expected_type = _MODE_BLOCK_TYPE[frame.narrative_mode]
        singleton_slots = self._singleton_slots(
            request.primary_product, request.media_format
        )
        allowed_slots = {*singleton_slots, _SPOKEN_SLOT}
        generated: list[NarrativeBlock] = []
        for raw_block in raw_blocks:
            if not isinstance(raw_block, dict):
                raise TypeError("block must be an object")
            block_type = self._required_string(raw_block.get("block_type"))
            if block_type != expected_type:
                raise ValueError("writer changed the frozen narrative mode")
            slot = self._required_string(raw_block.get("slot"))
            if slot not in allowed_slots:
                raise ValueError("writer returned an unknown visible slot")
            source_refs = self._string_refs(raw_block.get("source_refs"))
            if any(
                source_ref.startswith("source:user_actuality:")
                for source_ref in source_refs
            ):
                raise ValueError("writer cannot author an actuality block")
            generated.append(
                NarrativeBlock(
                    block_id=self._required_string(raw_block.get("block_id")),
                    block_type=block_type,
                    slot=slot,
                    text=self._required_string(raw_block.get("text")),
                    source_refs=source_refs,
                    scene_ids=self._string_refs(raw_block.get("scene_ids")),
                )
            )
        actual_blocks = tuple(
            NarrativeBlock(
                block_id=f"actuality:{index}",
                block_type="actuality_source",
                slot=_SPOKEN_SLOT,
                text=fact.exact_text,
                source_refs=(fact.source_id,),
                scene_ids=(),
            )
            for index, fact in enumerate(frame.user_facts, start=1)
        )
        provisional = (*actual_blocks, *generated)
        block_ids = [block.block_id for block in provisional]
        if len(set(block_ids)) != len(block_ids):
            raise ValueError("block ids must be unique")
        for slot in singleton_slots:
            if sum(block.slot == slot for block in provisional) != 1:
                raise ValueError(f"slot {slot} must appear exactly once")
        spoken_ids = [
            block.block_id for block in provisional if block.slot == _SPOKEN_SLOT
        ]
        order = [self._required_string(item) for item in raw_order]
        if len(order) != len(spoken_ids) or set(order) != set(spoken_ids):
            raise ValueError("spoken order must cover every spoken block")

        steps: list[SceneStep] = []
        for raw_step in raw_steps:
            if not isinstance(raw_step, dict):
                raise TypeError("scene step must be an object")
            purpose = self._required_string(raw_step.get("purpose"))
            if purpose not in {_COVER_PURPOSE, _SCENE_PURPOSE}:
                raise ValueError("scene purpose is invalid")
            block_refs = self._string_refs(raw_step.get("block_refs"))
            if (
                not block_refs
                or len(block_refs) > 3
                or any(ref not in block_ids for ref in block_refs)
            ):
                raise ValueError("scene must reference existing blocks")
            actor_refs = self._string_refs(
                raw_step.get("actor_refs") or [], allow_empty=True
            )
            resource_refs = self._string_refs(
                raw_step.get("resource_refs") or [], allow_empty=True
            )
            if any(ref not in context.actor_ids for ref in actor_refs):
                raise ValueError("scene uses an unregistered actor")
            if any(ref not in context.resource_ids for ref in resource_refs):
                raise ValueError("scene uses an unregistered resource")
            steps.append(
                SceneStep(
                    step_id=self._required_string(raw_step.get("step_id")),
                    purpose=purpose,
                    actor_refs=actor_refs,
                    resource_refs=resource_refs,
                    action_text=self._required_string(
                        raw_step.get("action_text")
                    ),
                    sound_text=self._optional_string(
                        raw_step.get("sound_text")
                    ),
                    production_note=self._optional_string(
                        raw_step.get("production_note")
                    ),
                    block_refs=block_refs,
                )
            )
        step_ids = [step.step_id for step in steps]
        if (
            len(set(step_ids)) != len(step_ids)
            or set(step_ids) & set(block_ids)
            or sum(step.purpose == _COVER_PURPOSE for step in steps) != 1
            or not any(step.purpose == _SCENE_PURPOSE for step in steps)
        ):
            raise ValueError("scene ids or purposes are incomplete")
        linked = {
            block_id: tuple(
                step.step_id for step in steps if block_id in step.block_refs
            )
            for block_id in block_ids
        }
        if any(not scene_ids for scene_ids in linked.values()):
            raise ValueError("every block must link to at least one scene")
        blocks = tuple(
            replace(block, scene_ids=linked[block.block_id])
            if block.block_type == "actuality_source"
            else block
            for block in provisional
        )
        if any(
            block.block_type != "actuality_source"
            and set(block.scene_ids) != set(linked[block.block_id])
            for block in blocks
        ):
            raise ValueError("block scene links must be complete")
        return NarrativeCore(
            speaker_ref=_SPEAKER_ID,
            blocks=blocks,
            spoken_order=tuple(order),
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
            "你是独立叙事观察器。只从最终可见成品提取观察，不裁决通过，不改写成品，不展示推理。",
            self._reviewer_prompt(request, frame, context, core, body),
            8192,
            thinking_disabled=False,
            timeout_seconds=self._review_timeout_seconds,
        )
        try:
            document = json.loads(
                self._json_content(
                    str(payload["choices"][0]["message"]["content"])
                )
            )
            raw_observations = document["observations"]
            if not isinstance(raw_observations, list):
                raise TypeError
            observations = tuple(
                parse_observation(value) for value in raw_observations
            )
        except (
            KeyError,
            IndexError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            raise GenerationFailed("独立 Reviewer 返回格式不完整") from exc
        scene_text = {
            step.step_id: self._scene_visible_text(step)
            for step in core.scene_steps
        }
        issues = reconcile_observations(
            frame=frame,
            blocks=core.blocks,
            scene_text=scene_text,
            scene_resource_refs={
                step.step_id: step.resource_refs for step in core.scene_steps
            },
            observations=observations,
            allowed_resource_ids=context.resource_ids,
            exact_product_facts=context.exact_product_facts,
        )
        return issues, payload, retries

    def _merge_block_repair(
        self,
        request: GenerationInput,
        frame: NarrativeFrame,
        context: BoundaryContext,
        core: NarrativeCore,
        issues: tuple[NarrativeIssue, ...],
        raw: object,
    ) -> NarrativeCore:
        if not isinstance(raw, dict):
            raise TypeError("repair must be an object")
        affected_blocks, affected_scenes = self._repair_scope(core, issues)
        if any(
            core.block(block_id).block_type == "actuality_source"
            for block_id in affected_blocks
        ):
            raise ValueError("service-authored actuality cannot be repaired")
        raw_blocks = raw.get("blocks")
        raw_scenes = raw.get("scene_steps")
        if not isinstance(raw_blocks, list) or not isinstance(raw_scenes, list):
            raise TypeError("repair collections are incomplete")
        if {
            value.get("block_id")
            for value in raw_blocks
            if isinstance(value, dict)
        } != affected_blocks or {
            value.get("step_id")
            for value in raw_scenes
            if isinstance(value, dict)
        } != affected_scenes:
            raise ValueError("repair scope drifted")
        replacement_blocks = {
            self._required_string(value.get("block_id")): value
            for value in raw_blocks
            if isinstance(value, dict)
        }
        replacement_scenes = {
            self._required_string(value.get("step_id")): value
            for value in raw_scenes
            if isinstance(value, dict)
        }
        merged_raw = {
            "speaker_ref": core.speaker_ref,
            "blocks": [
                replacement_blocks.get(
                    block.block_id, self._block_document(block)
                )
                for block in core.blocks
                if block.block_type != "actuality_source"
            ],
            "spoken_order": list(core.spoken_order),
            "scene_steps": [
                replacement_scenes.get(
                    scene.step_id, self._scene_document(scene)
                )
                for scene in core.scene_steps
            ],
        }
        return self._parse_core(request, frame, context, merged_raw)

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
        actuality_ids = {
            block.block_id
            for block in core.blocks
            if block.block_type == "actuality_source"
        }
        if any(
            issue.reason in nonrepairable_reasons
            or issue.target_id in actuality_ids
            for issue in issues
        ):
            raise GenerationFailed("独立 Reviewer 观察不完整或真人事实块不一致")

    @staticmethod
    def _repair_scope(
        core: NarrativeCore,
        issues: tuple[NarrativeIssue, ...],
    ) -> tuple[set[str], set[str]]:
        block_ids = {
            block.block_id
            for block in core.blocks
            if block.block_type != "actuality_source"
        }
        affected_blocks = {
            issue.target_id for issue in issues if issue.target_id in block_ids
        }
        failed_scenes = {
            issue.target_id
            for issue in issues
            if issue.target_id not in block_ids
        }
        for scene in core.scene_steps:
            if scene.step_id in failed_scenes:
                affected_blocks.update(
                    block_id
                    for block_id in scene.block_refs
                    if block_id in block_ids
                )
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
        slot_text = {
            block.slot: block.text
            for block in core.blocks
            if block.slot != _SPOKEN_SLOT
        }
        title = self._visible_text(slot_text["title"])
        contract = self._contract(request.primary_product, slot_text)
        spoken = self._visible_text(
            "\n\n".join(core.block(block_id).text for block_id in core.spoken_order)
        )
        cover = next(
            step
            for step in core.scene_steps
            if step.purpose == _COVER_PURPOSE
        )
        scenes = tuple(
            step
            for step in core.scene_steps
            if step.purpose == _SCENE_PURPOSE
        )
        sounds = "\n".join(
            text
            for step in core.scene_steps
            for text in (step.sound_text, step.production_note)
            if text
        )
        production: ContentProductionBundle
        if request.media_format == "video":
            fixed_seconds = self._fixed_duration_seconds(
                request.brand.production_conditions
            )
            duration = (
                f"{fixed_seconds} 秒"
                if fixed_seconds is not None
                else f"约 {self._natural_spoken_seconds(spoken)} 秒"
            )
            production = VideoProductionBundle(
                natural_guide=self._visible_text(slot_text["natural_guide"]),
                spoken_lines=spoken,
                visual_actions=self._visible_text(
                    "\n".join(step.action_text for step in scenes)
                ),
                subtitles=spoken,
                sound_and_production=self._visible_text(sounds),
                cover_or_first_frame=self._visible_text(cover.action_text),
                viewing_flow=self._visible_text(slot_text["viewing_flow"]),
                natural_duration=duration,
                release_caption_and_interaction=self._visible_text(
                    slot_text["release_caption"]
                ),
            )
        else:
            image_steps = (cover, *scenes)
            production = GraphicProductionBundle(
                natural_guide=self._visible_text(slot_text["natural_guide"]),
                hero_image=self._visible_text(cover.action_text),
                image_sequence=self._visible_text(
                    "\n".join(
                        ("首图：" if index == 1 else f"第{index}张：")
                        + step.action_text
                        for index, step in enumerate(image_steps, start=1)
                    )
                ),
                full_body=spoken,
                layout_and_production=self._visible_text(
                    "\n".join(
                        step.production_note
                        for step in core.scene_steps
                        if step.production_note
                    )
                ),
                release_caption_and_interaction=self._visible_text(
                    slot_text["release_caption"]
                ),
            )
        return title, contract, production, self._visible_body(
            title, production
        )

    @staticmethod
    def _contract(
        product: ContentProduct,
        slot_text: dict[str, str],
    ) -> ContentSemanticContract:
        values = tuple(
            DeepSeekGenerator._visible_text(slot_text[field])
            for field in _CONTRACT_FIELDS[product]
        )
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
        return "标题：" + title + "\n\n" + "\n\n".join(
            f"{heading}：{value}" for heading, value in sections
        )

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
        history = "\n".join(
            ("用户" if turn.role == "user" else "笛语") + "：" + turn.content
            for turn in request.history[-8:]
        ) or "（无）"
        products = "、".join(product.sku for product in request.products) or "无"
        forced = request.explicit_narrative_mode or "无显式模式"
        return f"""判断本轮是自然交流、只缺一个不可替代事实，还是可直接创作。只返回以下一种 JSON：
{{"kind":"chat","message":"自然回复"}}
{{"kind":"question","message":"一个具体事实问题","missing_fact_span":"逐字复制用户明确要求依赖的真实经历片段"}}
{{"kind":"ready","message":"一句自然承接","user_premises":["逐字复制实际使用的用户消息"],
"user_fact_spans":["逐字截取用户明确陈述的现实片段"],"narrative_mode":
"actuality_reflection|general_observation|hypothesis|dramatization",
"system_creative_plan":"系统自主选择的主题、切口、观点、结构、受众回报和平台组织",
"primary_value":"帮助选择|解释商品|建立人格|经营关系|视觉造型"}}

责任合同：
- 没有成品意图才 chat；不要把普通交流自动变成任务。
- 商品编号加生成请求、开放题材加生成请求、生活流水账／抱怨／感悟加生成请求、以及“没想好
  发什么”的生成请求都直接 ready。系统自己选观点与结构，不追问创作选择。
- 只有用户明确要写某段真人既成经历且缺少会决定真假的不可替代事实，才 question；只问一个。
- 只给题材且没有现实片段用 general_observation；给出真人生活／工作片段用
  actuality_reflection，并把现实片段从用户消息逐字截取，保留标点，不概括；明确条件推演用
  hypothesis；明确要求故事、短剧或情境演绎才用 dramatization。
- 显式模式为 dramatization 时必须使用它；没有明确演绎要求不得升级为剧情。
- general_observation 不创造人物动作、对白、动机、结果、地点、持有物或生活履历。
- actuality_reflection 的计划只能围绕逐字事实形成一般观察，不能扩写事实。
- 商品硬事实只来自当前可用商品；没有资料不猜。
- user_premises 必须包含本轮用户消息且只能逐字复制用户消息；普通聊天不带入。
- system_creative_plan 不是用户、品牌或经营事实，不能预先编造具体事件。

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
    ) -> str:
        singleton = self._singleton_slots(
            request.primary_product, request.media_format
        )
        actual_ids = [
            f"actuality:{index}"
            for index, _ in enumerate(frame.user_facts, start=1)
        ]
        example_order = ["b-spoken", *actual_ids]
        actual_text = "\n".join(
            f"- actuality:{index} = {fact.exact_text}"
            for index, fact in enumerate(frame.user_facts, start=1)
        ) or "（无服务端真人事实块）"
        source_registry = "\n".join(
            f"- {identifier}：{description}"
            for identifier, description in context.source_registry
        )
        resource_registry = "\n".join(
            f"- {identifier}：{description}"
            for identifier, description in context.resource_registry
        )
        mode_rule = {
            "actuality_reflection": (
                "你不能输出、改写或概括 actuality_source；只在 spoken_order 和 scene block_refs "
                "中安排服务端保留块。其余块全为 general_observation，只写独立的一般观察；"
                "不得补人物身份、关系、对白、动机、前因、结果、地点、持有物或习惯。"
            ),
            "general_observation": (
                "全部块为 general_observation。可以有观点、比喻、幽默和节奏；不得写任何具体人物"
                "做了什么、说了什么、为何如此、后来怎样、身在何处或拥有什么。"
            ),
            "hypothesis": (
                "全部块为 hypothesis，最终可见文字自然保留条件和可能性，不能写成已经发生。"
            ),
            "dramatization": (
                "全部块为 dramatization。可以创造角色和情节，但每个独立可见块都要自然显出这是"
                "情境演绎，不能绑定用户、真实员工、顾客、品牌案例或门店现场。"
            ),
        }[frame.narrative_mode]
        prior = request.prior_saved_body or "（首次生成）"
        revision = request.revision_instruction or "（首次生成）"
        expected_type = _MODE_BLOCK_TYPE[frame.narrative_mode]
        return f"""生成一个完整结构化成品。只返回 JSON。
用户原始前提：{request.weak_seed}
系统创作计划：{request.system_creative_plan}
本次修改：{revision}
旧成品（只用于修改对比，不是事实来源）：{prior}
叙事模式：{frame.narrative_mode}
模式合同：{mode_rule}
服务端真人事实块：
{actual_text}

品牌与账号：
{context.brand_text}
方法边界：
{context.method_text}
冻结商品事实（引用商品来源的块必须逐字选择其中一整句，不能改数字、SKU、颜色、材质或含义）：
{context.product_facts_text}
可引用事实来源：
{source_registry}
可用拍摄／制作资源：
{resource_registry}

受众价值：{_PRODUCT_VALUE[request.primary_product]}
平台／形式：{request.brand.platform}／{request.brand.media_format}
平台方向：{request.platform_direction.direction}

输出：
{{"speaker_ref":"{_SPEAKER_ID}",
"blocks":[{{"block_id":"b1","block_type":"{expected_type}","slot":"…","text":"…",
"source_refs":["…"],"scene_ids":["s1"]}}],
"spoken_order":{json.dumps(example_order, ensure_ascii=False)},
"scene_steps":[{{"step_id":"s1","purpose":"cover|scene","actor_refs":[],"resource_refs":["…"],
"action_text":"…","sound_text":"…","production_note":"…","block_refs":["…"]}}]}}

blocks 不得包含 actuality_source，也不得输出 actuality:* 的文本；服务端会逐字插入。generated block
类型必须全部是 {expected_type}。slot 必须恰好有一条：{", ".join(singleton)}，另有至少一条
spoken。spoken_order 必须覆盖全部 spoken 和这些服务端 id：{", ".join(actual_ids) or "无"}。
每个 block 都关联至少一个 scene，scene 的 block_refs 与 block.scene_ids 完整互相对应；每个
scene 最多关联三个 block，保持修复单元有界，不能用一个 scene 吞掉整篇。
source_refs 只能使用登记来源；一般观点／假设／演绎通常引用品牌基线或角色边界，商品事实引用
对应商品来源并逐字使用登记事实。不得引用用户现实来源承载 Writer 新写文字。

scene 恰好一个 cover、至少一个 scene。actor/resource 只用登记 id；现实事实来源永远不是资源。
生活题材和真人事实不得安排家庭成员、家、厨房、门店现场、家具、照片或现场声音重演。可以按
内容需要在创作者表达与本次原创抽象构成中自由组织，不固定手机、手写字卡或普通室内。
所有用户可见标题、导读、正文、口播、字幕、配文、画面、声音和制作提示都只能来自这些 block
与 scene；不要暴露 id、类型、来源、规则或审查说明。"""

    def _reviewer_prompt(
        self,
        request: GenerationInput,
        frame: NarrativeFrame,
        context: BoundaryContext,
        core: NarrativeCore,
        body: str,
    ) -> str:
        targets = [
            {"id": block.block_id, "target_kind": "block", "text": block.text}
            for block in core.blocks
        ] + [
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
            "user_facts": [
                {"source_id": fact.source_id, "exact_text": fact.exact_text}
                for fact in frame.user_facts
            ],
            "allowed_brand_fact_ids": list(frame.allowed_brand_fact_ids),
            "allowed_product_fact_ids": list(
                frame.allowed_product_fact_ids
            ),
        }
        resources = [
            {"id": identifier, "description": description}
            for identifier, description in context.resource_registry
        ]
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

逐项目标：
{json.dumps(targets, ensure_ascii=False)}

对每个 id 恰好返回一份观察，id 和 target_kind 必须原样。text_spans 至少一项，逐字复制该目标
真实存在、足以承载观察的精确跨度；不能抄别的目标。people 提取人物或人物类别，relationships
提取关系，actions_or_events 提取动作／事件，dialogue 提取具体对白，motives 提取动机，
causes/results 提取前因／结果，times/locations/possessions 分别提取时间、地点、持有物。

reality_binding 只选：
- user_actuality：逐字用户真人事实；
- general_observation：不主张具体事件发生的一般观察、观点或比喻；
- hypothesis：可见保留条件／可能性的推演；
- dramatization：可见自然表明是创作演绎；
- confirmed_fact：冻结品牌／组织／商品状态；
- uncertain：无法确定。
一般题材里只要出现具体人物做事、对白、动机、结果、时间地点或持有物，必须如实提取，不能因
语气温和而归为空。演绎只有在目标自身存在自然可见提示时才填 dramatization，并把提示逐字放入
dramatization_disclosure_spans；删掉提示会像现实叙述时不能留空。resource_refs 填该 scene
实际需要的登记资源 id；若需要未登记人物、家、店、厨房、家具、照片、现场声音或道具，填
unregistered:加简短名称。用户事实来源不是资源。instruction_conflicts 逐字列出与用户要求冲突
的目标片段；没有则空。任何语义无法确定时 uncertain=true。

只返回：
{{"observations":[{{"id":"…","target_kind":"block|scene","text_spans":["…"],
"people":[],"relationships":[],"actions_or_events":[],"dialogue":[],"motives":[],
"causes":[],"results":[],"times":[],"locations":[],"possessions":[],
"reality_binding":"…","resource_refs":[],"dramatization_disclosure_spans":[],
"instruction_conflicts":[],"uncertain":false}}]}}"""

    def _repair_prompt(
        self,
        request: GenerationInput,
        frame: NarrativeFrame,
        context: BoundaryContext,
        core: NarrativeCore,
        issues: tuple[NarrativeIssue, ...],
    ) -> str:
        affected_blocks, affected_scenes = self._repair_scope(core, issues)
        if any(
            core.block(block_id).block_type == "actuality_source"
            for block_id in affected_blocks
        ):
            raise GenerationFailed("服务端真人事实块无法修改")
        blocks = [
            self._block_document(block)
            for block in core.blocks
            if block.block_id in affected_blocks
        ]
        scenes = [
            self._scene_document(scene)
            for scene in core.scene_steps
            if scene.step_id in affected_scenes
        ]
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
系统创作计划：{request.system_creative_plan}
品牌边界：{context.brand_text}
冻结商品事实：{context.product_facts_text}
可用资源：{json.dumps(context.resource_registry, ensure_ascii=False)}
问题：{json.dumps(findings, ensure_ascii=False)}
必须完整替换的 blocks：{json.dumps(blocks, ensure_ascii=False)}
必须完整替换的 scenes：{json.dumps(scenes, ensure_ascii=False)}

保持每个 block_id、slot、每个 step_id 和 purpose 不变。block_type 仍为
{_MODE_BLOCK_TYPE[frame.narrative_mode]}。修复后 scene_ids/block_refs 必须完整互相对应。
一般观察出现具体真人事件时，重建整个观察块和关联画面，不把失败句塞到别处；真人原文只由
服务端块承担。资源越界时重建整个相关块与画面，不固定回退手机、字卡或室内。演绎必须在每个
相关块自然可见为演绎。商品硬事实只能逐字使用冻结登记句。

只返回：
{{"blocks":[完整 block 对象],"scene_steps":[完整 scene 对象]}}"""

    @staticmethod
    def _block_document(block: NarrativeBlock) -> dict[str, object]:
        return {
            "block_id": block.block_id,
            "block_type": block.block_type,
            "slot": block.slot,
            "text": block.text,
            "source_refs": list(block.source_refs),
            "scene_ids": list(block.scene_ids),
        }

    @staticmethod
    def _scene_document(scene: SceneStep) -> dict[str, object]:
        return {
            "step_id": scene.step_id,
            "purpose": scene.purpose,
            "actor_refs": list(scene.actor_refs),
            "resource_refs": list(scene.resource_refs),
            "action_text": scene.action_text,
            "sound_text": scene.sound_text,
            "production_note": scene.production_note,
            "block_refs": list(scene.block_refs),
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
        subject = product.display_name or product.sku
        facts = product.facts
        claims: list[str] = [f"商品编号是 {product.sku}。"]
        for key, label in (
            ("category", "品类"),
            ("material_or_structure", "材质或结构"),
            ("material", "材质"),
            ("structure", "结构"),
            ("silhouette", "轮廓"),
            ("observable_features", "可观察特征"),
        ):
            value = facts.get(key)
            if isinstance(value, str) and value.strip():
                claims.append(
                    f"{subject}已登记的{label}是{value.strip().rstrip('。')}。"
                )
        colors = facts.get("colors")
        if isinstance(colors, list) and colors and all(
            isinstance(value, str) for value in colors
        ):
            claims.append(
                f"{subject}已登记的颜色是{'、'.join(cast(list[str], colors))}。"
            )
        for key, label, unit in (
            ("sample_weight_m_grams", "M 码当前样衣重量", "克"),
            (
                "comparison_single_layer_short_coat_m_grams",
                "同季同长度单层短外套 M 码对照样衣重量",
                "克",
            ),
        ):
            value = facts.get(key)
            if isinstance(value, int):
                claims.append(f"{subject}已登记的{label}是 {value} {unit}。")
        for key, yes, no in (
            (
                "both_sides_complete",
                "两面均为完整外观",
                "未登记为两面均为完整外观",
            ),
            (
                "pockets_functional_both_sides",
                "两面口袋均可正常使用",
                "未登记为两面口袋均可正常使用",
            ),
        ):
            value = facts.get(key)
            if isinstance(value, bool):
                claims.append(f"{subject}已登记为{yes if value else no}。")
        boundary = facts.get("weight_boundary")
        if isinstance(boundary, str) and boundary.strip():
            claims.append(
                f"{subject}的重量资料边界是：当前只知道登记样衣的重量差异，"
                "不能据此归因结构或推断性能、价格、库存、用途和穿着结果。"
            )
        return tuple(dict.fromkeys(claims))

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
        with httpx.Client(
            timeout=httpx.Timeout(timeout_seconds or self._timeout_seconds)
        ) as client:
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
                    if (
                        response.status_code != 429
                        and not 500 <= response.status_code < 600
                    ):
                        raise GenerationFailed("模型服务拒绝当前请求")
                    if retries >= self._max_retries:
                        raise GenerationFailed("模型服务暂时不可用")
                    delay = self._retry_delay(
                        response.headers.get("Retry-After"), retries
                    )
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
                            parsedate_to_datetime(retry_after).timestamp()
                            - time.time(),
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
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
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
