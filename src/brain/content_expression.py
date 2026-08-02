from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.brain.creation_intent_gate import CreationCommitment, commitment_document
from src.shared.brand_publication import brand_context_packet_document
from src.shared.creative_plan import CreativePlanV2, creative_plan_document
from src.shared.delivery_compiler import DELIVERY_COMPILER_VERSION
from src.shared.errors import DomainError
from src.shared.factual_basis import (
    build_product_fact_packet,
    product_fact_packet_document,
)
from src.shared.media_program import (
    MediaCapabilityEnvelope,
    MediaProgramSelectionV1,
    media_envelope_digest,
    media_envelope_document,
    media_program_digest,
    media_program_document,
)
from src.shared.narrative import NarrativeFrame, frame_document
from src.shared.product_value import (
    ProductValueContract,
    product_value_contract_digest,
    product_value_contract_document,
)
from src.shared.types import (
    BrandContextPacket,
    ContentControlContext,
    CreativeDirection,
    DirectionSelection,
    ProductFact,
    SeriesContext,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_DIR = _PROJECT_ROOT / "config" / "content_expression"
_CATALOG_FILE = _CATALOG_DIR / "catalog-v1.json"
_INVENTORY_FILE = _CATALOG_DIR / "capability-inventory-v1.jsonl"

AXIS_ORDER: tuple[str, ...] = ("topic", "mechanism", "style", "form", "continuity")
CAPABILITY_STATES = frozenset({"verified", "composable", "experimental", "unsupported", "explicitly_out_of_scope"})
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
# The few spellings that turn a mention into a refusal.  They are checked as exact words, only
# in the short run of characters immediately before a declared label and only inside the same
# sentence; this is not fuzzy style detection and not a keyword blacklist.
REFUSAL_MARKERS: tuple[str, ...] = ("不要", "不想", "别", "不用", "取消")
_REFUSAL_WINDOW = 4
_SENTENCE_BREAKS = "，。！？；：\n,.!?;:"
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
    # A short, declared list of other exact spellings of this same label.  It is not fuzzy style
    # detection and not a keyword blacklist; anything not declared here stays free text.
    aliases: tuple[str, ...] = ()


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
    axes = tuple(CatalogAxis(str(item["key"]), str(item["label"]), str(item["question"])) for item in axes_raw)
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
        raw_aliases = item.get("aliases", [])
        if not isinstance(raw_aliases, list) or any(
            not isinstance(alias, str) or not alias.strip() for alias in raw_aliases
        ):
            raise _fail("内容表达目录存在无效的别名声明")
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
                aliases=tuple(str(alias) for alias in raw_aliases),
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


def assert_custom_direction_available(custom_text: str) -> None:
    """Fail honestly when a custom direction is exactly a declared non-stable catalog label.

    This is a state lookup against the versioned inventory, not fuzzy text classification. Free
    wording remains free wording; only an exact declared label can reach this guard. The caller
    keeps the person's input in place so the system never substitutes a supposedly supported
    direction or creates a half task.
    """
    requested = custom_text.strip()
    if not requested:
        return
    for record in load_inventory():
        labels = {
            str(record.get("source_label", "")).strip(),
            str(record.get("normalized_label", "")).strip(),
        }
        if requested not in labels:
            continue
        state = str(record.get("capability_state", ""))
        if state in COMPACT_STATES:
            return
        label = str(record.get("normalized_label") or record.get("source_label") or requested)
        if state == "experimental":
            raise _fail(
                f"「{label}」目前还是试验方向，暂不能作为稳定选项使用。你的原话会留在输入框中，可以换一种方向再试。"
            )
        if state == "explicitly_out_of_scope":
            raise _fail(f"「{label}」不属于当前内容创作范围。你的原话会留在输入框中，可以换成内容表达方向。")
        raise _fail(
            f"「{label}」目前还缺少可靠资料或直接能力，暂不能稳定完成。你的原话会留在输入框中，可以换一种方向再试。"
        )


def reconcile_sources(
    records: tuple[dict[str, object], ...],
) -> tuple[dict[str, dict[str, int]], tuple[str, ...]]:
    """Mechanically count real source labels per declared family and list missing positions."""
    summary: dict[str, dict[str, int]] = {}
    gaps: list[str] = []
    for family_label, family_code, target in DECLARED_SOURCE_TARGETS:
        defined = [record for record in records if str(record["stable_id"]).startswith(f"CAT-{family_code}-")]
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


def _declared_spellings(entry: CatalogEntry) -> tuple[str, ...]:
    return tuple(dict.fromkeys(word for word in (entry.label, *entry.aliases) if word))


def _mention_positions(text: str, word: str) -> list[int]:
    positions: list[int] = []
    start = text.find(word)
    while start >= 0:
        positions.append(start)
        start = text.find(word, start + 1)
    return positions


def _is_refused_at(text: str, start: int) -> bool:
    """True when one of the declared refusal words sits right in front of this mention."""
    window = text[max(0, start - _REFUSAL_WINDOW) : start]
    for separator in _SENTENCE_BREAKS:
        window = window.rsplit(separator, 1)[-1]
    return any(marker in window for marker in REFUSAL_MARKERS)


@dataclass(frozen=True)
class NaturalTextReading:
    """What this task's own words asked for, and what they asked not to use."""

    wanted: Mapping[str, CatalogEntry]
    refused: frozenset[str]


def read_natural_text(catalog: ExpressionCatalog, text: str) -> NaturalTextReading:
    """Read the person's own words against the declared spellings, and nothing else.

    A mention only counts when the person wrote a spelling this catalog declares.  A mention
    that one of the declared refusal words directly precedes in the same sentence is a refusal,
    never a choice.  Only entries that carry a restrained variant or are body related can be
    *applied* from free text, because applying one has to reuse the same visible restraint a
    clicked option gets; any declared entry can be *refused*, because a refusal only ever removes
    something and can never introduce an option.  The longest declared spelling wins per axis and
    everything else is left exactly as written — there is no fuzzy style detection, keyword
    blacklist, second model or review agent anywhere in this path.
    """
    if not text:
        return NaturalTextReading({}, frozenset())
    wanted: dict[str, tuple[int, CatalogEntry]] = {}
    refused: set[str] = set()
    for entry in catalog.entries:
        chosen = 0
        declined = 0
        length = 0
        # Longest spelling first, and a shorter one nested inside it is the same mention, not a
        # second one — otherwise 「不想要幽默玩梗」 would read as refusing 幽默玩梗 and choosing 玩梗.
        counted: list[tuple[int, int]] = []
        for word in sorted(_declared_spellings(entry), key=len, reverse=True):
            for start in _mention_positions(text, word):
                end = start + len(word)
                if any(start >= left and end <= right for left, right in counted):
                    continue
                counted.append((start, end))
                if _is_refused_at(text, start):
                    declined += 1
                else:
                    chosen += 1
                    length = max(length, len(word))
        if chosen:
            if not (entry.restrained_variant or entry.body_related):
                continue
            current = wanted.get(entry.axis)
            if current is None or length > current[0]:
                wanted[entry.axis] = (length, entry)
        elif declined:
            refused.add(entry.stable_id)
    return NaturalTextReading(
        wanted={axis: entry for axis, (_, entry) in wanted.items()},
        refused=frozenset(refused),
    )


def resolve_direction(
    catalog: ExpressionCatalog,
    selections: Mapping[str, str],
    custom_text: str,
    body_related_opt_in: bool,
    boundary_text: str,
    requested_catalog_version: str | None = None,
    saved_defaults: Mapping[str, str] | None = None,
    cleared_axes: tuple[str, ...] = (),
    natural_text: str = "",
) -> CreativeDirection:
    """Keep the user's own choice and, on a soft brand conflict, say how it was translated.

    Per axis the order is: what the person clicked for this task, then what this task's own words
    asked for, then a saved default.  A default is a standing convenience, so it never overrides
    what the person just said — including a refusal of that very default, which suppresses it for
    this task without editing the saved default itself.  A cleared axis never falls back to a
    saved default, and saying nothing never reads as switching a default off.
    """
    if requested_catalog_version and requested_catalog_version != catalog.catalog_version:
        raise _fail("创作方向目录已更新，请刷新后重新选择。")
    defaults = dict(saved_defaults or {})
    unknown_axes = [axis for axis in (*selections, *defaults, *cleared_axes) if axis not in AXIS_ORDER]
    if unknown_axes:
        raise _fail("创作方向只使用固定的五个方面。")
    restrained = boundary_is_restrained(catalog, boundary_text)
    spoken = read_natural_text(catalog, natural_text)
    resolved: list[DirectionSelection] = []
    notices: list[str] = []
    suggestions: list[str] = []
    for axis in AXIS_ORDER:
        if axis in cleared_axes:
            continue
        origin = "explicit"
        stable_id = selections.get(axis)
        if not stable_id:
            asked = spoken.wanted.get(axis)
            if asked is not None and asked.body_related and not body_related_opt_in:
                # A hard conflict: never silently apply it, never silently replace the wording.
                suggestions.append(
                    f"你提到的「{asked.label}」属于体型相关表达，需要你自己先打开才会使用；这次按你原话保留，没有替换。"
                )
                asked = None
            if asked is not None:
                stable_id = asked.stable_id
                origin = "natural_text"
        if not stable_id:
            saved = defaults.get(axis)
            if saved and saved not in spoken.refused:
                stable_id = saved
                origin = "default"
        if not stable_id:
            continue
        entry = catalog.entry(stable_id)
        if entry is None or entry.axis != axis:
            if origin == "default":
                # A saved default that no longer exists is dropped, never guessed or substituted.
                continue
            raise _fail("这个创作方向当前不可选，请刷新后重新选择。")
        if entry.body_related and not body_related_opt_in:
            if origin == "default":
                continue
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
                origin=origin,
            )
        )
        if translated:
            source = "你说的是" if origin == "natural_text" else "你选的是"
            notices.append(
                f"{source}{entry.label}；这版保留{entry.preserved_aspect}，"
                f"但按当前账号的表达边界收成了{applied_label}。"
            )
    body = "".join(notices)
    if body:
        body += "你还可以继续改。"
    body += "".join(suggestions)
    return CreativeDirection(
        catalog_version=catalog.catalog_version,
        selections=tuple(resolved),
        custom_text=custom_text.strip(),
        body_related_opt_in=body_related_opt_in,
        translation_notice=body or None,
        cleared_axes=tuple(axis for axis in AXIS_ORDER if axis in cleared_axes),
    )


def direction_summary(direction: CreativeDirection | None) -> str:
    """One collapsed natural line; never a form dump."""
    if direction is None or not direction.selections:
        return ""
    return "、".join(item.applied_label for item in direction.selections)


SNAPSHOT_SCHEMA = "content-context-snapshot-v1"


def snapshot_document(
    control: ContentControlContext,
    content_role: str,
    products: tuple[ProductFact, ...] = (),
    series_context: SeriesContext | None = None,
    business_data_kind: str = "formal_business_data",
    brand_reference_context: tuple[str, ...] = (),
    narrative_frame: NarrativeFrame | None = None,
    user_premise: str = "",
    creative_plan: CreativePlanV2 | None = None,
    creation_commitment: CreationCommitment | None = None,
    delivery_compiler_version: str | None = DELIVERY_COMPILER_VERSION,
    media_capability_envelope: MediaCapabilityEnvelope | None = None,
    media_program: MediaProgramSelectionV1 | None = None,
    product_value_contract: ProductValueContract | None = None,
    brand_context_packet: BrandContextPacket | None = None,
) -> dict[str, object]:
    """Freeze the conditions this task was compiled from.

    Task conditions only: the expression identity and boundary this run actually spoke from, the
    axis choices that shaped the content, the applied result and the versions used.  The effective
    body-related opt-in is frozen because it controls which catalog entry was legal for this task.
    Private preference body, collaboration note and defaults object stay in the owner-scoped table,
    because this snapshot lives in a tenant-scoped row.
    """
    direction = control.direction
    product_fact_packet = build_product_fact_packet(
        products,
        allowed_fact_ids=(narrative_frame.allowed_product_fact_ids if narrative_frame is not None else None),
    )
    return {
        "schema": SNAPSHOT_SCHEMA,
        "catalog_version": control.catalog_version,
        "original_direction": {
            "selections": (
                [
                    {
                        "axis": item.axis,
                        "stable_id": item.stable_id,
                        "label": item.label,
                        "origin": item.origin,
                    }
                    for item in direction.selections
                ]
                if direction
                else []
            ),
            "custom_text": direction.custom_text if direction else "",
            "cleared_axes": list(direction.cleared_axes) if direction else [],
            "body_related_opt_in": (direction.body_related_opt_in if direction else False),
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
        "content_role_boundary": control.content_role_boundary,
        "speaker_kind": control.speaker_kind,
        "legacy_content_role": False,
        "account_expression_profile_id": (
            str(control.account_expression.profile_id)
            if control.account_expression and control.account_expression.profile_id
            else None
        ),
        "account_expression_profile_version": (
            control.account_expression.version if control.account_expression else None
        ),
        "business_data_kind": business_data_kind,
        "brand_reference_context": list(brand_reference_context),
        "brand_context_packet": (
            brand_context_packet_document(
                brand_context_packet,
                include_text=True,
            )
            if brand_context_packet is not None
            else None
        ),
        "user_premise": user_premise,
        "creative_plan_v2": (creative_plan_document(creative_plan) if creative_plan is not None else None),
        "creation_commitment": (commitment_document(creation_commitment) if creation_commitment is not None else None),
        "narrative_frame": (frame_document(narrative_frame) if narrative_frame is not None else None),
        "creative_kernel_v1": None,
        "delivery_compiler_version": delivery_compiler_version,
        "media_capability_envelope": (
            media_envelope_document(media_capability_envelope) if media_capability_envelope is not None else None
        ),
        "media_capability_envelope_digest": (
            media_envelope_digest(media_capability_envelope) if media_capability_envelope is not None else None
        ),
        "media_program": (media_program_document(media_program) if media_program is not None else None),
        "media_program_digest": (media_program_digest(media_program) if media_program is not None else None),
        "product_value_contract": (
            product_value_contract_document(product_value_contract)
            if product_value_contract is not None
            else None
        ),
        "product_value_contract_digest": (
            product_value_contract_digest(product_value_contract)
            if product_value_contract is not None
            else None
        ),
        "reviewed_kernel_digest": None,
        "visible_provenance": None,
        "account_expression": (
            {
                "profile_id": (
                    str(control.account_expression.profile_id) if control.account_expression.profile_id else None
                ),
                "version": control.account_expression.version,
                "identity_position": control.account_expression.identity_position,
                "authority_boundary": control.account_expression.authority_boundary,
                "audience_relationship": control.account_expression.audience_relationship,
                "content_territories": control.account_expression.content_territories,
                "default_production_conditions": (control.account_expression.default_production_conditions),
            }
            if control.account_expression is not None
            else None
        ),
        "private_preference_mode": control.preference_mode,
        "private_preference_version": control.preference_version,
        "material_refs": [
            {"asset_id": str(item.asset_id), "reference_version": item.reference_version} for item in control.materials
        ],
        "material_snapshots": [
            {
                "asset_id": str(item.asset_id),
                "title": item.title,
                "media_type": item.media_type,
                "reference_version": item.reference_version,
                "text_body": item.text_body,
                "reference_note": item.reference_note,
            }
            for item in control.materials
        ],
        "product_facts": [
            {
                "sku": item.sku,
                "display_name": item.display_name,
                "facts": item.facts,
                "source_kind": item.source_kind,
                "source_note": item.source_note,
                "fact_version": item.fact_version,
                "applicability": item.applicability,
                "product_id": str(item.product_id) if item.product_id else None,
                "product_version_id": (
                    str(item.product_version_id) if item.product_version_id else None
                ),
            }
            for item in products
        ],
        "product_fact_packet": product_fact_packet_document(product_fact_packet),
        "immutable_product_fact_blocks": None,
        "used_product_fact_ids": None,
        "used_product_fact_block_ids": None,
        "product_fact_renderer_version": None,
        "reviewed_creative_digest": None,
        "series_context": (
            {
                "series_id": str(series_context.series_id),
                "revision": series_context.revision,
                "title": series_context.title,
                "premise": series_context.premise,
                "target_position": series_context.target_position,
                "user_asserted_published_continuity": (series_context.user_asserted_published_continuity),
                "prior_entries": [
                    {
                        "task_id": str(item.task_id),
                        "version_id": str(item.version_id),
                        "version": item.version,
                        "position": item.position,
                        "outline": item.outline,
                        "body": item.body,
                    }
                    for item in series_context.prior_entries
                ],
            }
            if series_context is not None
            else None
        ),
    }


def direction_from_snapshot(snapshot: Mapping[str, object]) -> CreativeDirection | None:
    """Rebuild the direction a task froze, without consulting today's catalog or brand."""
    applied = snapshot.get("applied_direction")
    original = snapshot.get("original_direction")
    original_labels: dict[str, str] = {}
    original_origins: dict[str, str] = {}
    custom_text = ""
    body_opt_in = False
    cleared: tuple[str, ...] = ()
    if isinstance(original, dict):
        custom_text = str(original.get("custom_text", ""))
        body_opt_in = bool(original.get("body_related_opt_in", False))
        raw_cleared = original.get("cleared_axes")
        if isinstance(raw_cleared, list):
            cleared = tuple(str(axis) for axis in raw_cleared if isinstance(axis, str))
        raw_selections = original.get("selections")
        if isinstance(raw_selections, list):
            for item in raw_selections:
                if isinstance(item, dict):
                    key = str(item.get("stable_id", ""))
                    original_labels[key] = str(item.get("label", ""))
                    original_origins[key] = str(item.get("origin", "explicit"))
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
                    origin=original_origins.get(stable_id, "explicit"),
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
        cleared_axes=cleared,
    )
