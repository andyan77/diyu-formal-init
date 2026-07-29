from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from src.shared.narrative import NarrativeFrame, NarrativeIssue
from src.shared.review_evidence import (
    ClauseContextV2,
    TextSourceV2,
    UnitContractV2,
    validate_server_owned_contexts_v2,
    writer_clause_contexts_v2,
)

CLAUSE_LICENSE_VERSION = "clause-license-v1"
CLAUSE_LICENSE_REVIEW_VERSION = "clause-license-review-v1"
CLAUSE_LICENSE_TOOL_NAME = "submit_clause_license_reviews_v1"

SubjectScopeV1: TypeAlias = Literal[
    "generic_only",
    "generic_or_fictional",
    "fictional_only",
]
ProhibitedBindingV1: TypeAlias = Literal[
    "current_person",
    "current_institution",
    "protected_exact_subject",
    "specific_social_relation_to_actuality",
    "unfrozen_dialogue",
    "actual_event_or_result",
    "unsupported_institution_fact",
    "unsupported_product_fact",
    "source_or_resource_as_fact",
    "discourse_contract_drift",
]
LicenseVerdictV1: TypeAlias = Literal[
    "supported",
    "unsupported",
    "uncertain",
]
LicenseReasonCodeV1: TypeAlias = Literal[
    "supported_by_license",
    "current_person",
    "current_institution",
    "protected_exact_subject",
    "specific_social_relation_to_actuality",
    "unfrozen_dialogue",
    "actual_event_or_result",
    "unsupported_institution_fact",
    "unsupported_product_fact",
    "source_or_resource_as_fact",
    "discourse_contract_drift",
    "insufficient_evidence",
]

_BASE_PROHIBITED_BINDINGS: tuple[ProhibitedBindingV1, ...] = (
    "current_person",
    "current_institution",
    "protected_exact_subject",
    "unsupported_institution_fact",
    "unsupported_product_fact",
    "source_or_resource_as_fact",
    "discourse_contract_drift",
)
_ACTUALITY_PROHIBITED_BINDINGS: tuple[ProhibitedBindingV1, ...] = (
    "specific_social_relation_to_actuality",
    "unfrozen_dialogue",
    "actual_event_or_result",
)
_ABSTRACT_PROHIBITED_BINDINGS: tuple[ProhibitedBindingV1, ...] = (
    "unfrozen_dialogue",
    "actual_event_or_result",
)
_REASON_CODES = frozenset(
    {
        "supported_by_license",
        "current_person",
        "current_institution",
        "protected_exact_subject",
        "specific_social_relation_to_actuality",
        "unfrozen_dialogue",
        "actual_event_or_result",
        "unsupported_institution_fact",
        "unsupported_product_fact",
        "source_or_resource_as_fact",
        "discourse_contract_drift",
        "insufficient_evidence",
    }
)


@dataclass(frozen=True)
class UnitClauseLicensePolicyV1:
    """Trusted policy frozen from the server skeleton before Writer execution."""

    unit_id: str
    discourse_contract: UnitContractV2
    subject_scope: SubjectScopeV1
    allowed_fact_refs: tuple[str, ...]
    prohibited_bindings: tuple[ProhibitedBindingV1, ...]


@dataclass(frozen=True)
class ClauseLicenseV1:
    license_version: str
    license_id: str
    clause_id: str
    unit_id: str
    text_source: TextSourceV2
    discourse_contract: UnitContractV2
    subject_scope: SubjectScopeV1
    allowed_fact_refs: tuple[str, ...]
    prohibited_bindings: tuple[ProhibitedBindingV1, ...]


@dataclass(frozen=True)
class ClauseLicenseReviewV1:
    clause_id: str
    license_id: str
    verdict: LicenseVerdictV1
    reason_code: LicenseReasonCodeV1
    unsupported_quote: str


@dataclass(frozen=True)
class ClauseLicenseReviewsV1:
    review_version: str
    reviews: tuple[ClauseLicenseReviewV1, ...]


@dataclass(frozen=True)
class ClauseLicenseResultV1:
    issues: tuple[NarrativeIssue, ...]


def build_unit_clause_license_policies_v1(
    *,
    frame: NarrativeFrame,
    unit_contracts: Mapping[str, UnitContractV2],
) -> tuple[UnitClauseLicensePolicyV1, ...]:
    """Freeze one semantic policy per server-owned writable unit before Writer runs."""
    actuality_scope = frame.narrative_mode == "actuality_reflection"
    policies: list[UnitClauseLicensePolicyV1] = []
    for unit_id, contract in unit_contracts.items():
        if contract == "frozen_fact":
            continue
        subject_scope: SubjectScopeV1 = (
            "fictional_only"
            if contract == "disclosed_dramatization"
            else "generic_or_fictional"
            if contract == "hypothetical_example"
            else "generic_only"
        )
        prohibited = list(_BASE_PROHIBITED_BINDINGS)
        if actuality_scope:
            prohibited.extend(_ACTUALITY_PROHIBITED_BINDINGS)
        elif contract in {"abstract_observation", "audience_guidance"}:
            prohibited.extend(_ABSTRACT_PROHIBITED_BINDINGS)
        elif contract == "recommendation":
            prohibited.append("unfrozen_dialogue")
        policies.append(
            UnitClauseLicensePolicyV1(
                unit_id=unit_id,
                discourse_contract=contract,
                subject_scope=subject_scope,
                allowed_fact_refs=(),
                prohibited_bindings=tuple(dict.fromkeys(prohibited)),
            )
        )
    identifiers = tuple(policy.unit_id for policy in policies)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("unit clause license policies are duplicated")
    return tuple(policies)


def materialize_clause_licenses_v1(
    *,
    contexts: Sequence[ClauseContextV2],
    policies: Sequence[UnitClauseLicensePolicyV1],
) -> tuple[ClauseLicenseV1, ...]:
    """Bind the pre-Writer unit policy to every deterministic writer-owned clause."""
    policy_by_unit = {policy.unit_id: policy for policy in policies}
    if len(policy_by_unit) != len(policies):
        raise ValueError("unit clause license policies are duplicated")
    licenses: list[ClauseLicenseV1] = []
    for context in writer_clause_contexts_v2(contexts):
        policy = policy_by_unit.get(context.unit_id)
        if policy is None or policy.discourse_contract != context.unit_contract:
            raise ValueError("writer clause has no trusted pre-Writer license policy")
        licenses.append(
            ClauseLicenseV1(
                license_version=CLAUSE_LICENSE_VERSION,
                license_id=f"license:{context.clause_id}",
                clause_id=context.clause_id,
                unit_id=context.unit_id,
                text_source=context.text_source,
                discourse_contract=policy.discourse_contract,
                subject_scope=policy.subject_scope,
                allowed_fact_refs=policy.allowed_fact_refs,
                prohibited_bindings=policy.prohibited_bindings,
            )
        )
    identifiers = tuple(license_.license_id for license_ in licenses)
    clause_ids = tuple(license_.clause_id for license_ in licenses)
    if not licenses or len(identifiers) != len(set(identifiers)) or len(clause_ids) != len(set(clause_ids)):
        raise ValueError("clause license coverage is invalid")
    return tuple(licenses)


def clause_license_review_json_schema(
    licenses: Sequence[ClauseLicenseV1],
) -> dict[str, object]:
    clause_ids = tuple(license_.clause_id for license_ in licenses)
    license_ids = tuple(license_.license_id for license_ in licenses)
    review_properties: dict[str, object] = {
        "clause_id": {"type": "string", "enum": list(clause_ids)},
        "license_id": {"type": "string", "enum": list(license_ids)},
        "verdict": {
            "type": "string",
            "enum": ["supported", "unsupported", "uncertain"],
        },
        "reason_code": {
            "type": "string",
            "enum": sorted(_REASON_CODES),
        },
        "unsupported_quote": {"type": "string"},
    }
    review_schema: dict[str, object] = {
        "type": "object",
        "properties": review_properties,
        "required": list(review_properties),
        "additionalProperties": False,
    }
    root_properties: dict[str, object] = {
        "review_version": {
            "type": "string",
            "enum": [CLAUSE_LICENSE_REVIEW_VERSION],
        },
        "reviews": {
            "type": "array",
            "items": review_schema,
        },
    }
    return {
        "type": "object",
        "properties": root_properties,
        "required": list(root_properties),
        "additionalProperties": False,
    }


def parse_clause_license_reviews_v1(
    value: object,
    *,
    licenses: Sequence[ClauseLicenseV1],
) -> ClauseLicenseReviewsV1:
    if not isinstance(value, Mapping) or frozenset(value) != {
        "review_version",
        "reviews",
    }:
        raise TypeError("clause license review root is invalid")
    raw_reviews = value.get("reviews")
    if value.get("review_version") != CLAUSE_LICENSE_REVIEW_VERSION or not isinstance(raw_reviews, list):
        raise TypeError("clause license review version is invalid")
    expected = {license_.clause_id: license_ for license_ in licenses}
    expected_order = tuple(license_.clause_id for license_ in licenses)
    reviews: list[ClauseLicenseReviewV1] = []
    received_ids: list[str] = []
    for raw in raw_reviews:
        if not isinstance(raw, Mapping) or frozenset(raw) != {
            "clause_id",
            "license_id",
            "verdict",
            "reason_code",
            "unsupported_quote",
        }:
            raise TypeError("clause license review is invalid")
        clause_id = _required_string(raw.get("clause_id"))
        license_id = _required_string(raw.get("license_id"))
        verdict = raw.get("verdict")
        reason_code = raw.get("reason_code")
        unsupported_quote = raw.get("unsupported_quote")
        license_ = expected.get(clause_id)
        if (
            license_ is None
            or clause_id in received_ids
            or license_id != license_.license_id
            or verdict not in {"supported", "unsupported", "uncertain"}
            or reason_code not in _REASON_CODES
            or not isinstance(unsupported_quote, str)
        ):
            raise TypeError("clause license review fields are invalid")
        if verdict == "supported" and (reason_code != "supported_by_license" or unsupported_quote):
            raise TypeError("supported clause license review is invalid")
        if verdict == "uncertain" and (reason_code != "insufficient_evidence" or unsupported_quote):
            raise TypeError("uncertain clause license review is invalid")
        if verdict == "unsupported" and (
            reason_code in {"supported_by_license", "insufficient_evidence"} or not unsupported_quote
        ):
            raise TypeError("unsupported clause license review is invalid")
        received_ids.append(clause_id)
        reviews.append(
            ClauseLicenseReviewV1(
                clause_id=clause_id,
                license_id=license_id,
                verdict=cast(LicenseVerdictV1, verdict),
                reason_code=cast(LicenseReasonCodeV1, reason_code),
                unsupported_quote=unsupported_quote,
            )
        )
    if tuple(received_ids) != expected_order:
        raise TypeError("clause license review coverage is invalid")
    return ClauseLicenseReviewsV1(
        review_version=CLAUSE_LICENSE_REVIEW_VERSION,
        reviews=tuple(reviews),
    )


def reconcile_clause_license_reviews_v1(
    *,
    contexts: Sequence[ClauseContextV2],
    policies: Sequence[UnitClauseLicensePolicyV1],
    licenses: Sequence[ClauseLicenseV1],
    reviews: ClauseLicenseReviewsV1,
    fact_text_by_id: Mapping[str, str],
) -> ClauseLicenseResultV1:
    source_issues = validate_server_owned_contexts_v2(
        contexts=contexts,
        fact_text_by_id=fact_text_by_id,
    )
    if source_issues:
        return ClauseLicenseResultV1(source_issues)
    expected_contexts = writer_clause_contexts_v2(contexts)
    expected_clause_ids = tuple(context.clause_id for context in expected_contexts)
    try:
        expected_licenses = materialize_clause_licenses_v1(
            contexts=contexts,
            policies=policies,
        )
    except ValueError:
        return ClauseLicenseResultV1(
            (
                NarrativeIssue(
                    "clause-license",
                    "license_assignment_drift",
                    "clause_license_policy_mismatch",
                ),
            )
        )
    if (
        reviews.review_version != CLAUSE_LICENSE_REVIEW_VERSION
        or tuple(licenses) != expected_licenses
        or tuple(license_.clause_id for license_ in licenses) != expected_clause_ids
        or tuple(review.clause_id for review in reviews.reviews) != expected_clause_ids
    ):
        return ClauseLicenseResultV1(
            (
                NarrativeIssue(
                    "clause-license",
                    "license_review_coverage",
                    "clause_or_license_set_drift",
                ),
            )
        )
    context_by_clause = {context.clause_id: context for context in expected_contexts}
    license_by_clause = {license_.clause_id: license_ for license_ in licenses}
    if len(license_by_clause) != len(licenses):
        return ClauseLicenseResultV1(
            (
                NarrativeIssue(
                    "clause-license",
                    "license_assignment_drift",
                    "clause_license_mismatch",
                ),
            )
        )
    issues: list[NarrativeIssue] = []
    for review in reviews.reviews:
        context = context_by_clause[review.clause_id]
        license_ = license_by_clause[review.clause_id]
        if review.license_id != license_.license_id:
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    "license_assignment_drift",
                    context.exact_text,
                )
            )
            continue
        if review.verdict == "uncertain":
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    "insufficient_evidence",
                    context.exact_text,
                )
            )
            continue
        if review.verdict == "supported":
            continue
        if len(_exact_match_starts(context.exact_text, review.unsupported_quote)) != 1:
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    "license_review_quote",
                    review.unsupported_quote,
                )
            )
            continue
        issues.append(
            NarrativeIssue(
                context.unit_id,
                _issue_reason(review.reason_code),
                review.unsupported_quote,
            )
        )
    return ClauseLicenseResultV1(tuple(dict.fromkeys(issues)))


def clause_license_document(
    licenses: Sequence[ClauseLicenseV1],
) -> list[dict[str, object]]:
    return [
        {
            "license_version": license_.license_version,
            "license_id": license_.license_id,
            "clause_id": license_.clause_id,
            "unit_id": license_.unit_id,
            "text_source": license_.text_source,
            "discourse_contract": license_.discourse_contract,
            "subject_scope": license_.subject_scope,
            "allowed_fact_refs": list(license_.allowed_fact_refs),
            "prohibited_bindings": list(license_.prohibited_bindings),
        }
        for license_ in licenses
    ]


def clause_license_review_document(
    reviews: ClauseLicenseReviewsV1,
) -> dict[str, object]:
    return {
        "review_version": reviews.review_version,
        "reviews": [
            {
                "clause_id": review.clause_id,
                "license_id": review.license_id,
                "verdict": review.verdict,
                "reason_code": review.reason_code,
                "unsupported_quote": review.unsupported_quote,
            }
            for review in reviews.reviews
        ],
    }


def _issue_reason(reason_code: LicenseReasonCodeV1) -> str:
    if reason_code == "current_person":
        return "unsupported_actuality_binding"
    if reason_code in {
        "current_institution",
        "protected_exact_subject",
        "unsupported_institution_fact",
    }:
        return "unsupported_institutional_assertion"
    if reason_code == "unsupported_product_fact":
        return "unsupported_product_claim"
    if reason_code == "source_or_resource_as_fact":
        return "unsupported_product_inference"
    if reason_code == "discourse_contract_drift":
        return "statement_mode_conflict"
    return "unsupported_actuality_expansion"


def _exact_match_starts(exact_text: str, quote: str) -> tuple[int, ...]:
    if not quote:
        return ()
    starts: list[int] = []
    cursor = 0
    while True:
        index = exact_text.find(quote, cursor)
        if index < 0:
            return tuple(starts)
        starts.append(index)
        cursor = index + 1


def _required_string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError("required string is invalid")
    return value
