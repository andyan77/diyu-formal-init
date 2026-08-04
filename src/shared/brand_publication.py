from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias
from uuid import UUID

from src.shared.types import (
    BrandContextPacket,
    BrandContextPacketV2,
    BrandContextPacketV3,
    ContentProduct,
)

PublicationRole: TypeAlias = Literal[
    "public_brand_fact",
    "expression_constraint",
    "creative_method",
    "internal_only",
]

PUBLICATION_PROJECTION_CONTRACT = "brand-publication-projection-v1"
BRAND_CONTEXT_PACKET_VERSION = "brand-context-packet-v2"
BRAND_CONTEXT_PACKET_V3_VERSION = "brand-context-packet-v3"


@dataclass(frozen=True)
class PublicationItemDraft:
    source_segment_id: UUID
    publication_role: PublicationRole
    published_text: str
    applicability: tuple[ContentProduct, ...]


def publication_projection_digest(
    items: Sequence[Mapping[str, object]],
) -> str:
    document = {
        "contract_version": PUBLICATION_PROJECTION_CONTRACT,
        "items": [dict(item) for item in items],
    }
    return hashlib.sha256(
        json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def brand_context_packet_digest(
    *,
    projection_id: str,
    projection_version: int,
    projection_digest: str,
    segments: Sequence[Mapping[str, object]],
) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "packet_version": BRAND_CONTEXT_PACKET_VERSION,
                "publication_projection_id": projection_id,
                "publication_projection_version": projection_version,
                "publication_projection_digest": projection_digest,
                "segments": [dict(segment) for segment in segments],
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def brand_context_packet_v3_digest(
    *,
    projection_id: str,
    projection_version: int,
    projection_digest: str,
    available_segment_refs: Sequence[str],
    frozen_segment_refs: Sequence[str],
    consumed_segment_refs: Sequence[str],
    displayed_segment_refs: Sequence[str],
    segments: Sequence[Mapping[str, object]],
) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "packet_version": BRAND_CONTEXT_PACKET_V3_VERSION,
                "publication_projection_id": projection_id,
                "publication_projection_version": projection_version,
                "publication_projection_digest": projection_digest,
                "available_segment_refs": list(available_segment_refs),
                "frozen_segment_refs": list(frozen_segment_refs),
                "consumed_segment_refs": list(consumed_segment_refs),
                "displayed_segment_refs": list(displayed_segment_refs),
                "segments": [dict(segment) for segment in segments],
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def brand_context_packet_document(
    packet: BrandContextPacket,
    *,
    include_text: bool,
) -> dict[str, object]:
    segments: list[dict[str, object]] = []
    for segment in packet.segments:
        document: dict[str, object] = {
            "segment_id": segment.segment_id,
            "source_document_id": segment.source_document_id,
            "source_document_version_id": segment.source_document_version_id,
            "source_id": segment.source_id,
            "source_version": segment.source_version,
            "semantic_kind": segment.semantic_kind,
            "evidence_level": segment.evidence_level,
            "visibility_scope": segment.visibility_scope,
            "digest": segment.digest,
        }
        if segment.source_digest is not None:
            document["source_digest"] = segment.source_digest
        if segment.source_document_digest is not None:
            document["source_document_digest"] = segment.source_document_digest
        if segment.applicability:
            document["applicability"] = list(segment.applicability)
        if include_text:
            document["exact_text"] = segment.exact_text
        segments.append(document)
    result: dict[str, object] = {
        "packet_version": packet.packet_version,
        "packet_digest": packet.packet_digest,
        "segments": segments,
    }
    if isinstance(packet, (BrandContextPacketV2, BrandContextPacketV3)):
        result.update(
            {
                "publication_projection_id": packet.publication_projection_id,
                "publication_projection_version": packet.publication_projection_version,
                "publication_projection_digest": packet.publication_projection_digest,
            }
        )
    if isinstance(packet, BrandContextPacketV3):
        result.update(
            {
                "available_segment_refs": list(packet.available_segment_refs),
                "frozen_segment_refs": list(packet.frozen_segment_refs),
                "consumed_segment_refs": list(packet.consumed_segment_refs),
                "displayed_segment_refs": list(packet.displayed_segment_refs),
            }
        )
    return result


def bind_brand_context_packet_v3_use(
    packet: BrandContextPacketV3,
    *,
    consumed_segment_refs: Sequence[str],
    displayed_segment_refs: Sequence[str],
) -> BrandContextPacketV3:
    """Freeze task use states without changing the confirmed source projection."""

    frozen = set(packet.frozen_segment_refs)
    consumed = tuple(dict.fromkeys(consumed_segment_refs))
    displayed = tuple(dict.fromkeys(displayed_segment_refs))
    if not set(consumed) <= frozen or not set(displayed) <= set(consumed):
        raise ValueError("brand context use exceeds the frozen task packet")
    document = brand_context_packet_document(packet, include_text=True)
    raw_segments = document["segments"]
    if not isinstance(raw_segments, list):
        raise ValueError("brand context packet segments are invalid")
    digest = brand_context_packet_v3_digest(
        projection_id=packet.publication_projection_id,
        projection_version=packet.publication_projection_version,
        projection_digest=packet.publication_projection_digest,
        available_segment_refs=packet.available_segment_refs,
        frozen_segment_refs=packet.frozen_segment_refs,
        consumed_segment_refs=consumed,
        displayed_segment_refs=displayed,
        segments=raw_segments,
    )
    return BrandContextPacketV3(
        packet.packet_version,
        digest,
        packet.publication_projection_id,
        packet.publication_projection_version,
        packet.publication_projection_digest,
        packet.available_segment_refs,
        packet.frozen_segment_refs,
        consumed,
        displayed,
        packet.segments,
    )
