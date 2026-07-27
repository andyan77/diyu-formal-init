from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from src.shared.types import (
    ContentTarget,
    MediaFormat,
    PlatformDirection,
    PlatformDirectionProvenance,
)

_SOURCE = Path(__file__).with_name("platform_directions.json")


def _required_text(mapping: dict[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("平台方向来源与时效字段无效")
    return value


def _optional_text(mapping: dict[str, object], key: str) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("平台方向可选版本字段无效")
    return value


def _text_tuple(mapping: dict[str, object], key: str, *, allow_empty: bool) -> tuple[str, ...]:
    value = mapping.get(key)
    if not isinstance(value, list) or (not allow_empty and not value):
        raise RuntimeError("平台方向来源或替代关系无效")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise RuntimeError("平台方向来源或替代关系无效")
    return tuple(cast(list[str], value))


def _load_resource() -> tuple[str, PlatformDirectionProvenance, dict[str, object]]:
    raw_value: object = json.loads(_SOURCE.read_text(encoding="utf-8"))
    if not isinstance(raw_value, dict):
        raise RuntimeError("平台方向资源无效")
    raw = cast(dict[str, object], raw_value)
    schema_version = raw.get("schema_version")
    version = raw.get("version")
    metadata_revision = raw.get("metadata_revision")
    targets = raw.get("targets")
    provenance_value = raw.get("provenance")
    if (
        not isinstance(schema_version, str)
        or not schema_version
        or not isinstance(version, str)
        or not version
        or not isinstance(metadata_revision, str)
        or not metadata_revision
        or not isinstance(targets, dict)
        or not isinstance(provenance_value, dict)
    ):
        raise RuntimeError("平台方向资源无效")
    provenance_raw = cast(dict[str, object], provenance_value)
    if "official_platform_rule_version" not in provenance_raw or "superseded_by" not in provenance_raw:
        raise RuntimeError("平台方向可选版本字段缺失")
    provenance = PlatformDirectionProvenance(
        resource_schema_version=schema_version,
        metadata_revision=metadata_revision,
        source_kind=_required_text(provenance_raw, "source_kind"),
        source_refs=_text_tuple(provenance_raw, "source_refs", allow_empty=False),
        official_platform_rule_version=_optional_text(provenance_raw, "official_platform_rule_version"),
        official_version_note=_required_text(provenance_raw, "official_version_note"),
        observed_or_effective_at=_required_text(provenance_raw, "observed_or_effective_at"),
        last_verified_at=_required_text(provenance_raw, "last_verified_at"),
        verification_status=_required_text(provenance_raw, "verification_status"),
        freshness_status=_required_text(provenance_raw, "freshness_status"),
        supersedes=_text_tuple(provenance_raw, "supersedes", allow_empty=True),
        superseded_by=_optional_text(provenance_raw, "superseded_by"),
        maintenance_owner=_required_text(provenance_raw, "maintenance_owner"),
    )
    return version, provenance, cast(dict[str, object], targets)


def _direction_digest(
    *,
    rule_id: str,
    rule_version: str,
    platform: str,
    media_format: str,
    direction: str,
) -> str:
    canonical = json.dumps(
        {
            "direction": direction,
            "media_format": media_format,
            "platform": platform,
            "rule_id": rule_id,
            "rule_version": rule_version,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def direction_for(target: ContentTarget) -> PlatformDirection:
    """Return the small, versioned platform direction used by one compilation."""
    version, provenance, targets = _load_resource()
    item = targets.get(target)
    if not isinstance(item, dict):
        raise RuntimeError("当前目标没有平台方向")
    item_mapping = cast(dict[str, object], item)
    rule_id = item_mapping.get("rule_id")
    rule_kind = item_mapping.get("rule_kind")
    platform = item_mapping.get("platform")
    media_format = item_mapping.get("media_format")
    applicability = item_mapping.get("applicability")
    platform_capability_source_ref = item_mapping.get("platform_capability_source_ref")
    platform_capability_source_scope = item_mapping.get("platform_capability_source_scope")
    direction_digest = item_mapping.get("direction_digest")
    direction = item_mapping.get("direction")
    if not all(
        isinstance(value, str) and value
        for value in (
            rule_id,
            rule_kind,
            platform,
            media_format,
            applicability,
            platform_capability_source_ref,
            platform_capability_source_scope,
            direction_digest,
            direction,
        )
    ):
        raise RuntimeError("平台方向资源字段无效")
    if media_format not in {"video", "graphic"}:
        raise RuntimeError("平台方向媒体格式无效")
    expected_digest = _direction_digest(
        rule_id=cast(str, rule_id),
        rule_version=version,
        platform=cast(str, platform),
        media_format=media_format,
        direction=cast(str, direction),
    )
    if direction_digest != expected_digest:
        raise RuntimeError("平台方向正文摘要无效")
    return PlatformDirection(
        version=version,
        rule_id=cast(str, rule_id),
        rule_kind=cast(str, rule_kind),
        platform=cast(str, platform),
        media_format=cast(MediaFormat, media_format),
        applicability=cast(str, applicability),
        platform_capability_source_ref=cast(str, platform_capability_source_ref),
        platform_capability_source_scope=cast(str, platform_capability_source_scope),
        direction_digest=direction_digest,
        direction=cast(str, direction),
        provenance=provenance,
    )


def target_label(target: ContentTarget) -> str:
    return {
        "douyin_video": "抖音视频",
        "xiaohongshu_video": "小红书视频",
        "xiaohongshu_graphic": "小红书图文",
        "wechat_channels_video": "微信视频号视频",
    }[target]


def target_from_text(text: str) -> ContentTarget | None:
    """Recognize only the four frozen target names; this is never a scope identifier."""
    normalized = text.casefold()
    if "小红书图文" in normalized or "改成图文" in normalized:
        return "xiaohongshu_graphic"
    if "小红书视频" in normalized:
        return "xiaohongshu_video"
    if "视频号" in normalized or "微信视频" in normalized:
        return "wechat_channels_video"
    if "抖音" in normalized:
        return "douyin_video"
    return None
