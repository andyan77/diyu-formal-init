from __future__ import annotations

from dataclasses import replace

import pytest

from src.shared.creative_kernel import (
    KERNEL_VERSION,
    CreativeKernelV1,
    apply_server_bearing_expression_contract,
    build_kernel_skeleton,
    parse_writer_kernel,
)
from src.shared.errors import DomainError
from src.shared.factual_basis import FrozenFactRecord
from src.shared.narrative import new_frame
from src.shared.server_bearing_expression import (
    P1_RELEASE_CAPTION,
    P1_SELECTION_UNIT_ID,
    assert_server_bearing_expression_matches,
    build_server_bearing_expression_contract,
    server_bearing_expression_digest,
    server_bearing_expression_document,
    server_bearing_expression_from_document,
)


def _writer_payload(
    skeleton: CreativeKernelV1,
    *,
    include_extra_id: str | None = None,
) -> dict[str, object]:
    writable_units = skeleton.writable_units
    units = [
        {
            "unit_id": unit.unit_id,
            "text": f"{unit.purpose} 的非承重自然表达。",
        }
        for unit in writable_units
    ]
    if include_extra_id is not None:
        units.append({"unit_id": include_extra_id, "text": "Writer 试图改写服务端承重单元。"})
    return {"units": units}


def test_p1_contract_owns_the_choice_body_and_keeps_non_bearing_writer_expression() -> None:
    frame = new_frame(
        "actuality_reflection",
        ("早上有点凉，中午又热，我不想带太多东西，今天怎么穿更稳妥？",),
        (),
    )
    contract = build_server_bearing_expression_contract(
        primary_product="dressing_decision",
        media_format="video",
        frame=frame,
        series_position=None,
    )
    assert contract is not None
    skeleton = build_kernel_skeleton(
        frame=frame,
        fact_registry=(FrozenFactRecord(frame.user_facts[0].source_id, frame.user_facts[0].exact_text, "user_actuality"),),
        constraint_refs=("constraint:test",),
        kernel_version=KERNEL_VERSION,
        primary_product="dressing_decision",
        media_format="video",
    )
    skeleton = apply_server_bearing_expression_contract(skeleton, contract)

    kernel = parse_writer_kernel(
        _writer_payload(skeleton),
        skeleton,
        server_bearing_expression_contract=contract,
        media_format="video",
    )

    selection = kernel.unit(P1_SELECTION_UNIT_ID)
    assert selection.text_source == "server_compiler"
    assert selection.mode == "recommendation"
    assert "如果" in selection.text
    assert "不预设某件单品一定有效" in selection.text
    assert {unit.purpose for unit in kernel.writable_units} == {
        "title",
        "natural_guide",
    }
    assert kernel.unit("unit:release-caption").text == P1_RELEASE_CAPTION
    assert kernel.unit("unit:release-caption").text_source == "server_compiler"
    assert P1_SELECTION_UNIT_ID not in {unit.unit_id for unit in kernel.writable_units}


def test_writer_cannot_return_a_server_bearing_unit() -> None:
    frame = new_frame(
        "actuality_reflection",
        ("今天喝了一直喝的蓝山咖啡，居然是甜的，帮我发一条。",),
        (),
    )
    contract = build_server_bearing_expression_contract(
        primary_product="brand_life_narrative",
        media_format="graphic",
        frame=frame,
        series_position=None,
    )
    assert contract is not None
    skeleton = apply_server_bearing_expression_contract(
        build_kernel_skeleton(
            frame=frame,
            fact_registry=(FrozenFactRecord(frame.user_facts[0].source_id, frame.user_facts[0].exact_text, "user_actuality"),),
            constraint_refs=("constraint:test",),
            kernel_version=KERNEL_VERSION,
            primary_product="brand_life_narrative",
            media_format="graphic",
        ),
        contract,
    )

    with pytest.raises(ValueError, match="coverage drifted"):
        parse_writer_kernel(
            _writer_payload(skeleton, include_extra_id="unit:title"),
            skeleton,
            server_bearing_expression_contract=contract,
            media_format="graphic",
        )


def test_actuality_title_fact_trace_and_caption_are_deterministic_and_bounded() -> None:
    frame = new_frame(
        "actuality_reflection",
        ("今天事情一件接一件，回到家才发现自己连水都忘了喝，帮我发一条。",),
        (),
    )
    contract = build_server_bearing_expression_contract(
        primary_product="brand_life_narrative",
        media_format="graphic",
        frame=frame,
        series_position=None,
    )

    assert contract is not None
    assert contract.fact_source_ids == (frame.user_facts[0].source_id,)
    assert contract.unit_text_by_id["unit:title"] == (
        "今天事情一件接一件：回到家才发现自己连水都忘了喝"
    )
    caption = contract.unit_text_by_id["unit:release-caption"]
    assert "回到家才发现自己连水都忘了喝" in caption
    assert "如果" not in caption
    assert all(value not in caption for value in ("身体", "健康", "心理", "因为", "导致"))
    document = server_bearing_expression_document(contract)
    parsed = server_bearing_expression_from_document(document)
    assert parsed == contract
    assert server_bearing_expression_digest(parsed) == server_bearing_expression_digest(contract)


def test_actuality_contract_rejects_tampering_and_media_drift() -> None:
    frame = new_frame(
        "actuality_reflection",
        ("今天喝了一直喝的蓝山咖啡，居然是甜的，帮我发一条。",),
        (),
    )
    contract = build_server_bearing_expression_contract(
        primary_product="brand_life_narrative",
        media_format="graphic",
        frame=frame,
        series_position=None,
    )
    assert contract is not None
    changed_unit = replace(contract.units[0], text="模型改写后的标题")

    with pytest.raises(DomainError, match="与当前任务不一致"):
        assert_server_bearing_expression_matches(
            replace(contract, units=(changed_unit, *contract.units[1:])),
            primary_product="brand_life_narrative",
            media_format="graphic",
            frame=frame,
            series_position=None,
        )
    with pytest.raises(DomainError, match="与当前任务不一致"):
        assert_server_bearing_expression_matches(
            contract,
            primary_product="brand_life_narrative",
            media_format="video",
            frame=frame,
            series_position=None,
        )


def test_historical_v4_kernel_without_bearing_contract_keeps_old_writer_shape() -> None:
    frame = new_frame("general_observation", (), ())
    skeleton = build_kernel_skeleton(
        frame=frame,
        fact_registry=(),
        constraint_refs=("constraint:test",),
        kernel_version=KERNEL_VERSION,
        primary_product="brand_life_narrative",
        media_format="graphic",
    )

    kernel = parse_writer_kernel(
        _writer_payload(skeleton),
        skeleton,
        media_format="graphic",
    )

    assert {unit.unit_id for unit in kernel.writable_units} == {
        unit.unit_id for unit in skeleton.units
    }
    assert all(unit.text_source == "writer" for unit in kernel.units)
