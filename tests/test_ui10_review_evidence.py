from __future__ import annotations

from dataclasses import replace

import pytest

from src.shared.creative_kernel import (
    CreativeKernelV1,
    build_kernel_skeleton,
    compiler_owned_unit_texts,
    parse_writer_kernel,
)
from src.shared.factual_basis import FrozenFactRecord
from src.shared.narrative import new_frame
from src.shared.review_evidence import (
    REVIEW_EVIDENCE_VERSION,
    ClauseEvidence,
    ProtectedSubjectScope,
    ReviewEvidenceV1,
    build_review_clauses,
    parse_review_evidence,
    reconcile_review_evidence,
)


def _kernel(
    body: str,
    *,
    facts: tuple[FrozenFactRecord, ...] = (),
    brand_fact_ids: tuple[str, ...] = (),
) -> CreativeKernelV1:
    frame = new_frame(
        "general_observation",
        (),
        (),
        brand_fact_ids,
    )
    skeleton = build_kernel_skeleton(
        frame=frame,
        fact_registry=facts,
        constraint_refs=("source:brand_baseline",),
    )
    return parse_writer_kernel(
        {
            "units": [
                {"unit_id": "unit:title", "text": "关系里也可以有边界"},
                {"unit_id": "unit:body", "text": body},
            ]
        },
        skeleton,
        compiler_owned_text_by_id=compiler_owned_unit_texts("brand_life_narrative"),
    )


def _evidence(
    kernel: CreativeKernelV1,
    *,
    body_changes: dict[str, object] | None = None,
) -> ReviewEvidenceV1:
    items: list[ClauseEvidence] = []
    for clause in build_review_clauses(kernel):
        changes = (
            body_changes
            if clause.unit_id == "unit:body" and body_changes is not None
            else {}
        )
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
                implicit_subject=str(
                    changes.get("implicit_subject", "none")
                ),  # type: ignore[arg-type]
                uncertain=bool(changes.get("uncertain", False)),
            )
        )
    return ReviewEvidenceV1(REVIEW_EVIDENCE_VERSION, tuple(items))


def _issues(
    kernel: CreativeKernelV1,
    evidence: ReviewEvidenceV1,
    *,
    facts: tuple[FrozenFactRecord, ...] = (),
    exact_names: tuple[str, ...] = ("笛语",),
) -> tuple[str, ...]:
    return tuple(
        issue.reason
        for issue in reconcile_review_evidence(
            kernel=kernel,
            review_clauses=build_review_clauses(kernel),
            evidence=evidence,
            fact_text_by_id={
                record.fact_id: record.exact_text for record in facts
            },
            allowed_constraint_ids=frozenset({"source:brand_baseline"}),
            protected_subjects=ProtectedSubjectScope(
                exact_names=exact_names,
                current_speaker_is_institutional=True,
            ),
        )
    )


def test_clause_split_is_deterministic_and_preserves_every_character() -> None:
    kernel = _kernel("第一句。第二句！\n第三句没有终止标点")
    body_clauses = tuple(
        clause
        for clause in build_review_clauses(kernel)
        if clause.unit_id == "unit:body"
    )

    assert "".join(clause.exact_text for clause in body_clauses) == (
        "第一句。第二句！\n第三句没有终止标点"
    )
    assert tuple(clause.visible_order for clause in body_clauses) == (
        100001,
        100002,
        100003,
    )


def test_a_abstract_principle_passes_from_exact_evidence() -> None:
    kernel = _kernel("换位思考不等于没有边界。")

    assert _issues(kernel, _evidence(kernel)) == ()


def test_b_event_evidence_fails_even_without_an_explicit_person() -> None:
    kernel = _kernel("饭桌上一句话让两个人都沉默。")
    reasons = _issues(
        kernel,
        _evidence(
            kernel,
            body_changes={
                "action_or_event_spans": ("一句话",),
                "result_spans": ("两个人都沉默",),
                "location_spans": ("饭桌上",),
                "implicit_subject": "generic",
            },
        ),
    )

    assert "situated_event_in_observation" in reasons


def test_c_ui09_wrong_abstract_label_cannot_override_service_ruling() -> None:
    kernel = _kernel("笛语相信婆媳关系需要换位思考。")
    evidence = _evidence(
        kernel,
        body_changes={
            "subject_spans": ("笛语",),
            "predicate_spans": ("相信",),
            "motive_spans": ("相信",),
            "action_or_event_spans": ("换位思考",),
        },
    )

    assert "unsupported_institutional_assertion" in _issues(
        kernel,
        evidence,
    )

    raw = {
        "evidence_version": REVIEW_EVIDENCE_VERSION,
        "clauses": [
            {
                "clause_id": "unit:body:clause:1",
                "exact_text": kernel.unit("unit:body").text,
                "subject_spans": ["笛语"],
                "predicate_spans": ["相信"],
                "action_or_event_spans": ["换位思考"],
                "dialogue_spans": [],
                "motive_spans": ["相信"],
                "cause_spans": [],
                "result_spans": [],
                "time_spans": [],
                "location_spans": [],
                "implicit_subject": "none",
                "uncertain": False,
                "observation_type": "abstract_principle",
            }
        ],
    }
    with pytest.raises(TypeError, match="clause is invalid"):
        parse_review_evidence(raw)


def test_c2_institutional_current_speaker_fails() -> None:
    kernel = _kernel("我们相信婆媳关系需要换位思考。")
    reasons = _issues(
        kernel,
        _evidence(
            kernel,
            body_changes={
                "subject_spans": ("我们",),
                "predicate_spans": ("相信",),
                "implicit_subject": "current_speaker",
            },
        ),
    )

    assert "unsupported_institutional_assertion" in reasons


def test_current_article_expression_is_not_an_institutional_fact() -> None:
    kernel = _kernel("这篇更想聊换位思考和边界。")
    evidence = _evidence(
        kernel,
        body_changes={
            "subject_spans": ("这篇",),
            "predicate_spans": ("想聊",),
            "implicit_subject": "none",
        },
    )

    assert _issues(kernel, evidence) == ()


def test_frame_allowed_brand_fact_is_exact_and_not_writer_owned() -> None:
    fact = FrozenFactRecord(
        "fact:brand:confirmed",
        "笛语确认本账号只发布人工终审后的草稿。",
        "brand",
    )
    kernel = _kernel(
        "这篇更想聊创作边界。",
        facts=(fact,),
        brand_fact_ids=(fact.fact_id,),
    )

    assert kernel.unit("unit:frozen-fact:1").text == fact.exact_text
    assert _issues(kernel, _evidence(kernel), facts=(fact,)) == ()

    mutated = replace(
        kernel,
        units=tuple(
            replace(unit, text="笛语一直这样做。")
            if unit.purpose == "frozen_fact"
            else unit
            for unit in kernel.units
        ),
    )
    assert "frozen_fact_changed" in _issues(
        mutated,
        _evidence(mutated),
        facts=(fact,),
    )


@pytest.mark.parametrize(
    "mutation",
    ("missing", "duplicate", "extra", "partial", "fake_span", "uncertain"),
)
def test_reviewer_evidence_failures_are_nonsemantic(
    mutation: str,
) -> None:
    kernel = _kernel("换位思考不等于没有边界。")
    evidence = _evidence(kernel)
    clauses = list(evidence.clauses)
    if mutation == "missing":
        clauses.pop()
    elif mutation == "duplicate":
        clauses.append(clauses[0])
    elif mutation == "extra":
        clauses.append(replace(clauses[0], clause_id="unit:extra:clause:1"))
    elif mutation == "partial":
        clauses[-1] = replace(
            clauses[-1],
            exact_text=clauses[-1].exact_text[:2],
        )
    elif mutation == "fake_span":
        clauses[-1] = replace(
            clauses[-1],
            predicate_spans=("不存在的谓词",),
        )
    else:
        clauses[-1] = replace(clauses[-1], uncertain=True)

    reasons = _issues(
        kernel,
        ReviewEvidenceV1(REVIEW_EVIDENCE_VERSION, tuple(clauses)),
    )

    expected = (
        "review_evidence_span"
        if mutation == "fake_span"
        else "review_evidence_uncertain"
        if mutation == "uncertain"
        else "review_evidence_coverage"
    )
    assert expected in reasons


def test_new_institution_name_with_stable_designator_is_not_fact_licensed() -> None:
    kernel = _kernel("山海公司承诺所有关系都要换位思考。")
    reasons = _issues(
        kernel,
        _evidence(
            kernel,
            body_changes={
                "subject_spans": ("山海公司",),
                "predicate_spans": ("承诺",),
            },
        ),
    )

    assert "unsupported_institutional_assertion" in reasons
