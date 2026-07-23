from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from src.shared.types import ContentTarget, MediaFormat, PlatformDirection

_SOURCE = Path(__file__).with_name("platform_directions.json")


def direction_for(target: ContentTarget) -> PlatformDirection:
    """Return the small, versioned platform direction used by one compilation."""
    raw = json.loads(_SOURCE.read_text(encoding="utf-8"))
    targets = raw.get("targets")
    if not isinstance(raw.get("version"), str) or not isinstance(targets, dict):
        raise RuntimeError("平台方向资源无效")
    item = targets.get(target)
    if not isinstance(item, dict):
        raise RuntimeError("当前目标没有平台方向")
    platform = item.get("platform")
    media_format = item.get("media_format")
    direction = item.get("direction")
    if not all(isinstance(value, str) and value for value in (platform, media_format, direction)):
        raise RuntimeError("平台方向资源字段无效")
    if media_format not in {"video", "graphic"}:
        raise RuntimeError("平台方向媒体格式无效")
    return PlatformDirection(
        version=cast(str, raw["version"]),
        platform=cast(str, platform),
        media_format=cast(MediaFormat, media_format),
        direction=cast(str, direction),
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
