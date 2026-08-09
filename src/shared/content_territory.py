from __future__ import annotations

from dataclasses import dataclass

from src.shared.types import BrandContext, BrandContextPacketV3, ContentProduct, ProductFact

# Schema 45 deliberately keeps the authority vocabulary closed.  The quality
# segment is typed by semantic_subject_type; its authority remains the existing
# headquarters formal class rather than inventing a migration-requiring enum.
QUALITY_DEMO_AUTHORITY_CLASS = "headquarters_formal"
QUALITY_DEMO_SUBJECT_TYPE = "logical_account_product_mission"


@dataclass(frozen=True)
class MissionEvidenceRequirement:
    role_prefix: str
    content_product: ContentProduct
    authority_class: str
    question: str


_MISSION_EVIDENCE_REQUIREMENTS = (
    MissionEvidenceRequirement(
        role_prefix="H04 ",
        content_product="product_truth",
        authority_class=QUALITY_DEMO_AUTHORITY_CLASS,
        question=(
            "这条品控内容目前缺少可消费的检查环节或品控记录。"
            "请先补充已确认的品控过程依据；系统不会把它自动改写成商品介绍。"
        ),
    ),
)


def missing_mission_evidence_question(
    context: BrandContext,
    content_product: ContentProduct,
    products: tuple[ProductFact, ...],
) -> str | None:
    """Return a pre-provider question for a typed mission/evidence gap."""

    requirement = next(
        (
            item
            for item in _MISSION_EVIDENCE_REQUIREMENTS
            if context.content_role_name.startswith(item.role_prefix)
            and content_product == item.content_product
        ),
        None,
    )
    if requirement is None:
        return None
    packet = context.context_packet
    if isinstance(packet, BrandContextPacketV3) and any(
        segment.semantic_kind == "brand_fact"
        and segment.authority_class == requirement.authority_class
        and segment.semantic_subject_type == QUALITY_DEMO_SUBJECT_TYPE
        and segment.semantic_subject_id is not None
        and any(
            segment.semantic_subject_id.endswith(f"/{product.sku}")
            for product in products
        )
        and (
            not segment.applicability
            or content_product in segment.applicability
        )
        for segment in packet.segments
    ):
        return None
    return requirement.question
