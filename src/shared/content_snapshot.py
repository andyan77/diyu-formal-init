from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from src.shared.creative_kernel import (
    CreativeKernelV1,
    kernel_from_document,
)
from src.shared.creative_plan import (
    CreativePlanV2,
    creative_plan_from_document,
)
from src.shared.errors import DomainError
from src.shared.media_program import (
    MediaCapabilityEnvelope,
    MediaProgramSelectionV1,
    assert_media_program_allowed,
    media_envelope_digest,
    media_envelope_from_document,
    media_program_digest,
    media_program_from_document,
)
from src.shared.narrative import NarrativeFrame, frame_from_document
from src.shared.product_value import (
    ProductValueContract,
    product_value_contract_digest,
    product_value_contract_from_document,
)
from src.shared.server_bearing_expression import (
    ServerBearingExpressionContractV1,
    server_bearing_expression_digest,
    server_bearing_expression_from_document,
)
from src.shared.types import ProductFact, SeriesContext, SeriesEntry

_CONTEXT_CATEGORY_LABELS = {
    "brand_fact": "品牌已确认资料",
    "expression_constraint": "品牌表达边界",
    "creative_method": "品牌创作方法",
    "candidate_product_guidance": "候选商品参考",
    "source_catalog_only": "来源目录",
}


def visible_context_basis(
    snapshot: Mapping[str, object] | None,
    *,
    account_name: str,
    channel: str,
    media_format: str,
) -> dict[str, object]:
    """Project frozen task inputs in product language without internal IDs."""

    snapshot = snapshot or {}
    packet = snapshot.get("brand_context_packet")
    raw_segments = packet.get("segments") if isinstance(packet, dict) else None
    categories: list[str] = []
    if isinstance(raw_segments, list):
        for segment in raw_segments:
            if not isinstance(segment, dict):
                continue
            label = _CONTEXT_CATEGORY_LABELS.get(str(segment.get("semantic_kind")))
            if label and label not in categories:
                categories.append(label)
    raw_products = snapshot.get("product_facts")
    has_products = isinstance(raw_products, list) and bool(raw_products)
    raw_materials = snapshot.get("material_snapshots")
    material_count = len(raw_materials) if isinstance(raw_materials, list) else 0
    format_label = "图文" if media_format == "graphic" else "视频"
    return {
        "account": account_name,
        "platform_and_format": f"{channel} · {format_label}",
        "brand_material_categories": categories,
        "has_product_facts": has_products,
        "selected_material_count": material_count,
        "gaps": [
            label
            for missing, label in (
                (not has_products, "本次没有使用具体商品资料"),
                (material_count == 0, "本次没有选择制作素材"),
            )
            if missing
        ],
    }


def frozen_narrative_frame(
    snapshot: Mapping[str, object],
) -> NarrativeFrame | None:
    value = snapshot.get("narrative_frame")
    return None if value is None else frame_from_document(value)


def frozen_user_premise(snapshot: Mapping[str, object], fallback: str) -> str:
    value = snapshot.get("user_premise")
    return value if isinstance(value, str) and value else fallback


def frozen_creative_plan(
    snapshot: Mapping[str, object],
) -> CreativePlanV2 | None:
    value = snapshot.get("creative_plan_v2")
    return None if value is None else creative_plan_from_document(value)


def frozen_creative_kernel(
    snapshot: Mapping[str, object],
) -> CreativeKernelV1 | None:
    value = snapshot.get(
        "creative_kernel_v2",
        snapshot.get("creative_kernel_v1"),
    )
    return None if value is None else kernel_from_document(value)


def frozen_delivery_compiler_version(
    snapshot: Mapping[str, object],
) -> str | None:
    value = snapshot.get("delivery_compiler_version")
    return value if isinstance(value, str) and value else None


def frozen_media_contract(
    snapshot: Mapping[str, object],
) -> tuple[
    MediaCapabilityEnvelope | None,
    MediaProgramSelectionV1 | None,
]:
    raw_envelope = snapshot.get("media_capability_envelope")
    raw_program = snapshot.get("media_program")
    if raw_envelope is None and raw_program is None:
        return None, None
    if raw_envelope is None or raw_program is None:
        raise DomainError("内容任务冻结的媒体合同不完整")
    envelope = media_envelope_from_document(raw_envelope)
    program = media_program_from_document(raw_program)
    assert_media_program_allowed(envelope, program)
    if snapshot.get("media_capability_envelope_digest") != media_envelope_digest(envelope):
        raise DomainError("内容任务冻结的媒体能力包摘要不一致")
    if snapshot.get("media_program_digest") != media_program_digest(program):
        raise DomainError("内容任务冻结的媒体程序摘要不一致")
    return envelope, program


def frozen_product_value_contract(
    snapshot: Mapping[str, object],
) -> ProductValueContract | None:
    value = snapshot.get("product_value_contract")
    digest = snapshot.get("product_value_contract_digest")
    if value is None and digest is None:
        return None
    if value is None or not isinstance(digest, str):
        raise DomainError("内容任务冻结的商品价值合同不完整")
    contract = product_value_contract_from_document(value)
    if product_value_contract_digest(contract) != digest:
        raise DomainError("内容任务冻结的商品价值合同摘要不一致")
    return contract


def frozen_server_bearing_expression_contract(
    snapshot: Mapping[str, object],
) -> ServerBearingExpressionContractV1 | None:
    value = snapshot.get("server_bearing_expression_contract")
    digest = snapshot.get("server_bearing_expression_digest")
    if value is None and digest is None:
        return None
    if value is None or not isinstance(digest, str):
        raise DomainError("内容任务冻结的服务端承重表达合同不完整")
    contract = server_bearing_expression_from_document(value)
    if server_bearing_expression_digest(contract) != digest:
        raise DomainError("内容任务冻结的服务端承重表达合同摘要不一致")
    return contract


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
        [str(item["applied_label"]) for item in applied if isinstance(item, dict) and item.get("applied_label")]
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
                product_id=(
                    UUID(str(raw["product_id"]))
                    if raw.get("product_id")
                    else None
                ),
                product_version_id=(
                    UUID(str(raw["product_version_id"]))
                    if raw.get("product_version_id")
                    else None
                ),
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
            user_asserted_published_continuity=bool(raw_context.get("user_asserted_published_continuity", False)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DomainError("内容任务冻结的系列前情无效") from exc
