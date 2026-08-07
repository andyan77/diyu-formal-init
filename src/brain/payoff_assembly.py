from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import get_args

from src.shared.publication_contract import (
    ProductDecisionBasisRefV2,
    SeriesDeltaV1,
    product_brief,
)
from src.shared.task_value_assembly import (
    PAYOFF_MAX_LENGTH,
    PAYOFF_MIN_LENGTH,
    PRE_PROPOSAL_CONFIRMATION_STATE,
    PROFILE_SIGNAL_FIELDS,
    TASK_VALUE_ASSEMBLY_VERSION,
    V0_PRODUCIBLE_PATHS,
    BrandRelevancePath,
    PayoffDegradationReason,
    TaskValueAssemblyTraceV1,
    TaskValueAssemblyV1,
    assert_task_value_assembly,
    is_static_default,
)
from src.shared.types import AccountExpression, ContentProduct

PAYOFF_RULESET_VERSION = "task-value-ruleset-v0"

CONTENT_PRODUCTS: tuple[str, ...] = tuple(get_args(ContentProduct))
TOPIC_ORIGINS: tuple[str, ...] = ("explicit_user", "system_selected")


@dataclass(frozen=True)
class PayoffRuleset:
    """The versioned decision table one payoff may be assembled from.

    Every phrase a reader could ever see is written here, reviewed here and
    digested here.  Nothing is interpolated from the account profile text, the
    user's seed or a product fact value, so a payoff can never leak them.
    """

    version: str
    candidate_order: tuple[BrandRelevancePath, ...]
    path_lead: Mapping[str, str]
    product_focus: Mapping[str, str]
    topic_tail: Mapping[str, str]
    series_continuity_tail: str
    product_expertise_products: tuple[str, ...]
    natural_reserved_path: Mapping[str, str]
    stance_profile_fields: tuple[str, ...]


RULESET_V0 = PayoffRuleset(
    version=PAYOFF_RULESET_VERSION,
    # Specificity order: a frozen product basis beats a frozen series, which beats
    # what the account's own five segments can justify.
    candidate_order=V0_PRODUCIBLE_PATHS,
    path_lead={
        "product_expertise": "让受众凭这一篇冻结的商品选择依据，拿到",
        "existing_series": "让持续在追这条系列的受众，在这一篇里继续拿到",
        "audience_relationship": "让本账号长期服务的这群受众，按各自处境拿到",
        "brand_stance": "让受众从本账号一贯的判断立场出发，拿到",
    },
    product_focus={
        "dressing_decision": "一次当下就能照着做的穿衣取舍",
        "product_truth": "一条只依据已确认信息的选择判断",
        "brand_life_narrative": "一个能独立带走的具体观察",
        "local_response": "一种在相似处境里可以继续的回应方式",
        "visual_styling_story": "一组能看清主辅关系的搭配看法",
    },
    topic_tail={
        "explicit_user": "；这一篇只回答本次提出的题目。",
        "system_selected": "；这一篇自带一个可被记住的切入点。",
    },
    series_continuity_tail="，而且不与前几篇的判断重复",
    # A life narrative or a local response must never be re-pointed at goods just
    # because a product basis happens to be frozen alongside it.
    product_expertise_products=(
        "dressing_decision",
        "product_truth",
        "visual_styling_story",
    ),
    natural_reserved_path={
        "local_response": "local_trust",
        "visual_styling_story": "brand_visual",
    },
    stance_profile_fields=(
        "identity_position",
        "authority_boundary",
        "content_territories",
    ),
)


@dataclass(frozen=True)
class PayoffAssemblyRequest:
    """Signals only. No profile sentence, seed text or product fact value enters here."""

    content_product: str
    topic_origin: str
    profile_signals: tuple[str, ...]
    product_basis_present: bool
    series_basis_present: bool
    series_position: int
    static_payoff: str
    static_defaults: tuple[str, ...]


def payoff_ruleset_document(ruleset: PayoffRuleset) -> dict[str, object]:
    return {
        "version": ruleset.version,
        "candidate_order": list(ruleset.candidate_order),
        "path_lead": dict(ruleset.path_lead),
        "product_focus": dict(ruleset.product_focus),
        "topic_tail": dict(ruleset.topic_tail),
        "series_continuity_tail": ruleset.series_continuity_tail,
        "product_expertise_products": list(ruleset.product_expertise_products),
        "natural_reserved_path": dict(ruleset.natural_reserved_path),
        "stance_profile_fields": list(ruleset.stance_profile_fields),
    }


def payoff_ruleset_digest(ruleset: PayoffRuleset) -> str:
    return hashlib.sha256(
        json.dumps(
            payoff_ruleset_document(ruleset),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def product_contract_job(content_product: str, topic_origin: str) -> str:
    """The五类产品 invariant central job, frozen against rewriting by anyone.

    EXE-V0 replaces what a reader gets, never what the product owes.  The
    assembler reads this and the contract asserts it did not move.
    """

    return product_brief(content_product, topic_origin)[0]


def static_payoff_defaults() -> tuple[str, ...]:
    """Every payoff the pre-V0 static table can produce, derived rather than copied."""

    return tuple(
        dict.fromkeys(
            product_brief(content_product, topic_origin)[1]
            for content_product in CONTENT_PRODUCTS
            for topic_origin in TOPIC_ORIGINS
        )
    )


def profile_signals(expression: AccountExpression | None) -> tuple[str, ...]:
    """Which of the五段 carry text, as field names — never the text itself."""

    if expression is None:
        return ()
    present = {
        "identity_position": expression.identity_position,
        "authority_boundary": expression.authority_boundary,
        "audience_relationship": expression.audience_relationship,
        "content_territories": expression.content_territories,
        "default_production_conditions": expression.default_production_conditions,
    }
    return tuple(field for field in PROFILE_SIGNAL_FIELDS if present[field].strip())


def build_payoff_request(
    *,
    content_product: str,
    topic_origin: str,
    account_expression: AccountExpression | None,
    product_basis: ProductDecisionBasisRefV2 | None,
    series_delta: SeriesDeltaV1 | None,
    static_payoff: str,
) -> PayoffAssemblyRequest:
    return PayoffAssemblyRequest(
        content_product=content_product,
        topic_origin=topic_origin,
        profile_signals=profile_signals(account_expression),
        product_basis_present=(product_basis is not None and bool(product_basis.supporting_fact_refs)),
        series_basis_present=(
            series_delta is not None
            and series_delta.series_position >= 1
            and bool(series_delta.required_new_judgment)
        ),
        series_position=(series_delta.series_position if series_delta is not None else 0),
        static_payoff=static_payoff,
        static_defaults=static_payoff_defaults(),
    )


def assemble_task_value(
    request: PayoffAssemblyRequest,
    *,
    ruleset: PayoffRuleset = RULESET_V0,
) -> TaskValueAssemblyV1:
    """Deterministically assemble one task's audience payoff, or degrade visibly.

    Same input, same output: no clock, no randomness, no model call.  A retry of
    the same request re-selects the same template and keeps the same digest.
    """

    digest = payoff_ruleset_digest(ruleset)
    safety_rejected = False
    gate_failed = False
    for path in ruleset.candidate_order:
        if not _path_has_signal(path, request, ruleset):
            continue
        if not _path_passes_safety(path, request, ruleset):
            safety_rejected = True
            continue
        payoff = _compose_payoff(path, request, ruleset)
        if not _payoff_passes_gate(payoff, request):
            gate_failed = True
            continue
        return _server_assembled(path, payoff, request, ruleset, digest)
    reason = _degradation_reason(
        request,
        ruleset,
        safety_rejected=safety_rejected,
        gate_failed=gate_failed,
    )
    return _static_fallback(request, ruleset, digest, reason)


def _path_has_signal(
    path: BrandRelevancePath,
    request: PayoffAssemblyRequest,
    ruleset: PayoffRuleset,
) -> bool:
    if path == "product_expertise":
        return request.product_basis_present
    if path == "existing_series":
        return request.series_basis_present
    if path == "audience_relationship":
        return "audience_relationship" in request.profile_signals
    if path == "brand_stance":
        return any(field in request.profile_signals for field in ruleset.stance_profile_fields)
    return False


def _path_passes_safety(
    path: BrandRelevancePath,
    request: PayoffAssemblyRequest,
    ruleset: PayoffRuleset,
) -> bool:
    if path == "product_expertise":
        return request.content_product in ruleset.product_expertise_products
    return True


def _compose_payoff(
    path: BrandRelevancePath,
    request: PayoffAssemblyRequest,
    ruleset: PayoffRuleset,
) -> str:
    continuity = ruleset.series_continuity_tail if _continues_series(path, request) else ""
    return "".join(
        (
            ruleset.path_lead.get(path, ""),
            ruleset.product_focus.get(request.content_product, ""),
            continuity,
            ruleset.topic_tail.get(request.topic_origin, ""),
        )
    )


def _continues_series(path: BrandRelevancePath, request: PayoffAssemblyRequest) -> bool:
    return path == "existing_series" and request.series_position > 1


def _payoff_passes_gate(payoff: str, request: PayoffAssemblyRequest) -> bool:
    return (
        bool(payoff)
        and PAYOFF_MIN_LENGTH <= len(payoff) <= PAYOFF_MAX_LENGTH
        and not is_static_default(payoff, request.static_defaults)
    )


def _template_id(
    path: BrandRelevancePath,
    request: PayoffAssemblyRequest,
    ruleset: PayoffRuleset,
) -> str:
    suffix = "+series" if _continues_series(path, request) else ""
    return f"{ruleset.version}/{path}/{request.content_product}/{request.topic_origin}{suffix}"


def _used_profile_fields(
    path: BrandRelevancePath,
    request: PayoffAssemblyRequest,
    ruleset: PayoffRuleset,
) -> tuple[str, ...]:
    if path == "audience_relationship":
        justifying: tuple[str, ...] = ("audience_relationship",)
    elif path == "brand_stance":
        justifying = ruleset.stance_profile_fields
    else:
        justifying = ()
    return tuple(field for field in PROFILE_SIGNAL_FIELDS if field in justifying and field in request.profile_signals)


def _degradation_reason(
    request: PayoffAssemblyRequest,
    ruleset: PayoffRuleset,
    *,
    safety_rejected: bool,
    gate_failed: bool,
) -> PayoffDegradationReason:
    if gate_failed:
        return "invalid_assembly"
    if safety_rejected:
        return "safety_gate_rejected"
    if request.content_product in ruleset.natural_reserved_path:
        return "unsupported_relevance_path"
    return "missing_profile_signal"


def _server_assembled(
    path: BrandRelevancePath,
    payoff: str,
    request: PayoffAssemblyRequest,
    ruleset: PayoffRuleset,
    digest: str,
) -> TaskValueAssemblyV1:
    assembly = TaskValueAssemblyV1(
        contract_version=TASK_VALUE_ASSEMBLY_VERSION,
        audience_payoff=payoff,
        payoff_origin="server_assembled",
        payoff_confirmation_state=PRE_PROPOSAL_CONFIRMATION_STATE,
        payoff_degraded=False,
        payoff_degradation_reason=None,
        brand_relevance_path=path,
        ruleset_version=ruleset.version,
        ruleset_digest=digest,
        assembly_trace=_trace(_template_id(path, request, ruleset), request, digest, path, ruleset),
    )
    assert_task_value_assembly(assembly)
    return assembly


def _static_fallback(
    request: PayoffAssemblyRequest,
    ruleset: PayoffRuleset,
    digest: str,
    reason: PayoffDegradationReason,
) -> TaskValueAssemblyV1:
    template_id = f"{ruleset.version}/static_fallback/{request.content_product}/{request.topic_origin}"
    assembly = TaskValueAssemblyV1(
        contract_version=TASK_VALUE_ASSEMBLY_VERSION,
        audience_payoff=request.static_payoff,
        payoff_origin="static_fallback",
        payoff_confirmation_state=PRE_PROPOSAL_CONFIRMATION_STATE,
        payoff_degraded=True,
        payoff_degradation_reason=reason,
        brand_relevance_path=None,
        ruleset_version=ruleset.version,
        ruleset_digest=digest,
        assembly_trace=_trace(template_id, request, digest, None, ruleset),
    )
    assert_task_value_assembly(assembly)
    return assembly


def _trace(
    template_id: str,
    request: PayoffAssemblyRequest,
    digest: str,
    path: BrandRelevancePath | None,
    ruleset: PayoffRuleset,
) -> TaskValueAssemblyTraceV1:
    return TaskValueAssemblyTraceV1(
        used_profile_fields=(() if path is None else _used_profile_fields(path, request, ruleset)),
        template_id=template_id,
        ruleset_digest=digest,
        product_basis_present=request.product_basis_present,
        series_basis_present=request.series_basis_present,
    )
