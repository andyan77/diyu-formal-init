from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from src.shared.creative_kernel import (
    DUAL_TRACK_KERNEL_VERSION,
    HYPOTHESIS_DISCLOSURE,
    OBSERVATION_ONLY_PROGRAM,
    OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM,
    OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM_V2,
    CreativeKernelV1,
    build_kernel_skeleton,
    kernel_digest,
    kernel_document,
    kernel_from_document,
    parse_writer_kernel,
    repair_kernel_units,
    select_kernel_program,
)
from src.shared.delivery_compiler import (
    DELIVERY_COMPILER_VERSION,
    ORIGINAL_COMPOSITION_RESOURCE_ID,
    DeliveryCompileInput,
    compile_delivery,
)
from src.shared.errors import GenerationFailed
from src.shared.factual_basis import FrozenFactRecord
from src.shared.narrative import new_frame
from src.shared.review_evidence import (
    REVIEW_EVIDENCE_VERSION,
    ClauseEvidence,
    ProtectedSubjectScope,
    ReviewEvidenceV1,
    build_review_clauses,
    reconcile_review_evidence,
)


def _raw_units(
    *,
    program_id: str,
    body: str = "换位思考不等于没有边界。",
    hypothetical: str = "饭桌上一句话让两个人都沉默。",
    title: str = "边界不是一道判决题",
) -> dict[str, object]:
    body_units = (
        [
            {
                "unit_id": "unit:body-opening",
                "text": body,
            },
            {
                "unit_id": "unit:hypothetical-example",
                "text": hypothetical,
            },
            {
                "unit_id": "unit:body-closing",
                "text": "理解不要求任何一方放弃自己的边界。",
            },
        ]
        if program_id == OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM
        else [{"unit_id": "unit:body", "text": body}]
    )
    return {
        "units": [
            {"unit_id": "unit:title", "text": title},
            *body_units,
        ]
    }


def _kernel(
    *,
    program_id: str = OBSERVATION_ONLY_PROGRAM,
    body: str = "换位思考不等于没有边界。",
    hypothetical: str = "饭桌上一句话让两个人都沉默。",
    facts: tuple[FrozenFactRecord, ...] = (),
) -> CreativeKernelV1:
    frame = new_frame(
        "actuality_reflection" if facts else "general_observation",
        tuple(record.exact_text for record in facts),
        (),
    )
    skeleton = build_kernel_skeleton(
        frame=frame,
        fact_registry=facts,
        constraint_refs=("source:brand_baseline",),
        program_id=program_id,  # type: ignore[arg-type]
    )
    return parse_writer_kernel(
        _raw_units(
            program_id=program_id,
            body=body,
            hypothetical=hypothetical,
        ),
        skeleton,
    )


def _evidence(
    kernel: CreativeKernelV1,
    *,
    changes_by_fragment: dict[str, dict[str, object]] | None = None,
) -> ReviewEvidenceV1:
    items: list[ClauseEvidence] = []
    for clause in build_review_clauses(kernel):
        changes: dict[str, object] = {}
        for fragment, candidate in (changes_by_fragment or {}).items():
            if fragment in clause.exact_text:
                changes = candidate
                break
        items.append(
            ClauseEvidence(
                clause_id=clause.clause_id,
                exact_text=clause.exact_text,
                subject_spans=tuple(
                    changes.get("subject_spans", ())  # type: ignore[arg-type]
                ),
                predicate_spans=tuple(
                    changes.get("predicate_spans", ())  # type: ignore[arg-type]
                ),
                action_or_event_spans=tuple(
                    changes.get(  # type: ignore[arg-type]
                        "action_or_event_spans", ()
                    )
                ),
                dialogue_spans=tuple(
                    changes.get("dialogue_spans", ())  # type: ignore[arg-type]
                ),
                motive_spans=tuple(
                    changes.get("motive_spans", ())  # type: ignore[arg-type]
                ),
                cause_spans=tuple(
                    changes.get("cause_spans", ())  # type: ignore[arg-type]
                ),
                result_spans=tuple(
                    changes.get("result_spans", ())  # type: ignore[arg-type]
                ),
                time_spans=tuple(
                    changes.get("time_spans", ())  # type: ignore[arg-type]
                ),
                location_spans=tuple(
                    changes.get("location_spans", ())  # type: ignore[arg-type]
                ),
                implicit_subject=str(changes.get("implicit_subject", "none")),  # type: ignore[arg-type]
                uncertain=False,
            )
        )
    return ReviewEvidenceV1(REVIEW_EVIDENCE_VERSION, tuple(items))


def _reasons(
    kernel: CreativeKernelV1,
    evidence: ReviewEvidenceV1,
    *,
    facts: tuple[FrozenFactRecord, ...] = (),
) -> tuple[str, ...]:
    return tuple(
        issue.reason
        for issue in reconcile_review_evidence(
            kernel=kernel,
            review_clauses=build_review_clauses(kernel),
            evidence=evidence,
            fact_text_by_id={record.fact_id: record.exact_text for record in facts},
            allowed_constraint_ids=frozenset({"source:brand_baseline"}),
            protected_subjects=ProtectedSubjectScope(
                exact_names=("笛语", "笛语服饰"),
                current_speaker_is_institutional=True,
            ),
        )
    )


def test_server_selects_one_bounded_program_from_frozen_context() -> None:
    general = new_frame("general_observation", (), ())
    assert select_kernel_program(frame=general) == OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM_V2

    actuality = new_frame("actuality_reflection", ("今天很忙。",), ())
    assert select_kernel_program(frame=actuality) == OBSERVATION_ONLY_PROGRAM

    prior_kernel = _kernel(program_id=OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM)
    fact_bearing_general = new_frame(
        "general_observation",
        (),
        (),
        brand_fact_ids=("fact:brand:confirmed",),
    )
    assert (
        select_kernel_program(
            frame=fact_bearing_general,
            prior_kernel=prior_kernel,
        )
        == OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM
    )


def test_program_id_must_match_service_owned_unit_shape() -> None:
    kernel = replace(
        _kernel(program_id=OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM),
        program_id=OBSERVATION_ONLY_PROGRAM,
    )

    reasons = _reasons(kernel, _evidence(kernel))

    assert reasons == ("kernel_program_drift",)


def test_abstract_principle_passes_and_unmarked_micro_event_fails() -> None:
    abstract = _kernel()
    assert _reasons(abstract, _evidence(abstract)) == ()

    micro = _kernel(body="饭桌上一句话让两个人都沉默。")
    reasons = _reasons(
        micro,
        _evidence(
            micro,
            changes_by_fragment={
                "饭桌上": {
                    "action_or_event_spans": ("一句话",),
                    "result_spans": ("两个人都沉默",),
                    "location_spans": ("饭桌上",),
                    "implicit_subject": "generic",
                }
            },
        ),
    )
    assert "situated_event_in_observation" in reasons


def test_same_micro_event_passes_inside_server_scoped_hypothesis() -> None:
    kernel = _kernel(
        program_id=OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM,
    )
    unit = kernel.unit("unit:hypothetical-example")
    assert unit.mode == "hypothesis"
    assert not unit.text.startswith(HYPOTHESIS_DISCLOSURE)
    evidence = _evidence(
        kernel,
        changes_by_fragment={
            "饭桌上": {
                "action_or_event_spans": ("一句话",),
                "result_spans": ("两个人都沉默",),
                "location_spans": ("饭桌上",),
                "implicit_subject": "generic",
            }
        },
    )

    assert _reasons(kernel, evidence) == ()


def test_deleting_server_hypothesis_scope_fails() -> None:
    kernel = _kernel(
        program_id=OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM,
    )
    mutated = replace(
        kernel,
        units=tuple(
            replace(
                unit,
                scope_id="",
            )
            if unit.unit_id == "unit:hypothetical-example"
            else unit
            for unit in kernel.units
        ),
    )

    with pytest.raises(GenerationFailed, match="表达轨"):
        compile_delivery(
            DeliveryCompileInput(
                primary_product="brand_life_narrative",
                media_format="graphic",
                products=(),
                production_conditions="原创文字卡。",
                allowed_resource_ids=frozenset({ORIGINAL_COMPOSITION_RESOURCE_ID}),
            ),
            mutated,
        )


@pytest.mark.parametrize(
    ("text", "subject", "reason"),
    (
        (
            "我家饭桌上一句话让两个人都沉默。",
            "我家",
            "unsupported_actuality_binding",
        ),
        (
            "真实员工在饭桌上说了一句话。",
            "真实员工",
            "unsupported_actuality_binding",
        ),
        (
            "真实顾客听完以后沉默了。",
            "真实顾客",
            "unsupported_actuality_binding",
        ),
        (
            "本店一直这样处理家庭分歧。",
            "本店",
            "unsupported_institutional_assertion",
        ),
        (
            "笛语相信婆媳关系需要换位思考。",
            "笛语",
            "unsupported_institutional_assertion",
        ),
    ),
)
def test_hypothesis_cannot_bind_current_reality(
    text: str,
    subject: str,
    reason: str,
) -> None:
    kernel = _kernel(
        program_id=OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM,
        hypothetical=text,
    )
    evidence = _evidence(
        kernel,
        changes_by_fragment={
            subject: {
                "subject_spans": (subject,),
                "predicate_spans": ("相信",)
                if "相信" in text
                else ("一直这样处理",)
                if "一直这样处理" in text
                else ("沉默",)
                if "沉默" in text
                else ("说",),
                "action_or_event_spans": ("沉默",) if "沉默" in text else ("说",) if "说" in text else (),
                "implicit_subject": "none",
            }
        },
    )

    assert reason in _reasons(kernel, evidence)


def test_hypothetical_people_never_become_production_resources() -> None:
    kernel = _kernel(
        program_id=OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM,
    )
    compiled = compile_delivery(
        DeliveryCompileInput(
            primary_product="brand_life_narrative",
            media_format="video",
            products=(),
            production_conditions="仅使用文字卡和旁白。",
            allowed_resource_ids=frozenset({ORIGINAL_COMPOSITION_RESOURCE_ID}),
        ),
        kernel,
    )

    assert compiled.resource_refs == (ORIGINAL_COMPOSITION_RESOURCE_ID,)
    assert all("hypothetical" not in resource for resource in compiled.resource_refs)
    assert "文字卡" in compiled.production.visual_actions  # type: ignore[union-attr]


def test_actuality_fact_and_program_survive_revision_invariants() -> None:
    fact = FrozenFactRecord(
        "source:user_actuality:1",
        "今天店里忙了一天，回家还因为谁洗碗拌了两句。",
        "user_actuality",
    )
    original = _kernel(facts=(fact,))
    revised = repair_kernel_units(
        kernel=original,
        affected_unit_ids=frozenset({"unit:body"}),
        raw={
            "units": [
                {
                    "unit_id": "unit:body",
                    "text": "道理先放一边，边界仍然不能替现实添戏。",
                }
            ]
        },
    )

    assert revised.program_id == original.program_id
    assert revised.unit("unit:frozen-fact:1") == original.unit("unit:frozen-fact:1")
    assert (
        select_kernel_program(
            frame=new_frame(
                "actuality_reflection",
                (fact.exact_text,),
                (),
            ),
            prior_kernel=original,
        )
        == original.program_id
    )
    assert DELIVERY_COMPILER_VERSION == "delivery-compiler-v4"

    mutated = replace(
        original,
        units=tuple(
            replace(unit, text="今天发生了很多事。") if unit.purpose == "frozen_fact" else unit
            for unit in original.units
        ),
    )
    assert "frozen_fact_changed" in _reasons(
        mutated,
        _evidence(mutated),
        facts=(fact,),
    )


def test_affected_unit_repair_must_change_its_complete_text() -> None:
    original = _kernel()

    with pytest.raises(ValueError, match="did not change every affected"):
        repair_kernel_units(
            kernel=original,
            affected_unit_ids=frozenset({"unit:body"}),
            raw={
                "units": [
                    {
                        "unit_id": "unit:body",
                        "text": original.unit("unit:body").text,
                    }
                ]
            },
        )


def test_legacy_kernel_document_remains_readable_and_recompilable() -> None:
    kernel = _kernel()
    legacy_document = kernel_document(kernel)
    legacy_document.pop("program_id")

    restored = cast(CreativeKernelV1, kernel_from_document(legacy_document))
    assert restored.kernel_version == DUAL_TRACK_KERNEL_VERSION
    assert restored.program_id == OBSERVATION_ONLY_PROGRAM
    assert kernel_from_document(kernel_document(restored)) == restored

    compiled = compile_delivery(
        DeliveryCompileInput(
            primary_product="brand_life_narrative",
            media_format="graphic",
            products=(),
            production_conditions="原创文字卡。",
            allowed_resource_ids=frozenset({ORIGINAL_COMPOSITION_RESOURCE_ID}),
        ),
        restored,
    )
    assert restored.unit("unit:body").text in compiled.body


def test_different_topic_changes_hypothetical_kernel_content() -> None:
    relationship = _kernel(
        program_id=OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM,
    )
    commute = parse_writer_kernel(
        _raw_units(
            program_id=OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM,
            title="通勤包不是越大越好",
            body="容量判断取决于每天真正会带走什么。",
            hypothetical="如果只带电脑和水杯，空出来的位置也有价值。",
        ),
        build_kernel_skeleton(
            frame=new_frame("general_observation", (), ()),
            fact_registry=(),
            constraint_refs=("source:brand_baseline",),
            program_id=(OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM),
        ),
    )

    assert kernel_digest(relationship) != kernel_digest(commute)
    assert relationship.unit("unit:hypothetical-example").text != commute.unit("unit:hypothetical-example").text
