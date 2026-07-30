from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from src.shared.errors import DomainError

_PREFILL_PATH = Path(__file__).resolve().parents[2] / "config" / "onboarding" / "diyu-m7-2b-prefill-v1.json"
_PROFILE_KEYS = (
    "identity_position",
    "authority_boundary",
    "audience_relationship",
    "content_territories",
    "default_production_conditions",
)


def load_brand_prefill(brand_name: str) -> dict[str, object] | None:
    """Load one source-grounded onboarding draft without promoting it to runtime truth."""
    raw = json.loads(_PREFILL_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise DomainError("品牌渐进入驻草案格式无效。")
    document = cast(dict[str, object], raw)
    if document.get("brand_name") != brand_name:
        return None
    if document.get("status") != "review_candidate":
        raise DomainError("品牌渐进入驻草案状态无效。")
    return document


def account_profile_prefill(
    brand_name: str,
    account_name: str,
    content_role: str,
) -> tuple[dict[str, object], str] | None:
    """Return an editable five-part draft for an exact account/role match."""
    document = load_brand_prefill(brand_name)
    if document is None:
        return None
    profiles = document.get("account_profiles")
    if not isinstance(profiles, list):
        raise DomainError("品牌账号画像草案格式无效。")
    for item in profiles:
        if not isinstance(item, dict):
            raise DomainError("品牌账号画像草案条目无效。")
        candidate = cast(dict[str, object], item)
        role_marker = candidate.get("content_role_contains")
        if (
            candidate.get("account_name") != account_name
            or not isinstance(role_marker, str)
            or role_marker not in content_role
        ):
            continue
        segments = candidate.get("segments")
        if not isinstance(segments, Mapping):
            raise DomainError("品牌账号五段画像草案无效。")
        checked = {
            key: value for key in _PROFILE_KEYS if isinstance((value := segments.get(key)), str) and value.strip()
        }
        if len(checked) != len(_PROFILE_KEYS):
            raise DomainError("品牌账号五段画像草案不完整。")
        draft: dict[str, object] = {
            "profile_id": None,
            "version": None,
            "is_draft": True,
            "content_role": content_role,
            **checked,
        }
        source_summary = document.get("source_summary")
        if not isinstance(source_summary, str) or not source_summary.strip():
            raise DomainError("品牌渐进入驻草案缺少来源说明。")
        return draft, source_summary
    return None


def generic_account_profile_candidate(brand_name: str) -> dict[str, str]:
    """Build an editable cold-start candidate without asserting brand facts."""
    normalized_brand = brand_name.strip() or "当前品牌"
    return {
        "identity_position": (
            f"作为{normalized_brand}对外表达的一套账号身份，围绕管理员确认后的品牌边界发声。"
        ),
        "authority_boundary": (
            "只使用已经确认的品牌、商品和经营资料；没有来源的价格、库存、效果、经历和承诺不作事实表达。"
        ),
        "audience_relationship": (
            "以平等、清楚的方式回应目标受众的真实问题，不冒充顾客、员工或具体人物经历。"
        ),
        "content_territories": (
            "从已确认的品牌资料、商品事实和账号长期主题中选择内容，不把候选草案当成正式事实。"
        ),
        "default_production_conditions": (
            "按当前已登记的人员、场地、设备和平台形式完成；未登记资源不默认可用。"
        ),
    }


def product_prefills(brand_name: str) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Return candidate rows separately from confirmed product facts."""
    document = load_brand_prefill(brand_name)
    if document is None:
        return [], {}
    drafts = document.get("product_drafts")
    if not isinstance(drafts, list) or not all(isinstance(item, dict) for item in drafts):
        raise DomainError("品牌商品预填草案格式无效。")
    source_refs = document.get("source_refs")
    if not isinstance(source_refs, list) or not all(isinstance(item, str) for item in source_refs):
        raise DomainError("品牌渐进入驻草案来源格式无效。")
    metadata: dict[str, object] = {
        "schema_version": str(document.get("schema_version") or ""),
        "status": str(document.get("status") or ""),
        "source_summary": str(document.get("source_summary") or ""),
        "source_refs": list(source_refs),
    }
    return [cast(dict[str, object], dict(item)) for item in drafts], metadata
