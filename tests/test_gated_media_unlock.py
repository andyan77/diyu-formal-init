from __future__ import annotations

from uuid import UUID

from src.shared.media_program import (
    build_media_capability_envelope_v2,
    select_media_program,
)
from src.shared.product_value import P5ProductDecisionBasisV2, build_product_decision_basis_v2
from src.shared.types import BoundProductMedia, ProductFact


def _bound(index: int, product: ProductFact) -> BoundProductMedia:
    base = f"00000000-0000-4000-8000-{index:012d}"
    return BoundProductMedia(
        binding_id=UUID(base),
        product_id=UUID(f"10000000-0000-4000-8000-{index:012d}"),
        product_version_id=UUID(f"20000000-0000-4000-8000-{index:012d}"),
        product=product,
        asset_id=UUID(f"30000000-0000-4000-8000-{index:012d}"),
        asset_version_id=UUID(f"40000000-0000-4000-8000-{index:012d}"),
        asset_version=1,
        media_type="video",
        source_ref=f"gate-d-master:{index}",
        source_checksum_sha256=f"{index}" * 64,
        root_account_id=UUID("50000000-0000-4000-8000-000000000001"),
        control_organization_id=UUID("60000000-0000-4000-8000-000000000001"),
    )


def test_gate_a_verified_main_color_supports_formal_p5_relation() -> None:
    products = (
        ProductFact(
            sku="DIYU-CSPU-001",
            display_name="男童明亮黄色短袖上衣",
            facts={
                "entity_kind": "apparel_product",
                "category": "男童短袖上衣",
                "main_color": "明亮黄色",
            },
            source_kind="gatea_verified_visual",
        ),
        ProductFact(
            sku="DIYU-CSPU-008",
            display_name="女童灰色松弛针织开衫",
            facts={
                "entity_kind": "apparel_product",
                "category": "针织开衫",
                "main_color": "灰色",
            },
            source_kind="gatea_verified_visual",
        ),
    )
    media = (_bound(1, products[0]), _bound(2, products[1]))
    envelope = build_media_capability_envelope_v2(
        platform_shape="抖音短视频完整成品",
        media_format="video",
        bound_product_media=media,
    )
    program = select_media_program(
        primary_product="visual_styling_story",
        envelope=envelope,
        mechanism_id=None,
        series_position=None,
        fact_count=4,
    )

    decision = build_product_decision_basis_v2(
        primary_product="visual_styling_story",
        products=products,
        bound_product_media=media,
        media_envelope=envelope,
        media_program=program,
    )

    assert isinstance(decision, P5ProductDecisionBasisV2)
    assert decision.relation_kind == "color_hierarchy"
    assert len(decision.supporting_fact_refs) == 4
