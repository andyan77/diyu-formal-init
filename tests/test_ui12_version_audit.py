from __future__ import annotations

from copy import deepcopy

import pytest

from src.infrastructure.postgres_repository import PostgresContentRepository
from src.shared.errors import DomainError
from src.shared.narrative import visible_digest
from src.shared.version_integrity import (
    AUDIT_VERSION_V1,
    AUDIT_VERSION_V2,
    AUDIT_VERSION_V3,
    FINAL_VISIBLE_PROJECTION_V2,
    FINAL_VISIBLE_PROJECTION_V3,
    validate_version_content,
)


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

    assert audit["audit_version"] == AUDIT_VERSION_V2
    assert audit["artifact_digest"] == "d" * 64
    assert audit["visible_projection"] == FINAL_VISIBLE_PROJECTION_V2
    assert audit["narrative_frame"] == merged["narrative_frame"]
    assert audit["creative_plan_v2"] == merged["creative_plan_v2"]
    assert audit["creative_kernel_v2"] == merged["creative_kernel_v2"]
    assert audit["delivery_compiler_version"] == "delivery-compiler-v2"


def test_media_native_version_audit_binds_the_final_visible_artifact() -> None:
    task = _task_snapshot()
    task["delivery_compiler_version"] = "delivery-compiler-v3"
    patch = _completion_patch()
    patch["delivery_compiler_version"] = "delivery-compiler-v3"
    kernel = patch["creative_kernel_v2"]
    assert isinstance(kernel, dict)
    kernel["kernel_version"] = "creative-kernel-v3"
    merged = PostgresContentRepository._validated_completion_snapshot(
        task,
        patch,
    )

    audit = PostgresContentRepository._version_audit_snapshot(
        merged,
        "e" * 64,
    )

    assert audit["audit_version"] == AUDIT_VERSION_V3
    assert audit["visible_projection"] == FINAL_VISIBLE_PROJECTION_V3
    assert audit["delivery_compiler_version"] == "delivery-compiler-v3"
    body = "标题：作品标题\n\n表达范围：一次说明\n\n完整正文：完整正文"
    digest = visible_digest("作品标题", body)
    validated = validate_version_content(
        {
            "outline": "作品标题",
            "body": body,
            "artifact_digest": digest,
            "version_audit_snapshot": {
                **audit,
                "artifact_digest": digest,
            },
        }
    )
    assert validated.audit_version == AUDIT_VERSION_V3
    assert validated.body == body


def test_legacy_version_without_audit_keeps_legacy_projection() -> None:
    content = validate_version_content(
        {
            "outline": "旧标题",
            "body": "自然导读：旧导读\n\n完整发布正文：旧正文",
            "artifact_digest": None,
            "version_audit_snapshot": {},
        }
    )

    assert content.audit_version is None
    assert content.body == "内容概要：旧导读\n\n完整发布正文：旧正文"


def test_legacy_version_keeps_ascii_colon_heading_like_text_verbatim() -> None:
    body = "开头\n限制: 不要改写这一句\n标题: 旧内容中的普通一句\n结尾"

    content = validate_version_content(
        {
            "outline": "旧标题",
            "body": body,
            "artifact_digest": None,
            "version_audit_snapshot": {},
        }
    )

    assert content.body == body


def test_audit_v1_keeps_legacy_projection_after_digest_validation() -> None:
    outline = "旧审计标题"
    body = "自然导读：旧导读\n\n完整发布正文：旧正文"
    digest = visible_digest(outline, body)

    content = validate_version_content(
        {
            "outline": outline,
            "body": body,
            "artifact_digest": digest,
            "version_audit_snapshot": {
                "audit_version": AUDIT_VERSION_V1,
                "artifact_digest": digest,
            },
        }
    )

    assert content.audit_version == AUDIT_VERSION_V1
    assert content.body == "内容概要：旧导读\n\n完整发布正文：旧正文"


def test_audit_v1_validates_digest_before_preserving_ascii_colon_text() -> None:
    outline = "旧审计标题"
    body = "开头\n完整发布正文: 普通历史文字\n结尾"
    digest = visible_digest(outline, body)

    content = validate_version_content(
        {
            "outline": outline,
            "body": body,
            "artifact_digest": digest,
            "version_audit_snapshot": {
                "audit_version": AUDIT_VERSION_V1,
                "artifact_digest": digest,
            },
        }
    )

    assert content.audit_version == AUDIT_VERSION_V1
    assert content.body == body


def test_audit_v2_returns_exact_compiled_visible_body_without_reparse() -> None:
    outline = "最终标题"
    body = "完整发布正文：第一段\n标题：正文里的保留结构反证"
    digest = visible_digest(outline, body)

    content = validate_version_content(
        {
            "outline": outline,
            "body": body,
            "artifact_digest": digest,
            "version_audit_snapshot": {
                "audit_version": AUDIT_VERSION_V2,
                "artifact_digest": digest,
                "visible_projection": FINAL_VISIBLE_PROJECTION_V2,
            },
        }
    )

    assert content.body == body


@pytest.mark.parametrize(
    ("digest", "snapshot"),
    (
        (
            "0" * 64,
            {
                "audit_version": AUDIT_VERSION_V2,
                "artifact_digest": "0" * 64,
                "visible_projection": FINAL_VISIBLE_PROJECTION_V2,
            },
        ),
        (
            "1" * 64,
            {
                "audit_version": AUDIT_VERSION_V2,
                "artifact_digest": "2" * 64,
                "visible_projection": FINAL_VISIBLE_PROJECTION_V2,
            },
        ),
        (
            "1" * 64,
            {
                "audit_version": AUDIT_VERSION_V2,
                "artifact_digest": "1" * 64,
            },
        ),
    ),
)
def test_new_audited_version_fails_closed_on_integrity_mismatch(
    digest: str,
    snapshot: dict[str, object],
) -> None:
    with pytest.raises(DomainError):
        validate_version_content(
            {
                "outline": "标题",
                "body": "正文",
                "artifact_digest": digest,
                "version_audit_snapshot": snapshot,
            }
        )
