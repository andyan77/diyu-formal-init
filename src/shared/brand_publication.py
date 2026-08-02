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
        if include_text:
            document["exact_text"] = segment.exact_text
        segments.append(document)
    result: dict[str, object] = {
        "packet_version": packet.packet_version,
        "packet_digest": packet.packet_digest,
        "segments": segments,
    }
    if isinstance(packet, BrandContextPacketV2):
        result.update(
            {
                "publication_projection_id": packet.publication_projection_id,
                "publication_projection_version": packet.publication_projection_version,
                "publication_projection_digest": packet.publication_projection_digest,
            }
        )
    return result
