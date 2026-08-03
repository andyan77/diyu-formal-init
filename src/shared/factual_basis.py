from __future__ import annotations

import hashlib
import json
from collections.abc import Collection
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from src.shared.types import ProductFact

FactKind: TypeAlias = Literal["user_actuality", "product", "brand"]
ProductFactValue: TypeAlias = str | int | bool | tuple[str, ...]
ProductClaimCategory: TypeAlias = Literal[
    "identity",
    "category",
    "structure",
    "appearance",
    "measurement",
    "construction",
    "boundary",
]

PRODUCT_FACT_PACKET_VERSION = "product-fact-packet-v1"
PRODUCT_FACT_RENDERER_VERSION = "immutable-product-fact-renderer-v3"
_PROHIBITED_PRODUCT_INFERENCES = (
    "performance",
    "efficacy",
    "use_result",
    "wear_result",
    "design_motive",
    "price",
    "inventory",
    "comparison_conclusion",
    "actual_experience",
)


@dataclass(frozen=True)
class FrozenFactRecord:
    fact_id: str
    exact_text: str
    fact_kind: FactKind


@dataclass(frozen=True)
class ProductFactPacketItem:
    product_id: str
    sku: str
    display_name: str
    entity_kind: str
    fact_id: str
    fact_key: str
    structured_value: ProductFactValue
    canonical_text: str
    source_kind: str
    source_note: str
    fact_version: int
    applicability: str
    allowed_claim_categories: tuple[ProductClaimCategory, ...]
    prohibited_inferences: tuple[str, ...]


@dataclass(frozen=True)
class ProductFactPacket:
    packet_version: str
    packet_digest: str
    facts: tuple[ProductFactPacketItem, ...]

    @property
    def fact_ids(self) -> frozenset[str]:
        return frozenset(item.fact_id for item in self.facts)


@dataclass(frozen=True)
class ImmutableFactBlock:
    fact_block_id: str
    fact_id: str
    canonical_text: str
    renderer_version: str
    visible_order: int


def product_fact_records(
    product: ProductFact,
) -> tuple[FrozenFactRecord, ...]:
    return tuple(
        FrozenFactRecord(item.fact_id, item.canonical_text, "product") for item in _product_packet_items(product)
    )


def brand_fact_records(
    reference_context: tuple[str, ...],
) -> tuple[FrozenFactRecord, ...]:
    return tuple(_record("brand", statement, "brand") for statement in dict.fromkeys(reference_context) if statement)


def registered_product_claims(
    product: ProductFact,
) -> tuple[str, ...]:
    return tuple(item.canonical_text for item in _product_packet_items(product))


def build_product_fact_packet(
    products: tuple[ProductFact, ...],
    *,
    allowed_fact_ids: Collection[str] | None = None,
) -> ProductFactPacket:
    facts = tuple(
        item
        for product in products
        for item in _product_packet_items(product)
        if allowed_fact_ids is None or item.fact_id in allowed_fact_ids
    )
    document = [_packet_item_document(item) for item in facts]
    digest = hashlib.sha256(
        json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return ProductFactPacket(
        packet_version=PRODUCT_FACT_PACKET_VERSION,
        packet_digest=digest,
        facts=facts,
    )


def immutable_product_fact_blocks(
    packet: ProductFactPacket,
) -> tuple[ImmutableFactBlock, ...]:
    return tuple(
        ImmutableFactBlock(
            fact_block_id=_fact_block_id(item.fact_id),
            fact_id=item.fact_id,
            canonical_text=item.canonical_text,
            renderer_version=PRODUCT_FACT_RENDERER_VERSION,
            visible_order=index,
        )
        for index, item in enumerate(packet.facts, start=1)
    )


def select_product_fact_block_ids(
    packet: ProductFactPacket,
    *,
    limit: int,
) -> tuple[str, ...]:
    """Select a small, stable fact set without delegating fact authorship to Writer."""
    if limit < 1:
        raise ValueError("product fact block limit must be positive")
    blocks_by_fact_id = {
        block.fact_id: block for block in immutable_product_fact_blocks(packet)
    }
    identity = tuple(
        item
        for item in packet.facts
        if item.fact_key == "display_name"
    )
    if not identity:
        identity = tuple(
            item
            for item in packet.facts
            if item.fact_key == "sku"
        )
    substantive = tuple(
        item
        for priority in (
            "appearance",
            "construction",
            "category",
            "measurement",
            "boundary",
            "structure",
        )
        for item in packet.facts
        if item.fact_key not in {"sku", "display_name"}
        and priority in item.allowed_claim_categories
    )
    selected = tuple(
        dict.fromkeys(
            item.fact_id
            for item in (*identity, *substantive)
        )
    )[:limit]
    return tuple(blocks_by_fact_id[fact_id].fact_block_id for fact_id in selected)


def product_fact_packet_document(
    packet: ProductFactPacket,
) -> dict[str, object]:
    return {
        "packet_version": packet.packet_version,
        "packet_digest": packet.packet_digest,
        "facts": [_packet_item_document(item) for item in packet.facts],
    }


def immutable_fact_blocks_document(
    blocks: tuple[ImmutableFactBlock, ...],
) -> list[dict[str, object]]:
    return [
        {
            "fact_block_id": block.fact_block_id,
            "fact_id": block.fact_id,
            "canonical_text": block.canonical_text,
            "renderer_version": block.renderer_version,
            "visible_order": block.visible_order,
        }
        for block in blocks
    ]


def product_fact_literal_spans(
    packet: ProductFactPacket,
    text: str,
) -> tuple[str, ...]:
    """Return exact trusted fact atoms copied into writer-owned text.

    These are current-packet values, not a language keyword list. Boolean
    facts have no stable literal form, stay hidden from Writer and remain
    server-owned immutable fact blocks.
    """
    atoms: list[str] = []
    for item in packet.facts:
        atoms.extend((item.sku, item.display_name))
        value = item.structured_value
        if isinstance(value, str):
            atoms.append(value)
        elif isinstance(value, int) and not isinstance(value, bool):
            atoms.append(str(value))
        elif isinstance(value, tuple):
            atoms.extend(value)
    unique = tuple(
        dict.fromkeys(
            atom.strip()
            for atom in atoms
            if atom.strip()
        )
    )
    return tuple(
        atom
        for atom in sorted(
            unique,
            key=lambda value: (-len(value), value),
        )
        if atom in text
    )


def _product_packet_items(
    product: ProductFact,
) -> tuple[ProductFactPacketItem, ...]:
    subject = product.display_name or product.sku
    facts = product.facts
    raw_entity_kind = facts.get("entity_kind")
    entity_kind = (
        raw_entity_kind.strip() if isinstance(raw_entity_kind, str) and raw_entity_kind.strip() else "catalog_product"
    )
    specs: list[
        tuple[
            str,
            ProductFactValue,
            str,
            tuple[ProductClaimCategory, ...],
        ]
    ] = [
        (
            "sku",
            product.sku,
            f"这件商品的型号是 {product.sku}。",
            ("identity",),
        )
    ]
    if product.display_name:
        display_descriptor = _display_descriptor(
            product.sku,
            product.display_name,
        )
        specs.append(
            (
                "display_name",
                product.display_name,
                f"{product.sku} 是一件{display_descriptor}。",
                ("identity",),
            )
        )
    for key, label in (
        ("category", "品类"),
        ("material_or_structure", "材质或结构"),
        ("material", "材质"),
        ("structure", "结构"),
        ("silhouette", "轮廓"),
        ("observable_features", "可观察特征"),
    ):
        value = facts.get(key)
        if isinstance(value, str) and value.strip():
            category: ProductClaimCategory = (
                "category"
                if key == "category"
                else "appearance"
                if key in {"silhouette", "observable_features"}
                else "structure"
            )
            specs.append(
                (
                    key,
                    value.strip(),
                    (f"{subject}的{label}是{value.strip().rstrip('。')}。"),
                    (category,),
                )
            )
    colors = facts.get("colors")
    if isinstance(colors, list) and colors and all(isinstance(value, str) for value in colors):
        color_values = tuple(cast(list[str], colors))
        specs.append(
            (
                "colors",
                color_values,
                f"{subject}已确认的可见颜色信息包括：{'、'.join(color_values)}。",
                ("appearance",),
            )
        )
    for key, label, unit in (
        ("sample_weight_m_grams", "M 码当前样衣重量", "克"),
        (
            "comparison_single_layer_short_coat_m_grams",
            "同季同长度单层短外套 M 码对照样衣重量",
            "克",
        ),
    ):
        value = facts.get(key)
        if isinstance(value, int):
            specs.append(
                (
                    key,
                    value,
                    f"{subject}的{label}是 {value} {unit}。",
                    ("measurement",),
                )
            )
    for key, yes, no in (
        (
            "both_sides_complete",
            "两面都以完整外观呈现",
            "现有资料未确认两面均为完整外观",
        ),
        (
            "pockets_functional_both_sides",
            "两面的口袋都可正常使用",
            "现有资料未确认两面的口袋均可正常使用",
        ),
    ):
        value = facts.get(key)
        if isinstance(value, bool):
            specs.append(
                (
                    key,
                    value,
                    f"{subject}{yes if value else no}。",
                    ("construction",),
                )
            )
    boundary = facts.get("weight_boundary")
    if isinstance(boundary, str) and boundary.strip():
        specs.append(
            (
                "weight_boundary",
                boundary.strip(),
                (
                    f"关于{subject}的重量，目前只能确认两件登记样衣的差异，"
                    "不能据此归因结构或推断性能、价格、库存、用途和穿着结果。"
                ),
                ("boundary",),
            )
        )
    return tuple(
        ProductFactPacketItem(
            product_id=f"product:{product.sku}",
            sku=product.sku,
            display_name=product.display_name,
            entity_kind=entity_kind,
            fact_id=_record("product", canonical_text, "product").fact_id,
            fact_key=fact_key,
            structured_value=structured_value,
            canonical_text=canonical_text,
            source_kind=product.source_kind,
            source_note=product.source_note,
            fact_version=product.fact_version,
            applicability=product.applicability,
            allowed_claim_categories=categories,
            prohibited_inferences=_PROHIBITED_PRODUCT_INFERENCES,
        )
        for fact_key, structured_value, canonical_text, categories in specs
    )


def _display_descriptor(sku: str, display_name: str) -> str:
    suffix = display_name[len(sku) :] if display_name.startswith(sku) else ""
    if suffix and (suffix[0].isspace() or suffix[0] in "-_·/"):
        normalized = suffix.lstrip(" -_·/")
        if normalized:
            return normalized
    return display_name


def _packet_item_document(
    item: ProductFactPacketItem,
) -> dict[str, object]:
    value: object = list(item.structured_value) if isinstance(item.structured_value, tuple) else item.structured_value
    return {
        "product_id": item.product_id,
        "sku": item.sku,
        "display_name": item.display_name,
        "entity_kind": item.entity_kind,
        "fact_id": item.fact_id,
        "fact_key": item.fact_key,
        "structured_value": value,
        "canonical_text": item.canonical_text,
        "source_kind": item.source_kind,
        "source_note": item.source_note,
        "fact_version": item.fact_version,
        "applicability": item.applicability,
        "allowed_claim_categories": list(item.allowed_claim_categories),
        "prohibited_inferences": list(item.prohibited_inferences),
    }


def _fact_block_id(fact_id: str) -> str:
    digest = hashlib.sha256(f"{PRODUCT_FACT_RENDERER_VERSION}:{fact_id}".encode()).hexdigest()[:16]
    return f"fact-block:product:{digest}"


def _record(
    namespace: str,
    exact_text: str,
    fact_kind: FactKind,
) -> FrozenFactRecord:
    digest = hashlib.sha256(exact_text.encode("utf-8")).hexdigest()[:16]
    return FrozenFactRecord(
        fact_id=f"fact:{namespace}:{digest}",
        exact_text=exact_text,
        fact_kind=fact_kind,
    )
