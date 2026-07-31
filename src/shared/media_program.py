from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from src.shared.errors import DomainError, GenerationFailed
from src.shared.types import (
    ContentProduct,
    MediaFormat,
    ReferenceMaterial,
)

MediaCapabilityId: TypeAlias = Literal[
    "abstract_composition",
    "creator_expression",
    "registered_product_display",
    "selected_media_asset",
]
MediaProgramId: TypeAlias = Literal[
    "graphic_fact_guided_v1",
    "graphic_observation_progression_v1",
    "graphic_choice_contrast_v1",
    "graphic_series_response_v1",
    "graphic_series_choice_v1",
    "graphic_registered_product_relation_v1",
    "graphic_selected_asset_sequence_v1",
    "video_dynamic_text_v1",
    "video_creator_expression_v1",
    "video_registered_product_display_v1",
    "video_condition_choice_v1",
    "video_selected_asset_sequence_v1",
]
OptionalCaptureSuggestionId: TypeAlias = Literal[
    "optional-current-subject-capture-v1",
    "optional-current-product-capture-v1",
]

MEDIA_CAPABILITY_ENVELOPE_VERSION = "media-capability-envelope-v1"
MEDIA_PROGRAM_VERSION = "media-program-v1"
ABSTRACT_COMPOSITION_RESOURCE_ID = "resource:original_composition"

_PROGRAM_MEDIA_FORMAT: dict[MediaProgramId, MediaFormat] = {
    "graphic_fact_guided_v1": "graphic",
    "graphic_observation_progression_v1": "graphic",
    "graphic_choice_contrast_v1": "graphic",
    "graphic_series_response_v1": "graphic",
    "graphic_series_choice_v1": "graphic",
    "graphic_registered_product_relation_v1": "graphic",
    "graphic_selected_asset_sequence_v1": "graphic",
    "video_dynamic_text_v1": "video",
    "video_creator_expression_v1": "video",
    "video_registered_product_display_v1": "video",
    "video_condition_choice_v1": "video",
    "video_selected_asset_sequence_v1": "video",
}
_PROGRAM_REQUIRED_CAPABILITIES: dict[
    MediaProgramId,
    frozenset[MediaCapabilityId],
] = {
    "graphic_fact_guided_v1": frozenset({"abstract_composition"}),
    "graphic_observation_progression_v1": frozenset({"abstract_composition"}),
    "graphic_choice_contrast_v1": frozenset({"abstract_composition"}),
    "graphic_series_response_v1": frozenset({"abstract_composition"}),
    "graphic_series_choice_v1": frozenset({"abstract_composition"}),
    "graphic_registered_product_relation_v1": frozenset(
        {"abstract_composition", "registered_product_display"}
    ),
    "graphic_selected_asset_sequence_v1": frozenset(
        {"abstract_composition", "selected_media_asset"}
    ),
    "video_dynamic_text_v1": frozenset({"abstract_composition"}),
    "video_creator_expression_v1": frozenset(
        {"abstract_composition", "creator_expression"}
    ),
    "video_registered_product_display_v1": frozenset(
        {"abstract_composition", "registered_product_display"}
    ),
    "video_condition_choice_v1": frozenset({"abstract_composition"}),
    "video_selected_asset_sequence_v1": frozenset(
        {"abstract_composition", "selected_media_asset"}
    ),
}
_PROGRAM_UNIT_BINDINGS: dict[MediaProgramId, tuple[str, ...]] = {
    "graphic_fact_guided_v1": (
        "unit:title",
        "unit:natural-guide",
        "unit:frozen-fact:*",
        "unit:body:*",
        "unit:release-caption",
    ),
    "graphic_observation_progression_v1": (
        "unit:title",
        "unit:natural-guide",
        "unit:body:*",
        "unit:release-caption",
    ),
    "graphic_choice_contrast_v1": (
        "unit:title",
        "unit:natural-guide",
        "unit:body:*",
        "unit:release-caption",
    ),
    "graphic_series_response_v1": (
        "unit:title",
        "unit:natural-guide",
        "series:prior-entries",
        "unit:body:*",
        "unit:release-caption",
    ),
    "graphic_series_choice_v1": (
        "unit:title",
        "unit:natural-guide",
        "series:prior-entries",
        "unit:body:*",
        "unit:release-caption",
    ),
    "graphic_registered_product_relation_v1": (
        "unit:title",
        "unit:frozen-fact:*",
        "unit:body:*",
        "unit:release-caption",
    ),
    "graphic_selected_asset_sequence_v1": (
        "unit:title",
        "unit:body:*",
        "unit:release-caption",
    ),
    "video_dynamic_text_v1": (
        "unit:title",
        "unit:natural-guide",
        "unit:body:*",
        "unit:release-caption",
    ),
    "video_creator_expression_v1": (
        "unit:title",
        "unit:natural-guide",
        "unit:body:*",
        "unit:release-caption",
    ),
    "video_registered_product_display_v1": (
        "unit:title",
        "unit:frozen-fact:*",
        "unit:body:*",
        "unit:release-caption",
    ),
    "video_condition_choice_v1": (
        "unit:title",
        "unit:natural-guide",
        "unit:body:*",
        "unit:release-caption",
    ),
    "video_selected_asset_sequence_v1": (
        "unit:title",
        "unit:body:*",
        "unit:release-caption",
    ),
}


@dataclass(frozen=True)
class MediaResourceV1:
    resource_id: str
    resource_version: str
    media_type: str
    source_ref: str
    capability_id: MediaCapabilityId


@dataclass(frozen=True)
class MediaCapabilityEnvelopeV1:
    envelope_version: str
    platform_shape: str
    media_format: MediaFormat
    capability_ids: tuple[MediaCapabilityId, ...]
    resources: tuple[MediaResourceV1, ...]
    allowed_program_ids: tuple[MediaProgramId, ...]

    @property
    def resource_ids(self) -> frozenset[str]:
        return frozenset(resource.resource_id for resource in self.resources)

    def resources_for(
        self,
        capability_id: MediaCapabilityId,
    ) -> tuple[MediaResourceV1, ...]:
        return tuple(
            resource
            for resource in self.resources
            if resource.capability_id == capability_id
        )


@dataclass(frozen=True)
class MediaProgramSelectionV1:
    program_version: str
    program_id: MediaProgramId
    required_resource_ids: tuple[str, ...]
    unit_bindings: tuple[str, ...]
    series_position: int | None
    optional_capture_suggestion_id: OptionalCaptureSuggestionId | None = None


def _canonical_digest(document: Mapping[str, object]) -> str:
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def media_envelope_document(
    envelope: MediaCapabilityEnvelopeV1,
) -> dict[str, object]:
    return {
        "envelope_version": envelope.envelope_version,
        "platform_shape": envelope.platform_shape,
        "media_format": envelope.media_format,
        "capability_ids": list(envelope.capability_ids),
        "resources": [
            {
                "resource_id": resource.resource_id,
                "resource_version": resource.resource_version,
                "media_type": resource.media_type,
                "source_ref": resource.source_ref,
                "capability_id": resource.capability_id,
            }
            for resource in envelope.resources
        ],
        "allowed_program_ids": list(envelope.allowed_program_ids),
    }


def media_program_document(
    selection: MediaProgramSelectionV1,
) -> dict[str, object]:
    return {
        "program_version": selection.program_version,
        "program_id": selection.program_id,
        "required_resource_ids": list(selection.required_resource_ids),
        "unit_bindings": list(selection.unit_bindings),
        "series_position": selection.series_position,
        "optional_capture_suggestion_id": (
            selection.optional_capture_suggestion_id
        ),
    }


def media_envelope_digest(envelope: MediaCapabilityEnvelopeV1) -> str:
    return _canonical_digest(media_envelope_document(envelope))


def media_program_digest(selection: MediaProgramSelectionV1) -> str:
    return _canonical_digest(media_program_document(selection))


def _allowed_programs(
    media_format: MediaFormat,
    capabilities: frozenset[MediaCapabilityId],
) -> tuple[MediaProgramId, ...]:
    return tuple(
        program_id
        for program_id, program_media_format in _PROGRAM_MEDIA_FORMAT.items()
        if program_media_format == media_format
        and _PROGRAM_REQUIRED_CAPABILITIES[program_id] <= capabilities
    )


def build_media_capability_envelope(
    *,
    platform_shape: str,
    media_format: MediaFormat,
    selected_materials: Sequence[ReferenceMaterial] = (),
    registered_resources: Sequence[MediaResourceV1] = (),
) -> MediaCapabilityEnvelopeV1:
    """Freeze media capabilities from selected trusted resources only.

    Product facts, user prose and production conditions deliberately are not
    inputs.  The caller may pass registered resources only after its own
    tenant/brand/account/organization and enabled-version checks.
    """

    resources: list[MediaResourceV1] = [
        MediaResourceV1(
            resource_id=ABSTRACT_COMPOSITION_RESOURCE_ID,
            resource_version="abstract-composition-v1",
            media_type="abstract",
            source_ref="server:abstract-composition-v1",
            capability_id="abstract_composition",
        )
    ]
    for material in selected_materials:
        if material.media_type not in {"image", "video"}:
            continue
        resources.append(
            MediaResourceV1(
                resource_id=(
                    f"resource:selected-media:{material.asset_id}:"
                    f"v{material.reference_version}"
                ),
                resource_version=str(material.reference_version),
                media_type=material.media_type,
                source_ref=(
                    f"material:{material.asset_id}:"
                    f"v{material.reference_version}"
                ),
                capability_id="selected_media_asset",
            )
        )
    resources.extend(registered_resources)
    resource_ids = [resource.resource_id for resource in resources]
    if len(resource_ids) != len(set(resource_ids)):
        raise DomainError("媒体能力包包含重复资源")
    if any(
        not resource.resource_id
        or not resource.resource_version
        or not resource.source_ref
        for resource in resources
    ):
        raise DomainError("媒体能力包资源缺少冻结版本或来源")
    capabilities = tuple(
        dict.fromkeys(resource.capability_id for resource in resources)
    )
    capability_set = frozenset(capabilities)
    return MediaCapabilityEnvelopeV1(
        envelope_version=MEDIA_CAPABILITY_ENVELOPE_VERSION,
        platform_shape=platform_shape,
        media_format=media_format,
        capability_ids=capabilities,
        resources=tuple(resources),
        allowed_program_ids=_allowed_programs(
            media_format,
            capability_set,
        ),
    )


def select_media_program(
    *,
    primary_product: ContentProduct,
    envelope: MediaCapabilityEnvelopeV1,
    mechanism_id: str | None,
    series_position: int | None,
    fact_count: int,
) -> MediaProgramSelectionV1:
    """Select one closed deterministic media program before Writer runs."""

    del mechanism_id
    selected_assets = envelope.resources_for("selected_media_asset")
    registered_products = envelope.resources_for(
        "registered_product_display"
    )
    creator_resources = envelope.resources_for("creator_expression")
    optional_suggestion: OptionalCaptureSuggestionId | None = None
    if primary_product == "visual_styling_story":
        if len(registered_products) < 2:
            raise GenerationFailed(
                "这条视觉造型内容需要先明确选择至少两件当前可用于制作的登记商品素材。"
            )
        program_id: MediaProgramId = (
            "graphic_registered_product_relation_v1"
            if envelope.media_format == "graphic"
            else "video_registered_product_display_v1"
        )
    elif selected_assets:
        program_id = (
            "graphic_selected_asset_sequence_v1"
            if envelope.media_format == "graphic"
            else "video_selected_asset_sequence_v1"
        )
    elif envelope.media_format == "video":
        if primary_product == "dressing_decision":
            program_id = "video_condition_choice_v1"
        elif creator_resources:
            program_id = "video_creator_expression_v1"
        else:
            program_id = "video_dynamic_text_v1"
        if primary_product == "product_truth":
            optional_suggestion = "optional-current-product-capture-v1"
        elif primary_product == "brand_life_narrative":
            optional_suggestion = "optional-current-subject-capture-v1"
    elif series_position is not None and series_position >= 3:
        program_id = "graphic_series_choice_v1"
    elif series_position == 2:
        program_id = "graphic_series_response_v1"
    elif primary_product == "product_truth" or fact_count > 1:
        program_id = "graphic_fact_guided_v1"
        if primary_product == "product_truth":
            optional_suggestion = "optional-current-product-capture-v1"
    elif primary_product in {"dressing_decision", "local_response"}:
        program_id = "graphic_choice_contrast_v1"
    else:
        program_id = "graphic_observation_progression_v1"
        if primary_product == "brand_life_narrative":
            optional_suggestion = "optional-current-subject-capture-v1"
    if program_id not in envelope.allowed_program_ids:
        raise GenerationFailed("当前媒体能力不能执行服务端选择的成品程序")
    required_capabilities = _PROGRAM_REQUIRED_CAPABILITIES[program_id]
    required_resource_ids = tuple(
        resource.resource_id
        for resource in envelope.resources
        if resource.capability_id in required_capabilities
        and (
            resource.capability_id == "abstract_composition"
            or program_id
            in {
                "graphic_registered_product_relation_v1",
                "video_registered_product_display_v1",
                "graphic_selected_asset_sequence_v1",
                "video_selected_asset_sequence_v1",
                "video_creator_expression_v1",
            }
        )
    )
    return MediaProgramSelectionV1(
        program_version=MEDIA_PROGRAM_VERSION,
        program_id=program_id,
        required_resource_ids=required_resource_ids,
        unit_bindings=_PROGRAM_UNIT_BINDINGS[program_id],
        series_position=series_position,
        optional_capture_suggestion_id=optional_suggestion,
    )


def assert_media_program_allowed(
    envelope: MediaCapabilityEnvelopeV1,
    selection: MediaProgramSelectionV1,
) -> None:
    if (
        envelope.envelope_version != MEDIA_CAPABILITY_ENVELOPE_VERSION
        or selection.program_version != MEDIA_PROGRAM_VERSION
    ):
        raise GenerationFailed("媒体能力包或成品程序版本无效")
    if selection.program_id not in envelope.allowed_program_ids:
        raise GenerationFailed("成品程序不属于冻结媒体能力包")
    if _PROGRAM_MEDIA_FORMAT[selection.program_id] != envelope.media_format:
        raise GenerationFailed("成品程序与冻结媒体形式不一致")
    if selection.unit_bindings != _PROGRAM_UNIT_BINDINGS[selection.program_id]:
        raise GenerationFailed("成品程序单元绑定漂移")
    required_capabilities = _PROGRAM_REQUIRED_CAPABILITIES[
        selection.program_id
    ]
    if not required_capabilities <= frozenset(envelope.capability_ids):
        raise GenerationFailed("成品程序缺少冻结媒体能力")
    if any(
        resource_id not in envelope.resource_ids
        for resource_id in selection.required_resource_ids
    ):
        raise GenerationFailed("成品程序引用了媒体能力包之外的资源")
    required_resources = {
        resource.resource_id
        for resource in envelope.resources
        if resource.capability_id in required_capabilities
        and (
            resource.capability_id == "abstract_composition"
            or selection.program_id
            in {
                "graphic_registered_product_relation_v1",
                "video_registered_product_display_v1",
                "graphic_selected_asset_sequence_v1",
                "video_selected_asset_sequence_v1",
                "video_creator_expression_v1",
            }
        )
    }
    if set(selection.required_resource_ids) != required_resources:
        raise GenerationFailed("成品程序所需资源集合漂移")


def media_envelope_from_document(
    value: object,
) -> MediaCapabilityEnvelopeV1:
    if not isinstance(value, Mapping):
        raise DomainError("冻结媒体能力包无效")
    try:
        raw_resources = value["resources"]
        raw_capabilities = value["capability_ids"]
        raw_programs = value["allowed_program_ids"]
        if (
            not isinstance(raw_resources, list)
            or not isinstance(raw_capabilities, list)
            or not isinstance(raw_programs, list)
        ):
            raise TypeError
        resources = tuple(
            MediaResourceV1(
                resource_id=str(resource["resource_id"]),
                resource_version=str(resource["resource_version"]),
                media_type=str(resource["media_type"]),
                source_ref=str(resource["source_ref"]),
                capability_id=cast(
                    MediaCapabilityId,
                    resource["capability_id"],
                ),
            )
            for resource in raw_resources
            if isinstance(resource, Mapping)
        )
        if len(resources) != len(raw_resources):
            raise TypeError
        envelope = MediaCapabilityEnvelopeV1(
            envelope_version=str(value["envelope_version"]),
            platform_shape=str(value["platform_shape"]),
            media_format=cast(MediaFormat, value["media_format"]),
            capability_ids=tuple(
                cast(MediaCapabilityId, item) for item in raw_capabilities
            ),
            resources=resources,
            allowed_program_ids=tuple(
                cast(MediaProgramId, item) for item in raw_programs
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DomainError("冻结媒体能力包无效") from exc
    expected = build_media_capability_envelope(
        platform_shape=envelope.platform_shape,
        media_format=envelope.media_format,
        registered_resources=tuple(
            resource
            for resource in envelope.resources
            if resource.capability_id != "abstract_composition"
        ),
    )
    if media_envelope_document(expected) != media_envelope_document(envelope):
        raise DomainError("冻结媒体能力包结构漂移")
    return envelope


def media_program_from_document(
    value: object,
) -> MediaProgramSelectionV1:
    if not isinstance(value, Mapping):
        raise DomainError("冻结媒体程序无效")
    try:
        raw_resources = value["required_resource_ids"]
        raw_bindings = value["unit_bindings"]
        if not isinstance(raw_resources, list) or not isinstance(
            raw_bindings,
            list,
        ):
            raise TypeError
        raw_position = value.get("series_position")
        raw_suggestion = value.get("optional_capture_suggestion_id")
        return MediaProgramSelectionV1(
            program_version=str(value["program_version"]),
            program_id=cast(MediaProgramId, value["program_id"]),
            required_resource_ids=tuple(str(item) for item in raw_resources),
            unit_bindings=tuple(str(item) for item in raw_bindings),
            series_position=(
                int(raw_position) if raw_position is not None else None
            ),
            optional_capture_suggestion_id=(
                cast(OptionalCaptureSuggestionId, raw_suggestion)
                if raw_suggestion is not None
                else None
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DomainError("冻结媒体程序无效") from exc
