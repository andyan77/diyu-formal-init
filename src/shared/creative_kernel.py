from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal, TypeAlias, cast

from src.shared.errors import DomainError
from src.shared.factual_basis import FrozenFactRecord
from src.shared.narrative import (
    NarrativeFrame,
    NarrativeIssue,
    ObservationType,
    ReviewerObservation,
)

KernelPurpose: TypeAlias = Literal[
    "title",
    "natural_guide",
    "frozen_fact",
    "body",
    "release_caption",
]

KERNEL_VERSION = "creative-kernel-v1"
DRAMATIZATION_DISCLOSURE = "情境演绎（虚构角色，不对应真实人物或品牌案例）："
HYPOTHESIS_DISCLOSURE = "假设："
_PURPOSES = frozenset(
    {
        "title",
        "natural_guide",
        "frozen_fact",
        "body",
        "release_caption",
    }
)
_OBSERVATION_TYPES = frozenset(
    {
        "abstract_principle",
        "situated_event",
        "institutional_assertion",
        "user_actuality",
        "hypothesis",
        "dramatization",
        "confirmed_fact",
        "uncertain",
    }
)


@dataclass(frozen=True)
class CreativeKernelUnit:
    unit_id: str
    purpose: KernelPurpose
    allowed_observation_types: tuple[ObservationType, ...]
    fact_refs: tuple[str, ...]
    constraint_refs: tuple[str, ...]
    visible_order: int
    text: str

    @property
    def writable(self) -> bool:
        return self.purpose != "frozen_fact"


@dataclass(frozen=True)
class CreativeKernelV1:
    kernel_version: str
    units: tuple[CreativeKernelUnit, ...]

    @property
    def writable_units(self) -> tuple[CreativeKernelUnit, ...]:
        return tuple(unit for unit in self.units if unit.writable)

    def unit(self, unit_id: str) -> CreativeKernelUnit:
        for unit in self.units:
            if unit.unit_id == unit_id:
                return unit
        raise KeyError(unit_id)


def build_kernel_skeleton(
    *,
    frame: NarrativeFrame,
    fact_registry: Sequence[FrozenFactRecord],
    constraint_refs: Sequence[str],
) -> CreativeKernelV1:
    """Build the one small server-owned writing skeleton for a new artifact."""
    body_types: tuple[ObservationType, ...]
    if frame.narrative_mode == "hypothesis":
        body_types = ("hypothesis",)
    elif frame.narrative_mode == "dramatization":
        body_types = ("dramatization",)
    else:
        body_types = ("abstract_principle",)
    constraints = tuple(dict.fromkeys(constraint_refs))
    units: list[CreativeKernelUnit] = [
        CreativeKernelUnit(
            unit_id="unit:title",
            purpose="title",
            allowed_observation_types=("abstract_principle",),
            fact_refs=(),
            constraint_refs=constraints,
            visible_order=10,
            text="",
        ),
        CreativeKernelUnit(
            unit_id="unit:natural-guide",
            purpose="natural_guide",
            allowed_observation_types=("abstract_principle",),
            fact_refs=(),
            constraint_refs=constraints,
            visible_order=20,
            text="",
        ),
    ]
    allowed_fact_ids = frame.allowed_fact_ids
    frozen_records = tuple(
        record
        for record in fact_registry
        if record.fact_id in allowed_fact_ids
    )
    for index, record in enumerate(frozen_records, start=1):
        observation_type: ObservationType
        if record.fact_kind == "user_actuality":
            observation_type = "user_actuality"
        elif record.fact_kind == "brand":
            observation_type = "institutional_assertion"
        else:
            observation_type = "confirmed_fact"
        units.append(
            CreativeKernelUnit(
                unit_id=f"unit:frozen-fact:{index}",
                purpose="frozen_fact",
                allowed_observation_types=(observation_type,),
                fact_refs=(record.fact_id,),
                constraint_refs=(),
                visible_order=30 + index,
                text=record.exact_text,
            )
        )
    units.extend(
        (
            CreativeKernelUnit(
                unit_id="unit:body",
                purpose="body",
                allowed_observation_types=body_types,
                fact_refs=(),
                constraint_refs=constraints,
                visible_order=100,
                text="",
            ),
            CreativeKernelUnit(
                unit_id="unit:release-caption",
                purpose="release_caption",
                allowed_observation_types=("abstract_principle",),
                fact_refs=(),
                constraint_refs=constraints,
                visible_order=110,
                text="",
            ),
        )
    )
    return CreativeKernelV1(
        kernel_version=KERNEL_VERSION,
        units=tuple(sorted(units, key=lambda unit: unit.visible_order)),
    )


def parse_writer_kernel(
    raw: object,
    skeleton: CreativeKernelV1,
) -> CreativeKernelV1:
    if not isinstance(raw, Mapping) or frozenset(raw) != {"units"}:
        raise TypeError("writer must return only units")
    raw_units = raw.get("units")
    if not isinstance(raw_units, list) or not raw_units:
        raise TypeError("writer units are incomplete")
    expected = {unit.unit_id: unit for unit in skeleton.writable_units}
    returned_ids = [
        value.get("unit_id")
        for value in raw_units
        if isinstance(value, Mapping)
    ]
    if (
        len(returned_ids) != len(raw_units)
        or len(returned_ids) != len(set(returned_ids))
        or set(returned_ids) != set(expected)
    ):
        raise ValueError("writer unit coverage drifted from server skeleton")
    replacements: dict[str, CreativeKernelUnit] = {}
    for raw_unit in raw_units:
        if not isinstance(raw_unit, Mapping) or frozenset(raw_unit) != {
            "unit_id",
            "text",
        }:
            raise TypeError("writer unit must contain only unit_id and text")
        unit_id = _required_string(raw_unit.get("unit_id"))
        replacements[unit_id] = replace(
            expected[unit_id],
            text=_service_wrap(
                expected[unit_id],
                _required_string(raw_unit.get("text")),
            ),
        )
    return CreativeKernelV1(
        kernel_version=KERNEL_VERSION,
        units=tuple(
            replacements.get(unit.unit_id, unit)
            for unit in skeleton.units
        ),
    )


def repair_kernel_units(
    *,
    kernel: CreativeKernelV1,
    affected_unit_ids: frozenset[str],
    raw: object,
) -> CreativeKernelV1:
    if not affected_unit_ids:
        raise ValueError("repair has no affected writable units")
    if any(
        not kernel.unit(unit_id).writable
        for unit_id in affected_unit_ids
    ):
        raise ValueError("service-authored fact units cannot be repaired")
    repair_skeleton = CreativeKernelV1(
        kernel_version=KERNEL_VERSION,
        units=tuple(
            replace(unit, text="")
            for unit in kernel.units
            if unit.unit_id in affected_unit_ids
        ),
    )
    repaired = parse_writer_kernel(raw, repair_skeleton)
    replacements = {unit.unit_id: unit for unit in repaired.units}
    return CreativeKernelV1(
        kernel_version=KERNEL_VERSION,
        units=tuple(
            replacements.get(unit.unit_id, unit) for unit in kernel.units
        ),
    )


def kernel_document(kernel: CreativeKernelV1) -> dict[str, object]:
    return {
        "kernel_version": kernel.kernel_version,
        "units": [
            {
                "unit_id": unit.unit_id,
                "purpose": unit.purpose,
                "allowed_observation_types": list(
                    unit.allowed_observation_types
                ),
                "fact_refs": list(unit.fact_refs),
                "constraint_refs": list(unit.constraint_refs),
                "visible_order": unit.visible_order,
                "text": unit.text,
            }
            for unit in kernel.units
        ],
    }


def kernel_from_document(value: object) -> CreativeKernelV1:
    if not isinstance(value, Mapping) or frozenset(value) != {
        "kernel_version",
        "units",
    }:
        raise DomainError("冻结创作内核结构无效")
    raw_units = value.get("units")
    if value.get("kernel_version") != KERNEL_VERSION or not isinstance(
        raw_units, list
    ):
        raise DomainError("冻结创作内核版本无效")
    units: list[CreativeKernelUnit] = []
    for raw in raw_units:
        if not isinstance(raw, Mapping) or frozenset(raw) != {
            "unit_id",
            "purpose",
            "allowed_observation_types",
            "fact_refs",
            "constraint_refs",
            "visible_order",
            "text",
        }:
            raise DomainError("冻结创作内核单元无效")
        purpose = raw.get("purpose")
        allowed = _string_tuple(raw.get("allowed_observation_types"))
        order = raw.get("visible_order")
        if (
            not isinstance(purpose, str)
            or purpose not in _PURPOSES
            or not allowed
            or any(item not in _OBSERVATION_TYPES for item in allowed)
            or not isinstance(order, int)
        ):
            raise DomainError("冻结创作内核单元字段无效")
        units.append(
            CreativeKernelUnit(
                unit_id=_required_string(raw.get("unit_id")),
                purpose=cast(KernelPurpose, purpose),
                allowed_observation_types=cast(
                    tuple[ObservationType, ...], allowed
                ),
                fact_refs=_string_tuple(raw.get("fact_refs")),
                constraint_refs=_string_tuple(raw.get("constraint_refs")),
                visible_order=order,
                text=_required_string(raw.get("text")),
            )
        )
    identifiers = [unit.unit_id for unit in units]
    orders = [unit.visible_order for unit in units]
    if (
        not units
        or len(identifiers) != len(set(identifiers))
        or len(orders) != len(set(orders))
        or orders != sorted(orders)
    ):
        raise DomainError("冻结创作内核顺序或标识无效")
    return CreativeKernelV1(KERNEL_VERSION, tuple(units))


def kernel_digest(kernel: CreativeKernelV1) -> str:
    canonical = json.dumps(
        kernel_document(kernel),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def reconcile_kernel_observations(
    *,
    kernel: CreativeKernelV1,
    observations: Sequence[ReviewerObservation],
    fact_text_by_id: Mapping[str, str],
    allowed_constraint_ids: frozenset[str],
) -> tuple[NarrativeIssue, ...]:
    """Close the review world around the reviewed kernel and nothing else."""
    by_id: dict[str, ReviewerObservation] = {}
    issues: list[NarrativeIssue] = []
    units = {unit.unit_id: unit for unit in kernel.units}
    for observation in observations:
        if observation.target_id not in units or observation.target_id in by_id:
            issues.append(
                NarrativeIssue(
                    observation.target_id,
                    "review_coverage",
                    observation.target_id,
                )
            )
            continue
        unit = units[observation.target_id]
        if observation.target_kind != "unit":
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "review_coverage",
                    observation.target_kind,
                )
            )
        if observation.text_spans != (unit.text,):
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "review_coverage",
                    observation.text_spans[0],
                )
            )
        semantic_spans = (
            *observation.people,
            *observation.relationships,
            *observation.actions_or_events,
            *observation.dialogue,
            *observation.motives,
            *observation.causes,
            *observation.results,
            *observation.times,
            *observation.locations,
            *observation.possessions,
            *observation.dramatization_disclosure_spans,
            *observation.instruction_conflicts,
        )
        if any(span not in unit.text for span in semantic_spans):
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "missing_exact_span",
                    next(span for span in semantic_spans if span not in unit.text),
                )
            )
        if observation.uncertain or observation.observation_type == "uncertain":
            issues.append(
                NarrativeIssue(unit.unit_id, "uncertain_meaning", unit.text)
            )
        if observation.instruction_conflicts:
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "instruction_conflict",
                    observation.instruction_conflicts[0],
                )
            )
        if observation.resource_refs:
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "review_resource_claim",
                    observation.resource_refs[0],
                )
            )
        if (
            observation.observation_type
            not in unit.allowed_observation_types
        ):
            reason = (
                "unsupported_institutional_assertion"
                if observation.observation_type
                == "institutional_assertion"
                else "unit_observation_drift"
            )
            issues.append(NarrativeIssue(unit.unit_id, reason, unit.text))
        if unit.purpose == "frozen_fact":
            exact = {
                fact_text_by_id[ref]
                for ref in unit.fact_refs
                if ref in fact_text_by_id
            }
            if (
                len(unit.fact_refs) != 1
                or unit.text not in exact
                or unit.constraint_refs
            ):
                issues.append(
                    NarrativeIssue(
                        unit.unit_id,
                        "frozen_fact_changed",
                        unit.text,
                    )
                )
        elif unit.fact_refs:
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "writer_fact_binding",
                    unit.text,
                )
            )
        if any(
            ref not in allowed_constraint_ids
            for ref in unit.constraint_refs
        ):
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "unknown_constraint_ref",
                    unit.text,
                )
            )
        if (
            observation.observation_type == "dramatization"
            and (
                DRAMATIZATION_DISCLOSURE
                not in observation.dramatization_disclosure_spans
                or not unit.text.startswith(DRAMATIZATION_DISCLOSURE)
            )
        ):
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "dramatization_not_visible",
                    unit.text,
                )
            )
        by_id[unit.unit_id] = observation
    for missing_id in set(units) - set(by_id):
        issues.append(NarrativeIssue(missing_id, "review_coverage", missing_id))
    return tuple(dict.fromkeys(issues))


def _service_wrap(unit: CreativeKernelUnit, text: str) -> str:
    if unit.allowed_observation_types == ("dramatization",):
        if text.startswith(DRAMATIZATION_DISCLOSURE):
            raise ValueError("writer cannot author the service disclosure")
        return f"{DRAMATIZATION_DISCLOSURE}\n{text}"
    if unit.allowed_observation_types == ("hypothesis",):
        if text.startswith(HYPOTHESIS_DISCLOSURE):
            raise ValueError("writer cannot author the service disclosure")
        return f"{HYPOTHESIS_DISCLOSURE}\n{text}"
    return text


def _required_string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError("value must be a non-empty string")
    return value.strip()


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise DomainError("冻结创作内核字符串列表无效")
    values = cast(list[str], value)
    if len(values) != len(set(values)):
        raise DomainError("冻结创作内核字符串列表重复")
    return tuple(values)
