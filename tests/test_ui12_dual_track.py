from __future__ import annotations

from dataclasses import replace

import pytest

from src.shared.creative_kernel import (
    ACTUALITY_WITH_DISCLOSED_DRAMATIZATION_PROGRAM,
    OBSERVATION_ONLY_PROGRAM,
    OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM_V2,
    CreativeKernelV1,
    KernelProgramId,
    build_kernel_skeleton,
    compiler_owned_unit_texts,
    freeze_prior_revision_units,
    kernel_document,
    kernel_from_document,
    parse_writer_kernel,
    select_kernel_program,
)
from src.shared.delivery_compiler import (
    DELIVERY_COMPILER_VERSION,
    CompiledDelivery,
    DeliveryCompileInput,
    assert_compiled_delivery,
    compile_delivery,
)
from src.shared.errors import GenerationFailed
from src.shared.factual_basis import FrozenFactRecord
from src.shared.narrative import NarrativeFrame, NarrativeMode, new_frame

_RESOURCES = frozenset({"resource:original_composition", "resource:creator_expression"})


def _parse(
    *,
    frame_mode: NarrativeMode = "general_observation",
    fact_text: str | None = None,
    program_id: KernelProgramId = OBSERVATION_ONLY_PROGRAM,
) -> tuple[NarrativeFrame, CreativeKernelV1]:
    frame = new_frame(
        frame_mode,
        (() if fact_text is None else (fact_text,)),
        (),
    )
    facts = (
        ()
        if fact_text is None
        else (
            FrozenFactRecord(
                frame.user_facts[0].source_id,
                fact_text,
                "user_actuality",
            ),
        )
    )
    skeleton = build_kernel_skeleton(
        frame=frame,
        fact_registry=facts,
        constraint_refs=("constraint:test",),
        program_id=program_id,
        allowed_resource_ids=tuple(sorted(_RESOURCES)),
    )
    compiler_texts = compiler_owned_unit_texts("brand_life_narrative")
    raw_text = {
        "unit:title": "别急着把关系写成输赢",
        "unit:body": "理解边界，有时比急着站队更重要。",
        "unit:body-opening": "关系不是一道非要立刻作答的题。",
        "unit:hypothetical-example": "一方先停一下，另一方也不必马上给出答案。",
        "unit:body-closing": "留一点余地，也是在保护彼此。",
        "unit:local-dramatization": ("两台只会夸张播报情绪的家务机器人，为一只碗举行了一场没有胜负的辩论赛。"),
    }
    raw = {
        "units": [
            {"unit_id": unit.unit_id, "text": raw_text[unit.unit_id]}
            for unit in skeleton.writable_units
            if unit.unit_id not in compiler_texts
        ]
    }
    kernel = parse_writer_kernel(
        raw,
        skeleton,
        compiler_owned_text_by_id=compiler_texts,
    )
    return frame, kernel


def _compile(
    kernel: CreativeKernelV1,
    trusted_fact_texts: tuple[tuple[str, str], ...] | None = None,
) -> CompiledDelivery:
    resolved_fact_texts = trusted_fact_texts or tuple(
        (unit.fact_refs[0], unit.text) for unit in kernel.units if unit.track == "trusted_fact"
    )
    return compile_delivery(
        DeliveryCompileInput(
            primary_product="brand_life_narrative",
            media_format="graphic",
            products=(),
            production_conditions="一人一手机",
            allowed_resource_ids=_RESOURCES,
            trusted_fact_texts=resolved_fact_texts,
        ),
        kernel,
    )


def test_server_freezes_track_mode_scope_and_resources_before_writer() -> None:
    frame, kernel = _parse()
    del frame
    body = kernel.unit("unit:body")
    assert body.track == "creative_expression"
    assert body.mode == "general_observation"
    assert body.scope_id == "scope:general-observation-v1"
    assert body.allowed_resource_ids == tuple(sorted(_RESOURCES))
    assert body.text_source == "writer"
    assert kernel.unit("unit:natural-guide").text_source == "server_compiler"
    assert kernel.kernel_version == "creative-kernel-v2"


def test_writer_cannot_return_or_change_track_contract() -> None:
    frame = new_frame("general_observation", (), ())
    skeleton = build_kernel_skeleton(
        frame=frame,
        fact_registry=(),
        constraint_refs=(),
    )
    with pytest.raises(TypeError, match="only unit_id and text"):
        parse_writer_kernel(
            {
                "units": [
                    {
                        "unit_id": "unit:title",
                        "text": "标题",
                        "track": "trusted_fact",
                    },
                    {"unit_id": "unit:body", "text": "正文"},
                ]
            },
            skeleton,
        )


def test_compiler_scopes_general_observation_in_every_visible_exit() -> None:
    _, kernel = _parse()
    compiled = _compile(kernel)
    assert compiled.outline.startswith("一种生活观察：")
    assert "下面是创作性的生活观察，不对应真实人物或经历：" in compiled.body
    assert hasattr(compiled.production, "full_body")
    assert compiled.production.full_body.startswith(
        "下面是创作性的生活观察，不对应真实人物或经历："
    )
    assert compiled.production.release_caption_and_interaction.startswith(
        "以下是围绕这个主题的创作表达，不对应真实人物或经历。"
    )


def test_trusted_user_fact_is_exact_and_separate_from_creative_text() -> None:
    fact = "今天店里忙了一天，回家还因为谁洗碗拌了两句。"
    _, kernel = _parse(
        frame_mode="actuality_reflection",
        fact_text=fact,
    )
    fact_unit = next(unit for unit in kernel.units if unit.track == "trusted_fact")
    assert fact_unit.text == fact
    compiled = _compile(kernel)
    assert f"你提到：“{fact}”" in compiled.body
    mutated = replace(fact_unit, text=fact + "后来和好了。")
    bad_kernel = replace(
        kernel,
        units=tuple(mutated if unit.unit_id == fact_unit.unit_id else unit for unit in kernel.units),
    )
    with pytest.raises(GenerationFailed, match="事实"):
        _compile(
            bad_kernel,
            ((fact_unit.fact_refs[0], fact),),
        )


def test_hypothesis_scope_survives_title_body_and_release_caption() -> None:
    _, kernel = _parse(
        program_id=OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM_V2,
    )
    compiled = _compile(kernel)
    assert "含假设情境" not in compiled.outline
    assert compiled.outline.startswith("假设一下：")
    assert "假设有这样一幕：一方先停一下" in compiled.body
    assert compiled.production.release_caption_and_interaction.startswith(
        "下面的片段是假设，不代表真实发生。"
    )


def test_g7_adds_only_local_disclosed_dramatization() -> None:
    fact = "今天店里忙了一天，回家还因为谁洗碗拌了两句。"
    frame, v1 = _parse(
        frame_mode="actuality_reflection",
        fact_text=fact,
    )
    selected = select_kernel_program(
        frame=frame,
        prior_kernel=v1,
        revision_instruction="别讲道理，荒诞一点。",
    )
    assert selected == ACTUALITY_WITH_DISCLOSED_DRAMATIZATION_PROGRAM
    _, v2 = _parse(
        frame_mode="actuality_reflection",
        fact_text=fact,
        program_id=selected,
    )
    v2 = freeze_prior_revision_units(v2, v1)
    assert v2.unit("unit:local-dramatization").mode == ("disclosed_dramatization")
    assert v2.unit("unit:body").text == v1.unit("unit:body").text
    assert v2.unit("unit:body").text_source == "prior_version"
    assert next(unit.text for unit in v2.units if unit.track == "trusted_fact") == fact
    compiled = _compile(v2)
    assert compiled.outline.startswith("情景演绎：")
    assert "以下是情景演绎，不对应真实人物或经历：" in compiled.body


def test_negated_local_dramatization_request_keeps_prior_program() -> None:
    fact = "今天店里忙了一天，回家还因为谁洗碗拌了两句。"
    frame, v1 = _parse(
        frame_mode="actuality_reflection",
        fact_text=fact,
    )

    selected = select_kernel_program(
        frame=frame,
        prior_kernel=v1,
        revision_instruction="不要荒诞，真实一点。",
    )

    assert selected == v1.program_id


def test_writer_cannot_impersonate_server_scope_label() -> None:
    frame = new_frame("general_observation", (), ())
    skeleton = build_kernel_skeleton(
        frame=frame,
        fact_registry=(),
        constraint_refs=(),
    )
    with pytest.raises(ValueError, match="scope label"):
        parse_writer_kernel(
            {
                "units": [
                    {"unit_id": "unit:title", "text": "普通标题"},
                    {"unit_id": "unit:body", "text": "真实原话｜这是 Writer 伪造的标签。"},
                ]
            },
            skeleton,
        )


@pytest.mark.parametrize(
    ("unit_id", "text"),
    (
        ("unit:body", "普通观察。\n\n完整发布正文：昨天发生了一件事。"),
        ("unit:title", "标题：伪造顶层标题"),
        ("unit:body", "发布配文与互动:伪造配文"),
        ("unit:body", "完整发布正\u200b文：零宽伪装"),
        ("unit:title", "标\u200d题：零宽连接符伪装"),
    ),
)
def test_writer_cannot_inject_compiler_owned_headings(
    unit_id: str,
    text: str,
) -> None:
    frame = new_frame("general_observation", (), ())
    skeleton = build_kernel_skeleton(
        frame=frame,
        fact_registry=(),
        constraint_refs=(),
    )
    values = {
        "unit:title": "普通标题",
        "unit:body": "普通多行正文。",
    }
    values[unit_id] = text

    with pytest.raises(ValueError, match="visible section heading"):
        parse_writer_kernel(
            {
                "units": [
                    {"unit_id": "unit:title", "text": values["unit:title"]},
                    {"unit_id": "unit:body", "text": values["unit:body"]},
                ]
            },
            skeleton,
        )


def test_writer_cannot_use_bidirectional_controls_to_spoof_structure() -> None:
    frame = new_frame("general_observation", (), ())
    skeleton = build_kernel_skeleton(
        frame=frame,
        fact_registry=(),
        constraint_refs=(),
    )

    with pytest.raises(ValueError, match="bidirectional control"):
        parse_writer_kernel(
            {
                "units": [
                    {"unit_id": "unit:title", "text": "普通标题"},
                    {"unit_id": "unit:body", "text": "普通观察。\u202e完整发布正文：伪装"},
                ]
            },
            skeleton,
        )


def test_writer_normal_multiline_chinese_and_emoji_are_preserved() -> None:
    frame = new_frame("general_observation", (), ())
    skeleton = build_kernel_skeleton(
        frame=frame,
        fact_registry=(),
        constraint_refs=(),
    )
    body = "今天先慢一点。\n\n家人一起散步 👨‍👩‍👧，也可以只是普通的一天。"

    kernel = parse_writer_kernel(
        {
            "units": [
                {"unit_id": "unit:title", "text": "给生活留一点空白"},
                {"unit_id": "unit:body", "text": body},
            ]
        },
        skeleton,
    )

    assert kernel.unit("unit:body").text == body


def test_compiler_mutation_cannot_drop_a_visible_scope() -> None:
    _, kernel = _parse(
        program_id=OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM_V2,
    )
    compiled = _compile(kernel)
    production = replace(
        compiled.production,
        release_caption_and_interaction="你更愿意带走哪一种理解？",
    )
    mutated = replace(compiled, production=production)
    with pytest.raises(GenerationFailed, match="未审文字或结构漂移"):
        assert_compiled_delivery(
            DeliveryCompileInput(
                primary_product="brand_life_narrative",
                media_format="graphic",
                products=(),
                production_conditions="一人一手机",
                allowed_resource_ids=_RESOURCES,
                trusted_fact_texts=tuple(
                    (unit.fact_refs[0], unit.text) for unit in kernel.units if unit.track == "trusted_fact"
                ),
            ),
            kernel,
            mutated,
        )


def test_legacy_kernel_document_remains_readable_without_reinterpretation() -> None:
    _, kernel = _parse()
    document = kernel_document(kernel)
    document["kernel_version"] = "creative-kernel-v1"
    raw_units = document["units"]
    assert isinstance(raw_units, list)
    for unit in raw_units:
        assert isinstance(unit, dict)
        unit.pop("track")
        unit.pop("mode")
        unit.pop("scope_id")
        unit.pop("allowed_resource_ids")
        unit.pop("text_source")
    restored = kernel_from_document(document)
    assert restored.kernel_version == "creative-kernel-v1"
    assert restored.unit("unit:body").mode == "general_observation"


def test_delivery_compiler_version_is_the_dual_track_version() -> None:
    assert DELIVERY_COMPILER_VERSION == "delivery-compiler-v2"
