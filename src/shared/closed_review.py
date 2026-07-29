from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from src.shared.factual_basis import (
    ProductFactPacket,
    product_fact_literal_spans,
)
from src.shared.narrative import NarrativeIssue
from src.shared.review_evidence import (
    ClauseContextV2,
    ProtectedSubjectScopeV2,
    SubjectBindingV2,
    validate_server_owned_contexts_v2,
    writer_clause_contexts_v2,
)

CLOSED_REVIEW_VERSION = "review-evidence-v2"
CLOSED_REVIEW_TOOL_NAME = "submit_review_evidence_v2"

AnswerStatus: TypeAlias = Literal["present", "absent", "uncertain"]
EvidenceScope: TypeAlias = Literal["entire_clause", "none"]
ReviewDimension: TypeAlias = Literal[
    "subject_binding",
    "relationship_claim",
    "actual_event",
    "dialogue_attribution",
    "motive_or_mental_state",
    "cause_or_result",
    "time_location_possession",
    "institutional_or_product_claim",
    "statement_mode",
    "disclosure",
    "product_attribute_claim",
    "product_performance_or_efficacy",
    "product_use_or_wear_result",
    "product_design_motive",
    "product_price_or_inventory",
    "product_comparison_conclusion",
    "product_actual_experience",
    "source_or_resource_as_fact",
]
StatementMode: TypeAlias = Literal[
    "actuality",
    "generic_observation",
    "recommendation",
    "hypothesis",
    "dramatization",
]

CLOSED_REVIEW_DIMENSIONS: tuple[ReviewDimension, ...] = (
    "subject_binding",
    "relationship_claim",
    "actual_event",
    "dialogue_attribution",
    "motive_or_mental_state",
    "cause_or_result",
    "time_location_possession",
    "institutional_or_product_claim",
    "statement_mode",
    "disclosure",
)
PRODUCT_REVIEW_DIMENSIONS: tuple[ReviewDimension, ...] = (
    "product_attribute_claim",
    "product_performance_or_efficacy",
    "product_use_or_wear_result",
    "product_design_motive",
    "product_price_or_inventory",
    "product_comparison_conclusion",
    "product_actual_experience",
    "source_or_resource_as_fact",
)

_STATEMENT_MODES = frozenset(
    {
        "actuality",
        "generic_observation",
        "recommendation",
        "hypothesis",
        "dramatization",
    }
)
_ALLOWED_OPERANDS: dict[ReviewDimension, tuple[str, ...]] = {
    "subject_binding": (
        "current_speaker",
        "current_user",
        "generic",
        "fictional_role",
        "protected_exact_subject",
        "other_specific_person",
        "named_institution",
        "named_product",
    ),
    "relationship_claim": (
        "kinship",
        "partner",
        "family",
        "cohabitation",
        "colleague",
        "employee",
        "customer",
        "other_social_relation",
    ),
    "actual_event": (
        "action",
        "reaction",
        "event",
        "state",
        "completed_state",
    ),
    "dialogue_attribution": (
        "direct_dialogue",
        "reported_dialogue",
        "example_dialogue",
    ),
    "motive_or_mental_state": (
        "desire",
        "expectation",
        "fear",
        "need",
        "intent",
        "belief",
        "emotion",
        "other_mental_state",
    ),
    "cause_or_result": ("cause", "result", "causal_link"),
    "time_location_possession": ("time", "location", "possession"),
    "institutional_or_product_claim": (
        "institution_belief",
        "institution_practice",
        "institution_history",
        "institution_commitment",
        "product_fact",
        "product_performance",
    ),
    "statement_mode": tuple(sorted(_STATEMENT_MODES)),
    "disclosure": (
        "actuality_conflict",
        "hypothesis_scope_conflict",
        "dramatization_scope_conflict",
    ),
    "product_attribute_claim": (
        "hard_attribute",
        "numeric_attribute",
    ),
    "product_performance_or_efficacy": (
        "performance",
        "efficacy",
    ),
    "product_use_or_wear_result": (
        "use_result",
        "wear_result",
    ),
    "product_design_motive": ("design_motive",),
    "product_price_or_inventory": ("price", "inventory"),
    "product_comparison_conclusion": ("comparison_conclusion",),
    "product_actual_experience": ("actual_experience",),
    "source_or_resource_as_fact": (
        "source_as_fact",
        "resource_as_fact",
    ),
}


@dataclass(frozen=True)
class ClosedReviewQuestion:
    question_id: str
    clause_id: str
    dimension: ReviewDimension
    exact_text: str
    visible_order: int
    allowed_quotes: tuple[str, ...]
    allowed_operands: tuple[str, ...]


@dataclass(frozen=True)
class ClosedReviewAnswer:
    question_id: str
    status: AnswerStatus
    evidence_scope: EvidenceScope
    quote: str
    operands: tuple[str, ...]


@dataclass(frozen=True)
class ClosedReviewAnswers:
    evidence_version: str
    answers: tuple[ClosedReviewAnswer, ...]


@dataclass(frozen=True)
class ClaimInventoryItem:
    claim_id: str
    clause_id: str
    claim_kind: ReviewDimension
    statement_mode: StatementMode
    subject_binding: SubjectBindingV2
    exact_quote: str
    source_ref: str | None
    operands: tuple[str, ...]


@dataclass(frozen=True)
class ClosedReviewResult:
    issues: tuple[NarrativeIssue, ...]
    claims: tuple[ClaimInventoryItem, ...]


def build_closed_review_questions(
    contexts: Sequence[ClauseContextV2],
    *,
    product_fact_packet: ProductFactPacket | None = None,
) -> tuple[ClosedReviewQuestion, ...]:
    dimensions = (
        (*CLOSED_REVIEW_DIMENSIONS, *PRODUCT_REVIEW_DIMENSIONS)
        if product_fact_packet is not None and product_fact_packet.facts
        else CLOSED_REVIEW_DIMENSIONS
    )
    questions: list[ClosedReviewQuestion] = []
    for context in writer_clause_contexts_v2(contexts):
        quotes = _unique_quote_candidates(context.exact_text)
        for dimension in dimensions:
            questions.append(
                ClosedReviewQuestion(
                    question_id=(f"{context.clause_id}:risk:{dimension}"),
                    clause_id=context.clause_id,
                    dimension=dimension,
                    exact_text=context.exact_text,
                    visible_order=context.visible_order,
                    allowed_quotes=quotes,
                    allowed_operands=_ALLOWED_OPERANDS[dimension],
                )
            )
    identifiers = tuple(question.question_id for question in questions)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("closed review question ids are duplicated")
    return tuple(questions)


def closed_review_json_schema(
    questions: Sequence[ClosedReviewQuestion],
) -> dict[str, object]:
    question_ids = tuple(question.question_id for question in questions)
    operands = tuple(dict.fromkeys(operand for question in questions for operand in question.allowed_operands))
    answer_properties: dict[str, object] = {
        "question_id": {
            "type": "string",
            "enum": list(question_ids),
        },
        "uncertain": {"type": "boolean"},
        "operands": {
            "type": "array",
            "items": {"type": "string", "enum": list(operands)},
        },
    }
    answer_schema: dict[str, object] = {
        "type": "object",
        "properties": answer_properties,
        "required": list(answer_properties),
        "additionalProperties": False,
    }
    root_properties: dict[str, object] = {
        "evidence_version": {
            "type": "string",
            "enum": [CLOSED_REVIEW_VERSION],
        },
        "answers": {
            "type": "array",
            "items": answer_schema,
        },
    }
    return {
        "type": "object",
        "properties": root_properties,
        "required": list(root_properties),
        "additionalProperties": False,
    }


def parse_closed_review_answers(
    value: object,
    *,
    questions: Sequence[ClosedReviewQuestion],
) -> ClosedReviewAnswers:
    if not isinstance(value, Mapping) or frozenset(value) != {
        "evidence_version",
        "answers",
    }:
        raise TypeError("closed review root is invalid")
    raw_answers = value.get("answers")
    if value.get("evidence_version") != CLOSED_REVIEW_VERSION or not isinstance(raw_answers, list):
        raise TypeError("closed review version is invalid")

    expected = {question.question_id: question for question in questions}
    expected_order = tuple(question.question_id for question in questions)
    parsed: list[ClosedReviewAnswer] = []
    received_ids: list[str] = []
    for raw in raw_answers:
        if not isinstance(raw, Mapping) or frozenset(raw) != {
            "question_id",
            "uncertain",
            "operands",
        }:
            raise TypeError("closed review answer is invalid")
        question_id = _required_string(raw.get("question_id"))
        question = expected.get(question_id)
        if question is None or question_id in received_ids:
            raise TypeError("closed review answer coverage is invalid")
        uncertain = raw.get("uncertain")
        raw_operands = raw.get("operands")
        if (
            not isinstance(uncertain, bool)
            or not isinstance(raw_operands, list)
            or any(not isinstance(item, str) for item in raw_operands)
        ):
            raise TypeError("closed review answer fields are invalid")
        operands = tuple(cast(list[str], raw_operands))
        if len(operands) != len(set(operands)) or any(operand not in question.allowed_operands for operand in operands):
            raise TypeError("closed review answer operands are invalid")
        status: AnswerStatus = (
            "uncertain"
            if uncertain
            else "present"
            if operands
            else "absent"
        )
        if question.dimension == "statement_mode" and (
            status == "absent" or (status == "present" and len(operands) != 1)
        ):
            raise TypeError("closed review statement mode is invalid")
        normalized_scope: EvidenceScope = (
            "entire_clause"
            if status in {"present", "uncertain"}
            else "none"
        )
        received_ids.append(question_id)
        parsed.append(
            ClosedReviewAnswer(
                question_id=question_id,
                status=status,
                evidence_scope=normalized_scope,
                quote=(
                    question.exact_text
                    if normalized_scope == "entire_clause"
                    else ""
                ),
                operands=operands,
            )
        )
    if tuple(received_ids) != expected_order:
        raise TypeError("closed review answer coverage is invalid")
    return ClosedReviewAnswers(
        evidence_version=CLOSED_REVIEW_VERSION,
        answers=tuple(parsed),
    )


def reconcile_closed_review_answers(
    *,
    contexts: Sequence[ClauseContextV2],
    questions: Sequence[ClosedReviewQuestion],
    answers: ClosedReviewAnswers,
    fact_text_by_id: Mapping[str, str],
    protected_subjects: ProtectedSubjectScopeV2,
    product_fact_packet: ProductFactPacket | None = None,
) -> ClosedReviewResult:
    source_issues = validate_server_owned_contexts_v2(
        contexts=contexts,
        fact_text_by_id=fact_text_by_id,
    )
    if source_issues:
        return ClosedReviewResult(source_issues, ())
    expected_questions = build_closed_review_questions(
        contexts,
        product_fact_packet=product_fact_packet,
    )
    if tuple(questions) != expected_questions:
        return ClosedReviewResult(
            (
                NarrativeIssue(
                    "closed-review",
                    "review_question_coverage",
                    "question_set_drift",
                ),
            ),
            (),
        )
    expected_ids = tuple(question.question_id for question in expected_questions)
    received_ids = tuple(answer.question_id for answer in answers.answers)
    if answers.evidence_version != CLOSED_REVIEW_VERSION or received_ids != expected_ids:
        return ClosedReviewResult(
            (
                NarrativeIssue(
                    "closed-review",
                    "review_answer_coverage",
                    "answer_set_drift",
                ),
            ),
            (),
        )
    uncertain = next(
        (answer for answer in answers.answers if answer.status == "uncertain"),
        None,
    )
    if uncertain is not None:
        question = {item.question_id: item for item in expected_questions}[uncertain.question_id]
        return ClosedReviewResult(
            (
                NarrativeIssue(
                    _context_by_clause(contexts)[question.clause_id].unit_id,
                    "insufficient_evidence",
                    uncertain.quote or question.exact_text,
                ),
            ),
            (),
        )
    try:
        claims = materialize_claim_inventory(
            contexts=contexts,
            questions=expected_questions,
            answers=answers,
            protected_subjects=protected_subjects,
        )
    except ValueError:
        return ClosedReviewResult(
            (
                NarrativeIssue(
                    "closed-review",
                    "claim_inventory_drift",
                    "claim_materialization_failed",
                ),
            ),
            (),
        )
    inventory_issues = validate_claim_inventory(
        questions=expected_questions,
        answers=answers,
        claims=claims,
    )
    if inventory_issues:
        return ClosedReviewResult(inventory_issues, ())
    issues = _claim_inventory_issues(
        contexts,
        claims,
        product_fact_packet,
    )
    return ClosedReviewResult(tuple(dict.fromkeys(issues)), claims)


def materialize_claim_inventory(
    *,
    contexts: Sequence[ClauseContextV2],
    questions: Sequence[ClosedReviewQuestion],
    answers: ClosedReviewAnswers,
    protected_subjects: ProtectedSubjectScopeV2,
) -> tuple[ClaimInventoryItem, ...]:
    contexts_by_clause = _context_by_clause(contexts)
    questions_by_id = {question.question_id: question for question in questions}
    answers_by_clause: dict[str, dict[ReviewDimension, ClosedReviewAnswer]] = {}
    for answer in answers.answers:
        question = questions_by_id.get(answer.question_id)
        if question is None:
            raise ValueError("answer has no trusted question")
        answers_by_clause.setdefault(question.clause_id, {})[question.dimension] = answer

    claims: list[ClaimInventoryItem] = []
    for clause_id, dimensions in answers_by_clause.items():
        context = contexts_by_clause.get(clause_id)
        expected_dimensions = {question.dimension for question in questions if question.clause_id == clause_id}
        if context is None or set(dimensions) != expected_dimensions:
            raise ValueError("claim inventory clause coverage drifted")
        mode_answer = dimensions["statement_mode"]
        if mode_answer.status != "present" or len(mode_answer.operands) != 1:
            raise ValueError("claim inventory statement mode drifted")
        mode = cast(StatementMode, mode_answer.operands[0])
        if mode not in _STATEMENT_MODES:
            raise ValueError("claim inventory statement mode is invalid")
        binding = _binding_from_answer(
            dimensions["subject_binding"],
            context,
            protected_subjects,
        )
        for dimension in tuple(question.dimension for question in questions if question.clause_id == clause_id):
            answer = dimensions[dimension]
            if answer.status != "present":
                continue
            claims.append(
                ClaimInventoryItem(
                    claim_id=f"claim:{clause_id}:{dimension}",
                    clause_id=clause_id,
                    claim_kind=dimension,
                    statement_mode=mode,
                    subject_binding=binding,
                    exact_quote=answer.quote,
                    source_ref=context.fact_ref,
                    operands=answer.operands,
                )
            )
    identifiers = tuple(claim.claim_id for claim in claims)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("claim inventory ids are duplicated")
    return tuple(claims)


def claim_inventory_document(
    claims: Sequence[ClaimInventoryItem],
) -> list[dict[str, object]]:
    return [
        {
            "claim_id": claim.claim_id,
            "clause_id": claim.clause_id,
            "claim_kind": claim.claim_kind,
            "statement_mode": claim.statement_mode,
            "subject_binding": claim.subject_binding,
            "exact_quote": claim.exact_quote,
            "source_ref": claim.source_ref,
            "operands": list(claim.operands),
        }
        for claim in claims
    ]


def validate_claim_inventory(
    *,
    questions: Sequence[ClosedReviewQuestion],
    answers: ClosedReviewAnswers,
    claims: Sequence[ClaimInventoryItem],
) -> tuple[NarrativeIssue, ...]:
    question_by_id = {question.question_id: question for question in questions}
    expected = {
        (
            f"claim:{question.clause_id}:{question.dimension}",
            question.clause_id,
            question.dimension,
            answer.quote,
            answer.operands,
        )
        for answer in answers.answers
        if answer.status == "present"
        for question in (question_by_id[answer.question_id],)
    }
    actual = {
        (
            claim.claim_id,
            claim.clause_id,
            claim.claim_kind,
            claim.exact_quote,
            claim.operands,
        )
        for claim in claims
    }
    if expected == actual and len(actual) == len(claims):
        return ()
    return (
        NarrativeIssue(
            "closed-review",
            "claim_inventory_drift",
            "claim_inventory_coverage",
        ),
    )


def _claim_inventory_issues(
    contexts: Sequence[ClauseContextV2],
    claims: Sequence[ClaimInventoryItem],
    product_fact_packet: ProductFactPacket | None,
) -> list[NarrativeIssue]:
    claims_by_clause: dict[str, dict[ReviewDimension, ClaimInventoryItem]] = {}
    for claim in claims:
        claims_by_clause.setdefault(claim.clause_id, {})[claim.claim_kind] = claim
    issues: list[NarrativeIssue] = []
    for context in writer_clause_contexts_v2(contexts):
        clause_claims = claims_by_clause.get(context.clause_id, {})
        mode_claim = clause_claims.get("statement_mode")
        if mode_claim is None:
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    "claim_inventory_drift",
                    context.exact_text,
                )
            )
            continue
        mode = mode_claim.statement_mode
        binding = mode_claim.subject_binding
        dimensions = frozenset(clause_claims)
        packet_fact_ids = product_fact_packet.fact_ids if product_fact_packet is not None else frozenset()
        if any(ref not in packet_fact_ids for ref in context.claim_refs):
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    "unsupported_product_claim",
                    context.exact_text,
                )
            )
            continue
        literal_spans = (
            product_fact_literal_spans(
                product_fact_packet,
                context.exact_text,
            )
            if product_fact_packet is not None
            else ()
        )
        if literal_spans:
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    "product_fact_must_use_immutable_block",
                    literal_spans[0],
                )
            )
            continue
        product_risk = next(
            (dimension for dimension in PRODUCT_REVIEW_DIMENSIONS if dimension in dimensions),
            None,
        )
        if product_risk is not None:
            reason = (
                "product_fact_must_use_immutable_block"
                if product_risk == "product_attribute_claim"
                else "unsupported_product_inference"
            )
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    reason,
                    clause_claims[product_risk].exact_quote,
                )
            )
            continue
        if "disclosure" in dimensions:
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    "disclosure_conflict",
                    clause_claims["disclosure"].exact_quote,
                )
            )
            continue
        if "institutional_or_product_claim" in dimensions:
            product_operands = {
                "product_fact",
                "product_performance",
            }
            reason = (
                "unsupported_product_claim"
                if set(clause_claims["institutional_or_product_claim"].operands) & product_operands
                else "unsupported_institutional_assertion"
            )
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    reason,
                    clause_claims["institutional_or_product_claim"].exact_quote,
                )
            )
            continue
        if binding in {
            "current_institution",
            "protected_exact_subject",
        }:
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    "unsupported_institutional_assertion",
                    mode_claim.exact_quote,
                )
            )
            continue
        compatibility_issue = _contract_mode_issue(
            context,
            mode,
            mode_claim.exact_quote,
        )
        if compatibility_issue is not None:
            issues.append(compatibility_issue)
            continue
        event_claim = clause_claims.get("actual_event")
        event_operands = (
            set(event_claim.operands)
            if event_claim is not None
            else set()
        )
        if event_claim is not None and (
            mode == "actuality"
            or (
                mode == "generic_observation"
                and bool(
                    event_operands
                    & {"action", "event", "reaction"}
                )
            )
        ):
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    (
                        "situated_event_in_observation"
                        if mode == "generic_observation"
                        else "unsupported_actuality_expansion"
                    ),
                    event_claim.exact_quote,
                )
            )
            continue
        if binding == "current_person" and dimensions & {
            "relationship_claim",
            "dialogue_attribution",
            "motive_or_mental_state",
            "cause_or_result",
            "time_location_possession",
        }:
            risk = next(
                dimension
                for dimension in (
                    *CLOSED_REVIEW_DIMENSIONS,
                    *PRODUCT_REVIEW_DIMENSIONS,
                )
                if dimension in dimensions and dimension not in {"subject_binding", "statement_mode"}
            )
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    "unsupported_actuality_binding",
                    clause_claims[risk].exact_quote,
                )
            )
            continue
        if mode == "actuality" and dimensions & {
            "relationship_claim",
            "dialogue_attribution",
            "motive_or_mental_state",
            "cause_or_result",
            "time_location_possession",
        }:
            risk = next(
                dimension
                for dimension in (
                    *CLOSED_REVIEW_DIMENSIONS,
                    *PRODUCT_REVIEW_DIMENSIONS,
                )
                if dimension in dimensions and dimension not in {"subject_binding", "statement_mode"}
            )
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    "unsupported_actuality_expansion",
                    clause_claims[risk].exact_quote,
                )
            )
            continue
        if mode == "generic_observation" and "dialogue_attribution" in dimensions:
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    "situated_event_in_observation",
                    clause_claims["dialogue_attribution"].exact_quote,
                )
            )
            continue
        if binding == "current_person" and mode == "actuality":
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    "unsupported_actuality_binding",
                    mode_claim.exact_quote,
                )
            )
    return issues


def _contract_mode_issue(
    context: ClauseContextV2,
    mode: StatementMode,
    fragment: str,
) -> NarrativeIssue | None:
    contract = context.unit_contract
    allowed: dict[str, frozenset[StatementMode]] = {
        "abstract_observation": frozenset({"generic_observation"}),
        "audience_guidance": frozenset(
            {"generic_observation", "recommendation", "hypothesis"}
        ),
        "recommendation": frozenset({"recommendation"}),
        "hypothetical_example": frozenset({"hypothesis"}),
        "disclosed_dramatization": frozenset({"dramatization"}),
        "actuality_reflection": frozenset({"generic_observation", "recommendation", "hypothesis"}),
    }
    if mode in allowed.get(contract, frozenset()):
        return None
    reason = (
        "recommendation_in_observation"
        if contract == "abstract_observation" and mode == "recommendation"
        else "statement_mode_conflict"
    )
    return NarrativeIssue(context.unit_id, reason, fragment)


def _binding_from_answer(
    answer: ClosedReviewAnswer,
    context: ClauseContextV2,
    protected_subjects: ProtectedSubjectScopeV2,
) -> SubjectBindingV2:
    if answer.status == "uncertain":
        return "uncertain"
    if answer.status == "absent":
        return "none"
    operands = set(answer.operands)
    if "protected_exact_subject" in operands:
        if not any(name and name in answer.quote for name in protected_subjects.exact_names):
            raise ValueError("protected subject operand has no trusted name")
        return "protected_exact_subject"
    if "named_institution" in operands or "named_product" in operands:
        return "protected_exact_subject"
    if "current_speaker" in operands:
        if context.speaker_kind == "institutional_account":
            return "current_institution"
        if context.speaker_kind == "personal_ip_account":
            return "current_person"
        return "uncertain"
    if "current_user" in operands:
        return "current_person"
    if "generic" in operands:
        return "generic"
    if operands & {"fictional_role", "other_specific_person"}:
        return "fictional_role"
    return "none"


def _context_by_clause(
    contexts: Sequence[ClauseContextV2],
) -> dict[str, ClauseContextV2]:
    return {context.clause_id: context for context in writer_clause_contexts_v2(contexts)}


def _unique_quote_candidates(exact_text: str) -> tuple[str, ...]:
    candidates: list[str] = [exact_text]
    start = 0
    for index, character in enumerate(exact_text):
        if character not in "，,、：:；;。！？.!?\n":
            continue
        chunk = exact_text[start : index + 1]
        if chunk.strip() and _quote_is_unique(exact_text, chunk):
            candidates.append(chunk)
        start = index + 1
    tail = exact_text[start:]
    if tail.strip() and _quote_is_unique(exact_text, tail):
        candidates.append(tail)
    return tuple(dict.fromkeys(candidates))


def _quote_is_unique(exact_text: str, quote: str) -> bool:
    return len(_exact_match_starts(exact_text, quote)) == 1


def _exact_match_starts(text: str, quote: str) -> tuple[int, ...]:
    if not quote:
        return ()
    starts: list[int] = []
    offset = 0
    while True:
        index = text.find(quote, offset)
        if index < 0:
            return tuple(starts)
        starts.append(index)
        offset = index + 1


def _required_string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError("field must be a non-empty string")
    return value
