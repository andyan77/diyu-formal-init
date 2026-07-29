from __future__ import annotations

from dataclasses import replace

import pytest

from src.shared.creative_kernel import (
    DRAMATIZATION_DISCLOSURE,
    CreativeKernelV1,
    build_kernel_skeleton,
    compiler_owned_unit_texts,
    kernel_digest,
    parse_writer_kernel,
    reconcile_kernel_observations,
)
from src.shared.delivery_compiler import (
    ORIGINAL_COMPOSITION_RESOURCE_ID,
    DeliveryCompileInput,
    assert_compiled_delivery,
    compile_delivery,
)
from src.shared.errors import GenerationFailed
from src.shared.factual_basis import FrozenFactRecord
from src.shared.narrative import ReviewerObservation, new_frame


def _raw_units(
    *,
    title: str = "边界不是一道判决题",
    body: str = "换位思考不等于没有边界。",
) -> dict[str, object]:
    return {
        "units": [
            {"unit_id": "unit:title", "text": title},
            {"unit_id": "unit:body", "text": body},
        ]
    }


def _kernel(
    *,
    mode: str = "general_observation",
    facts: tuple[FrozenFactRecord, ...] = (),
    body: str = "换位思考不等于没有边界。",
) -> CreativeKernelV1:
    frame = new_frame(
        mode,  # type: ignore[arg-type]
        (tuple(record.exact_text for record in facts) if mode == "actuality_reflection" else ()),
        (),
    )
    skeleton = build_kernel_skeleton(
        frame=frame,
        fact_registry=facts,
        constraint_refs=("source:brand_baseline",),
    )
    return parse_writer_kernel(_raw_units(body=body), skeleton)


def _observation(
    *,
    unit_id: str,
    text: str,
    observation_type: str,
    disclosure: tuple[str, ...] = (),
    event_spans: tuple[str, ...] = (),
) -> ReviewerObservation:
    return ReviewerObservation(
        target_id=unit_id,
        target_kind="unit",
        text_spans=(text,),
        people=(),
        relationships=(),
        actions_or_events=event_spans,
        dialogue=(),
        motives=(),
        causes=(),
        results=(),
        times=(),
        locations=(),
        possessions=(),
        observation_type=observation_type,  # type: ignore[arg-type]
        resource_refs=(),
        dramatization_disclosure_spans=disclosure,
        instruction_conflicts=(),
        uncertain=False,
    )


def _complete_observations(
    kernel: CreativeKernelV1,
    *,
    body_type: str = "abstract_principle",
    body_event_spans: tuple[str, ...] = (),
) -> tuple[ReviewerObservation, ...]:
    observations: list[ReviewerObservation] = []
    for unit in kernel.units:
        observation_type = (
            "user_actuality"
            if unit.purpose == "frozen_fact"
            else body_type
            if unit.purpose == "body"
            else "abstract_principle"
        )
        disclosure = (DRAMATIZATION_DISCLOSURE,) if observation_type == "dramatization" else ()
        observations.append(
            _observation(
                unit_id=unit.unit_id,
                text=unit.text,
                observation_type=observation_type,
                disclosure=disclosure,
                event_spans=(body_event_spans if unit.purpose == "body" else ()),
            )
        )
    return tuple(observations)


@pytest.mark.parametrize(
    "forbidden_field",
    ("scene", "resource", "action", "sound", "production_note"),
)
def test_writer_cannot_return_delivery_or_production_fields(
    forbidden_field: str,
) -> None:
    skeleton = build_kernel_skeleton(
        frame=new_frame("general_observation", (), ()),
        fact_registry=(),
        constraint_refs=(),
    )
    raw = _raw_units()
    units = raw["units"]
    assert isinstance(units, list)
    first = units[0]
    assert isinstance(first, dict)
    first[forbidden_field] = "越界字段"

    with pytest.raises(TypeError, match="only unit_id and text"):
        parse_writer_kernel(raw, skeleton)


@pytest.mark.parametrize("drift", ("unknown", "omitted", "duplicate"))
def test_writer_unit_ids_are_a_closed_world(drift: str) -> None:
    skeleton = build_kernel_skeleton(
        frame=new_frame("general_observation", (), ()),
        fact_registry=(),
        constraint_refs=(),
    )
    raw = _raw_units()
    units = raw["units"]
    assert isinstance(units, list)
    if drift == "unknown":
        units[0] = {"unit_id": "unit:invented", "text": "越界"}
    elif drift == "omitted":
        units.pop()
    else:
        units.append(dict(units[0]))

    with pytest.raises(ValueError, match="coverage drifted"):
        parse_writer_kernel(raw, skeleton)


def test_writer_straight_quotes_are_normalized_before_review() -> None:
    skeleton = build_kernel_skeleton(
        frame=new_frame("general_observation", (), ()),
        fact_registry=(),
        constraint_refs=(),
    )

    kernel = parse_writer_kernel(
        _raw_units(
            title='最怕的不是吵架，而是这种"客气"',
        ),
        skeleton,
    )

    assert kernel.unit("unit:title").text == "最怕的不是吵架，而是这种“客气”"


def test_writer_unmatched_straight_quote_fails_closed() -> None:
    skeleton = build_kernel_skeleton(
        frame=new_frame("general_observation", (), ()),
        fact_registry=(),
        constraint_refs=(),
    )

    with pytest.raises(ValueError, match="unmatched double quote"):
        parse_writer_kernel(
            _raw_units(
                title='最怕的不是吵架，而是这种"客气',
            ),
            skeleton,
        )


def test_service_fact_unit_is_exact_and_writer_cannot_return_it() -> None:
    fact = FrozenFactRecord(
        "source:user_actuality:1",
        "今天店里忙了一天，回家还因为谁洗碗拌了两句。",
        "user_actuality",
    )
    frame = new_frame(
        "actuality_reflection",
        (fact.exact_text,),
        (),
    )
    skeleton = build_kernel_skeleton(
        frame=frame,
        fact_registry=(fact,),
        constraint_refs=("source:brand_baseline",),
    )
    raw = _raw_units()
    units = raw["units"]
    assert isinstance(units, list)
    units.append(
        {
            "unit_id": "unit:frozen-fact:1",
            "text": "丈夫最后把碗洗了。",
        }
    )

    with pytest.raises(ValueError, match="coverage drifted"):
        parse_writer_kernel(raw, skeleton)

    kernel = parse_writer_kernel(_raw_units(), skeleton)
    frozen = kernel.unit("unit:frozen-fact:1")
    assert frozen.text == fact.exact_text
    assert frozen.fact_refs == (fact.fact_id,)


def test_mutation_of_a_service_fact_is_detected_by_reconciliation() -> None:
    fact = FrozenFactRecord(
        "source:user_actuality:1",
        "今天店里忙了一天，回家还因为谁洗碗拌了两句。",
        "user_actuality",
    )
    original = _kernel(mode="actuality_reflection", facts=(fact,))
    mutated = replace(
        original,
        units=tuple(
            replace(unit, text="丈夫最后把碗洗了。") if unit.purpose == "frozen_fact" else unit
            for unit in original.units
        ),
    )
    issues = reconcile_kernel_observations(
        kernel=mutated,
        observations=_complete_observations(mutated),
        fact_text_by_id={fact.fact_id: fact.exact_text},
        allowed_constraint_ids=frozenset({"source:brand_baseline"}),
    )

    assert any(issue.reason == "frozen_fact_changed" for issue in issues)


def test_micro_event_fails_but_abstract_principle_passes() -> None:
    micro = _kernel(body="饭桌上一句话让两个人都沉默。")
    micro_issues = reconcile_kernel_observations(
        kernel=micro,
        observations=_complete_observations(
            micro,
            body_type="situated_event",
            body_event_spans=("一句话让两个人都沉默",),
        ),
        fact_text_by_id={},
        allowed_constraint_ids=frozenset({"source:brand_baseline"}),
    )
    assert any(issue.target_id == "unit:body" and issue.reason == "unit_observation_drift" for issue in micro_issues)

    abstract = _kernel(body="换位思考不等于没有边界。")
    assert (
        reconcile_kernel_observations(
            kernel=abstract,
            observations=_complete_observations(abstract),
            fact_text_by_id={},
            allowed_constraint_ids=frozenset({"source:brand_baseline"}),
        )
        == ()
    )


def test_kernel_reviewer_cannot_claim_a_production_resource() -> None:
    kernel = _kernel()
    observations = tuple(
        replace(
            observation,
            resource_refs=("resource:invented-room",),
        )
        if observation.target_id == "unit:body"
        else observation
        for observation in _complete_observations(kernel)
    )
    issues = reconcile_kernel_observations(
        kernel=kernel,
        observations=observations,
        fact_text_by_id={},
        allowed_constraint_ids=frozenset({"source:brand_baseline"}),
    )

    assert any(issue.reason == "review_resource_claim" for issue in issues)


def test_unfounded_institutional_assertion_fails() -> None:
    kernel = _kernel(body="笛语相信婆媳关系需要换位思考。")
    issues = reconcile_kernel_observations(
        kernel=kernel,
        observations=_complete_observations(
            kernel,
            body_type="institutional_assertion",
        ),
        fact_text_by_id={},
        allowed_constraint_ids=frozenset({"source:brand_baseline"}),
    )
    assert any(
        issue.target_id == "unit:body" and issue.reason == "unsupported_institutional_assertion" for issue in issues
    )


def test_dramatization_requires_the_server_disclosure() -> None:
    kernel = _kernel(
        mode="dramatization",
        body="甲说先停一下，乙把原本的话换了一种说法。",
    )
    assert kernel.unit("unit:body").mode == "disclosed_dramatization"
    assert not kernel.unit("unit:body").text.startswith(DRAMATIZATION_DISCLOSURE)
    compiled = compile_delivery(
        DeliveryCompileInput(
            primary_product="brand_life_narrative",
            media_format="graphic",
            products=(),
            production_conditions="原创文字卡。",
            allowed_resource_ids=frozenset({ORIGINAL_COMPOSITION_RESOURCE_ID}),
        ),
        kernel,
    )
    assert DRAMATIZATION_DISCLOSURE.removesuffix("：") in compiled.body


def test_delivery_compiler_rejects_unreviewed_text_and_resources() -> None:
    kernel = _kernel()
    request = DeliveryCompileInput(
        primary_product="brand_life_narrative",
        media_format="graphic",
        products=(),
        production_conditions="原创文字卡。",
        allowed_resource_ids=frozenset({ORIGINAL_COMPOSITION_RESOURCE_ID}),
    )
    compiled = compile_delivery(request, kernel)
    compiler_texts = compiler_owned_unit_texts("brand_life_narrative")
    assert compiled.production.natural_guide.endswith(compiler_texts["unit:natural-guide"])
    assert compiled.production.release_caption_and_interaction.endswith(compiler_texts["unit:release-caption"])
    assert kernel.unit("unit:natural-guide").text == ""
    assert kernel.unit("unit:release-caption").text == ""
    assert compiler_texts["unit:natural-guide"] in compiled.body
    assert compiler_texts["unit:release-caption"] in compiled.body
    assert compiled.visible_provenance["natural_guide"][0].startswith("phrase:compiler-guide-")
    assert compiled.visible_provenance["release_caption_and_interaction"][0].startswith("phrase:compiler-release-")

    with pytest.raises(GenerationFailed, match="未审文字或结构漂移"):
        assert_compiled_delivery(
            request,
            kernel,
            replace(compiled, body=compiled.body + "\n未经审查的新结论。"),
        )
    with pytest.raises(GenerationFailed, match="未审文字或结构漂移"):
        assert_compiled_delivery(
            request,
            kernel,
            replace(
                compiled,
                resource_refs=(
                    *compiled.resource_refs,
                    "resource:unregistered-room",
                ),
            ),
        )


def test_user_fact_never_becomes_a_production_resource() -> None:
    fact = FrozenFactRecord(
        "source:user_actuality:1",
        "今天店里忙了一天，回家还因为谁洗碗拌了两句。",
        "user_actuality",
    )
    kernel = _kernel(mode="actuality_reflection", facts=(fact,))
    request = DeliveryCompileInput(
        primary_product="brand_life_narrative",
        media_format="graphic",
        products=(),
        production_conditions="原创文字卡。",
        allowed_resource_ids=frozenset({ORIGINAL_COMPOSITION_RESOURCE_ID}),
        trusted_fact_texts=((fact.fact_id, fact.exact_text),),
    )
    compiled = compile_delivery(request, kernel)

    assert fact.fact_id not in compiled.resource_refs
    assert fact.exact_text in compiled.production.full_body  # type: ignore[union-attr]
    assert compiled.resource_refs == (ORIGINAL_COMPOSITION_RESOURCE_ID,)


def test_kernel_changes_for_a_non_golden_topic() -> None:
    first = _kernel(
        body="换位思考不等于没有边界。",
    )
    second = parse_writer_kernel(
        _raw_units(
            title="通勤包不是越大越好",
            body="每天真正会带走的东西，才决定容量怎样取舍。",
        ),
        build_kernel_skeleton(
            frame=new_frame("general_observation", (), ()),
            fact_registry=(),
            constraint_refs=("source:brand_baseline",),
        ),
    )

    assert kernel_digest(first) != kernel_digest(second)
    assert first.unit("unit:body").text != second.unit("unit:body").text
