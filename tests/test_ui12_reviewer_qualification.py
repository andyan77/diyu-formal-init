from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, cast

from scripts.run_ui12_reviewer_qualification import (
    _ALL_DIMENSIONS,
    _bundle_contexts,
    _expected_present,
    _packet,
    _qualification_mismatches,
)
from src.shared.closed_review import (
    CLOSED_REVIEW_VERSION,
    AnswerStatus,
    ClosedReviewAnswer,
    ClosedReviewAnswers,
    build_closed_review_questions,
    reconcile_closed_review_answers,
)
from src.shared.review_evidence import (
    ClauseContextV2,
    ProtectedSubjectScopeV2,
    validate_server_owned_contexts_v2,
)

_FIXTURE_PATH = Path("tests/fixtures/ui12_reviewer_qualification_v1.json")


def _fixture() -> dict[str, Any]:
    value = json.loads(_FIXTURE_PATH.read_text())
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _expected_answers(
    bundle: dict[str, Any],
) -> tuple[
    ClosedReviewAnswers,
    tuple[ClauseContextV2, ...],
    dict[str, dict[str, Any]],
    dict[str, str],
]:
    packet = _packet(bundle.get("product_scope") is True)
    contexts, fact_text_by_id, samples_by_clause = _bundle_contexts(
        bundle,
        packet,
    )
    questions = build_closed_review_questions(
        contexts,
        product_fact_packet=packet,
    )
    answers: list[ClosedReviewAnswer] = []
    for question in questions:
        sample = samples_by_clause[question.clause_id]
        present = _expected_present(sample)
        uncertain = frozenset(cast(list[str], sample["uncertain"]))
        if (
            question.dimension == "statement_mode"
            and "statement_mode" not in present
            and "statement_mode" not in uncertain
        ):
            mode_by_contract = {
                "abstract_observation": "generic_observation",
                "audience_guidance": "generic_observation",
                "recommendation": "recommendation",
                "hypothetical_example": "hypothesis",
                "disclosed_dramatization": "dramatization",
                "actuality_reflection": "generic_observation",
            }
            present["statement_mode"] = (
                mode_by_contract[cast(str, sample["unit_contract"])],
            )
        status: AnswerStatus = (
            "present"
            if question.dimension in present
            else "uncertain"
            if question.dimension in uncertain
            else "absent"
        )
        operands = present.get(question.dimension, ())
        answers.append(
            ClosedReviewAnswer(
                question_id=question.question_id,
                status=status,
                evidence_scope=(
                    "entire_clause"
                    if status in {"present", "uncertain"}
                    else "none"
                ),
                quote=question.exact_text if status in {"present", "uncertain"} else "",
                operands=operands,
            )
        )
    return (
        ClosedReviewAnswers(
            evidence_version=CLOSED_REVIEW_VERSION,
            answers=tuple(answers),
        ),
        contexts,
        samples_by_clause,
        fact_text_by_id,
    )


def test_frozen_reviewer_qualification_oracle_is_exhaustive_and_server_consistent() -> None:
    fixture = _fixture()
    assert fixture["qualification_version"] == "ui12-reviewer-qualification-v1"
    seen_sample_ids: set[str] = set()
    for raw_bundle in fixture["bundles"]:
        bundle = cast(dict[str, Any], raw_bundle)
        packet = _packet(bundle.get("product_scope") is True)
        answers, raw_contexts, samples_by_clause, fact_text_by_id = _expected_answers(
            bundle
        )
        contexts = raw_contexts
        sample_ids = {
            cast(str, sample["sample_id"])
            for sample in samples_by_clause.values()
        }
        assert not (seen_sample_ids & sample_ids)
        seen_sample_ids |= sample_ids
        for sample in samples_by_clause.values():
            present = frozenset(_expected_present(sample))
            uncertain = frozenset(cast(list[str], sample["uncertain"]))
            explicit_absent = frozenset(cast(list[str], sample["absent"]))
            assert present <= _ALL_DIMENSIONS
            assert uncertain <= _ALL_DIMENSIONS
            assert explicit_absent <= _ALL_DIMENSIONS
            assert not (present & uncertain)
            assert not (present & explicit_absent)
            assert not (uncertain & explicit_absent)

        questions = build_closed_review_questions(
            contexts,
            product_fact_packet=packet,
        )
        source_issues = validate_server_owned_contexts_v2(
            contexts=contexts,
            fact_text_by_id=fact_text_by_id,
        )
        assert source_issues == ()
        if not questions:
            assert {
                context.text_source
                for context in contexts
            } == {
                "frozen_user_fact",
                "frozen_product_fact",
            }
            continue
        result = reconcile_closed_review_answers(
            contexts=contexts,
            questions=questions,
            answers=answers,
            fact_text_by_id=fact_text_by_id,
            protected_subjects=ProtectedSubjectScopeV2(
                exact_names=tuple(cast(list[str], bundle["protected_subjects"])),
                speaker_kind="institutional_account",
            ),
            product_fact_packet=packet,
        )
        issues_by_unit = {
            context.unit_id: tuple(
                issue.reason
                for issue in result.issues
                if issue.target_id == context.unit_id
            )
            for context in contexts
        }
        assert (
            _qualification_mismatches(
                samples_by_clause=samples_by_clause,
                questions=questions,
                answers=answers,
                issues_by_unit=issues_by_unit,
            )
            == []
        )


def test_cross_bundle_consistency_control_has_identical_clause_and_oracle() -> None:
    occurrences: dict[str, list[tuple[str, object]]] = defaultdict(list)
    for raw_bundle in _fixture()["bundles"]:
        bundle = cast(dict[str, Any], raw_bundle)
        packet = _packet(bundle.get("product_scope") is True)
        contexts, _, samples_by_clause = _bundle_contexts(bundle, packet)
        contexts_by_clause = {
            context.clause_id: context
            for context in contexts
        }
        for clause_id, sample in samples_by_clause.items():
            key = sample.get("consistency_key")
            if isinstance(key, str):
                occurrences[key].append(
                    (
                        cast(str, bundle["partition"]),
                        (
                            contexts_by_clause[clause_id],
                            _expected_present(sample),
                            tuple(sample["uncertain"]),
                        ),
                    )
                )
    assert set(occurrences) == {"generic-motive-cross-bundle"}
    controls = occurrences["generic-motive-cross-bundle"]
    assert {partition for partition, _ in controls} == {
        "development",
        "holdout",
    }
    assert len(controls) == 2
    left = cast(tuple[Any, ...], controls[0][1])
    right = cast(tuple[Any, ...], controls[1][1])
    assert left[0].clause_id == right[0].clause_id
    assert left[0].exact_text == right[0].exact_text
    assert left[0].unit_contract == right[0].unit_contract
    assert left[1:] == right[1:]


def test_known_hard_false_negative_cannot_pass_the_qualification_oracle() -> None:
    bundle = cast(
        dict[str, Any],
        next(
            raw
            for raw in _fixture()["bundles"]
            if raw["bundle_id"] == "development-g4-g7-hard"
        ),
    )
    packet = _packet(False)
    contexts, _, samples_by_clause = _bundle_contexts(bundle, packet)
    questions = build_closed_review_questions(contexts)
    all_absent = ClosedReviewAnswers(
        evidence_version=CLOSED_REVIEW_VERSION,
        answers=tuple(
            ClosedReviewAnswer(
                question_id=question.question_id,
                status=(
                    "present"
                    if question.dimension == "statement_mode"
                    else "absent"
                ),
                evidence_scope=(
                    "entire_clause"
                    if question.dimension == "statement_mode"
                    else "none"
                ),
                quote=(
                    question.exact_text
                    if question.dimension == "statement_mode"
                    else ""
                ),
                operands=(
                    ("generic_observation",)
                    if question.dimension == "statement_mode"
                    else ()
                ),
            )
            for question in questions
        ),
    )
    mismatches = _qualification_mismatches(
        samples_by_clause=samples_by_clause,
        questions=questions,
        answers=all_absent,
        issues_by_unit={},
    )
    assert {
        cast(str, mismatch["dimension"])
        for mismatch in mismatches
    } >= {
        "relationship_claim",
        "motive_or_mental_state",
        "cause_or_result",
        "statement_mode",
        "server_ruling",
    }
