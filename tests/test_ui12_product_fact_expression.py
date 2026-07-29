from __future__ import annotations

from dataclasses import replace

import pytest

from src.shared.closed_review import (
    CLOSED_REVIEW_VERSION,
    PRODUCT_REVIEW_DIMENSIONS,
    build_closed_review_questions,
    parse_closed_review_answers,
    reconcile_closed_review_answers,
)
from src.shared.creative_kernel import (
    CreativeKernelV1,
    build_kernel_skeleton,
    parse_writer_kernel,
)
from src.shared.delivery_compiler import (
    ORIGINAL_COMPOSITION_RESOURCE_ID,
    DeliveryCompileInput,
    compile_delivery,
)
from src.shared.errors import GenerationFailed
from src.shared.factual_basis import (
    ProductFactPacket,
    build_product_fact_packet,
    immutable_product_fact_blocks,
    product_fact_records,
)
from src.shared.narrative import new_frame
from src.shared.review_evidence import (
    ClauseContextV2,
    ProtectedSubjectScopeV2,
    build_clause_contexts_v2,
)
from src.shared.types import GraphicProductionBundle, ProductFact

_SCOPE = ProtectedSubjectScopeV2(
    exact_names=("笛语",),
    speaker_kind="institutional_account",
)
# Sanitized exact excerpts from the preserved G2 Writer calls.  The root-only
# originals remain outside Git (provider-call-02 sha256 cb1b203f..., repaired
# provider-call-05 sha256 39a31714...).  These are negative claims, not a
# product- or sentence-specific runtime rule.
_HISTORICAL_G2_PRODUCT_GUESSES = (
    (
        "但它不能确认的是个体使用体验的差异，比如实际耗电量是否与标称一致、长期耐用性如何，或者是否适合特定场景。",
        "product_use_or_wear_result",
        "use_result",
    ),
    (
        "兼容性需结合具体设备测试，不能仅凭参数表断言，接口标准匹配或软件驱动支持可能存在未列明的限制。",
        "product_performance_or_efficacy",
        "performance",
    ),
)


def _product() -> ProductFact:
    return ProductFact(
        sku="ZX-C218",
        display_name="双面短外套",
        facts={
            "category": "double-faced short coat",
            "colors": ["炭灰纯色", "深绿细格纹"],
            "both_sides_complete": True,
            "sample_weight_m_grams": 960,
            "weight_boundary": ("only the current sample weight difference is known"),
        },
        source_kind="verified_product_record",
        source_note="当前租户商品资料",
        fact_version=3,
        applicability="current_product",
    )


def _product_contract() -> tuple[
    ProductFact,
    ProductFactPacket,
    CreativeKernelV1,
]:
    product = _product()
    records = product_fact_records(product)
    frame = new_frame(
        "general_observation",
        (),
        tuple(record.fact_id for record in records),
    )
    skeleton = build_kernel_skeleton(
        frame=frame,
        fact_registry=records,
        constraint_refs=("constraint:account-tone",),
    )
    packet = build_product_fact_packet(
        (product,),
        allowed_fact_ids=frame.allowed_product_fact_ids,
    )
    return product, packet, skeleton


def _parsed_product_kernel(
    *,
    block_ids: tuple[str, ...] | None = None,
    claim_refs: tuple[str, ...] = (),
    required_block_ids: tuple[str, ...] | None = None,
) -> tuple[CreativeKernelV1, ProductFactPacket]:
    _, packet, skeleton = _product_contract()
    blocks = immutable_product_fact_blocks(packet)
    selected = block_ids or tuple(
        block.fact_block_id
        for block in blocks
        if next(item.fact_key for item in packet.facts if item.fact_id == block.fact_id) in {"display_name", "category"}
    )
    raw = {
        "fact_block_refs": list(selected),
        "units": [
            {
                "unit_id": unit.unit_id,
                "text": {
                    "title": "先看差异，再决定怎样理解",
                    "natural_guide": "这篇从已确认的信息出发，区分可见差异和未经证实的结论。",
                    "body": "信息可以帮助判断，但不替人预告实际体验。",
                    "release_caption": "先看清已知边界，再保留自己的选择。",
                }[unit.purpose],
                "claim_refs": list(claim_refs),
            }
            for unit in skeleton.writable_units
        ],
    }
    return (
        parse_writer_kernel(
            raw,
            skeleton,
            fact_blocks=blocks,
            allowed_claim_ids=packet.fact_ids,
            required_fact_block_ids=required_block_ids,
        ),
        packet,
    )


def _product_review_result(
    *,
    text: str,
    risk_dimension: str,
    risk_operand: str,
    claim_refs: tuple[str, ...],
) -> tuple[str, ...]:
    _, packet, _ = _product_contract()
    contexts = (
        ClauseContextV2(
            clause_id="unit:body:clause:1",
            unit_id="unit:body",
            exact_text=text,
            visible_order=1001,
            text_source="writer_unit",
            unit_contract="abstract_observation",
            speaker_kind="institutional_account",
            claim_refs=claim_refs,
        ),
    )
    questions = build_closed_review_questions(
        contexts,
        product_fact_packet=packet,
    )
    raw_answers: list[dict[str, object]] = []
    for question in questions:
        if question.dimension == "statement_mode":
            status = "present"
            quote = text
            operands = ["generic_observation"]
        elif question.dimension == risk_dimension:
            status = "present"
            quote = text
            operands = [risk_operand]
        else:
            status = "absent"
            quote = ""
            operands = []
        raw_answers.append(
            {
                "question_id": question.question_id,
                "status": status,
                "quote": quote,
                "operands": operands,
            }
        )
    answers = parse_closed_review_answers(
        {
            "evidence_version": CLOSED_REVIEW_VERSION,
            "answers": raw_answers,
        },
        questions=questions,
    )
    result = reconcile_closed_review_answers(
        contexts=contexts,
        questions=questions,
        answers=answers,
        fact_text_by_id={},
        protected_subjects=_SCOPE,
        product_fact_packet=packet,
    )
    return tuple(issue.reason for issue in result.issues)


def test_packet_exposes_trusted_identity_category_and_stable_digest() -> None:
    product, packet, _ = _product_contract()
    replay = build_product_fact_packet((product,))

    assert packet.packet_digest == replay.packet_digest
    assert {item.fact_key for item in packet.facts} >= {
        "sku",
        "display_name",
        "category",
    }
    assert {item.display_name for item in packet.facts} == {"双面短外套"}
    assert {item.entity_kind for item in packet.facts} == {"catalog_product"}
    assert any(
        item.fact_key == "category" and item.structured_value == "double-faced short coat" for item in packet.facts
    )
    assert all(
        "performance" in item.prohibited_inferences and "design_motive" in item.prohibited_inferences
        for item in packet.facts
    )


def test_writer_can_only_select_existing_blocks_and_packet_claim_refs() -> None:
    _, packet, skeleton = _product_contract()
    blocks = immutable_product_fact_blocks(packet)
    base_units = [
        {
            "unit_id": unit.unit_id,
            "text": "不把已知信息扩大成体验结论。",
            "claim_refs": [],
        }
        for unit in skeleton.writable_units
    ]

    with pytest.raises(ValueError, match="invented"):
        parse_writer_kernel(
            {
                "fact_block_refs": ["fact-block:product:forged"],
                "units": base_units,
            },
            skeleton,
            fact_blocks=blocks,
            allowed_claim_ids=packet.fact_ids,
        )
    with pytest.raises(TypeError, match="outside the kernel contract"):
        parse_writer_kernel(
            {
                "units": base_units,
            },
            skeleton,
            fact_blocks=blocks,
            allowed_claim_ids=packet.fact_ids,
        )
    bad_claim_units = [
        {
            **unit,
            "claim_refs": ["fact:product:unrelated"],
        }
        for unit in base_units
    ]
    with pytest.raises(ValueError, match="outside ProductFactPacket"):
        parse_writer_kernel(
            {
                "fact_block_refs": [blocks[0].fact_block_id],
                "units": bad_claim_units,
            },
            skeleton,
            fact_blocks=blocks,
            allowed_claim_ids=packet.fact_ids,
        )
    with pytest.raises(TypeError, match="fields"):
        parse_writer_kernel(
            {
                "fact_block_refs": [blocks[0].fact_block_id],
                "units": [
                    {
                        **unit,
                        "fact_text": "Writer 伪造的商品事实正文。",
                    }
                    for unit in base_units
                ],
            },
            skeleton,
            fact_blocks=blocks,
            allowed_claim_ids=packet.fact_ids,
        )


def test_compiler_inserts_selected_blocks_exactly_and_rejects_mutation() -> None:
    product, packet, _ = _product_contract()
    kernel, _ = _parsed_product_kernel()
    blocks = immutable_product_fact_blocks(packet)
    request = DeliveryCompileInput(
        primary_product="product_truth",
        media_format="graphic",
        products=(product,),
        production_conditions="原创文字卡。",
        allowed_resource_ids=frozenset(
            {
                ORIGINAL_COMPOSITION_RESOURCE_ID,
                "resource:product:ZX-C218",
            }
        ),
        immutable_fact_blocks=blocks,
    )

    compiled = compile_delivery(request, kernel)
    assert isinstance(compiled.production, GraphicProductionBundle)
    selected = tuple(
        block for block_id in kernel.selected_fact_block_ids for block in blocks if block.fact_block_id == block_id
    )
    assert all(compiled.production.full_body.count(block.canonical_text) == 1 for block in selected)
    assert all(
        block.fact_id not in compiled.resource_refs and block.fact_block_id not in compiled.resource_refs
        for block in selected
    )

    mutated = tuple(
        replace(block, canonical_text="被改写的商品事实。")
        if block.fact_block_id == selected[0].fact_block_id
        else block
        for block in blocks
    )
    with pytest.raises(GenerationFailed, match="事实块漂移"):
        compile_delivery(
            replace(request, immutable_fact_blocks=mutated),
            kernel,
        )


def test_selected_fact_units_are_renumbered_into_the_trusted_contract_sidecar() -> None:
    product, _, _ = _product_contract()
    kernel, _ = _parsed_product_kernel()
    records = product_fact_records(product)
    frame = new_frame(
        "general_observation",
        (),
        tuple(record.fact_id for record in records),
    )
    fact_units = tuple(
        unit for unit in kernel.units if unit.purpose == "frozen_fact"
    )

    assert tuple(unit.unit_id for unit in fact_units) == tuple(
        f"unit:frozen-fact:{index}"
        for index in range(1, len(fact_units) + 1)
    )
    contexts = build_clause_contexts_v2(
        kernel=kernel,
        frame=frame,
        fact_registry=records,
        allowed_constraint_ids=frozenset(
            {"constraint:account-tone"}
        ),
        speaker_kind="institutional_account",
    )
    assert sum(
        context.text_source == "frozen_product_fact"
        for context in contexts
    ) == len(fact_units)
    assert {
        context.unit_contract
        for context in contexts
        if context.unit_id == "unit:body"
    } == {"audience_guidance"}


def test_writer_clause_context_excludes_paragraph_separator_whitespace() -> None:
    product, _, _ = _product_contract()
    kernel, _ = _parsed_product_kernel()
    kernel = replace(
        kernel,
        units=tuple(
            replace(
                unit,
                text="第一句。\n\n第二句。",
            )
            if unit.unit_id == "unit:body"
            else unit
            for unit in kernel.units
        ),
    )
    records = product_fact_records(product)
    frame = new_frame(
        "general_observation",
        (),
        tuple(record.fact_id for record in records),
    )

    contexts = build_clause_contexts_v2(
        kernel=kernel,
        frame=frame,
        fact_registry=records,
        allowed_constraint_ids=frozenset(
            {"constraint:account-tone"}
        ),
        speaker_kind="institutional_account",
    )
    body = tuple(
        context.exact_text
        for context in contexts
        if context.unit_id == "unit:body"
    )

    assert body == ("第一句。", "第二句。")
    assert all(text == text.strip() for text in body)


def test_claim_refs_never_license_attributes_performance_or_design_motive() -> None:
    _, packet, _ = _product_contract()
    structural_fact = next(item.fact_id for item in packet.facts if item.fact_key == "category")

    assert _product_review_result(
        text="它属于双面短外套。",
        risk_dimension="product_attribute_claim",
        risk_operand="hard_attribute",
        claim_refs=(structural_fact,),
    ) == ("product_fact_must_use_immutable_block",)
    assert _product_review_result(
        text="这样的结构让它更耐用。",
        risk_dimension="product_performance_or_efficacy",
        risk_operand="performance",
        claim_refs=(structural_fact,),
    ) == ("unsupported_product_inference",)
    assert _product_review_result(
        text="这样设计就是为了让穿着更轻松。",
        risk_dimension="product_design_motive",
        risk_operand="design_motive",
        claim_refs=(structural_fact,),
    ) == ("unsupported_product_inference",)


@pytest.mark.parametrize(
    ("text", "risk_dimension", "risk_operand"),
    _HISTORICAL_G2_PRODUCT_GUESSES,
)
def test_preserved_g2_electronics_guesses_fail_under_product_contract(
    text: str,
    risk_dimension: str,
    risk_operand: str,
) -> None:
    _, packet, _ = _product_contract()
    fact_id = next(iter(packet.fact_ids))

    assert _product_review_result(
        text=text,
        risk_dimension=risk_dimension,
        risk_operand=risk_operand,
        claim_refs=(fact_id,),
    ) == ("unsupported_product_inference",)


def test_source_or_resource_cannot_become_product_fact_permission() -> None:
    _, packet, _ = _product_contract()
    fact_id = next(iter(packet.fact_ids))

    assert _product_review_result(
        text="因为拍摄现场有样衣，所以这项性能已经得到证实。",
        risk_dimension="source_or_resource_as_fact",
        risk_operand="resource_as_fact",
        claim_refs=(fact_id,),
    ) == ("unsupported_product_inference",)


def test_revision_cannot_change_packet_fact_blocks_or_order() -> None:
    first, packet = _parsed_product_kernel()
    blocks = immutable_product_fact_blocks(packet)
    replacement = next(
        block.fact_block_id for block in blocks if block.fact_block_id not in first.selected_fact_block_ids
    )
    changed = (
        first.selected_fact_block_ids[0],
        replacement,
    )

    with pytest.raises(ValueError, match="revision changed"):
        _parsed_product_kernel(
            block_ids=changed,
            required_block_ids=first.selected_fact_block_ids,
        )


def test_product_question_set_is_closed_and_only_applies_with_packet() -> None:
    _, packet, _ = _product_contract()
    context = (
        ClauseContextV2(
            clause_id="unit:body:clause:1",
            unit_id="unit:body",
            exact_text="先看已知信息，再保留选择。",
            visible_order=1001,
            text_source="writer_unit",
            unit_contract="abstract_observation",
            speaker_kind="institutional_account",
        ),
    )

    without_packet = build_closed_review_questions(context)
    with_packet = build_closed_review_questions(
        context,
        product_fact_packet=packet,
    )

    assert (
        tuple(question.dimension for question in with_packet[-len(PRODUCT_REVIEW_DIMENSIONS) :])
        == PRODUCT_REVIEW_DIMENSIONS
    )
    assert len(with_packet) == len(without_packet) + len(PRODUCT_REVIEW_DIMENSIONS)
