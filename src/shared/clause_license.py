from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from src.shared.factual_basis import (
    ProductFactPacket,
    product_fact_literal_spans,
)
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
LicenseExpressionTypeV1: TypeAlias = Literal[
    "generic_observation",
    "recommendation",
    "non_situated_metaphor",
    "hypothetical_expression",
    "dramatized_expression",
]
BindingCheckStatusV1: TypeAlias = Literal[
    "absent",
    "present",
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
    "specific_social_relation_to_actuality",
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
_EXPRESSION_TYPES: tuple[LicenseExpressionTypeV1, ...] = (
    "generic_observation",
    "recommendation",
    "non_situated_metaphor",
    "hypothetical_expression",
    "dramatized_expression",
)
_BINDING_CHECK_STATUSES: tuple[BindingCheckStatusV1, ...] = (
    "absent",
    "present",
    "uncertain",
)
_PROHIBITED_BINDING_QUESTIONS: dict[
    ProhibitedBindingV1,
    str,
] = {
    "current_person": (
        "这条文字是否把新增关系、经历、动作、心理、因果或结果绑定为当前用户或当前真人的现实？"
    ),
    "current_institution": (
        "这条文字是否让当前品牌、组织、门店或账号承担观点、做法、经历、承诺或历史？"
    ),
    "protected_exact_subject": (
        "这条文字是否直接或指代性地绑定服务端保护的精确主体？"
    ),
    "specific_social_relation_to_actuality": (
        "这条文字是否把亲属、伴侣、家庭、同住、同事、员工、顾客或其他具体社会关系"
        "实例化为当前现实或未披露的具体处境？"
    ),
    "unfrozen_dialogue": (
        "这条文字是否新增任何直接对白、转述、具体说法或言语归属？"
    ),
    "actual_event_or_result": (
        "这条文字是否让人物做事、反应、产生心理或动机、形成事件链或得到结果，"
        "而不只是非情境化比喻、一般判断或清楚建议？"
    ),
    "unsupported_institution_fact": (
        "这条文字是否新增机构事实、经营做法、历史、信念或承诺且没有精确事实来源？"
    ),
    "unsupported_product_fact": (
        "即使位于虚构场景、角色对白或假设举例，这条文字是否仍新增、复述或推导了没有"
        "事实许可的商品属性、数字、性能、用途、效果、价格、库存、设计动机、比较或实际体验？"
    ),
    "source_or_resource_as_fact": (
        "这条文字是否把资料来源、表达约束或制作资源当成现实或商品事实许可证？"
    ),
    "discourse_contract_drift": (
        "这条文字的实际语态是否超出服务端允许的表达类型或服务端披露范围？"
    ),
}
_QUOTE_BOUNDARIES = frozenset('，,、：:；;。！？.!?\n"')


@dataclass(frozen=True)
class UnitClauseLicensePolicyV1:
    """Trusted policy frozen from the server skeleton before Writer execution."""

    unit_id: str
    discourse_contract: UnitContractV2
    subject_scope: SubjectScopeV1
    allowed_expression_types: tuple[LicenseExpressionTypeV1, ...]
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
    allowed_expression_types: tuple[LicenseExpressionTypeV1, ...]
    allowed_fact_refs: tuple[str, ...]
    prohibited_bindings: tuple[ProhibitedBindingV1, ...]


@dataclass(frozen=True)
class ProhibitedBindingCheckV1:
    binding_id: ProhibitedBindingV1
    status: BindingCheckStatusV1


@dataclass(frozen=True)
class ClauseLicenseReviewV1:
    clause_id: str
    license_id: str
    verdict: LicenseVerdictV1
    expression_type: LicenseExpressionTypeV1
    binding_checks: tuple[ProhibitedBindingCheckV1, ...]
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
                allowed_expression_types=_allowed_expression_types(contract),
                allowed_fact_refs=(),
                prohibited_bindings=tuple(dict.fromkeys(prohibited)),
            )
        )
    identifiers = tuple(policy.unit_id for policy in policies)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("unit clause license policies are duplicated")
    return tuple(policies)


def prohibited_binding_question_v1(
    binding_id: ProhibitedBindingV1,
) -> str:
    """Return the stable closed question carried by one binding ID."""
    return _PROHIBITED_BINDING_QUESTIONS[binding_id]


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
                allowed_expression_types=policy.allowed_expression_types,
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
        "expression_type": {
            "type": "string",
            "enum": list(_EXPRESSION_TYPES),
        },
        "binding_checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "binding_id": {
                        "type": "string",
                        "enum": sorted({binding for license_ in licenses for binding in license_.prohibited_bindings}),
                    },
                    "status": {
                        "type": "string",
                        "enum": list(_BINDING_CHECK_STATUSES),
                    },
                },
                "required": ["binding_id", "status"],
                "additionalProperties": False,
            },
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
        if not isinstance(raw, Mapping):
            raise TypeError("clause license review is invalid")
        raw_fields = frozenset(raw)
        proof_fields = {
            "clause_id",
            "license_id",
            "expression_type",
            "binding_checks",
            "unsupported_quote",
        }
        legacy_fields = {
            "clause_id",
            "license_id",
            "verdict",
            "expression_type",
            "binding_checks",
            "reason_code",
            "unsupported_quote",
        }
        if raw_fields not in {
            frozenset(proof_fields),
            frozenset(legacy_fields),
        }:
            raise TypeError("clause license review is invalid")
        clause_id = _required_string(raw.get("clause_id"))
        license_id = _required_string(raw.get("license_id"))
        expression_type = raw.get("expression_type")
        raw_binding_checks = raw.get("binding_checks")
        unsupported_quote = raw.get("unsupported_quote")
        license_ = expected.get(clause_id)
        if (
            license_ is None
            or clause_id in received_ids
            or license_id != license_.license_id
            or expression_type not in _EXPRESSION_TYPES
            or not isinstance(raw_binding_checks, list)
            or not isinstance(unsupported_quote, str)
        ):
            raise TypeError("clause license review fields are invalid")
        binding_checks = _parse_binding_checks(
            raw_binding_checks,
            license_=license_,
        )
        statuses = tuple(check.status for check in binding_checks)
        present_bindings = {check.binding_id for check in binding_checks if check.status == "present"}
        if raw_fields == frozenset(legacy_fields):
            verdict = raw.get("verdict")
            reason_code = raw.get("reason_code")
            if (
                verdict not in {
                    "supported",
                    "unsupported",
                    "uncertain",
                }
                or reason_code not in _REASON_CODES
            ):
                raise TypeError(
                    "clause license review fields are invalid"
                )
        elif "uncertain" in statuses:
            verdict = "uncertain"
            reason_code = "insufficient_evidence"
        elif present_bindings:
            verdict = "unsupported"
            reason_code = next(
                binding
                for binding in license_.prohibited_bindings
                if binding in present_bindings
            )
        else:
            verdict = "supported"
            reason_code = "supported_by_license"
        if verdict == "supported" and (
            reason_code != "supported_by_license"
            or unsupported_quote
            or expression_type not in license_.allowed_expression_types
            or any(status != "absent" for status in statuses)
        ):
            raise TypeError("supported clause license review is invalid")
        if verdict == "uncertain" and (
            reason_code != "insufficient_evidence"
            or unsupported_quote
            or "uncertain" not in statuses
            or "present" in statuses
        ):
            raise TypeError("uncertain clause license review is invalid")
        if verdict == "unsupported" and (
            reason_code in {"supported_by_license", "insufficient_evidence"}
            or reason_code not in license_.prohibited_bindings
            or reason_code not in present_bindings
            or "uncertain" in statuses
            or not unsupported_quote
        ):
            raise TypeError("unsupported clause license review is invalid")
        received_ids.append(clause_id)
        reviews.append(
            ClauseLicenseReviewV1(
                clause_id=clause_id,
                license_id=license_id,
                verdict=cast(LicenseVerdictV1, verdict),
                expression_type=cast(
                    LicenseExpressionTypeV1,
                    expression_type,
                ),
                binding_checks=binding_checks,
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
    product_fact_packet: ProductFactPacket | None = None,
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
        if product_fact_packet is not None:
            if any(fact_ref not in product_fact_packet.fact_ids for fact_ref in context.claim_refs):
                issues.append(
                    NarrativeIssue(
                        context.unit_id,
                        "unsupported_product_claim",
                        context.exact_text,
                    )
                )
                continue
            literal_spans = product_fact_literal_spans(
                product_fact_packet,
                context.exact_text,
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
        proof_issue = _license_proof_issue(
            context=context,
            license_=license_,
            review=review,
        )
        if proof_issue is not None:
            issues.append(proof_issue)
            continue
        uncertain_checks = tuple(check for check in review.binding_checks if check.status == "uncertain")
        if uncertain_checks:
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    "insufficient_evidence",
                    context.exact_text,
                )
            )
            continue
        present_checks = tuple(check for check in review.binding_checks if check.status == "present")
        if not present_checks:
            continue
        if (
            len(review.unsupported_quote.strip()) < 2
            or len(
                _exact_match_starts(
                    context.exact_text,
                    review.unsupported_quote,
                )
            )
            != 1
        ):
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    "license_review_quote",
                    review.unsupported_quote,
                )
            )
            continue
        issues.extend(
            NarrativeIssue(
                context.unit_id,
                _issue_reason(check.binding_id),
                review.unsupported_quote,
            )
            for check in present_checks
        )
    return ClauseLicenseResultV1(tuple(dict.fromkeys(issues)))


def unsupported_quote_candidates_v1(exact_text: str) -> tuple[str, ...]:
    """Return small, quote-safe exact substrings with unique clause identity."""
    candidates: list[str] = []
    start = 0
    for index, character in enumerate(exact_text):
        if character not in _QUOTE_BOUNDARIES:
            continue
        candidate = exact_text[start:index].strip()
        if len(candidate) >= 2 and '"' not in candidate and len(_exact_match_starts(exact_text, candidate)) == 1:
            candidates.append(candidate)
        start = index + 1
    tail = exact_text[start:].strip()
    if len(tail) >= 2 and '"' not in tail and len(_exact_match_starts(exact_text, tail)) == 1:
        candidates.append(tail)
    return tuple(dict.fromkeys(candidates))


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
            "allowed_expression_types": list(license_.allowed_expression_types),
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
                "expression_type": review.expression_type,
                "binding_checks": [
                    {
                        "binding_id": check.binding_id,
                        "status": check.status,
                    }
                    for check in review.binding_checks
                ],
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


def _allowed_expression_types(
    contract: UnitContractV2,
) -> tuple[LicenseExpressionTypeV1, ...]:
    if contract in {"actuality_reflection", "audience_guidance"}:
        return (
            "generic_observation",
            "recommendation",
            "non_situated_metaphor",
        )
    if contract == "abstract_observation":
        return (
            "generic_observation",
            "non_situated_metaphor",
        )
    if contract == "recommendation":
        return ("recommendation",)
    if contract == "hypothetical_example":
        return ("hypothetical_expression",)
    if contract == "disclosed_dramatization":
        return ("dramatized_expression",)
    raise ValueError("writer unit contract has no expression license")


def _parse_binding_checks(
    raw_checks: list[object],
    *,
    license_: ClauseLicenseV1,
) -> tuple[ProhibitedBindingCheckV1, ...]:
    checks: list[ProhibitedBindingCheckV1] = []
    for raw_check in raw_checks:
        if not isinstance(raw_check, Mapping) or frozenset(raw_check) != {
            "binding_id",
            "status",
        }:
            raise TypeError("prohibited binding check is invalid")
        binding_id = raw_check.get("binding_id")
        status = raw_check.get("status")
        if binding_id not in license_.prohibited_bindings or status not in _BINDING_CHECK_STATUSES:
            raise TypeError("prohibited binding check fields are invalid")
        checks.append(
            ProhibitedBindingCheckV1(
                binding_id=cast(ProhibitedBindingV1, binding_id),
                status=cast(BindingCheckStatusV1, status),
            )
        )
    check_by_binding = {check.binding_id: check for check in checks}
    if len(check_by_binding) != len(checks) or frozenset(check_by_binding) != frozenset(license_.prohibited_bindings):
        raise TypeError("prohibited binding check coverage is invalid")
    return tuple(check_by_binding[binding] for binding in license_.prohibited_bindings)


def _license_proof_issue(
    *,
    context: ClauseContextV2,
    license_: ClauseLicenseV1,
    review: ClauseLicenseReviewV1,
) -> NarrativeIssue | None:
    if tuple(check.binding_id for check in review.binding_checks) != license_.prohibited_bindings or len(
        {check.binding_id for check in review.binding_checks}
    ) != len(review.binding_checks):
        return NarrativeIssue(
            context.unit_id,
            "license_review_proof",
            "prohibited_binding_coverage",
        )
    statuses = tuple(check.status for check in review.binding_checks)
    present_bindings = {check.binding_id for check in review.binding_checks if check.status == "present"}
    if review.verdict == "supported":
        valid = (
            review.expression_type in license_.allowed_expression_types
            and all(status == "absent" for status in statuses)
            and review.reason_code == "supported_by_license"
            and not review.unsupported_quote
        )
    elif review.verdict == "uncertain":
        valid = (
            "uncertain" in statuses
            and "present" not in statuses
            and review.reason_code == "insufficient_evidence"
            and not review.unsupported_quote
        )
    else:
        valid = (
            bool(present_bindings)
            and "uncertain" not in statuses
            and review.reason_code in present_bindings
            and bool(review.unsupported_quote)
        )
    if valid:
        return None
    return NarrativeIssue(
        context.unit_id,
        "license_review_proof",
        context.exact_text,
    )


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
