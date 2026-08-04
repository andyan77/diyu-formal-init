from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from uuid import uuid4

import pytest

from src.shared.brand_publication import (
    brand_context_packet_v3_digest,
    publication_projection_digest,
)
from src.shared.errors import DomainError
from src.shared.tenant_brand_sources import SourceDocumentDraft, SourceSegmentDraft
from src.tool.tenant01_publication_evidence import (
    validate_context_consumption_evidence,
    validate_current_projection,
)


def _document(
    source_id: str,
    semantic_kind: str,
    text: str,
) -> SourceDocumentDraft:
    digest = sha256(text.encode()).hexdigest()
    document_digest = sha256(f"document:{source_id}".encode()).hexdigest()
    segment = SourceSegmentDraft(
        segment_id=uuid4(),
        segment_key=f"{source_id}:V1:line:1:{digest[:16]}",
        heading_path=("正式来源",),
        source_locator="line:1",
        exact_text=text,
        semantic_kind=semantic_kind,  # type: ignore[arg-type]
        evidence_level="brand_user_authorized",
        applicability=source_id,
        digest=digest,
    )
    return SourceDocumentDraft(
        document_id=uuid4(),
        source_id=source_id,
        embedded_title=f"{source_id} 标题",
        provenance_filename=f"{source_id}.md",
        source_version="V1",
        original_status="已确认",
        activation_status="brand_user_authorized",
        authorization_source="bounded test",
        raw_sha256=document_digest,
        normalized_sha256=document_digest,
        source_size=1,
        source_mtime_ns=1,
        normalized_content=text,
        semantic_kind=semantic_kind,  # type: ignore[arg-type]
        segments=(segment,),
        products=(),
    )


def _projection() -> tuple[tuple[SourceDocumentDraft, ...], dict[str, object]]:
    documents = (
        _document("SOURCE-BRAND-001", "brand_fact", "已确认的公开品牌定位。"),
        _document("SOURCE-BOUNDARY-001", "expression_constraint", "只使用已确认事实。"),
        _document("SOURCE-METHOD-001", "creative_method", "每篇只保留一个主导方向。"),
    )
    roles = (
        "public_brand_fact",
        "expression_constraint",
        "creative_method",
    )
    items: list[dict[str, object]] = []
    digest_items: list[dict[str, object]] = []
    for position, (document, role) in enumerate(zip(documents, roles, strict=True), start=1):
        segment = document.segments[0]
        item_id = str(uuid4())
        item = {
            "id": item_id,
            "position": position,
            "publication_role": role,
            "published_text": segment.exact_text,
            "applicability": ["brand_life_narrative"],
            "source_kind": "brand_source_segment",
            "source_segment_id": str(segment.segment_id),
            "source_document_id": str(document.document_id),
            "source_id": document.source_id,
            "source_locator": segment.source_locator,
            "source_label": document.embedded_title,
            "source_version": document.source_version,
            "source_digest": segment.digest,
            "source_document_digest": document.normalized_sha256,
        }
        items.append(item)
        digest_items.append(
            {
                "position": position,
                "publication_role": role,
                "published_text": segment.exact_text,
                "applicability": ["brand_life_narrative"],
                "source_kind": "brand_source_segment",
                "source_ref": str(segment.segment_id),
                "source_version": document.source_version,
                "source_digest": segment.digest,
            }
        )
    current = {
        "id": str(uuid4()),
        "version": 2,
        "status": "confirmed",
        "digest": publication_projection_digest(digest_items),
        "created_by": "管理员",
        "created_at": "2026-08-04T00:00:00+00:00",
        "confirmed_by": "管理员",
        "confirmed_at": "2026-08-04T00:01:00+00:00",
        "is_current": True,
        "items": items,
    }
    baseline = {
        "id": str(uuid4()),
        "version": 1,
        "status": "retired",
        "digest": "a" * 64,
        "created_by": "历史迁移",
        "created_at": "2026-08-03T00:00:00+00:00",
        "confirmed_by": "历史迁移",
        "confirmed_at": "2026-08-03T00:00:00+00:00",
        "is_current": False,
        "items": [
            {
                "position": 1,
                "publication_role": "expression_constraint",
                "published_text": "历史兼容基线",
                "applicability": [],
                "source_kind": "brand_expression_baseline",
                "source_segment_id": None,
                "source_document_id": None,
                "source_id": None,
                "source_locator": None,
                "source_label": "已确认品牌表达基线",
                "source_version": "1",
                "source_digest": "b" * 64,
                "source_document_digest": None,
            }
        ],
    }
    return documents, {
        "contract_version": "brand-publication-projection-v1",
        "current": current,
        "history": [current, baseline],
    }


def test_source_bound_projection_gate_accepts_three_roles_and_preserves_baseline() -> None:
    documents, projection = _projection()

    current, selected = validate_current_projection(documents, projection)

    assert current["version"] == 2
    assert {str(item["publication_role"]) for item in selected} == {
        "public_brand_fact",
        "expression_constraint",
        "creative_method",
    }


@pytest.mark.parametrize(
    "mutation",
    (
        "baseline_only",
        "template_or_acceptance",
        "missing_source_segment",
        "missing_source_version",
        "missing_source_digest",
        "missing_document_digest",
        "internal_only",
        "all_raw_segments",
        "remove_compatibility_history",
        "digest_drift",
    ),
)
def test_publication_projection_gate_mutations_fail_closed(mutation: str) -> None:
    documents, projection = _projection()
    mutated = deepcopy(projection)
    current = mutated["current"]
    assert isinstance(current, dict)
    items = current["items"]
    assert isinstance(items, list)
    if mutation == "baseline_only":
        current["items"] = [
            {
                **items[0],
                "source_kind": "brand_expression_baseline",
                "source_segment_id": None,
            }
        ]
    elif mutation == "template_or_acceptance":
        template = _document("SOURCE-TEMPLATE-001", "template_only", "待填写模板")
        documents = (*documents, template)
        items[0].update(
            {
                "source_segment_id": str(template.segments[0].segment_id),
                "source_document_id": str(template.document_id),
                "source_id": template.source_id,
                "source_version": template.source_version,
                "source_digest": template.segments[0].digest,
                "source_document_digest": template.normalized_sha256,
            }
        )
    elif mutation == "missing_source_segment":
        items[0]["source_segment_id"] = None
    elif mutation == "missing_source_version":
        items[0]["source_version"] = ""
    elif mutation == "missing_source_digest":
        items[0]["source_digest"] = None
    elif mutation == "missing_document_digest":
        items[0]["source_document_digest"] = None
    elif mutation == "internal_only":
        items[0]["publication_role"] = "internal_only"
    elif mutation == "all_raw_segments":
        current["items"] = [deepcopy(items[index % 3]) for index in range(65)]
    elif mutation == "remove_compatibility_history":
        mutated["history"] = [current]
    elif mutation == "digest_drift":
        current["digest"] = "f" * 64
    with pytest.raises(DomainError):
        validate_current_projection(documents, mutated)


def _packet(
    *,
    projection_id: str,
    projection_digest: str,
    content_product: str,
) -> dict[str, object]:
    segments = [
        {
            "segment_id": "projection-item-boundary",
            "source_document_id": str(uuid4()),
            "source_document_version_id": str(uuid4()),
            "source_id": f"brand_source_segment:{uuid4()}",
            "source_version": "V1",
            "semantic_kind": "expression_constraint",
            "evidence_level": "confirmed_publication",
            "visibility_scope": "brand_all",
            "digest": sha256("只使用确认事实".encode()).hexdigest(),
            "exact_text": "只使用确认事实",
            "source_digest": "b" * 64,
            "source_document_digest": "c" * 64,
            "applicability": [content_product],
        },
        {
            "segment_id": "projection-item-method",
            "source_document_id": str(uuid4()),
            "source_document_version_id": str(uuid4()),
            "source_id": f"brand_source_segment:{uuid4()}",
            "source_version": "V1",
            "semantic_kind": "creative_method",
            "evidence_level": "confirmed_publication",
            "visibility_scope": "brand_all",
            "digest": sha256("每篇保留一个主导方向".encode()).hexdigest(),
            "exact_text": "每篇保留一个主导方向",
            "source_digest": "d" * 64,
            "source_document_digest": "e" * 64,
            "applicability": [content_product],
        },
    ]
    available = ["projection-item-boundary", "projection-item-method"]
    packet_digest = brand_context_packet_v3_digest(
        projection_id=projection_id,
        projection_version=2,
        projection_digest=projection_digest,
        available_segment_refs=available,
        frozen_segment_refs=available,
        consumed_segment_refs=available,
        displayed_segment_refs=[],
        segments=segments,
    )
    return {
        "packet_version": "brand-context-packet-v3",
        "packet_digest": packet_digest,
        "publication_projection_id": projection_id,
        "publication_projection_version": 2,
        "publication_projection_digest": projection_digest,
        "available_segment_refs": available,
        "frozen_segment_refs": available,
        "consumed_segment_refs": available,
        "displayed_segment_refs": [],
        "segments": segments,
    }


def _context_evidence() -> dict[str, object]:
    projection_id = str(uuid4())
    projection_digest = "a" * 64

    def success(
        case_id: str,
        input_text: str,
        classification: str,
        content_product: str,
        narrative_mode: str,
        *,
        product: bool = False,
    ) -> dict[str, object]:
        product_ref = "fact:SKU-001:category"
        snapshot: dict[str, object] = {
            "brand_context_packet": _packet(
                projection_id=projection_id,
                projection_digest=projection_digest,
                content_product=content_product,
            ),
            "used_product_fact_ids": [product_ref] if product else [],
        }
        if product:
            snapshot.update(
                {
                    "product_value_contract": {
                        "supporting_fact_refs": [product_ref],
                    },
                    "product_fact_packet": {
                        "facts": [
                            {
                                "fact_id": product_ref,
                                "sku": "SKU-001",
                            }
                        ]
                    },
                }
            )
        return {
            "case_id": case_id,
            "outcome": "succeeded",
            "input": input_text,
            "classification": classification,
            "content_product": content_product,
            "narrative_mode": narrative_mode,
            "task_delta": 1,
            "run_delta": 1,
            "version_delta": 1,
            "permanent_running": 0,
            "writer_calls": 1,
            "product_fact_refs": [product_ref] if product else [],
            "selected_skus": ["SKU-001"] if product else [],
            "snapshot": snapshot,
            "artifact_digest": sha256(f"artifact:{case_id}".encode()).hexdigest(),
        }

    def rejected(case_id: str, classification: str) -> dict[str, object]:
        return {
            "case_id": case_id,
            "outcome": "rejected_before_task",
            "input": "不受支持的明确事实声明",
            "classification": classification,
            "content_product": "none",
            "narrative_mode": "none",
            "task_delta": 0,
            "run_delta": 0,
            "version_delta": 0,
            "permanent_running": 0,
            "writer_calls": 0,
            "product_fact_refs": [],
            "selected_skus": [],
            "snapshot": None,
            "artifact_digest": None,
        }

    v1_packet = "1" * 64
    v1_artifact = "2" * 64
    return {
        "schema_version": "tenant01-formal-context-consumption-v1",
        "candidate_sha": "f" * 40,
        "tenant_id": "tenant-formal",
        "brand_id": "brand-formal",
        "schema_revision": "20260817_44",
        "observed_at": "2026-08-04T00:00:00+00:00",
        "raw_segment_count": 5046,
        "formal_user": {
            "id": str(uuid4()),
            "username": "笛语品控",
            "entry_kind": "tenant_user",
            "business_data_kind": "formal_business_data",
        },
        "current_projection": {
            "id": projection_id,
            "version": 2,
            "digest": projection_digest,
        },
        "cases": [
            success(
                "factory_actuality",
                "今天去工厂验厂，今年量装大货的车缝品质有了大幅度的提升",
                "task_actuality",
                "brand_life_narrative",
                "actuality_reflection",
            ),
            success(
                "explicit_product",
                "请解释 SKU-001 的已确认商品事实",
                "specific_product_claim",
                "product_truth",
                "product_explanation",
                product=True,
            ),
            rejected("institutional_guarantee", "institutional_claim"),
            rejected("unknown_sku", "specific_product_claim"),
            success(
                "ordinary_life",
                "今天有点累，但还是想把事情慢慢做好。",
                "general_topic",
                "brand_life_narrative",
                "general_observation",
            ),
        ],
        "version_replay": {
            "v1_projection_id": projection_id,
            "v2_projection_id": projection_id,
            "v1_packet_digest": v1_packet,
            "v2_packet_digest": v1_packet,
            "v1_artifact_digest": v1_artifact,
            "v1_reread_artifact_digest": v1_artifact,
            "current_version": 2,
            "read_sequence": [1, 2, 1, 2],
            "copy_version": 2,
            "export_version": 2,
        },
        "projection_isolation": {
            "old_projection_id": projection_id,
            "old_projection_version": 2,
            "new_projection_id": str(uuid4()),
            "new_projection_version": 3,
            "new_projection_status": "confirmed",
            "new_projection_digest": "c" * 64,
            "old_task_packet_before": v1_packet,
            "old_task_packet_after": v1_packet,
            "old_task_artifact_before": v1_artifact,
            "old_task_artifact_after": v1_artifact,
        },
        "user_visible_readiness": {
            "ordinary_content": "available",
            "P4": "data_missing",
            "P5": "data_missing",
            "DM01": "data_missing",
            "all_capabilities_ready": False,
        },
        "checks": [
            {"id": value, "status": "PASS"}
            for value in (
                "FORMAL_USER_DIYU_QC",
                "FORMAL_MEMBER_DUPLICATE_DISPLAY_NAME",
                "FORMAL_MEMBER_USERNAME_CONFLICT",
                "FORMAL_MEMBER_ACTIVATION_RESET",
                "FORMAL_MEMBER_GRANT_DISABLE_RESTORE",
                "PERMISSION_403_SESSION_PRESERVED",
                "SEND_ZERO_OBJECTS",
                "FACTORY_ACTUALITY_V1",
                "EXPLICIT_PRODUCT_SCOPED_FACTS",
                "INSTITUTIONAL_GUARANTEE_PRETASK_REJECT",
                "UNKNOWN_SKU_PRETASK_REJECT",
                "ORDINARY_LIFE_NOT_FORCED_PRODUCT",
                "V1_V2_REPLAY_IMMUTABLE",
                "CROSS_PLATFORM_STRUCTURE",
                "PROJECTION_ISOLATION",
                "USER_VISIBLE_DATA_GAPS",
            )
        ],
    }


def test_formal_context_consumption_gate_requires_real_use_and_replay() -> None:
    evidence = _context_evidence()

    cases = validate_context_consumption_evidence(
        evidence,
        expected_candidate_sha="f" * 40,
        expected_tenant_id="tenant-formal",
    )

    assert len(cases) == 5


def test_formal_context_consumption_gate_accepts_isolated_local_login_alias() -> None:
    evidence = _context_evidence()
    formal_user = evidence["formal_user"]
    assert isinstance(formal_user, dict)
    formal_user["username"] = "笛语品控-0123456789"

    cases = validate_context_consumption_evidence(
        evidence,
        expected_candidate_sha="f" * 40,
        expected_tenant_id="tenant-formal",
    )

    assert len(cases) == 5


@pytest.mark.parametrize(
    "mutation",
    (
        "internal_to_writer",
        "all_raw_segments",
        "factory_as_product",
        "product_as_general",
        "new_projection_pollutes_old",
        "new_projection_not_confirmed",
        "new_projection_same_digest",
        "no_consumed_refs",
        "synthetic_user",
        "missing_applicability",
        "product_refs_not_frozen",
    ),
)
def test_formal_context_consumption_mutations_fail_closed(mutation: str) -> None:
    evidence = _context_evidence()
    cases = evidence["cases"]
    assert isinstance(cases, list)
    factory = cases[0]
    product = cases[1]
    assert isinstance(factory, dict) and isinstance(product, dict)
    factory_snapshot = factory["snapshot"]
    assert isinstance(factory_snapshot, dict)
    packet = factory_snapshot["brand_context_packet"]
    assert isinstance(packet, dict)
    segments = packet["segments"]
    assert isinstance(segments, list) and isinstance(segments[0], dict)
    if mutation == "internal_to_writer":
        segments[0]["semantic_kind"] = "internal_only"
    elif mutation == "all_raw_segments":
        packet["available_segment_refs"] = [f"raw-{index}" for index in range(5046)]
    elif mutation == "factory_as_product":
        factory["content_product"] = "product_truth"
    elif mutation == "product_as_general":
        product["classification"] = "general_topic"
    elif mutation == "new_projection_pollutes_old":
        isolation = evidence["projection_isolation"]
        assert isinstance(isolation, dict)
        isolation["old_task_packet_after"] = "9" * 64
    elif mutation == "new_projection_not_confirmed":
        isolation = evidence["projection_isolation"]
        assert isinstance(isolation, dict)
        isolation["new_projection_status"] = "candidate"
    elif mutation == "new_projection_same_digest":
        isolation = evidence["projection_isolation"]
        current = evidence["current_projection"]
        assert isinstance(isolation, dict) and isinstance(current, dict)
        isolation["new_projection_digest"] = current["digest"]
    elif mutation == "no_consumed_refs":
        packet["consumed_segment_refs"] = []
    elif mutation == "synthetic_user":
        formal_user = evidence["formal_user"]
        assert isinstance(formal_user, dict)
        formal_user["business_data_kind"] = "synthetic_acceptance"
    elif mutation == "missing_applicability":
        segments[0]["applicability"] = []
    elif mutation == "product_refs_not_frozen":
        product_snapshot = product["snapshot"]
        assert isinstance(product_snapshot, dict)
        product_snapshot["used_product_fact_ids"] = []
    with pytest.raises(DomainError):
        validate_context_consumption_evidence(
            evidence,
            expected_candidate_sha="f" * 40,
            expected_tenant_id="tenant-formal",
        )
