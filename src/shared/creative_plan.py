from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from src.shared.errors import DomainError

CreativePrimaryValue: TypeAlias = Literal[
    "dressing_decision",
    "product_truth",
    "brand_life_narrative",
    "local_response",
    "visual_styling_story",
]
ProhibitedBinding: TypeAlias = Literal[
    "no_situated_event",
    "no_institutional_assertion",
    "no_user_history_expansion",
    "no_unregistered_resource",
]

PLAN_VERSION = "creative-plan-v2"
ACCOUNT_BASELINE_TONE_ID = "tone:account-baseline"
REQUIRED_PROHIBITED_BINDINGS: tuple[ProhibitedBinding, ...] = (
    "no_situated_event",
    "no_institutional_assertion",
    "no_user_history_expansion",
    "no_unregistered_resource",
)
_PLAN_KEYS = frozenset(
    {
        "plan_version",
        "topic_spans",
        "primary_value",
        "tone_ids",
        "mechanism_id",
        "platform_shape",
        "prohibited_bindings",
    }
)
_PRIMARY_VALUES = frozenset(
    {
        "dressing_decision",
        "product_truth",
        "brand_life_narrative",
        "local_response",
        "visual_styling_story",
    }
)


@dataclass(frozen=True)
class CreativePlanV2:
    plan_version: str
    topic_spans: tuple[str, ...]
    primary_value: CreativePrimaryValue
    tone_ids: tuple[str, ...]
    mechanism_id: str | None
    platform_shape: str
    prohibited_bindings: tuple[ProhibitedBinding, ...]


def platform_shape(target: str, media_format: str) -> str:
    return f"{target}:{media_format}"


def build_creative_plan(
    *,
    topic_spans: Sequence[str],
    primary_value: CreativePrimaryValue,
    tone_ids: Sequence[str],
    mechanism_id: str | None,
    target_shape: str,
) -> CreativePlanV2:
    return CreativePlanV2(
        plan_version=PLAN_VERSION,
        topic_spans=tuple(dict.fromkeys(topic_spans)),
        primary_value=primary_value,
        tone_ids=tuple(dict.fromkeys(tone_ids)),
        mechanism_id=mechanism_id,
        platform_shape=target_shape,
        prohibited_bindings=REQUIRED_PROHIBITED_BINDINGS,
    )


def creative_plan_document(plan: CreativePlanV2) -> dict[str, object]:
    return {
        "plan_version": plan.plan_version,
        "topic_spans": list(plan.topic_spans),
        "primary_value": plan.primary_value,
        "tone_ids": list(plan.tone_ids),
        "mechanism_id": plan.mechanism_id,
        "platform_shape": plan.platform_shape,
        "prohibited_bindings": list(plan.prohibited_bindings),
    }


def creative_plan_from_document(value: object) -> CreativePlanV2:
    if not isinstance(value, Mapping) or frozenset(value) != _PLAN_KEYS:
        raise DomainError("冻结创作计划结构无效")
    version = value.get("plan_version")
    raw_topics = value.get("topic_spans")
    primary = value.get("primary_value")
    raw_tones = value.get("tone_ids")
    mechanism = value.get("mechanism_id")
    shape = value.get("platform_shape")
    raw_prohibited = value.get("prohibited_bindings")
    if (
        version != PLAN_VERSION
        or not isinstance(raw_topics, list)
        or not raw_topics
        or any(not isinstance(item, str) or not item for item in raw_topics)
        or not isinstance(primary, str)
        or primary not in _PRIMARY_VALUES
        or not isinstance(raw_tones, list)
        or not raw_tones
        or any(not isinstance(item, str) or not item for item in raw_tones)
        or (mechanism is not None and not isinstance(mechanism, str))
        or not isinstance(shape, str)
        or not shape
        or not isinstance(raw_prohibited, list)
        or tuple(raw_prohibited) != REQUIRED_PROHIBITED_BINDINGS
    ):
        raise DomainError("冻结创作计划字段无效")
    return CreativePlanV2(
        plan_version=PLAN_VERSION,
        topic_spans=tuple(dict.fromkeys(cast(list[str], raw_topics))),
        primary_value=cast(CreativePrimaryValue, primary),
        tone_ids=tuple(dict.fromkeys(cast(list[str], raw_tones))),
        mechanism_id=mechanism,
        platform_shape=shape,
        prohibited_bindings=REQUIRED_PROHIBITED_BINDINGS,
    )


def validate_creative_plan(
    plan: CreativePlanV2,
    *,
    user_turns: Sequence[str],
    allowed_tone_ids: Sequence[str],
    allowed_mechanism_ids: Sequence[str],
    expected_primary_value: CreativePrimaryValue,
    expected_platform_shape: str,
) -> None:
    available_tones = frozenset(allowed_tone_ids)
    available_mechanisms = frozenset(allowed_mechanism_ids)
    if (
        plan.plan_version != PLAN_VERSION
        or not plan.topic_spans
        or len(plan.topic_spans) > 8
        or any(
            len(span) > 1000
            or not any(span in user_turn for user_turn in user_turns)
            for span in plan.topic_spans
        )
        or not plan.tone_ids
        or any(tone_id not in available_tones for tone_id in plan.tone_ids)
        or (
            plan.mechanism_id is not None
            and plan.mechanism_id not in available_mechanisms
        )
        or plan.primary_value != expected_primary_value
        or plan.platform_shape != expected_platform_shape
        or plan.prohibited_bindings != REQUIRED_PROHIBITED_BINDINGS
    ):
        raise DomainError("创作计划超出服务端冻结边界")
