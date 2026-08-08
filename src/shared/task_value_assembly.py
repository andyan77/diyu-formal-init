from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias

from src.shared.errors import DomainError

TASK_VALUE_ASSEMBLY_VERSION = "task-value-assembly-v1"

BrandRelevancePath: TypeAlias = Literal[
    "product_expertise",
    "existing_series",
    "audience_relationship",
    "brand_stance",
    "brand_visual",
    "local_trust",
    "organization_people",
]

# ADR-013 §4 lists the seven paths a finished brand work may accumulate.  V0 only
# assembles the first four; the rest need evidence this package does not freeze.
BRAND_RELEVANCE_PATHS: tuple[BrandRelevancePath, ...] = (
    "product_expertise",
    "existing_series",
    "audience_relationship",
    "brand_stance",
    "brand_visual",
    "local_trust",
    "organization_people",
)
BRAND_RELEVANCE_CONTRACT_VERSION = "brand-relevance-resolution-v1"
BRAND_RELEVANCE_SOURCE_TYPES: dict[BrandRelevancePath, frozenset[str]] = {
    "product_expertise": frozenset({"product_decision_basis"}),
    "existing_series": frozenset({"series_episode"}),
    "audience_relationship": frozenset({"account_profile"}),
    "brand_stance": frozenset({"account_profile"}),
    "brand_visual": frozenset({"brand_visual_qualification"}),
    "local_trust": frozenset({"local_trust_qualification"}),
    "organization_people": frozenset({"organization_people_qualification"}),
}
V0_PRODUCIBLE_PATHS: tuple[BrandRelevancePath, ...] = (
    "product_expertise",
    "existing_series",
    "audience_relationship",
    "brand_stance",
)
V0_RESERVED_PATHS: tuple[BrandRelevancePath, ...] = (
    "brand_visual",
    "local_trust",
    "organization_people",
)

PayoffOrigin: TypeAlias = Literal["server_assembled", "static_fallback"]
PAYOFF_ORIGINS: tuple[PayoffOrigin, ...] = ("server_assembled", "static_fallback")

# EXE-V0 has no confirmation surface at all: the proposal round trip arrives with
# EXE-06.  The field exists from day one so the later states never rewrite history.
PRE_PROPOSAL_CONFIRMATION_STATE = "unavailable_pre_proposal"

PayoffDegradationReason: TypeAlias = Literal[
    "missing_profile_signal",
    "invalid_assembly",
    "unsupported_relevance_path",
    "safety_gate_rejected",
]
PAYOFF_DEGRADATION_REASONS: tuple[PayoffDegradationReason, ...] = (
    "missing_profile_signal",
    "invalid_assembly",
    "unsupported_relevance_path",
    "safety_gate_rejected",
)

# The publishing account's five plain-language segments (``AccountExpression``).
# Only the field *names* may ever reach a trace; the段 text never leaves the server.
PROFILE_SIGNAL_FIELDS: tuple[str, ...] = (
    "identity_position",
    "authority_boundary",
    "audience_relationship",
    "content_territories",
    "default_production_conditions",
)

PAYOFF_MIN_LENGTH = 10
PAYOFF_MAX_LENGTH = 120
MAX_TRACE_PROFILE_FIELDS = len(PROFILE_SIGNAL_FIELDS)

_PUNCTUATION = "，。；：、！？（）「」『』“”‘’—…·,.;:!?()[]{}<>\"'`~-_/\\|"


@dataclass(frozen=True)
class TaskValueAssemblyTraceV1:
    """What drove one assembly, in field names and ids only.

    Deliberately a precise type contract rather than free text: no profile
    sentences, no seed text, no product fact values, no internal segment ids and
    no personal data may travel with a task snapshot.
    """

    used_profile_fields: tuple[str, ...]
    template_id: str
    ruleset_digest: str
    product_basis_present: bool
    series_basis_present: bool


@dataclass(frozen=True)
class BrandRelevanceEvidenceV1:
    """One typed, frozen source actually consumed by an applied relevance path."""

    contract_version: str
    path_family: BrandRelevancePath
    source_object_type: str
    source_id: str
    source_version: str
    source_digest: str
    actual_consumed_refs: tuple[str, ...]
    organization_ref: str | None = None
    authorization_ref: str | None = None
    media_ref: str | None = None


@dataclass(frozen=True)
class TaskValueAssemblyV1:
    """The independently versioned value object frozen next to a content task."""

    contract_version: str
    audience_payoff: str
    payoff_origin: PayoffOrigin
    payoff_confirmation_state: str
    payoff_degraded: bool
    payoff_degradation_reason: str | None
    brand_relevance_path: str | None
    ruleset_version: str
    ruleset_digest: str
    assembly_trace: TaskValueAssemblyTraceV1
    brand_relevance_state: str | None = None
    brand_relevance_evidence: BrandRelevanceEvidenceV1 | None = None
    brand_relevance_degraded_reason: str | None = None
    demonstration_eligible: bool | None = None


def task_value_assembly_document(
    assembly: TaskValueAssemblyV1,
) -> dict[str, object]:
    """Return one JSON-native representation used by JSONB and evidence."""

    trace = assembly.assembly_trace
    document: dict[str, object] = {
        "contract_version": assembly.contract_version,
        "audience_payoff": assembly.audience_payoff,
        "payoff_origin": assembly.payoff_origin,
        "payoff_confirmation_state": assembly.payoff_confirmation_state,
        "payoff_degraded": assembly.payoff_degraded,
        "payoff_degradation_reason": assembly.payoff_degradation_reason,
        "brand_relevance_path": assembly.brand_relevance_path,
        "ruleset_version": assembly.ruleset_version,
        "ruleset_digest": assembly.ruleset_digest,
        "assembly_trace": {
            "used_profile_fields": list(trace.used_profile_fields),
            "template_id": trace.template_id,
            "ruleset_digest": trace.ruleset_digest,
            "product_basis_present": trace.product_basis_present,
            "series_basis_present": trace.series_basis_present,
        },
    }
    if assembly.brand_relevance_state is not None:
        evidence = assembly.brand_relevance_evidence
        document.update(
            {
                "brand_relevance_state": assembly.brand_relevance_state,
                "brand_relevance_evidence": (
                    {
                        "contract_version": evidence.contract_version,
                        "path_family": evidence.path_family,
                        "source_object_type": evidence.source_object_type,
                        "source_id": evidence.source_id,
                        "source_version": evidence.source_version,
                        "source_digest": evidence.source_digest,
                        "actual_consumed_refs": list(evidence.actual_consumed_refs),
                        "organization_ref": evidence.organization_ref,
                        "authorization_ref": evidence.authorization_ref,
                        "media_ref": evidence.media_ref,
                    }
                    if evidence is not None
                    else None
                ),
                "brand_relevance_degraded_reason": assembly.brand_relevance_degraded_reason,
                "demonstration_eligible": assembly.demonstration_eligible,
            }
        )
    return document


def task_value_assembly_digest(assembly: TaskValueAssemblyV1) -> str:
    return hashlib.sha256(
        json.dumps(
            task_value_assembly_document(assembly),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def task_value_assembly_from_document(value: object) -> TaskValueAssemblyV1:
    if not isinstance(value, Mapping):
        raise DomainError("内容任务冻结的价值组装无效")
    raw_trace = value.get("assembly_trace")
    if not isinstance(raw_trace, Mapping):
        raise DomainError("内容任务冻结的价值组装无效")
    raw_relevance = value.get("brand_relevance_evidence")
    relevance_evidence: BrandRelevanceEvidenceV1 | None = None
    if raw_relevance is not None:
        if not isinstance(raw_relevance, Mapping):
            raise DomainError("内容任务冻结的品牌关联证据无效")
        try:
            path_family = _brand_relevance_path(raw_relevance["path_family"])
            relevance_evidence = BrandRelevanceEvidenceV1(
                contract_version=str(raw_relevance["contract_version"]),
                path_family=path_family,
                source_object_type=str(raw_relevance["source_object_type"]),
                source_id=str(raw_relevance["source_id"]),
                source_version=str(raw_relevance["source_version"]),
                source_digest=str(raw_relevance["source_digest"]),
                actual_consumed_refs=_string_tuple(raw_relevance.get("actual_consumed_refs")),
                organization_ref=_optional_string(raw_relevance.get("organization_ref")),
                authorization_ref=_optional_string(raw_relevance.get("authorization_ref")),
                media_ref=_optional_string(raw_relevance.get("media_ref")),
            )
        except (KeyError, TypeError) as exc:
            raise DomainError("内容任务冻结的品牌关联证据无效") from exc
    try:
        assembly = TaskValueAssemblyV1(
            contract_version=str(value["contract_version"]),
            audience_payoff=str(value["audience_payoff"]),
            payoff_origin=_payoff_origin(value["payoff_origin"]),
            payoff_confirmation_state=str(value["payoff_confirmation_state"]),
            payoff_degraded=_required_bool(value["payoff_degraded"]),
            payoff_degradation_reason=_optional_string(value.get("payoff_degradation_reason")),
            brand_relevance_path=_optional_string(value.get("brand_relevance_path")),
            ruleset_version=str(value["ruleset_version"]),
            ruleset_digest=str(value["ruleset_digest"]),
            assembly_trace=TaskValueAssemblyTraceV1(
                used_profile_fields=_profile_field_tuple(raw_trace.get("used_profile_fields")),
                template_id=str(raw_trace["template_id"]),
                ruleset_digest=str(raw_trace["ruleset_digest"]),
                product_basis_present=_required_bool(raw_trace["product_basis_present"]),
                series_basis_present=_required_bool(raw_trace["series_basis_present"]),
            ),
            brand_relevance_state=_optional_string(value.get("brand_relevance_state")),
            brand_relevance_evidence=relevance_evidence,
            brand_relevance_degraded_reason=_optional_string(value.get("brand_relevance_degraded_reason")),
            demonstration_eligible=_optional_bool(value.get("demonstration_eligible")),
        )
    except (KeyError, TypeError) as exc:
        raise DomainError("内容任务冻结的价值组装无效") from exc
    assert_task_value_assembly(assembly)
    return assembly


def assert_task_value_assembly(assembly: TaskValueAssemblyV1) -> None:
    """Fail closed on any assembly that would misrepresent how a payoff was produced."""

    trace = assembly.assembly_trace
    if (
        assembly.contract_version != TASK_VALUE_ASSEMBLY_VERSION
        or assembly.payoff_origin not in PAYOFF_ORIGINS
        or assembly.payoff_confirmation_state != PRE_PROPOSAL_CONFIRMATION_STATE
        or assembly.ruleset_version == ""
        or assembly.ruleset_digest != trace.ruleset_digest
        or trace.template_id == ""
        or len(trace.used_profile_fields) > MAX_TRACE_PROFILE_FIELDS
        or len(set(trace.used_profile_fields)) != len(trace.used_profile_fields)
        or not set(trace.used_profile_fields) <= set(PROFILE_SIGNAL_FIELDS)
        or _profile_field_tuple(list(trace.used_profile_fields)) != trace.used_profile_fields
    ):
        raise DomainError("内容任务冻结的价值组装无效")
    _required_sha256(assembly.ruleset_digest)
    assert_payoff_within_bounds(assembly.audience_payoff)
    _assert_origin_consistency(assembly)
    _assert_brand_relevance_consistency(assembly)


def assert_payoff_within_bounds(payoff: str) -> None:
    if not payoff or not PAYOFF_MIN_LENGTH <= len(payoff) <= PAYOFF_MAX_LENGTH:
        raise DomainError("内容任务的读者回报长度越界")


def _assert_origin_consistency(assembly: TaskValueAssemblyV1) -> None:
    if assembly.payoff_origin == "server_assembled":
        supported_paths = BRAND_RELEVANCE_PATHS if assembly.brand_relevance_state is not None else V0_PRODUCIBLE_PATHS
        invalid = (
            assembly.payoff_degraded
            or assembly.payoff_degradation_reason is not None
            or assembly.brand_relevance_path not in supported_paths
        )
    else:
        invalid = (
            not assembly.payoff_degraded
            or assembly.payoff_degradation_reason not in PAYOFF_DEGRADATION_REASONS
            or assembly.brand_relevance_path is not None
        )
    if invalid:
        raise DomainError("内容任务冻结的价值溯源自相矛盾")


def _assert_brand_relevance_consistency(assembly: TaskValueAssemblyV1) -> None:
    """Keep historical V0 documents intact and validate the expand-only Gate B fields."""

    if assembly.brand_relevance_state is None:
        if any(
            value is not None
            for value in (
                assembly.brand_relevance_evidence,
                assembly.brand_relevance_degraded_reason,
                assembly.demonstration_eligible,
            )
        ):
            raise DomainError("内容任务冻结的品牌关联状态不完整")
        return
    evidence = assembly.brand_relevance_evidence
    if assembly.brand_relevance_state == "applied":
        if (
            evidence is None
            or assembly.brand_relevance_path != evidence.path_family
            or assembly.brand_relevance_degraded_reason is not None
            or assembly.demonstration_eligible is not True
        ):
            raise DomainError("内容任务冻结的品牌关联状态不一致")
        assert_brand_relevance_evidence(evidence)
        return
    if assembly.brand_relevance_state != "degraded" or (
        evidence is not None
        or assembly.brand_relevance_path is not None
        or not assembly.brand_relevance_degraded_reason
        or assembly.demonstration_eligible is not False
    ):
        raise DomainError("内容任务冻结的品牌关联状态不一致")


def assert_brand_relevance_evidence(evidence: BrandRelevanceEvidenceV1) -> None:
    if (
        evidence.contract_version != BRAND_RELEVANCE_CONTRACT_VERSION
        or evidence.source_object_type not in BRAND_RELEVANCE_SOURCE_TYPES[evidence.path_family]
        or not evidence.source_id
        or not evidence.source_version
        or not evidence.actual_consumed_refs
        or len(set(evidence.actual_consumed_refs)) != len(evidence.actual_consumed_refs)
    ):
        raise DomainError("内容任务冻结的品牌关联证据无效")
    _required_sha256(evidence.source_digest)
    if evidence.path_family == "brand_visual" and not evidence.media_ref:
        raise DomainError("品牌视觉路径缺少冻结媒体资格引用")
    if evidence.path_family == "local_trust" and not evidence.organization_ref:
        raise DomainError("本地信任路径缺少冻结区域或门店引用")
    if evidence.path_family == "organization_people" and (
        not evidence.organization_ref or not evidence.authorization_ref
    ):
        raise DomainError("组织人物路径缺少冻结组织或人物授权引用")


def assert_task_value_matches_contract(
    assembly: TaskValueAssemblyV1,
    *,
    contract_audience_payoff: str,
    central_job_before: str,
    central_job_after: str,
) -> None:
    """The frozen contract carries exactly the assembled value, and nothing else moved."""

    assert_task_value_assembly(assembly)
    if assembly.audience_payoff != contract_audience_payoff:
        raise DomainError("内容任务的读者回报与冻结合同不一致")
    if not central_job_before or central_job_before != central_job_after:
        raise DomainError("内容任务的产品职责在组装前后被改写")


def normalized_payoff(payoff: str) -> str:
    """Collapse whitespace and punctuation so a reworded static default still matches."""

    return "".join(character for character in payoff if not character.isspace() and character not in _PUNCTUATION)


def is_static_default(payoff: str, static_defaults: Sequence[str]) -> bool:
    normalized = normalized_payoff(payoff)
    return any(normalized == normalized_payoff(default) for default in static_defaults)


def _payoff_origin(value: object) -> PayoffOrigin:
    if value == "server_assembled":
        return "server_assembled"
    if value == "static_fallback":
        return "static_fallback"
    raise DomainError("内容任务冻结的价值组装无效")


def _profile_field_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise DomainError("内容任务冻结的价值组装无效")
    selected = {str(item) for item in value}
    return tuple(field for field in PROFILE_SIGNAL_FIELDS if field in selected)


def _required_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise DomainError("内容任务冻结的价值组装无效")
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise DomainError("内容任务冻结的价值组装无效")
    return value


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise DomainError("内容任务冻结的价值组装无效")
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise DomainError("内容任务冻结的品牌关联证据无效")
    return tuple(value)


def _brand_relevance_path(value: object) -> BrandRelevancePath:
    if value not in BRAND_RELEVANCE_PATHS:
        raise DomainError("内容任务冻结的品牌关联路径无效")
    return value


def _required_sha256(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise DomainError("内容任务冻结的价值组装无效")
    return value
