from __future__ import annotations

from dataclasses import replace

from src.brain.creation_intent_gate import explicit_intent_span
from src.ports.content_generator import ContentGenerator
from src.shared.creative_kernel import (
    CREATIVE_KERNEL_V5_VERSION,
    DUAL_TRACK_KERNEL_VERSION,
    KERNEL_VERSION,
    MAX_PRODUCT_FACT_BLOCKS,
    MEDIA_NATIVE_KERNEL_VERSION,
    OBSERVATION_ONLY_PROGRAM,
    CreativeKernelV1,
    build_creative_kernel_v5,
    build_kernel_skeleton,
    compiler_owned_unit_texts,
    creative_units_digest,
    freeze_prior_revision_units,
    kernel_digest,
    kernel_document,
    parse_writer_kernel,
    select_kernel_program,
)
from src.shared.creative_plan import (
    ACCOUNT_BASELINE_TONE_ID,
    build_creative_plan,
    platform_shape,
)
from src.shared.delivery_compiler import (
    DELIVERY_COMPILER_V5_VERSION,
    DELIVERY_COMPILER_VERSION,
    DUAL_TRACK_DELIVERY_COMPILER_VERSION,
    MEDIA_NATIVE_DELIVERY_COMPILER_VERSION,
    DeliveryCompileInput,
    compile_delivery,
)
from src.shared.errors import GenerationFailed
from src.shared.factual_basis import (
    FrozenFactRecord,
    brand_fact_records,
    build_product_fact_packet,
    immutable_fact_blocks_document,
    immutable_product_fact_blocks,
    product_fact_packet_document,
    product_fact_records,
    select_product_fact_block_ids,
)
from src.shared.media_program import (
    media_envelope_digest,
    media_envelope_document,
    media_program_digest,
    media_program_document,
)
from src.shared.narrative import legacy_frame, visible_digest
from src.shared.product_value import (
    P2ProductDecisionBasisV2,
    P2ProductValueContractV1,
    P5ProductDecisionBasisV2,
    P5ProductValueContractV1,
    product_value_contract_digest,
    product_value_contract_document,
)
from src.shared.publication_contract import (
    IntakeSpanRole,
    PublicationContractV2,
    PublicationContractV3,
    publication_contract_digest,
    publication_contract_document,
)
from src.shared.types import (
    ContentProduct,
    ContentSemanticContract,
    ConversationDecision,
    ConversationInput,
    GeneratedArtifact,
    GenerationInput,
    GraphicProductionBundle,
    P1SemanticContract,
    P2SemanticContract,
    P3SemanticContract,
    P4SemanticContract,
    P5SemanticContract,
    RoutingInput,
    VideoProductionBundle,
)
from src.shared.writer_request import (
    WriterOutputV3,
    build_writer_request_v3,
    writer_output_digest,
    writer_output_document,
    writer_request_digest,
    writer_request_document,
)


class DeterministicContentGenerator(ContentGenerator):
    """Offline test double for route, contract, scope and version regression only."""

    @property
    def model_name(self) -> str:
        return "deterministic-content-test-stub"

    def route(self, request: RoutingInput) -> ContentProduct | None:
        text = request.weak_seed.casefold()
        if _ordinary_chat(text):
            return None
        if any(value in text for value in ("想先看", "不用解释", "不用先解释", "留点空", "门店回应", "店里这几天")):
            return "local_response"
        if any(value in text for value in ("店长", "自我怀疑", "三位客人", "我会注意")):
            return "brand_life_narrative"
        if any(value in text for value in ("接着这个系列", "系列下一篇", "下一篇内容")):
            return "brand_life_narrative"
        if any(value in text for value in ("单独拍", "单独用", "画面", "视觉重音", "走动里换", "重音")):
            return "visual_styling_story"
        if any(value in text for value in ("一件顶两件", "解释双面", "不要替两面站队", "商品")):
            return "product_truth"
        if any(
            value in text
            for value in (
                "哪面",
                "怎么穿",
                "怎么选",
                "先穿",
                "口袋",
                "上镜",
                "会议",
                "开完",
                "接孩子",
                "下雨",
                "骑车",
                "接着上一条",
                "复用当前",
            )
        ):
            return "dressing_decision"
        return "brand_life_narrative" if "内容" in text or "写一条" in text else None

    def collaborate(self, request: ConversationInput) -> ConversationDecision:
        """Deterministic interaction double; production semantics stay in DeepSeek."""
        text = request.message.strip()
        normalized = text.casefold()
        if _ordinary_chat(normalized):
            return ConversationDecision("chat", "可以。你想随便聊聊，或把一个观察慢慢说清楚，都可以。")
        if "去年创业最困难的那个月" in text:
            return ConversationDecision(
                "question",
                "那个最困难的月里，哪一件真实发生的事最能代表当时的困难？",
                creation_proposal=True,
                proposed_intent_span=text,
            )
        combined = "\n".join([*(turn.content for turn in request.history), text])
        product = self.route(RoutingInput(combined, request.brand, request.products, None)) or "brand_life_narrative"
        roles: tuple[tuple[str, IntakeSpanRole], ...] = tuple(
            (
                candidate.source_id,
                (
                    "creation_instruction"
                    if explicit_intent_span(candidate.exact_text) is not None
                    else "observable_actuality"
                ),
            )
            for candidate in request.user_fact_candidates
        )
        fact_source_ids = tuple(source_id for source_id, role in roles if role == "observable_actuality")
        return ConversationDecision(
            "ready",
            f"好，我按当前选择的{request.brand.platform}{request.brand.media_format}整理。",
            user_premises=(text,),
            narrative_mode=(
                request.explicit_narrative_mode
                or ("actuality_reflection" if fact_source_ids else "general_observation")
            ),
            creative_plan=build_creative_plan(
                topic_spans=(text,),
                primary_value=product,
                tone_ids=(request.allowed_tone_ids or (ACCOUNT_BASELINE_TONE_ID,)),
                mechanism_id=(request.allowed_mechanism_ids[0] if request.allowed_mechanism_ids else None),
                target_shape=(request.platform_shape or platform_shape(request.target, request.brand.media_format)),
            ),
            primary_product=product,
            user_span_roles=roles,
            creation_proposal=True,
            proposed_intent_span=text,
        )

    def generate(self, request: GenerationInput) -> GeneratedArtifact:
        if isinstance(request.publication_contract, PublicationContractV3):
            return self._generate_publication_v3(request)
        if request.delivery_compiler_version in {
            DUAL_TRACK_DELIVERY_COMPILER_VERSION,
            MEDIA_NATIVE_DELIVERY_COMPILER_VERSION,
            DELIVERY_COMPILER_VERSION,
        }:
            return self._generate_kernel(request)
        return self._generate_legacy(request)

    def _generate_publication_v3(
        self,
        request: GenerationInput,
    ) -> GeneratedArtifact:
        contract = request.publication_contract
        if (
            not isinstance(contract, PublicationContractV3)
            or request.delivery_compiler_version != DELIVERY_COMPILER_V5_VERSION
            or request.narrative_frame is None
            or request.media_capability_envelope is None
            or request.media_program is None
        ):
            raise ValueError("deterministic V3 request is incomplete")
        if (
            contract.platform_direction.target != request.target
            or contract.platform_direction.media_format != request.media_format
            or contract.platform_direction.direction_version
            != request.platform_direction.version
            or contract.platform_direction.direction_digest
            != request.platform_direction.direction_digest
        ):
            raise GenerationFailed("Writer 平台责任没有绑定冻结平台方向")
        frame = request.narrative_frame
        facts = (
            *(
                FrozenFactRecord(
                    fact.source_id,
                    fact.exact_text,
                    "user_actuality",
                )
                for fact in frame.user_facts
            ),
            *(
                record
                for product in request.products
                for record in product_fact_records(product)
                if record.fact_id in frame.allowed_product_fact_ids
            ),
            *(
                record
                for record in brand_fact_records(request.brand.brand_reference_context)
                if record.fact_id in frame.allowed_brand_fact_ids
            ),
        )
        product_packet = build_product_fact_packet(
            request.products,
            allowed_fact_ids=frame.allowed_product_fact_ids,
        )
        fact_blocks = immutable_product_fact_blocks(product_packet)
        product_basis = (
            request.product_value_contract
            if isinstance(
                request.product_value_contract,
                (P2ProductDecisionBasisV2, P5ProductDecisionBasisV2),
            )
            else None
        )
        writer_request = build_writer_request_v3(
            contract,
            product_decision_basis=product_basis,
            platform_expression_responsibility=(
                request.platform_direction.direction
            ),
            prior_output=request.prior_writer_output,
            revision_instruction=request.revision_instruction,
        )
        output = self._deterministic_writer_output_v3(request)
        output_digest = writer_output_digest(output)
        supporting_refs = product_basis.supporting_fact_refs if product_basis is not None else ()
        selected_blocks = tuple(block for block in fact_blocks if block.fact_id in supporting_refs)
        selected_refs = tuple(
            dict.fromkeys(
                (
                    *(
                        ref
                        for ref in contract.frozen_fact_refs
                        if ref.startswith("source:user_actuality:") or ref.startswith("brand:")
                    ),
                    *supporting_refs,
                )
            )
        )
        kernel = build_creative_kernel_v5(
            writer_output_digest=output_digest,
            trusted_fact_refs=selected_refs,
            selected_fact_blocks=selected_blocks,
            media_program_id=request.media_program.program_id,
            media_unit_bindings=request.media_program.unit_bindings,
        )
        delivery_input = DeliveryCompileInput(
            primary_product=request.primary_product,
            media_format=request.media_format,
            products=request.products,
            production_conditions=request.brand.production_conditions,
            allowed_resource_ids=request.media_capability_envelope.resource_ids,
            immutable_fact_blocks=fact_blocks,
            trusted_fact_texts=tuple((fact.fact_id, fact.exact_text) for fact in facts),
            media_capability_envelope=request.media_capability_envelope,
            media_program=request.media_program,
            product_value_contract=product_basis,
            publication_contract=contract,
            writer_output=output,
        )
        compiled = compile_delivery(delivery_input, kernel)
        checked_digest = kernel_digest(kernel)
        return GeneratedArtifact(
            outline=compiled.outline,
            body=compiled.body,
            model=self.model_name,
            latency_ms=0,
            retry_count=0,
            provider_usage=None,
            primary_product=request.primary_product,
            semantic_contract=compiled.semantic_contract,
            production=compiled.production,
            reviewed_digest=visible_digest(compiled.outline, compiled.body),
            completion_snapshot_patch={
                "creative_kernel_v5": kernel_document(kernel),
                "writer_request_v3": writer_request_document(writer_request),
                "writer_request_v3_digest": writer_request_digest(writer_request),
                "writer_output_v3": writer_output_document(output),
                "writer_output_v3_digest": output_digest,
                "expression_plan_version": CREATIVE_KERNEL_V5_VERSION,
                "expression_plan_digest": checked_digest,
                "delivery_compiler_version": DELIVERY_COMPILER_V5_VERSION,
                "writer_model": self.model_name,
                "version_authorization": "deterministic-publication-v3",
                "claim_inventory_v1": [],
                "deterministic_checked_kernel_digest": checked_digest,
                "reviewed_creative_digest": output_digest,
                "product_fact_packet": product_fact_packet_document(product_packet),
                "immutable_product_fact_blocks": (immutable_fact_blocks_document(selected_blocks)),
                "used_product_fact_ids": [block.fact_id for block in selected_blocks],
                "used_product_fact_block_ids": [block.fact_block_id for block in selected_blocks],
                "product_fact_renderer_version": (selected_blocks[0].renderer_version if selected_blocks else None),
                "visible_provenance": {field: list(sources) for field, sources in compiled.visible_provenance.items()},
                "delivery_resource_refs": list(compiled.resource_refs),
                "media_capability_envelope": media_envelope_document(request.media_capability_envelope),
                "media_capability_envelope_digest": media_envelope_digest(request.media_capability_envelope),
                "media_program": media_program_document(request.media_program),
                "media_program_digest": media_program_digest(request.media_program),
                "product_value_contract": (
                    product_value_contract_document(product_basis) if product_basis is not None else None
                ),
                "product_value_contract_digest": (
                    product_value_contract_digest(product_basis) if product_basis is not None else None
                ),
                "publication_contract": publication_contract_document(contract),
                "publication_contract_digest": publication_contract_digest(contract),
            },
        )

    @staticmethod
    def _deterministic_writer_output_v3(
        request: GenerationInput,
    ) -> WriterOutputV3:
        body_by_product = {
            "dressing_decision": (
                "先用可以独立成立的内层打底，再加一层随时能脱下的外层。"
                "这样会多一个穿脱动作，却保留了在条件变化时调整的余地；出门前确认每一层单独使用也合适。"
            ),
            "product_truth": (
                "把已确认的差异放回这一次选择：你真正需要哪一种可见重点，决定了取舍。"
                "只有当这种差异正好回应眼前目标时，它才值得成为选择理由。"
            ),
            "brand_life_narrative": (
                "值得说的往往不是给生活补一个解释，而是把眼前那点具体张力看清。"
                "留住这个分寸，内容才不会替别人把答案说完。"
            ),
            "local_response": (
                "先给对方保留自己看一看的空间，再在对方需要时提供清楚帮助。"
                "主动与克制之间的取舍，决定了这次回应是否真正尊重选择。"
            ),
            "visual_styling_story": ("让主视觉先建立重心，辅助视觉随后回应；两者的先后与面积共同形成明确关系。"),
        }
        return WriterOutputV3(
            output_version="writer-output-v3",
            title=_media_native_title(request.primary_product),
            natural_guide="这一篇把一个具体判断完整说清楚。",
            creative_body=(
                body_by_product[request.primary_product]
                + ("\n\n这次把表达调整得更贴近你的修改，原来的判断仍然清楚。" if request.revision_instruction else "")
            ),
            publication_caption="先看清这次真正需要保留的重点，再决定怎样行动。",
        )

    def _generate_kernel(
        self,
        request: GenerationInput,
    ) -> GeneratedArtifact:
        frame = request.narrative_frame or legacy_frame(
            tuple(record.fact_id for product in request.products for record in product_fact_records(product))
        )
        facts = (
            *(
                FrozenFactRecord(
                    fact.source_id,
                    fact.exact_text,
                    "user_actuality",
                )
                for fact in frame.user_facts
            ),
            *(
                record
                for product in request.products
                for record in product_fact_records(product)
                if record.fact_id in frame.allowed_product_fact_ids
            ),
        )
        if request.delivery_compiler_version == DUAL_TRACK_DELIVERY_COMPILER_VERSION:
            kernel_version = DUAL_TRACK_KERNEL_VERSION
        elif request.delivery_compiler_version == MEDIA_NATIVE_DELIVERY_COMPILER_VERSION:
            kernel_version = MEDIA_NATIVE_KERNEL_VERSION
        else:
            kernel_version = KERNEL_VERSION
        allowed_resources = (
            request.media_capability_envelope.resource_ids
            if request.media_capability_envelope is not None
            else frozenset(
                {
                    "resource:original_composition",
                    "resource:creator_expression",
                    *(f"resource:product:{product.sku}" for product in request.products),
                }
            )
        )
        publication_v2 = isinstance(
            request.publication_contract,
            PublicationContractV2,
        )
        prior_kernel = (
            request.prior_creative_kernel if isinstance(request.prior_creative_kernel, CreativeKernelV1) else None
        )
        legacy_product_contract = (
            request.product_value_contract
            if isinstance(
                request.product_value_contract,
                (P2ProductValueContractV1, P5ProductValueContractV1),
            )
            else None
        )
        skeleton = build_kernel_skeleton(
            frame=frame,
            fact_registry=facts,
            constraint_refs=("constraint:deterministic-test-stub",),
            program_id=(
                prior_kernel.program_id
                if publication_v2 and prior_kernel is not None
                else OBSERVATION_ONLY_PROGRAM
                if publication_v2
                else select_kernel_program(
                    frame=frame,
                    prior_kernel=prior_kernel,
                    revision_instruction=request.revision_instruction,
                )
            ),
            allowed_resource_ids=tuple(sorted(allowed_resources)),
            media_format=request.media_format,
            kernel_version=kernel_version,
            primary_product=request.primary_product,
            product_value_contract=(None if publication_v2 else legacy_product_contract),
        )
        skeleton = freeze_prior_revision_units(
            skeleton,
            prior_kernel,
        )
        _, guide, spoken, _, subtitles, _ = self._parts(request)
        if kernel_version == DUAL_TRACK_KERNEL_VERSION:
            spoken = spoken + "\n\n" + subtitles + _control_sections(request)
            if request.revision_instruction:
                spoken += "\n\n这次按你的修改要求改变了允许调整的表达。"
            release_caption = subtitles + _control_sections(request)
            title = _outline(request.primary_product)
        else:
            if request.primary_product == "dressing_decision":
                guide = _deterministic_p1_writer_guide(request, guide)
            if request.primary_product == "visual_styling_story" and any(
                phrase in request.weak_seed for phrase in ("无口播", "无对白", "无解说", "不讲")
            ):
                spoken = "无口播、无对白、无解说；由已登记商品画面、动作关系和字幕承担内容。"
            direction = (
                "、".join(selection.applied_label for selection in request.creative_direction.selections)
                if request.creative_direction is not None
                else ""
            )
            custom = request.creative_direction.custom_text if request.creative_direction is not None else ""
            series_bridge = ""
            if request.series_context and request.series_context.prior_entries:
                previous = request.series_context.prior_entries[-1]
                series_bridge = (
                    f"\n\n承接上一篇《{previous.outline}》留下的问题，"
                    f"这一篇把观察推进到第 {request.series_context.target_position} 篇。"
                )
            control_bridge = (
                "\n\n本次表达会采用" + "、".join(value for value in (direction, custom) if value) + "。"
                if direction or custom
                else ""
            )
            account_bridge = (
                "\n\n这次从这个账号一贯的表达位置展开：" + request.account_expression.identity_position
                if request.account_expression is not None
                else ""
            )
            material_bridge = (
                "\n\n本次只参考已明确选择的" + "、".join(item.title for item in request.reference_materials) + "。"
                if request.reference_materials
                else ""
            )
            spoken = spoken + series_bridge + control_bridge + account_bridge + material_bridge
            if request.revision_instruction:
                spoken += "\n\n这次按你的修改要求改变了允许调整的表达。"
            release_caption = subtitles.splitlines()[0].strip() + ("；接着上篇继续。" if series_bridge else "")
            title = _media_native_title(request.primary_product)
        product_packet = build_product_fact_packet(
            request.products,
            allowed_fact_ids=frame.allowed_product_fact_ids,
        )
        fact_blocks = immutable_product_fact_blocks(product_packet)
        required_fact_block_ids: tuple[str, ...] | None = None
        if prior_kernel is not None:
            required_fact_block_ids = prior_kernel.selected_fact_block_ids or tuple(
                block.fact_block_id
                for block in fact_blocks
                if any(
                    unit.purpose == "frozen_fact" and unit.fact_refs == (block.fact_id,) for unit in prior_kernel.units
                )
            )
        selected_fact_block_ids = required_fact_block_ids or select_product_fact_block_ids(
            product_packet,
            limit=MAX_PRODUCT_FACT_BLOCKS,
        )
        if fact_blocks:
            skeleton = replace(
                skeleton,
                selected_fact_block_ids=selected_fact_block_ids,
            )
        delivery_input = DeliveryCompileInput(
            primary_product=request.primary_product,
            media_format=request.media_format,
            products=request.products,
            production_conditions=request.brand.production_conditions,
            allowed_resource_ids=allowed_resources,
            immutable_fact_blocks=fact_blocks,
            trusted_fact_texts=tuple((fact.fact_id, fact.exact_text) for fact in facts),
            media_capability_envelope=request.media_capability_envelope,
            media_program=request.media_program,
            product_value_contract=request.product_value_contract,
            publication_contract=request.publication_contract,
        )
        compiler_texts = (
            compiler_owned_unit_texts(request.primary_product) if kernel_version == DUAL_TRACK_KERNEL_VERSION else {}
        )
        text_by_id = {
            "unit:title": title,
            "unit:natural-guide": guide,
            "unit:media-opening": (
                "首图用一句具体矛盾作视觉入口。"
                if request.media_format == "graphic"
                else "开头两秒由创作者直接抛出本篇核心反差。"
            ),
            "unit:media-sequence": (
                (
                    "只补拍四张：第 1 张给出入口；第 2、3 张推进判断；第 4 张收束到可执行选择。"
                    if "四张" in request.brand.production_conditions
                    else "第 1 张给出入口；第 2、3 张推进判断；末张收束到可执行选择。"
                )
                if request.media_format == "graphic"
                else "先抛出反差，再拆开判断，最后回到一个可执行选择。"
            ),
            "unit:subtitle-strategy": "只标出转折句和最终选择，不重复整段台词。",
            "unit:production-note": ("使用当前登记的创作者、手机和普通室内条件完成；声音保持自然。"),
            "unit:body": spoken,
            "unit:body-opening": spoken,
            "unit:hypothetical-example": ("一方先停一下，另一方也不必马上给出答案。"),
            "unit:body-closing": "理解可以靠近，边界也仍然成立。",
            "unit:local-dramatization": ("两台只会夸张播报情绪的家务机器人，为一只碗举行了一场毫无胜负的辩论赛。"),
            "unit:release-caption": release_caption,
        }
        raw: dict[str, object] = {
            "units": [
                {
                    "unit_id": unit.unit_id,
                    "text": text_by_id[unit.unit_id],
                }
                for unit in skeleton.writable_units
            ]
        }
        kernel = parse_writer_kernel(
            raw,
            skeleton,
            fact_blocks=fact_blocks,
            allowed_claim_ids=product_packet.fact_ids,
            required_fact_block_ids=required_fact_block_ids,
            compiler_owned_text_by_id=compiler_texts,
            media_format=request.media_format,
        )
        compiled = compile_delivery(
            delivery_input,
            kernel,
        )
        selected_blocks = tuple(
            block
            for block_id in kernel.selected_fact_block_ids
            for block in fact_blocks
            if block.fact_block_id == block_id
        )
        return GeneratedArtifact(
            outline=compiled.outline,
            body=compiled.body,
            model=self.model_name,
            latency_ms=0,
            retry_count=0,
            provider_usage=None,
            primary_product=request.primary_product,
            semantic_contract=compiled.semantic_contract,
            production=compiled.production,
            reviewed_digest=visible_digest(compiled.outline, compiled.body),
            completion_snapshot_patch={
                "creative_kernel_v2": kernel_document(kernel),
                "expression_plan_version": "expression-plan-v1",
                "expression_plan_digest": kernel_digest(kernel),
                "delivery_compiler_version": request.delivery_compiler_version,
                "writer_model": self.model_name,
                "version_authorization": "deterministic-dual-track-v1",
                "claim_inventory_v1": [],
                "reviewed_kernel_digest": kernel_digest(kernel),
                "reviewed_creative_digest": creative_units_digest(kernel),
                "product_fact_packet": product_fact_packet_document(product_packet),
                "immutable_product_fact_blocks": (immutable_fact_blocks_document(selected_blocks)),
                "used_product_fact_ids": [block.fact_id for block in selected_blocks],
                "used_product_fact_block_ids": list(kernel.selected_fact_block_ids),
                "product_fact_renderer_version": (fact_blocks[0].renderer_version if fact_blocks else None),
                "visible_provenance": {field: list(sources) for field, sources in compiled.visible_provenance.items()},
                "delivery_resource_refs": list(compiled.resource_refs),
                "media_capability_envelope": (
                    media_envelope_document(request.media_capability_envelope)
                    if request.media_capability_envelope is not None
                    else None
                ),
                "media_capability_envelope_digest": (
                    media_envelope_digest(request.media_capability_envelope)
                    if request.media_capability_envelope is not None
                    else None
                ),
                "media_program": (
                    media_program_document(request.media_program) if request.media_program is not None else None
                ),
                "media_program_digest": (
                    media_program_digest(request.media_program) if request.media_program is not None else None
                ),
                "product_value_contract": (
                    product_value_contract_document(request.product_value_contract)
                    if request.product_value_contract is not None
                    else None
                ),
                "product_value_contract_digest": (
                    product_value_contract_digest(request.product_value_contract)
                    if request.product_value_contract is not None
                    else None
                ),
                "publication_contract": (
                    publication_contract_document(request.publication_contract)
                    if request.publication_contract is not None
                    else None
                ),
                "publication_contract_digest": (
                    publication_contract_digest(request.publication_contract)
                    if request.publication_contract is not None
                    else None
                ),
            },
        )

    def _generate_legacy(self, request: GenerationInput) -> GeneratedArtifact:
        contract, guide, spoken, visuals, subtitles, sound = self._parts(request)
        production = self._production(request, contract, guide, spoken, visuals, subtitles, sound)
        revision = "\n\n这次只按你的自然修改更新了同一任务的表达。" if request.revision_instruction else ""
        prior = "\n\n已承接当前合法作用域内明确授权的前情。" if request.prior_saved_body else ""
        core = "\n\n内容核心：" + " ".join(str(value) for value in vars(contract).values())
        body = (
            _visible_body(_outline(request.primary_product), production)
            + core
            + prior
            + revision
            + _control_sections(request)
        )
        outline = _outline(request.primary_product)
        return GeneratedArtifact(
            outline=outline,
            body=body,
            model=self.model_name,
            latency_ms=0,
            retry_count=0,
            provider_usage=None,
            primary_product=request.primary_product,
            semantic_contract=contract,
            production=production,
            reviewed_digest=visible_digest(outline, body),
        )

    @staticmethod
    def _production(
        request: GenerationInput,
        contract: ContentSemanticContract,
        guide: str,
        spoken: str,
        visuals: str,
        subtitles: str,
        sound: str,
    ) -> VideoProductionBundle | GraphicProductionBundle:
        if request.media_format == "graphic":
            four_images = "四张" in request.brand.production_conditions
            return GraphicProductionBundle(
                natural_guide=guide,
                hero_image="首图拍摄安排：用当前商品和本篇最关键的可见关系作出标题承诺，不使用视频截图。",
                image_sequence=(
                    "只补拍四张：第 1 张给出首图承诺；第 2 张让关键商品或关系完整可见；"
                    "第 3 张补足必要比较或动作；第 4 张完成本篇判断。每张只承担这一项职责。"
                    if four_images
                    else "第 1 张给出首图承诺；第 2 张让关键商品或关系完整可见；"
                    "第 3 张补足必要比较或动作；最后一张完成本篇判断。每张只承担这一项职责。"
                ),
                full_body="\n".join(str(value) for value in vars(contract).values()),
                layout_and_production="按当前一人一手机条件补拍或选图；不把视频帧、台词卡或长文切片当作图片序列。",
                release_caption_and_interaction="正文已经完成当前判断；不需要额外互动时自然结束。",
            )
        silent = request.primary_product == "visual_styling_story" and any(
            phrase in request.weak_seed for phrase in ("无口播", "无对白", "无解说", "不讲")
        )
        return VideoProductionBundle(
            natural_guide=guide,
            spoken_lines="无口播、无对白、无解说；由画面和同期声承担内容。" if silent else spoken,
            visual_actions=visuals,
            subtitles=subtitles,
            sound_and_production=sound,
            cover_or_first_frame="封面/首帧拍摄安排：第一眼就让当前商品关系或判断进入画面。",
            viewing_flow="从当前入口开始，依次完成事实、动作或判断，并在主价值成立处自然收束。",
            natural_duration=(
                "8 秒窄主题版：只保留仍能独立成立的一项命题，不称与原完整版本等义。"
                if "8 秒" in request.brand.production_conditions
                else "以把当前主要价值与必要边界说清为准，不套固定秒数。"
            ),
            release_caption_and_interaction="发布配文复述当前完整结论；不适用互动时自然结束。",
        )

    @staticmethod
    def _parts(
        request: GenerationInput,
    ) -> tuple[ContentSemanticContract, str, str, str, str, str]:
        product = request.primary_product
        zx_c218 = _product_facts(request, "ZX-C218")
        colors = _colors(zx_c218)
        color_pair = f"{colors[0]}和{colors[1]}" if len(colors) >= 2 else "这件外套的两面"
        weight = str(zx_c218.get("sample_weight_m_grams", "当前"))
        comparison_weight = str(zx_c218.get("comparison_single_layer_short_coat_m_grams", "对照"))
        if product == "product_truth":
            return (
                P2SemanticContract(
                    f"双面不等于一件顶两件：{color_pair}都是完整外观、两面的口袋也都可正常使用，但它仍是一件外套。",
                    f"M 码当前样衣约 {weight} 克，比同季同长度单层短外套 M 码样衣约 {comparison_weight} 克更重；不能把全部差异简单归因于双面结构。",
                    "这只说明当前样衣存在重量差异，不推断价格、面料性能、普遍上身结果或设计动机。",
                ),
                "从一件真实样衣的两面与重量差异出发，把能确认和不能下结论的部分说清楚。",
                f"别把双面说成两件。{color_pair}都能独立出现，口袋两面都能用；M 码样衣约 {weight} 克，同季同长度单层短外套 M 码样衣约 {comparison_weight} 克。它给的是一次翻面后的不同视觉，不是多买到一件外套。",
                "同一人先穿炭灰走过镜头，再在转身时翻到深绿细格纹；最后把样衣放在秤旁，但不把数字夸成性能结论。",
                "双面，不等于两件。\n能确认的，和还不能下结论的，都留在镜头里。",
                "一人一手机，保留翻面摩擦和脚步声；不补拍价格牌、库存或未经提供的材质细节。",
            )
        if product == "brand_life_narrative":
            if request.brand.brand_name != "折线之间":
                return (
                    P3SemanticContract(
                        f"{request.brand.account_name}从当前已确认的品牌表达出发，"
                        "选择尊重每个人自己的生活节奏，不替具体家庭编造经历。",
                        "受众得到的是一种可带回日常的许可：一家人可以彼此呼应，也可以各自成立。",
                        f"这由“{request.brand.content_role_name}”在已确认品牌边界内表达，"
                        "不冒充创始人、研发、门店、顾客或具体家庭。",
                    ),
                    "从已经确认的品牌关系观出发，讲清一家人不必穿成同一个答案。",
                    "一家人站在一起，不一定要穿成一套。有人喜欢安静一点，有人愿意多一点颜色；"
                    "彼此看得见，也各自舒服，就已经是一种自然的呼应。我们只说当前确认过的品牌立场，"
                    "不替任何一个真实家庭补写经历。",
                    "一人一手机，用不同衣架或空白色卡表示几种独立选择；不出现具体商品、价格、库存、"
                    "顾客或门店画面，也不把概念冒充已实拍。",
                    "一家人，可以自然呼应。\n也可以，各自成立。",
                    "使用普通室内环境与轻微生活声；不制造儿童、身体、年龄或家庭焦虑。",
                )
            return (
                P3SemanticContract(
                    "南城店店长会把“我先看看”当成需要被尊重的停顿，而不是必须立刻解决的犹豫。",
                    "受众能看见这家店怎样克制地观察和待人，而不是被要求接受一个标准答案。",
                    "这来自南城店店长/门店经营者的合法观察位置，不冒充顾客经历或总部政策。",
                ),
                "从门店里三个相似的停顿，讲清账号愿意怎样把空间留给人。",
                "今天有三位客人都说：我先看看。店长没有急着把这句话接成成交话术，只把那件 ZX-C218 挂回原位，等对方自己走近。她也会怀疑自己是不是太克制，但还是愿意把选择留在顾客手里。",
                "一人手机拍店长整理炭灰面和深绿细格纹的两次停顿；不拍顾客正脸，不复述任何个人识别信息。",
                "“我先看看”，可以只是看看。\n把空间留出来，也是一种服务。",
                "门店环境声即可；这是账号的生活观察，不是店内巡检、承诺或全国服务政策。",
            )
        if product == "local_response":
            return (
                P4SemanticContract(
                    "南城店里重复出现的“我先看看”是一次近场服务信号，不被解释成顾客的单一原因。",
                    "南城店账号的回应是：想先看就先看，不用解释。",
                    "未到店的人也能带走一种关系许可：可以按自己的节奏靠近一件衣服。",
                ),
                "从南城店已知的近场信号出发，给未到店的人一句可迁移的关系回应。",
                "如果你走进南城店，只想先看看，也完全可以。我们不替你猜今天为什么犹豫，也不催你给理由；衣服先在这里，等你按自己的节奏靠近。",
                "拍一只手把 ZX-C218 的炭灰面和深绿细格纹依次留在同一根挂杆上，再留出一段空镜。",
                "想先看就先看，不用解释。",
                "一人一手机、普通门店空间；不把这句话扩展成交易承诺、顾客画像或全国政策。",
            )
        if product == "visual_styling_story":
            return (
                P5SemanticContract(
                    f"ZX-C218 双面短外套：{color_pair}两面均为完整外观，口袋两面可用。",
                    f"同一个人、同一个走动动作里，翻面让画面从安静的{colors[0] if colors else '第一面'}重音转向更有纹理的{colors[1] if len(colors) > 1 else '另一面'}重音。",
                    "拿掉翻面、走动和两面在画面中的前后关系，这条内容不再成立为可见的造型命题。",
                ),
                "以 ZX-C218 的真实双面为锚，让同一动作改变画面的视觉重音。",
                f"人不用换。先用{colors[0] if colors else '第一面'}从门口走向镜头，走到最近处时抬手翻面；同一步继续向前，{colors[1] if len(colors) > 1 else '另一面'}接住原来的动作。不是两套造型，也不是资料朗读，是同一个人把重音换了一下。",
                f"固定机位拍连续走动：{colors[0] if colors else '第一面'}进入、手部翻面、{colors[1] if len(colors) > 1 else '另一面'}离开。两面口袋都留一个短镜头，不增加未经提供的搭配或功能主张。",
                f"人没换，画面换了重音。\n{colors[0] if colors else '第一面'}停一下，{colors[1] if len(colors) > 1 else '另一面'}再往前一步。",
                "一人一部手机、普通门店空间；保留脚步声，音乐只做轻节拍，不把概念冒充已实拍或门店陈列执行。",
            )
        if any(word in request.weak_seed for word in ("雨", "骑车", "湿")):
            choice = "把移动中的安全、耐受和到达后的可整理性放在造型完整度之前。"
            boundary = "若当天并不需要长时间移动，或已有可靠的防护与替换条件，这个排序可以改变。"
            action = "出门前做一次抬腿、转身和收纳物品的动作试验，再决定是否减少容易受潮或牵扯的部分。"
        else:
            choice = "保住已经为正式场合完成的分寸，再检查它是否允许自然移动和切换。"
            boundary = "若后一段确实需要大量活动，或一处衣物让人持续分心，就应优先调整那一处。"
            action = "在进入下一段安排前走几步、弯腰拿东西、换手拎物，观察是否还需要反复整理。"
        return (
            P1SemanticContract(choice, boundary, action),
            "从当前真实情境出发，先给出条件性选择，再留出可以改变判断的边界。",
            f"同一身衣服不必为不同场合重新证明两次自己。{choice}{boundary}{action}",
            "先拍连续走动和弯腰拿东西的自然测试，再拍一处需要调整或保留的细节。",
            "先保住分寸。\n走几步，再决定要不要改。",
            "一人一部手机，环境声和脚步声即可；不补造商品事实或顾客身份。",
        )


def _control_sections(request: GenerationInput) -> str:
    """Make the user's own control choices observable in the offline artifact."""
    parts: list[str] = []
    direction = request.creative_direction
    if direction is not None:
        if direction.selections:
            parts.append("\n\n本次创作方向：" + "、".join(item.applied_label for item in direction.selections))
        if direction.custom_text:
            parts.append("\n\n本次自然补充：" + direction.custom_text)
    if request.account_expression is not None:
        # The account's own words may appear; its internal version number is a receipt field.
        parts.append("\n\n当前账号表达位置：" + request.account_expression.identity_position)
    if request.reference_materials:
        parts.append("\n\n本次参考：" + "、".join(item.title for item in request.reference_materials))
    return "".join(parts)


def _deterministic_p1_writer_guide(
    request: GenerationInput,
    base_guide: str,
) -> str:
    """Project test inputs through the P1 Writer-owned, non-bearing guide.

    The real P1 choice, boundary, action and release caption remain owned by the
    server-bearing contract.  This offline double only makes frozen controls and
    a de-identified input emphasis observable to API and history regressions.
    """
    if any(word in request.weak_seed for word in ("雨", "骑车", "湿")):
        input_emphasis = "本次先观察移动和天气条件，再决定哪些部分需要调整。"
    else:
        input_emphasis = "本次先观察场合切换和实际动作，再决定哪些部分需要调整。"

    parts = [base_guide, input_emphasis]
    direction = request.creative_direction
    if direction is not None:
        applied = "、".join(selection.applied_label for selection in direction.selections)
        controls = "、".join(value for value in (applied, direction.custom_text) if value)
        if controls:
            parts.append("本次表达会采用" + controls + "。")
    if request.account_expression is not None:
        parts.append("这次从这个账号一贯的表达位置展开：" + request.account_expression.identity_position)
    if request.reference_materials:
        parts.append("本次只参考已明确选择的" + "、".join(item.title for item in request.reference_materials) + "。")
    if request.revision_instruction:
        parts.append("这次修改只调整非承重表达，原选择依据和边界保持不变。")
    return "\n\n".join(parts)


def _ordinary_chat(text: str) -> bool:
    return any(value in text for value in ("hello", "你好", "有点困", "挺安静", "谢谢")) and not any(
        value in text for value in ("写", "内容", "双面", "外套", "穿", "商品", "拍")
    )


def _outline(product: ContentProduct) -> str:
    return {
        "dressing_decision": "帮助受众完成一个带边界的穿衣选择。",
        "product_truth": "解释一项真实商品理解及其当前边界。",
        "brand_life_narrative": "让受众认识账号怎样观察、判断和待人。",
        "local_response": "从南城店近场信号给出可迁移的关系回应。",
        "visual_styling_story": "让真实商品在画面关系中形成新的穿着可能。",
    }[product]


def _media_native_title(product: ContentProduct) -> str:
    """Natural titles for the offline double; production Writer remains model-owned."""
    return {
        "dressing_decision": "一身衣服，先过真实的一天",
        "product_truth": "双面之外，先把能确认的说清",
        "brand_life_narrative": "不急着替别人回答",
        "local_response": "想自己看看，也可以",
        "visual_styling_story": "人没换，画面的重音换了",
    }[product]


def _product_facts(request: GenerationInput, sku: str) -> dict[str, object]:
    return next((product.facts for product in request.products if product.sku == sku), {})


def _colors(facts: dict[str, object]) -> tuple[str, ...]:
    raw = facts.get("colors")
    return tuple(str(value) for value in raw) if isinstance(raw, list) else ()


def _visible_body(title: str, production: VideoProductionBundle | GraphicProductionBundle) -> str:
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


DeterministicP1Generator = DeterministicContentGenerator
