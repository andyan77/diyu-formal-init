from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.shared.errors import DomainError
from src.shared.types import ContentControlContext, CreativeDirection, DirectionSelection

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_DIR = _PROJECT_ROOT / "config" / "content_expression"
_CATALOG_FILE = _CATALOG_DIR / "catalog-v1.json"
_INVENTORY_FILE = _CATALOG_DIR / "capability-inventory-v1.jsonl"

AXIS_ORDER: tuple[str, ...] = ("topic", "mechanism", "style", "form", "continuity")
CAPABILITY_STATES = frozenset(
    {"verified", "composable", "experimental", "unsupported", "explicitly_out_of_scope"}
)
COMPACT_STATES = frozenset({"verified", "composable"})
GAP_TYPES = frozenset(
    {
        "unclassified",
        "knowledge",
        "generation_method",
        "media_tool",
        "product_scope",
        "policy_conflict",
        "source_gap",
    }
)
# Declared research targets from ADR-027 §决策 2.  They are reconciliation goals, not evidence
# that the positions exist; missing positions become CAT-SOURCE-GAP-* records.
DECLARED_SOURCE_TARGETS: tuple[tuple[str, str, int], ...] = (
    ("风格", "STYLE", 20),
    ("题材", "TOPIC", 55),
    ("体裁", "GENRE", 44),
)


@dataclass(frozen=True)
class CatalogAxis:
    key: str
    label: str
    question: str


@dataclass(frozen=True)
class CatalogEntry:
    stable_id: str
    axis: str
    label: str
    source_label: str
    capability_state: str
    body_related: bool
    restrained_variant: str
    preserved_aspect: str


@dataclass(frozen=True)
class ExpressionCatalog:
    """The one versioned runtime view of the five expression axes.

    Only Git-versioned repository data reaches here; tenants have no catalog editing surface.
    """

    catalog_version: str
    axes: tuple[CatalogAxis, ...]
    restraint_markers: tuple[str, ...]
    entries: tuple[CatalogEntry, ...]

    def entry(self, stable_id: str) -> CatalogEntry | None:
        return next((item for item in self.entries if item.stable_id == stable_id), None)

    def visible(self, body_related_opt_in: bool) -> tuple[CatalogEntry, ...]:
        """Body-related options stay hidden until the person themself turns them on."""
        return tuple(item for item in self.entries if body_related_opt_in or not item.body_related)


def _fail(message: str) -> DomainError:
    return DomainError(message)


def _load_catalog_document(path: Path) -> ExpressionCatalog:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail("内容表达目录无法读取") from exc
    if not isinstance(raw, dict):
        raise _fail("内容表达目录结构无效")
    version = raw.get("catalog_version")
    if not isinstance(version, str) or not version.startswith("content-expression-catalog-v"):
        raise _fail("内容表达目录版本无效")
    axes_raw = raw.get("axes")
    if not isinstance(axes_raw, list) or [item.get("key") for item in axes_raw] != list(AXIS_ORDER):
        raise _fail("内容表达目录必须恰好覆盖固定五轴")
    axes = tuple(
        CatalogAxis(str(item["key"]), str(item["label"]), str(item["question"])) for item in axes_raw
    )
    markers_raw = raw.get("brand_restraint_markers")
    if not isinstance(markers_raw, list) or not markers_raw:
        raise _fail("内容表达目录缺少品牌克制标记")
    entries_raw = raw.get("entries")
    if not isinstance(entries_raw, list) or not entries_raw:
        raise _fail("内容表达目录缺少条目")
    entries: list[CatalogEntry] = []
    seen: set[str] = set()
    for item in entries_raw:
        if not isinstance(item, dict):
            raise _fail("内容表达目录条目结构无效")
        stable_id = str(item.get("stable_id", ""))
        state = str(item.get("capability_state", ""))
        axis = str(item.get("axis", ""))
        if not stable_id or stable_id in seen:
            raise _fail("内容表达目录存在重复或空的稳定标识")
        if state not in CAPABILITY_STATES:
            raise _fail("内容表达目录存在未知能力状态")
        if state not in COMPACT_STATES:
            raise _fail("精简目录只能包含已验证或可组合的能力")
        if axis not in AXIS_ORDER:
            raise _fail("内容表达目录存在未知表达轴")
        seen.add(stable_id)
        entries.append(
            CatalogEntry(
                stable_id=stable_id,
                axis=axis,
                label=str(item.get("label", "")),
                source_label=str(item.get("source_label", "")),
                capability_state=state,
                body_related=bool(item.get("body_related", False)),
                restrained_variant=str(item.get("restrained_variant", "")),
                preserved_aspect=str(item.get("preserved_aspect", "")),
            )
        )
    return ExpressionCatalog(
        catalog_version=version,
        axes=axes,
        restraint_markers=tuple(str(marker) for marker in markers_raw),
        entries=tuple(entries),
    )


@lru_cache(maxsize=1)
def load_catalog() -> ExpressionCatalog:
    return _load_catalog_document(_CATALOG_FILE)


def load_inventory(path: Path = _INVENTORY_FILE) -> tuple[dict[str, object], ...]:
    """Read the full research panorama; it is an accounting view, not a runtime option list."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise _fail("能力全景清单无法读取") from exc
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in lines:
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict):
            raise _fail("能力全景清单结构无效")
        stable_id = str(record.get("stable_id", ""))
        if not stable_id or stable_id in seen:
            raise _fail("能力全景清单存在重复或空的稳定标识")
        if str(record.get("capability_state", "")) not in CAPABILITY_STATES:
            raise _fail("能力全景清单存在未知能力状态")
        if str(record.get("mapped_axis", "")) not in AXIS_ORDER:
            raise _fail("能力全景清单存在未知表达轴")
        gap_type = str(record.get("gap_type", ""))
        if gap_type and gap_type not in GAP_TYPES:
            raise _fail("能力全景清单存在未知缺口类型")
        seen.add(stable_id)
        records.append(record)
    return tuple(records)


def reconcile_sources(
    records: tuple[dict[str, object], ...],
) -> tuple[dict[str, dict[str, int]], tuple[str, ...]]:
    """Mechanically count real source labels per declared family and list missing positions."""
    summary: dict[str, dict[str, int]] = {}
    gaps: list[str] = []
    for family_label, family_code, target in DECLARED_SOURCE_TARGETS:
        defined = [
            record
            for record in records
            if str(record["stable_id"]).startswith(f"CAT-{family_code}-")
        ]
        family_gaps = [
            str(record["stable_id"])
            for record in records
            if str(record["stable_id"]).startswith(f"CAT-SOURCE-GAP-{family_code}-")
        ]
        summary[family_label] = {
            "defined": len(defined),
            "declared_target": target,
            "source_gaps": len(family_gaps),
        }
        gaps.extend(sorted(family_gaps))
    return summary, tuple(gaps)


def boundary_is_restrained(catalog: ExpressionCatalog, boundary_text: str) -> bool:
    """Deterministic, catalog-declared restraint detection; never a second model gate."""
    return any(marker in boundary_text for marker in catalog.restraint_markers)


def resolve_direction(
    catalog: ExpressionCatalog,
    selections: Mapping[str, str],
    custom_text: str,
    body_related_opt_in: bool,
    boundary_text: str,
    requested_catalog_version: str | None = None,
) -> CreativeDirection:
    """Keep the user's own choice and, on a soft brand conflict, say how it was translated."""
    if requested_catalog_version and requested_catalog_version != catalog.catalog_version:
        raise _fail("创作方向目录已更新，请刷新后重新选择。")
    unknown_axes = [axis for axis in selections if axis not in AXIS_ORDER]
    if unknown_axes:
        raise _fail("创作方向只使用固定的五个方面。")
    restrained = boundary_is_restrained(catalog, boundary_text)
    resolved: list[DirectionSelection] = []
    notices: list[str] = []
    for axis in AXIS_ORDER:
        stable_id = selections.get(axis)
        if not stable_id:
            continue
        entry = catalog.entry(stable_id)
        if entry is None or entry.axis != axis:
            raise _fail("这个创作方向当前不可选，请刷新后重新选择。")
        if entry.body_related and not body_related_opt_in:
            raise _fail("体型相关的方向需要你先自己打开才能使用。")
        translated = bool(restrained and entry.restrained_variant)
        applied_label = entry.restrained_variant if translated else entry.label
        resolved.append(
            DirectionSelection(
                axis=axis,
                stable_id=entry.stable_id,
                label=entry.label,
                applied_label=applied_label,
                translated=translated,
                preserved_aspect=entry.preserved_aspect if translated else "",
            )
        )
        if translated:
            notices.append(
                f"你选的是{entry.label}；这版保留{entry.preserved_aspect}，"
                f"但按当前账号的表达边界收成了{applied_label}。"
            )
    notice = ("".join(notices) + "你还可以继续改。") if notices else None
    return CreativeDirection(
        catalog_version=catalog.catalog_version,
        selections=tuple(resolved),
        custom_text=custom_text.strip(),
        body_related_opt_in=body_related_opt_in,
        translation_notice=notice,
    )


def direction_summary(direction: CreativeDirection | None) -> str:
    """One collapsed natural line; never a form dump."""
    if direction is None or not direction.selections:
        return ""
    return "、".join(item.applied_label for item in direction.selections)


SNAPSHOT_SCHEMA = "content-context-snapshot-v1"


def snapshot_document(control: ContentControlContext, content_role: str) -> dict[str, object]:
    """Freeze the conditions this task was compiled from.

    Task conditions only: the axis choices that actually shaped this content, the applied result
    and the versions used.  Private preference state — its body, its defaults object and whether
    the person turned body-related options on — stays in the owner-scoped table, because this
    snapshot lives in a tenant-scoped row.
    """
    direction = control.direction
    return {
        "schema": SNAPSHOT_SCHEMA,
        "catalog_version": control.catalog_version,
        "original_direction": {
            "selections": (
                [
                    {"axis": item.axis, "stable_id": item.stable_id, "label": item.label}
                    for item in direction.selections
                ]
                if direction
                else []
            ),
            "custom_text": direction.custom_text if direction else "",
        },
        "applied_direction": (
            [
                {
                    "axis": item.axis,
                    "stable_id": item.stable_id,
                    "applied_label": item.applied_label,
                    "translated": item.translated,
                    "preserved_aspect": item.preserved_aspect,
                }
                for item in direction.selections
            ]
            if direction
            else []
        ),
        "translation_notice": direction.translation_notice if direction else None,
        "content_role": content_role,
        "legacy_content_role": False,
        "account_expression_profile_id": (
            str(control.account_expression.profile_id)
            if control.account_expression and control.account_expression.profile_id
            else None
        ),
        "account_expression_profile_version": (
            control.account_expression.version if control.account_expression else None
        ),
        "private_preference_mode": control.preference_mode,
        "private_preference_version": control.preference_version,
        "material_refs": [
            {"asset_id": str(item.asset_id), "reference_version": item.reference_version}
            for item in control.materials
        ],
    }


def direction_from_snapshot(snapshot: Mapping[str, object]) -> CreativeDirection | None:
    """Rebuild the direction a task froze, without consulting today's catalog or brand."""
    applied = snapshot.get("applied_direction")
    original = snapshot.get("original_direction")
    original_labels: dict[str, str] = {}
    custom_text = ""
    body_opt_in = False
    if isinstance(original, dict):
        custom_text = str(original.get("custom_text", ""))
        body_opt_in = bool(original.get("body_related_opt_in", False))
        raw_selections = original.get("selections")
        if isinstance(raw_selections, list):
            for item in raw_selections:
                if isinstance(item, dict):
                    original_labels[str(item.get("stable_id", ""))] = str(item.get("label", ""))
    selections: list[DirectionSelection] = []
    if isinstance(applied, list):
        for item in applied:
            if not isinstance(item, dict):
                continue
            stable_id = str(item.get("stable_id", ""))
            selections.append(
                DirectionSelection(
                    axis=str(item.get("axis", "")),
                    stable_id=stable_id,
                    label=original_labels.get(stable_id, str(item.get("applied_label", ""))),
                    applied_label=str(item.get("applied_label", "")),
                    translated=bool(item.get("translated", False)),
                    preserved_aspect=str(item.get("preserved_aspect", "")),
                )
            )
    if not selections and not custom_text:
        return None
    notice = snapshot.get("translation_notice")
    version = snapshot.get("catalog_version")
    return CreativeDirection(
        catalog_version=str(version) if isinstance(version, str) else "",
        selections=tuple(selections),
        custom_text=custom_text,
        body_related_opt_in=body_opt_in,
        translation_notice=str(notice) if isinstance(notice, str) else None,
    )
