from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from src.shared.types import ProductFact

FactKind: TypeAlias = Literal["user_actuality", "product", "brand"]


@dataclass(frozen=True)
class FrozenFactRecord:
    fact_id: str
    exact_text: str
    fact_kind: FactKind


def product_fact_records(
    product: ProductFact,
) -> tuple[FrozenFactRecord, ...]:
    return tuple(
        _record("product", statement, "product")
        for statement in registered_product_claims(product)
    )


def brand_fact_records(
    reference_context: tuple[str, ...],
) -> tuple[FrozenFactRecord, ...]:
    return tuple(
        _record("brand", statement, "brand")
        for statement in dict.fromkeys(reference_context)
        if statement
    )


def registered_product_claims(
    product: ProductFact,
) -> tuple[str, ...]:
    subject = product.display_name or product.sku
    facts = product.facts
    claims: list[str] = [f"商品编号是 {product.sku}。"]
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
            claims.append(
                f"{subject}已登记的{label}是{value.strip().rstrip('。')}。"
            )
    colors = facts.get("colors")
    if isinstance(colors, list) and colors and all(
        isinstance(value, str) for value in colors
    ):
        claims.append(
            f"{subject}已登记的颜色是{'、'.join(cast(list[str], colors))}。"
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
            claims.append(f"{subject}已登记的{label}是 {value} {unit}。")
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
            claims.append(f"{subject}已登记为{yes if value else no}。")
    boundary = facts.get("weight_boundary")
    if isinstance(boundary, str) and boundary.strip():
        claims.append(
            f"{subject}的重量资料边界是：当前只知道登记样衣的重量差异，"
            "不能据此归因结构或推断性能、价格、库存、用途和穿着结果。"
        )
    return tuple(dict.fromkeys(claims))


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
