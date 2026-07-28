from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from src.shared.errors import DomainError
from src.shared.types import ProductFact, SeriesContext, SeriesEntry


def visible_direction(snapshot: object) -> tuple[str | None, list[str]]:
    """Project only what a reader of a finished version may see.

    A version keeps the transparent brand translation it was actually produced with, so reopening
    an old version must not make a translated direction look like the user's untouched choice.
    Stable ids, profile ids and preference state stay out of this projection.
    """
    if not isinstance(snapshot, dict):
        return None, []
    notice = snapshot.get("translation_notice")
    applied = snapshot.get("applied_direction")
    labels = (
        [
            str(item["applied_label"])
            for item in applied
            if isinstance(item, dict) and item.get("applied_label")
        ]
        if isinstance(applied, list)
        else []
    )
    return (notice if isinstance(notice, str) and notice else None), labels


def frozen_product_facts(snapshot: Mapping[str, object]) -> tuple[ProductFact, ...] | None:
    """Return the exact product facts frozen with a task.

    ``None`` distinguishes a pre-M7-2B snapshot from a task that deliberately froze no products.
    """
    raw_products = snapshot.get("product_facts")
    if raw_products is None:
        return None
    if not isinstance(raw_products, list):
        raise DomainError("内容任务冻结的商品资料无效")
    products: list[ProductFact] = []
    for raw in raw_products:
        if not isinstance(raw, dict):
            raise DomainError("内容任务冻结的商品资料无效")
        facts = raw.get("facts")
        version = raw.get("fact_version")
        if not isinstance(facts, dict) or not isinstance(version, int):
            raise DomainError("内容任务冻结的商品资料无效")
        products.append(
            ProductFact(
                sku=str(raw.get("sku") or ""),
                display_name=str(raw.get("display_name") or ""),
                facts=dict(facts),
                source_kind=str(raw.get("source_kind") or ""),
                source_note=str(raw.get("source_note") or ""),
                fact_version=version,
                applicability=str(raw.get("applicability") or ""),
            )
        )
    return tuple(products)


def frozen_series_context(snapshot: Mapping[str, object]) -> SeriesContext | None:
    """Reconstruct only the immutable series projection used for the original task."""
    raw_context = snapshot.get("series_context")
    if raw_context is None:
        return None
    if not isinstance(raw_context, dict):
        raise DomainError("内容任务冻结的系列前情无效")
    raw_entries = raw_context.get("prior_entries")
    if not isinstance(raw_entries, list):
        raise DomainError("内容任务冻结的系列前情无效")
    entries: list[SeriesEntry] = []
    try:
        for raw in raw_entries:
            if not isinstance(raw, dict):
                raise ValueError
            entries.append(
                SeriesEntry(
                    task_id=UUID(str(raw["task_id"])),
                    version_id=UUID(str(raw["version_id"])),
                    version=int(str(raw["version"])),
                    position=int(str(raw["position"])),
                    outline=str(raw["outline"]),
                    body=str(raw["body"]),
                )
            )
        return SeriesContext(
            series_id=UUID(str(raw_context["series_id"])),
            revision=int(str(raw_context["revision"])),
            title=str(raw_context["title"]),
            premise=str(raw_context["premise"]),
            target_position=int(str(raw_context["target_position"])),
            prior_entries=tuple(entries),
            user_asserted_published_continuity=bool(
                raw_context.get("user_asserted_published_continuity", False)
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DomainError("内容任务冻结的系列前情无效") from exc
