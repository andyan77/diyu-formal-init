from __future__ import annotations

from dataclasses import replace

import pytest

from src.shared.closed_review import (
    CLOSED_REVIEW_DIMENSIONS,
    CLOSED_REVIEW_VERSION,
    ClaimInventoryItem,
    ClosedReviewAnswers,
    build_closed_review_questions,
    closed_review_json_schema,
    materialize_claim_inventory,
    parse_closed_review_answers,
    reconcile_closed_review_answers,
    validate_claim_inventory,
)
from src.shared.review_evidence import (
    ClauseContextV2,
    ProtectedSubjectScopeV2,
)

_SCOPE = ProtectedSubjectScopeV2(
    exact_names=("笛语",),
    speaker_kind="personal_ip_account",
)


def _context(
    text: str,
    *,
    contract: str = "actuality_reflection",
    clause_id: str = "unit:body:clause:1",
) -> tuple[ClauseContextV2, ...]:
    return (
        ClauseContextV2(
            clause_id=clause_id,
            unit_id="unit:body",
            exact_text=text,
            visible_order=1001,
            text_source="writer_unit",
            unit_contract=contract,  # type: ignore[arg-type]
            speaker_kind="personal_ip_account",
        ),
    )


def _raw_answers(
    contexts: tuple[ClauseContextV2, ...],
    *,
    overrides: dict[
        str,
        tuple[str, str, tuple[str, ...]],
    ]
    | None = None,
) -> dict[str, object]:
    questions = build_closed_review_questions(contexts)
    changed = overrides or {}
    answers: list[dict[str, object]] = []
    for question in questions:
        status, _legacy_quote, operands = changed.get(
            question.dimension,
            (
                "present",
                question.exact_text,
                ("generic_observation",),
            )
            if question.dimension == "statement_mode"
            else ("absent", "", ()),
        )
        answers.append(
            {
                "question_id": question.question_id,
                "status": status,
                "evidence_scope": (
                    "entire_clause"
                    if status in {"present", "uncertain"}
                    else "none"
                ),
                "operands": list(operands),
            }
        )
    return {
        "evidence_version": CLOSED_REVIEW_VERSION,
        "answers": answers,
    }


def _parse(
    contexts: tuple[ClauseContextV2, ...],
    overrides: dict[str, tuple[str, str, tuple[str, ...]]],
) -> ClosedReviewAnswers:
    questions = build_closed_review_questions(contexts)
    return parse_closed_review_answers(
        _raw_answers(contexts, overrides=overrides),
        questions=questions,
    )


def _reasons(
    contexts: tuple[ClauseContextV2, ...],
    answers: ClosedReviewAnswers,
) -> tuple[str, ...]:
    questions = build_closed_review_questions(contexts)
    return tuple(
        issue.reason
        for issue in reconcile_closed_review_answers(
            contexts=contexts,
            questions=questions,
            answers=answers,
            fact_text_by_id={},
            protected_subjects=_SCOPE,
        ).issues
    )


def test_every_writer_clause_gets_the_complete_closed_question_set() -> None:
    contexts = (
        *_context("换位思考不等于没有边界。"),
        *_context(
            "很多争执背后，可能有被看见的需要。",
            clause_id="unit:body:clause:2",
        ),
    )

    questions = build_closed_review_questions(contexts)

    assert len(questions) == len(contexts) * len(CLOSED_REVIEW_DIMENSIONS)
    assert (
        tuple(question.dimension for question in questions[: len(CLOSED_REVIEW_DIMENSIONS)]) == CLOSED_REVIEW_DIMENSIONS
    )
    assert len({question.question_id for question in questions}) == len(questions)


def test_strict_schema_closes_question_ids_and_all_object_fields() -> None:
    questions = build_closed_review_questions(_context("换位思考不等于没有边界。"))
    schema = closed_review_json_schema(questions)
    properties = schema["properties"]
    assert isinstance(properties, dict)
    answers = properties["answers"]
    assert isinstance(answers, dict)
    answer = answers["items"]
    assert isinstance(answer, dict)
    answer_properties = answer["properties"]
    assert isinstance(answer_properties, dict)

    assert schema["required"] == list(properties)
    assert schema["additionalProperties"] is False
    assert answer["required"] == list(answer_properties)
    assert answer["additionalProperties"] is False
    assert answer_properties["question_id"] == {
        "type": "string",
        "enum": [question.question_id for question in questions],
    }
    assert answer_properties["evidence_scope"] == {
        "type": "string",
        "enum": ["entire_clause", "none"],
    }
    assert "quote" not in answer_properties


@pytest.mark.parametrize("mutation", ("missing", "duplicate", "extra"))
def test_question_answer_coverage_fails_closed(mutation: str) -> None:
    contexts = _context("换位思考不等于没有边界。")
    questions = build_closed_review_questions(contexts)
    raw = _raw_answers(contexts)
    answers = raw["answers"]
    assert isinstance(answers, list)
    if mutation == "missing":
        answers.pop()
    elif mutation == "duplicate":
        answers[-1] = dict(answers[0])
    else:
        extra = dict(answers[-1])
        extra["question_id"] = "unknown-question"
        answers.append(extra)

    with pytest.raises(TypeError, match="coverage"):
        parse_closed_review_answers(raw, questions=questions)


@pytest.mark.parametrize(
    "mutation",
    ("present_without_scope", "absent_with_scope", "unknown_scope"),
)
def test_answer_clause_scope_contract_fails_closed(mutation: str) -> None:
    contexts = _context("换位思考不等于没有边界。")
    questions = build_closed_review_questions(contexts)
    raw = _raw_answers(
        contexts,
        overrides={
            "relationship_claim": (
                "present",
                "换位思考不等于没有边界。",
                ("other_social_relation",),
            )
        },
    )
    answers = raw["answers"]
    assert isinstance(answers, list)
    target = next(
        item for item in answers if isinstance(item, dict) and str(item["question_id"]).endswith(":relationship_claim")
    )
    if mutation == "present_without_scope":
        target["evidence_scope"] = "none"
    elif mutation == "absent_with_scope":
        target["status"] = "absent"
    else:
        target["evidence_scope"] = "partial"

    with pytest.raises(TypeError, match="answer"):
        parse_closed_review_answers(raw, questions=questions)


def test_present_answer_materializes_the_trusted_full_clause() -> None:
    text = "当双方都疲惫时，需要的不是争论对错，而是一个暂停，一份体谅。"
    contexts = _context(text)
    questions = build_closed_review_questions(contexts)
    raw = _raw_answers(
        contexts,
        overrides={
            "motive_or_mental_state": (
                "present",
                "需要的不是争论对错，而是一个暂停，一份体谅。",
                ("need",),
            )
        },
    )

    answers = parse_closed_review_answers(
        raw,
        questions=questions,
    )

    motive = next(
        answer
        for answer in answers.answers
        if answer.question_id.endswith(":motive_or_mental_state")
    )
    assert motive.evidence_scope == "entire_clause"
    assert motive.quote == text


def test_full_clause_scope_does_not_delegate_repeated_text_addressing() -> None:
    contexts = _context("停一下，再停一下。")
    questions = build_closed_review_questions(contexts)
    raw = _raw_answers(
        contexts,
        overrides={
            "actual_event": (
                "present",
                "停一下",
                ("action",),
            )
        },
    )

    answers = parse_closed_review_answers(
        raw,
        questions=questions,
    )

    event = next(
        answer
        for answer in answers.answers
        if answer.question_id.endswith(":actual_event")
    )
    assert event.evidence_scope == "entire_clause"
    assert event.quote == contexts[0].exact_text


def test_uncertain_is_insufficient_and_never_materialized() -> None:
    contexts = _context("这件事也许和此前的经历有关。")
    answers = _parse(
        contexts,
        {
            "subject_binding": (
                "uncertain",
                "这件事也许和此前的经历有关。",
                (),
            )
        },
    )

    result = reconcile_closed_review_answers(
        contexts=contexts,
        questions=build_closed_review_questions(contexts),
        answers=answers,
        fact_text_by_id={},
        protected_subjects=_SCOPE,
    )

    assert tuple(issue.reason for issue in result.issues) == ("insufficient_evidence",)
    assert result.claims == ()


def test_current_g4_relationship_motive_and_cause_are_rejected() -> None:
    text = "忙碌后的拌嘴，看似琐碎，却折射出亲密关系中的期待与默契。"
    contexts = _context(text)
    answers = _parse(
        contexts,
        {
            "subject_binding": (
                "present",
                text,
                ("current_user",),
            ),
            "relationship_claim": (
                "present",
                text,
                ("partner",),
            ),
            "motive_or_mental_state": (
                "present",
                text,
                ("expectation",),
            ),
            "cause_or_result": (
                "present",
                text,
                ("causal_link",),
            ),
            "statement_mode": (
                "present",
                text,
                ("actuality",),
            ),
        },
    )

    assert _reasons(contexts, answers) == ("statement_mode_conflict",)


def test_actuality_cannot_escape_by_claiming_generic_mode() -> None:
    text = "我们两个人其实都渴望被看见。"
    contexts = _context(text)
    answers = _parse(
        contexts,
        {
            "subject_binding": (
                "present",
                text,
                ("current_user",),
            ),
            "relationship_claim": (
                "present",
                text,
                ("partner",),
            ),
            "motive_or_mental_state": (
                "present",
                text,
                ("desire",),
            ),
        },
    )

    assert _reasons(contexts, answers) == ("unsupported_actuality_binding",)


def test_generic_motive_observation_is_allowed() -> None:
    text = "很多争执背后，可能有被看见的需要。"
    contexts = _context(text)
    answers = _parse(
        contexts,
        {
            "subject_binding": (
                "present",
                text,
                ("generic",),
            ),
            "motive_or_mental_state": (
                "present",
                text,
                ("need",),
            ),
        },
    )

    assert _reasons(contexts, answers) == ()


def test_recommendation_and_hypothesis_keep_creative_freedom() -> None:
    recommendation = "双方可以先说一句辛苦了。"
    recommendation_contexts = _context(recommendation)
    recommendation_answers = _parse(
        recommendation_contexts,
        {
            "subject_binding": (
                "present",
                recommendation,
                ("generic",),
            ),
            "dialogue_attribution": (
                "present",
                recommendation,
                ("example_dialogue",),
            ),
            "statement_mode": (
                "present",
                recommendation,
                ("recommendation",),
            ),
        },
    )
    hypothesis = "如果双方先说一句辛苦了，气氛可能会松一点。"
    hypothesis_contexts = _context(hypothesis)
    hypothesis_answers = _parse(
        hypothesis_contexts,
        {
            "subject_binding": (
                "present",
                hypothesis,
                ("generic",),
            ),
            "dialogue_attribution": (
                "present",
                hypothesis,
                ("example_dialogue",),
            ),
            "cause_or_result": (
                "present",
                hypothesis,
                ("result",),
            ),
            "statement_mode": (
                "present",
                hypothesis,
                ("hypothesis",),
            ),
        },
    )

    assert _reasons(recommendation_contexts, recommendation_answers) == ()
    assert _reasons(hypothesis_contexts, hypothesis_answers) == ()


def test_audience_question_is_not_a_recommendation() -> None:
    text = "你们如何看待彼此付出的平衡？"
    contexts = _context(
        text,
        contract="abstract_observation",
    )
    generic = _parse(
        contexts,
        {
            "subject_binding": (
                "present",
                text,
                ("generic",),
            ),
            "relationship_claim": (
                "present",
                text,
                ("other_social_relation",),
            ),
        },
    )
    mislabeled = _parse(
        contexts,
        {
            "subject_binding": (
                "present",
                text,
                ("generic",),
            ),
            "relationship_claim": (
                "present",
                text,
                ("other_social_relation",),
            ),
            "statement_mode": (
                "present",
                text,
                ("recommendation",),
            ),
        },
    )

    assert _reasons(contexts, generic) == ()
    assert _reasons(contexts, mislabeled) == (
        "recommendation_in_observation",
    )


def test_audience_guidance_accepts_safe_summary_invitation_or_condition() -> None:
    summary = "这篇从理解与边界说起。"
    summary_contexts = _context(summary, contract="audience_guidance")
    invitation = "不妨从彼此的付出开始看。"
    invitation_contexts = _context(
        invitation,
        contract="audience_guidance",
    )
    condition = "如果你也常常没有灵感，这篇会提供一个观察角度。"
    condition_contexts = _context(
        condition,
        contract="audience_guidance",
    )
    actuality = "昨天我们终于理解了彼此。"
    actuality_contexts = _context(
        actuality,
        contract="audience_guidance",
    )

    assert _reasons(summary_contexts, _parse(summary_contexts, {})) == ()
    assert (
        _reasons(
            invitation_contexts,
            _parse(
                invitation_contexts,
                {
                    "statement_mode": (
                        "present",
                        invitation,
                        ("recommendation",),
                    )
                },
            ),
        )
        == ()
    )
    assert (
        _reasons(
            condition_contexts,
            _parse(
                condition_contexts,
                {
                    "subject_binding": (
                        "present",
                        condition,
                        ("generic",),
                    ),
                    "statement_mode": (
                        "present",
                        condition,
                        ("hypothesis",),
                    ),
                },
            ),
        )
        == ()
    )
    assert _reasons(
        actuality_contexts,
        _parse(
            actuality_contexts,
            {
                "subject_binding": (
                    "present",
                    actuality,
                    ("current_speaker",),
                ),
                "actual_event": ("present", actuality, ("event",)),
                "statement_mode": (
                    "present",
                    actuality,
                    ("actuality",),
                ),
            },
        ),
    ) == ("statement_mode_conflict",)


def test_product_claim_is_distinct_from_institutional_assertion() -> None:
    text = "这件商品已登记为双面完整外观。"
    contexts = _context(text)
    answers = _parse(
        contexts,
        {
            "subject_binding": (
                "present",
                text,
                ("named_product",),
            ),
            "institutional_or_product_claim": (
                "present",
                text,
                ("product_fact",),
            ),
        },
    )

    assert _reasons(contexts, answers) == ("unsupported_product_claim",)


def test_present_to_absent_mutation_changes_server_ruling() -> None:
    text = "她说：“今天辛苦了”。"
    contexts = _context(text)
    present = _parse(
        contexts,
        {
            "subject_binding": (
                "present",
                text,
                ("generic",),
            ),
            "dialogue_attribution": (
                "present",
                text,
                ("direct_dialogue",),
            ),
        },
    )
    absent = _parse(
        contexts,
        {
            "subject_binding": (
                "present",
                text,
                ("generic",),
            ),
        },
    )

    assert _reasons(contexts, present) == ("situated_event_in_observation",)
    assert _reasons(contexts, absent) == ()


def test_server_rejects_an_omitted_claim_inventory_item() -> None:
    text = "很多争执背后，可能有被看见的需要。"
    contexts = _context(text)
    questions = build_closed_review_questions(contexts)
    answers = _parse(
        contexts,
        {
            "subject_binding": (
                "present",
                text,
                ("generic",),
            ),
            "motive_or_mental_state": (
                "present",
                text,
                ("need",),
            ),
        },
    )
    claims = materialize_claim_inventory(
        contexts=contexts,
        questions=questions,
        answers=answers,
        protected_subjects=_SCOPE,
    )

    assert validate_claim_inventory(
        questions=questions,
        answers=answers,
        claims=claims[:-1],
    )


def test_writer_authored_claim_inventory_is_not_a_valid_input() -> None:
    text = "很多争执背后，可能有被看见的需要。"
    contexts = _context(text)
    questions = build_closed_review_questions(contexts)
    answers = _parse(contexts, {})
    forged = ClaimInventoryItem(
        claim_id="claim:forged",
        clause_id=contexts[0].clause_id,
        claim_kind="motive_or_mental_state",
        statement_mode="generic_observation",
        subject_binding="generic",
        exact_quote=text,
        source_ref=None,
        operands=("need",),
    )

    assert validate_claim_inventory(
        questions=questions,
        answers=answers,
        claims=(forged,),
    )


def test_claim_inventory_is_server_owned_and_immutable() -> None:
    text = "很多争执背后，可能有被看见的需要。"
    contexts = _context(text)
    questions = build_closed_review_questions(contexts)
    answers = _parse(
        contexts,
        {
            "subject_binding": (
                "present",
                text,
                ("generic",),
            ),
            "motive_or_mental_state": (
                "present",
                text,
                ("need",),
            ),
        },
    )
    claims = materialize_claim_inventory(
        contexts=contexts,
        questions=questions,
        answers=answers,
        protected_subjects=_SCOPE,
    )

    with pytest.raises(AttributeError):
        claims[0].claim_kind = "actual_event"  # type: ignore[misc]
    assert replace(claims[0]) == claims[0]
