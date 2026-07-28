from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from src.shared.errors import DomainError

NarrativeMode: TypeAlias = Literal[
    "actuality_reflection",
    "general_observation",
    "hypothesis",
    "dramatization",
]
NarrativeBlockType: TypeAlias = Literal[
    "actuality_source",
    "general_observation",
    "hypothesis",
    "dramatization",
]
ReviewTargetKind: TypeAlias = Literal["block", "scene"]
RealityBinding: TypeAlias = Literal[
    "user_actuality",
    "general_observation",
    "hypothesis",
    "dramatization",
    "confirmed_fact",
    "uncertain",
]

FRAME_VERSION = "narrative-frame-v1"
_MODES = frozenset(
    {
        "actuality_reflection",
        "general_observation",
        "hypothesis",
        "dramatization",
    }
)
_BLOCK_TYPES = frozenset(
    {
        "actuality_source",
        "general_observation",
        "hypothesis",
        "dramatization",
    }
)
_REALITY_BINDINGS = frozenset(
    {
        "user_actuality",
        "general_observation",
        "hypothesis",
        "dramatization",
        "confirmed_fact",
        "uncertain",
    }
)


@dataclass(frozen=True)
class FrozenUserFact:
    source_id: str
    exact_text: str


@dataclass(frozen=True)
class NarrativeFrame:
    frame_version: str
    narrative_mode: NarrativeMode
    user_facts: tuple[FrozenUserFact, ...]
    allowed_brand_fact_ids: tuple[str, ...]
    allowed_product_fact_ids: tuple[str, ...]

    @property
    def allowed_fact_ids(self) -> frozenset[str]:
        return frozenset(
            (
                *(fact.source_id for fact in self.user_facts),
                *self.allowed_brand_fact_ids,
                *self.allowed_product_fact_ids,
            )
        )


@dataclass(frozen=True)
class NarrativeBlock:
    block_id: str
    block_type: NarrativeBlockType
    slot: str
    text: str
    source_refs: tuple[str, ...]
    linked_scene_ids: tuple[str, ...]

    @property
    def scene_ids(self) -> tuple[str, ...]:
        """Compatibility alias for internal readers of the UI-06 prototype shape."""
        return self.linked_scene_ids


@dataclass(frozen=True)
class ReviewerObservation:
    target_id: str
    target_kind: ReviewTargetKind
    text_spans: tuple[str, ...]
    people: tuple[str, ...]
    relationships: tuple[str, ...]
    actions_or_events: tuple[str, ...]
    dialogue: tuple[str, ...]
    motives: tuple[str, ...]
    causes: tuple[str, ...]
    results: tuple[str, ...]
    times: tuple[str, ...]
    locations: tuple[str, ...]
    possessions: tuple[str, ...]
    reality_binding: RealityBinding
    resource_refs: tuple[str, ...]
    dramatization_disclosure_spans: tuple[str, ...]
    instruction_conflicts: tuple[str, ...]
    uncertain: bool


@dataclass(frozen=True)
class NarrativeIssue:
    target_id: str
    reason: str
    fragment: str


def frame_document(frame: NarrativeFrame) -> dict[str, object]:
    return {
        "frame_version": frame.frame_version,
        "narrative_mode": frame.narrative_mode,
        "user_facts": [
            {"source_id": fact.source_id, "exact_text": fact.exact_text}
            for fact in frame.user_facts
        ],
        "allowed_brand_fact_ids": list(frame.allowed_brand_fact_ids),
        "allowed_product_fact_ids": list(frame.allowed_product_fact_ids),
    }


def frame_from_document(value: object) -> NarrativeFrame:
    if not isinstance(value, Mapping):
        raise DomainError("内容任务冻结的叙事框架无效")
    version = value.get("frame_version")
    mode = value.get("narrative_mode")
    raw_facts = value.get("user_facts")
    if (
        version != FRAME_VERSION
        or not isinstance(mode, str)
        or mode not in _MODES
        or not isinstance(raw_facts, list)
    ):
        raise DomainError("内容任务冻结的叙事框架无效")
    facts: list[FrozenUserFact] = []
    for raw in raw_facts:
        if not isinstance(raw, Mapping):
            raise DomainError("内容任务冻结的叙事框架无效")
        source_id = raw.get("source_id")
        exact_text = raw.get("exact_text")
        if (
            not isinstance(source_id, str)
            or not source_id.startswith("source:user_actuality:")
            or not isinstance(exact_text, str)
            or not exact_text
        ):
            raise DomainError("内容任务冻结的叙事框架无效")
        facts.append(FrozenUserFact(source_id, exact_text))
    brand_ids = _string_tuple(value.get("allowed_brand_fact_ids"))
    product_ids = _string_tuple(value.get("allowed_product_fact_ids"))
    if len({fact.source_id for fact in facts}) != len(facts):
        raise DomainError("内容任务冻结的叙事框架无效")
    if mode == "actuality_reflection" and not facts:
        raise DomainError("真人事实反思缺少冻结原文")
    if mode != "actuality_reflection" and facts:
        raise DomainError("当前叙事模式不能冻结真人事实")
    return NarrativeFrame(
        frame_version=FRAME_VERSION,
        narrative_mode=cast(NarrativeMode, mode),
        user_facts=tuple(facts),
        allowed_brand_fact_ids=brand_ids,
        allowed_product_fact_ids=product_ids,
    )


def new_frame(
    mode: NarrativeMode,
    user_fact_spans: Sequence[str],
    product_fact_ids: Sequence[str],
) -> NarrativeFrame:
    facts = tuple(
        FrozenUserFact(f"source:user_actuality:{index}", text)
        for index, text in enumerate(user_fact_spans, start=1)
    )
    if mode == "actuality_reflection" and not facts:
        raise DomainError("真人事实反思缺少用户原文")
    if mode != "actuality_reflection" and facts:
        raise DomainError("只有真人事实反思可以冻结用户现实原文")
    return NarrativeFrame(
        frame_version=FRAME_VERSION,
        narrative_mode=mode,
        user_facts=facts,
        allowed_brand_fact_ids=(
            "source:brand_baseline",
            "source:role_boundary",
            "source:organization",
        ),
        allowed_product_fact_ids=tuple(dict.fromkeys(product_fact_ids)),
    )


def legacy_frame(product_fact_ids: Sequence[str] = ()) -> NarrativeFrame:
    """Give pre-UI-06 tasks a conservative replay frame without inventing facts."""
    return new_frame("general_observation", (), product_fact_ids)


def visible_digest(outline: str, body: str) -> str:
    canonical = json.dumps(
        {"outline": outline, "body": body},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def parse_observation(value: object) -> ReviewerObservation:
    if not isinstance(value, Mapping):
        raise TypeError("reviewer observation must be an object")
    target_id = _required_string(value.get("id"))
    target_kind = _required_string(value.get("target_kind"))
    reality_binding = _required_string(value.get("reality_binding"))
    uncertain = value.get("uncertain")
    raw_claims = value.get("claims")
    if target_kind not in {"block", "scene"}:
        raise TypeError("reviewer target kind is invalid")
    if reality_binding not in _REALITY_BINDINGS:
        raise TypeError("reviewer reality binding is invalid")
    if not isinstance(uncertain, bool):
        raise TypeError("reviewer uncertainty must be boolean")
    if not isinstance(raw_claims, list):
        raise TypeError("reviewer claims must be a list")
    grouped: dict[str, list[str]] = {
        category: []
        for category in (
            "people",
            "relationships",
            "actions_or_events",
            "dialogue",
            "motives",
            "causes",
            "results",
            "times",
            "locations",
            "possessions",
        )
    }
    for raw_claim in raw_claims:
        if not isinstance(raw_claim, Mapping):
            raise TypeError("reviewer claim must be an object")
        category = _required_string(raw_claim.get("category"))
        span = _required_string(raw_claim.get("span"))
        if category not in grouped:
            raise TypeError("reviewer claim category is invalid")
        grouped[category].append(span)
    return ReviewerObservation(
        target_id=target_id,
        target_kind=cast(ReviewTargetKind, target_kind),
        text_spans=_string_tuple(value.get("text_spans"), allow_empty=False),
        people=tuple(grouped["people"]),
        relationships=tuple(grouped["relationships"]),
        actions_or_events=tuple(grouped["actions_or_events"]),
        dialogue=tuple(grouped["dialogue"]),
        motives=tuple(grouped["motives"]),
        causes=tuple(grouped["causes"]),
        results=tuple(grouped["results"]),
        times=tuple(grouped["times"]),
        locations=tuple(grouped["locations"]),
        possessions=tuple(grouped["possessions"]),
        reality_binding=cast(RealityBinding, reality_binding),
        resource_refs=_string_tuple(value.get("resource_refs")),
        dramatization_disclosure_spans=_string_tuple(
            value.get("dramatization_disclosure_spans")
        ),
        instruction_conflicts=_string_tuple(value.get("instruction_conflicts")),
        uncertain=uncertain,
    )


def reconcile_observations(
    *,
    frame: NarrativeFrame,
    blocks: Sequence[NarrativeBlock],
    scene_text: Mapping[str, str],
    scene_resource_refs: Mapping[str, tuple[str, ...]],
    observations: Sequence[ReviewerObservation],
    allowed_resource_ids: frozenset[str],
    exact_product_facts: Mapping[str, frozenset[str]],
) -> tuple[NarrativeIssue, ...]:
    """Deterministically reconcile extracted meaning with one frozen frame."""
    targets: dict[str, tuple[ReviewTargetKind, str]] = {
        block.block_id: ("block", block.text) for block in blocks
    }
    for scene_id, text in scene_text.items():
        if scene_id in targets:
            return (NarrativeIssue(scene_id, "duplicate_target_id", scene_id),)
        targets[scene_id] = ("scene", text)
    by_id: dict[str, ReviewerObservation] = {}
    issues: list[NarrativeIssue] = []
    for observation in observations:
        if observation.target_id not in targets or observation.target_id in by_id:
            issues.append(
                NarrativeIssue(
                    observation.target_id,
                    "review_coverage",
                    observation.target_id,
                )
            )
            continue
        expected_kind, target_text = targets[observation.target_id]
        if observation.target_kind != expected_kind:
            issues.append(
                NarrativeIssue(
                    observation.target_id,
                    "review_coverage",
                    observation.target_kind,
                )
            )
        if observation.text_spans != (target_text,):
            issues.append(
                NarrativeIssue(
                    observation.target_id,
                    "review_coverage",
                    observation.text_spans[0],
                )
            )
        if any(span not in target_text for span in observation.text_spans):
            issues.append(
                NarrativeIssue(
                    observation.target_id,
                    "missing_exact_span",
                    next(
                        span
                        for span in observation.text_spans
                        if span not in target_text
                    ),
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
        if any(span not in target_text for span in semantic_spans):
            issues.append(
                NarrativeIssue(
                    observation.target_id,
                    "missing_exact_span",
                    next(span for span in semantic_spans if span not in target_text),
                )
            )
        if observation.uncertain or observation.reality_binding == "uncertain":
            issues.append(
                NarrativeIssue(
                    observation.target_id,
                    "uncertain_meaning",
                    target_text,
                )
            )
        if observation.instruction_conflicts:
            issues.append(
                NarrativeIssue(
                    observation.target_id,
                    "instruction_conflict",
                    observation.instruction_conflicts[0],
                )
            )
        by_id[observation.target_id] = observation
    for missing_id in set(targets) - set(by_id):
        issues.append(NarrativeIssue(missing_id, "review_coverage", missing_id))

    facts_by_id = {fact.source_id: fact.exact_text for fact in frame.user_facts}
    for block in blocks:
        block_observation = by_id.get(block.block_id)
        if block_observation is None:
            continue
        if not block.source_refs or any(
            source_ref not in frame.allowed_fact_ids
            for source_ref in block.source_refs
        ):
            issues.append(
                NarrativeIssue(block.block_id, "unknown_fact_source", block.text)
            )
        if block.block_type == "actuality_source":
            if (
                facts_by_id.get(block.source_refs[0] if block.source_refs else "")
                != block.text
                or len(block.source_refs) != 1
                or block_observation.reality_binding != "user_actuality"
            ):
                issues.append(
                    NarrativeIssue(
                        block.block_id,
                        "actuality_changed",
                        block.text,
                    )
                )
            continue
        if "source:user_actuality" in " ".join(block.source_refs):
            issues.append(
                NarrativeIssue(
                    block.block_id,
                    "actuality_source_reused",
                    block.text,
                )
            )
        if block.block_type == "general_observation":
            product_sources = tuple(
                source_ref
                for source_ref in block.source_refs
                if source_ref in frame.allowed_product_fact_ids
            )
            if block_observation.reality_binding == "confirmed_fact":
                exact = frozenset(
                    statement
                    for source_ref in product_sources
                    for statement in exact_product_facts.get(source_ref, frozenset())
                )
                if not exact or block.text not in exact:
                    issues.append(
                        NarrativeIssue(
                            block.block_id,
                            "unsupported_product_fact",
                            block.text,
                        )
                    )
            elif block_observation.reality_binding != "general_observation":
                issues.append(
                    NarrativeIssue(
                        block.block_id,
                        "concrete_event_in_observation",
                        block.text,
                    )
                )
            person_event = (
                (block_observation.people or block_observation.relationships)
                and any(
                    (
                        block_observation.actions_or_events,
                        block_observation.motives,
                        block_observation.causes,
                        block_observation.results,
                    )
                )
            )
            concrete = (
                block_observation.dialogue,
                block_observation.times,
                block_observation.locations,
                block_observation.possessions,
            )
            if (
                block_observation.reality_binding == "general_observation"
                and (person_event or any(concrete))
            ):
                fragment = (
                    block_observation.actions_or_events
                    or block_observation.motives
                    or block_observation.causes
                    or block_observation.results
                    or next(group for group in concrete if group)
                )[0]
                issues.append(
                    NarrativeIssue(
                        block.block_id,
                        "concrete_event_in_observation",
                        fragment,
                    )
                )
        elif block.block_type == "hypothesis":
            if block_observation.reality_binding != "hypothesis":
                issues.append(
                    NarrativeIssue(
                        block.block_id,
                        "hypothesis_became_actual",
                        block.text,
                    )
                )
        elif block.block_type == "dramatization":
            if (
                block_observation.reality_binding != "dramatization"
                or not block_observation.dramatization_disclosure_spans
                or any(
                    span not in block.text
                    for span in block_observation.dramatization_disclosure_spans
                )
            ):
                issues.append(
                    NarrativeIssue(
                        block.block_id,
                        "dramatization_not_visible",
                        block.text,
                    )
                )

    for scene_id, declared_resources in scene_resource_refs.items():
        scene_observation = by_id.get(scene_id)
        if scene_observation is None:
            continue
        linked_types = {
            block.block_type
            for block in blocks
            if scene_id in block.linked_scene_ids
        }
        if scene_observation.reality_binding == "user_actuality":
            issues.append(
                NarrativeIssue(
                    scene_id,
                    "actuality_used_as_scene",
                    scene_text[scene_id],
                )
            )
        if frame.narrative_mode in {
            "actuality_reflection",
            "general_observation",
        }:
            if scene_observation.reality_binding not in {
                "general_observation",
                "confirmed_fact",
            }:
                issues.append(
                    NarrativeIssue(
                        scene_id,
                        "scene_mode_drift",
                        scene_text[scene_id],
                    )
                )
            unsupported_scene_detail = (
                scene_observation.relationships
                or scene_observation.dialogue
                or scene_observation.motives
                or scene_observation.causes
                or scene_observation.results
                or scene_observation.times
                or scene_observation.locations
                or scene_observation.possessions
            )
            unregistered_people = (
                scene_observation.people
                and "resource:creator_expression"
                not in scene_observation.resource_refs
            )
            if unsupported_scene_detail or unregistered_people:
                fragment = (
                    unsupported_scene_detail
                    or scene_observation.people
                )[0]
                issues.append(
                    NarrativeIssue(
                        scene_id,
                        "unregistered_scene_actuality",
                        fragment,
                    )
                )
        elif frame.narrative_mode == "hypothesis":
            if scene_observation.reality_binding not in {
                "general_observation",
                "hypothesis",
                "confirmed_fact",
            }:
                issues.append(
                    NarrativeIssue(
                        scene_id,
                        "scene_mode_drift",
                        scene_text[scene_id],
                    )
                )
        elif (
            scene_observation.reality_binding == "dramatization"
            and "dramatization" not in linked_types
        ):
            issues.append(
                NarrativeIssue(
                    scene_id,
                    "scene_mode_drift",
                    scene_text[scene_id],
                )
            )
        if any(resource not in allowed_resource_ids for resource in declared_resources):
            issues.append(
                NarrativeIssue(
                    scene_id,
                    "unsupported_resource",
                    next(
                        resource
                        for resource in declared_resources
                        if resource not in allowed_resource_ids
                    ),
                )
            )
        if any(
            resource not in allowed_resource_ids
            or resource.startswith("source:user_actuality:")
            for resource in scene_observation.resource_refs
        ):
            issues.append(
                NarrativeIssue(
                    scene_id,
                    "unsupported_resource",
                    next(
                        resource
                        for resource in scene_observation.resource_refs
                        if resource not in allowed_resource_ids
                        or resource.startswith("source:user_actuality:")
                    ),
                )
            )
    return tuple(dict.fromkeys(issues))


def _required_string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError("value must be a non-empty string")
    return value.strip()


def _string_tuple(
    value: object,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise TypeError("value must be a string list")
    result = tuple(dict.fromkeys(value))
    if not allow_empty and not result:
        raise TypeError("value must not be empty")
    return result
