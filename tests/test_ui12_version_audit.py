from __future__ import annotations

from copy import deepcopy

import pytest

from src.infrastructure.postgres_repository import PostgresContentRepository
from src.shared.errors import DomainError


def _task_snapshot() -> dict[str, object]:
    return {
        "creation_commitment": {"gate_version": "creation-intent-gate-v1"},
        "creative_plan_v2": {"plan_version": "creative-plan-v2"},
        "narrative_frame": {
            "frame_version": "narrative-frame-v1",
            "narrative_mode": "actuality_reflection",
            "user_facts": [
                {
                    "source_id": "source:user_actuality:turn-1:clause-1:abc123",
                    "exact_text": "我没有和婆婆吵架。",
                }
            ],
        },
        "delivery_compiler_version": "delivery-compiler-v2",
        "product_fact_packet": {"packet_version": "product-fact-packet-v1", "facts": []},
        "immutable_product_fact_blocks": None,
        "used_product_fact_ids": None,
        "used_product_fact_block_ids": None,
        "product_fact_renderer_version": None,
        "delivery_resource_refs": None,
    }


def _completion_patch() -> dict[str, object]:
    return {
        "creative_kernel_v2": {"kernel_version": "creative-kernel-v2", "units": []},
        "expression_plan_version": "expression-plan-v1",
        "expression_plan_digest": "a" * 64,
        "delivery_compiler_version": "delivery-compiler-v2",
        "writer_model": "deepseek-v4-flash",
        "version_authorization": "deterministic-dual-track-v1",
        "claim_inventory_v1": [],
        "reviewed_kernel_digest": "b" * 64,
        "reviewed_creative_digest": "c" * 64,
        "product_fact_packet": {"packet_version": "product-fact-packet-v1", "facts": []},
        "immutable_product_fact_blocks": [],
        "used_product_fact_ids": [],
        "used_product_fact_block_ids": [],
        "product_fact_renderer_version": None,
        "visible_provenance": {"body": ["unit:body"]},
        "delivery_resource_refs": ["resource:original_composition"],
    }


def test_repository_rejects_arbitrary_snapshot_patch_fields() -> None:
    patch = _completion_patch()
    patch["narrative_frame"] = {"narrative_mode": "dramatization"}

    with pytest.raises(DomainError, match="字段不完整或越界"):
        PostgresContentRepository._validated_completion_snapshot(
            _task_snapshot(),
            patch,
        )


def test_repository_rejects_revision_fact_source_changes() -> None:
    initial = PostgresContentRepository._validated_completion_snapshot(
        _task_snapshot(),
        _completion_patch(),
    )
    revision = deepcopy(_completion_patch())
    revision["product_fact_packet"] = {
        "packet_version": "product-fact-packet-v1",
        "facts": [{"fact_id": "invented"}],
    }

    with pytest.raises(DomainError, match="product_fact_packet"):
        PostgresContentRepository._validated_completion_snapshot(
            initial,
            revision,
        )


def test_each_version_audit_copies_the_frozen_contract_and_artifact_digest() -> None:
    merged = PostgresContentRepository._validated_completion_snapshot(
        _task_snapshot(),
        _completion_patch(),
    )

    audit = PostgresContentRepository._version_audit_snapshot(
        merged,
        "d" * 64,
    )

    assert audit["audit_version"] == "content-version-audit-v1"
    assert audit["artifact_digest"] == "d" * 64
    assert audit["narrative_frame"] == merged["narrative_frame"]
    assert audit["creative_plan_v2"] == merged["creative_plan_v2"]
    assert audit["creative_kernel_v2"] == merged["creative_kernel_v2"]
    assert audit["delivery_compiler_version"] == "delivery-compiler-v2"
