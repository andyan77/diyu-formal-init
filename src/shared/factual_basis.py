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
PRODUCT_FACT_RENDERER_VERSION = "immutable-product-fact-renderer-v1"
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

    These are current-packet values, not a language keyword list.  Boolean
    facts have no stable literal form and remain the Reviewer's responsibility.
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
            f"商品编号是 {product.sku}。",
            ("identity",),
        )
    ]
    if product.display_name:
        specs.append(
            (
                "display_name",
                product.display_name,
                f"商品 {product.sku} 已登记的名称是“{product.display_name}”。",
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
                    (f"{subject}已登记的{label}是{value.strip().rstrip('。')}。"),
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
                f"{subject}已登记的颜色是{'、'.join(color_values)}。",
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
                    f"{subject}已登记的{label}是 {value} {unit}。",
                    ("measurement",),
                )
            )
    for key, yes, no in (
        (
            "both_sides_complete",
            "两面均为完整外观",
            "未登记为两面均为完整外观",
        ),
        (
            "pockets_functional_both_sides",
            "两面口袋均可正常使用",
            "未登记为两面口袋均可正常使用",
        ),
    ):
        value = facts.get(key)
        if isinstance(value, bool):
            specs.append(
                (
                    key,
                    value,
                    f"{subject}已登记为{yes if value else no}。",
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
                    f"{subject}的重量资料边界是：当前只知道登记样衣的重量差异，"
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
