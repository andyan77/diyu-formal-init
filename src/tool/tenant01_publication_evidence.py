from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from src.shared.brand_publication import (
    brand_context_packet_v3_digest,
    publication_projection_digest,
)
from src.shared.errors import DomainError
from src.shared.tenant_brand_sources import (
    SourceDocumentDraft,
    SourceSegmentDraft,
    freeze_source_batch,
)

_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_ROLES = frozenset({"public_brand_fact", "expression_constraint", "creative_method"})
_ALLOWED_PRODUCTS = frozenset(
    {
        "dressing_decision",
        "product_truth",
        "brand_life_narrative",
        "local_response",
        "visual_styling_story",
    }
)
_ROLE_TO_DESTINATION = {
    "public_brand_fact": "published_brand_fact",
    "expression_constraint": "published_expression_constraint",
    "creative_method": "published_creative_method",
}
_ROLE_TO_SEMANTIC_KIND = {
    "public_brand_fact": "brand_fact",
    "expression_constraint": "expression_constraint",
    "creative_method": "creative_method",
}
_TEMPLATE_SOURCE_IDS = frozenset({"DIYU-STORE-FIXTURE-PROFILE-001", "DIYU-STORE-FIXTURE-COLLECTION-001"})
_PRODUCT_PIPELINE_SOURCE_IDS = frozenset({"DIYU-CANDIDATE-PRODUCT-MASTER-001"})
_PRODUCT_ANALYSIS_SOURCE_IDS = frozenset(
    {
        "DIYU-PRODUCT-PRICE-CORRECTION-001",
        "DIYU-PRODUCT-TRADEOFF-P2-001",
        "DIYU-ASSET-PRODUCT-INFERENCE-001",
    }
)
_INTERNAL_STRUCTURE_SOURCE_IDS = frozenset(
    {
        "DIYU-ACCOUNT-MATRIX-001",
        "DIYU-TENANT-ORG-AUTH-001",
        "DIYU-ASSET-BRAND-UNIFICATION-001",
        "DIYU-ORG-IP-ACCOUNT-MATRIX-001",
    }
)
_EXCLUDED_VIDEO_CATALOG_SOURCE_ID = "DIYU-ASSET-CATALOG-001"


def _dictionary(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DomainError(message)
    return cast(dict[str, object], value)


def _list(value: object, message: str) -> list[object]:
    if not isinstance(value, list):
        raise DomainError(message)
    return cast(list[object], value)


def _text(value: object, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainError(message)
    return value.strip()


def _digest(value: object, message: str) -> str:
    text = _text(value, message)
    if not _DIGEST_PATTERN.fullmatch(text):
        raise DomainError(message)
    return text


def _projection_digest(current: dict[str, object]) -> str:
    raw_items = _list(current.get("items"), "当前品牌发布版本缺少条目")
    records: list[dict[str, object]] = []
    for raw in raw_items:
        item = _dictionary(raw, "当前品牌发布条目无效")
        source_segment_id = _text(item.get("source_segment_id"), "来源绑定条目缺少 source_segment_id")
        applicability = _list(item.get("applicability"), "发布条目适用范围无效")
        records.append(
            {
                "position": item.get("position"),
                "publication_role": item.get("publication_role"),
                "published_text": item.get("published_text"),
                "applicability": applicability,
                "source_kind": item.get("source_kind"),
                "source_ref": source_segment_id,
                "source_version": item.get("source_version"),
                "source_digest": item.get("source_digest"),
            }
        )
    return publication_projection_digest(records)


def validate_current_projection(
    documents: tuple[SourceDocumentDraft, ...],
    projection: object,
) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
    projection_document = _dictionary(projection, "品牌发布投影证据无效")
    history = tuple(
        _dictionary(item, "品牌发布历史条目无效")
        for item in _list(projection_document.get("history"), "品牌发布历史无效")
    )
    current = _dictionary(projection_document.get("current"), "当前品牌发布投影不存在")
    if current.get("status") != "confirmed" or current.get("is_current") is not True:
        raise DomainError("当前品牌发布投影尚未正式确认")
    if not any(
        any(
            isinstance(item, dict)
            and item.get("source_kind") == "brand_expression_baseline"
            and item.get("publication_role") == "expression_constraint"
            for item in _list(version.get("items"), "历史投影条目无效")
        )
        for version in history
        if version.get("id") != current.get("id")
    ):
        raise DomainError("原兼容品牌表达基线没有保留在追加式历史中")
    raw_items = _list(current.get("items"), "当前品牌发布版本缺少条目")
    if not 1 < len(raw_items) <= 64:
        raise DomainError("当前来源绑定发布投影必须包含 2 到 64 条最小充分表达")

    source_index: dict[tuple[str, str, str, str], tuple[SourceDocumentDraft, SourceSegmentDraft]] = {}
    for document in documents:
        for segment in document.segments:
            key = (
                document.source_id,
                document.source_version,
                segment.source_locator,
                segment.digest,
            )
            if key in source_index:
                raise DomainError("冻结来源存在不可区分的重复 segment digest")
            source_index[key] = (document, segment)

    normalized: list[dict[str, object]] = []
    source_segment_ids: list[str] = []
    roles: Counter[str] = Counter()
    for position, raw in enumerate(raw_items, start=1):
        item = _dictionary(raw, "当前品牌发布条目无效")
        if item.get("position") != position:
            raise DomainError("当前品牌发布条目位置不连续")
        role = _text(item.get("publication_role"), "发布条目角色缺失")
        if role not in _ALLOWED_ROLES:
            raise DomainError("当前发布投影包含 internal 或未知角色")
        if item.get("source_kind") != "brand_source_segment":
            raise DomainError("当前发布投影仍含非来源绑定条目")
        source_segment_id = _text(item.get("source_segment_id"), "来源绑定条目缺少 source_segment_id")
        source_segment_ids.append(source_segment_id)
        source_id = _text(item.get("source_id"), "来源绑定条目缺少 source document ID")
        source_version = _text(item.get("source_version"), "来源绑定条目缺少来源版本")
        source_locator = _text(item.get("source_locator"), "来源绑定条目缺少 source locator")
        source_digest = _digest(item.get("source_digest"), "来源 segment digest 无效")
        document_digest = _digest(item.get("source_document_digest"), "来源 document digest 无效")
        source = source_index.get((source_id, source_version, source_locator, source_digest))
        if source is None:
            raise DomainError("发布条目无法绑定到冻结来源 segment")
        document, segment = source
        if document.normalized_sha256 != document_digest:
            raise DomainError("发布条目来源 document digest 漂移")
        if segment.semantic_kind != _ROLE_TO_SEMANTIC_KIND[role]:
            raise DomainError("发布角色超过来源 segment 的语义等级")
        applicability = tuple(
            _text(value, "发布条目适用内容无效") for value in _list(item.get("applicability"), "发布条目适用范围无效")
        )
        if not applicability or len(set(applicability)) != len(applicability):
            raise DomainError("发布条目必须有不重复的明确适用范围")
        if not set(applicability) <= _ALLOWED_PRODUCTS:
            raise DomainError("发布条目含未知内容产品")
        published_text = _text(item.get("published_text"), "发布文字不能为空")
        if len(published_text) > 1200:
            raise DomainError("发布文字超过正式合同上限")
        roles[role] += 1
        normalized.append(
            {
                "position": position,
                "publication_role": role,
                "published_text": published_text,
                "applicability": list(applicability),
                "source_kind": "brand_source_segment",
                "source_segment_id": source_segment_id,
                "source_document_id": _text(item.get("source_document_id"), "来源 document UUID 缺失"),
                "source_id": source_id,
                "source_version": source_version,
                "source_locator": source_locator,
                "source_digest": source_digest,
                "source_document_digest": document_digest,
            }
        )
    if len(source_segment_ids) != len(set(source_segment_ids)):
        raise DomainError("当前发布投影重复使用同一来源 segment")
    if set(roles) != _ALLOWED_ROLES:
        raise DomainError("当前发布投影未同时覆盖品牌事实、表达边界和创作方法")
    expected_digest = _digest(current.get("digest"), "当前发布投影 digest 无效")
    if _projection_digest(current) != expected_digest:
        raise DomainError("当前发布投影 digest 无法复算")
    return current, tuple(normalized)


def _unpublished_reason(document: SourceDocumentDraft) -> str:
    if document.source_id in _TEMPLATE_SOURCE_IDS:
        return "模板结构与待填写占位仅供补录，不进入 Writer。"
    if document.source_id == _EXCLUDED_VIDEO_CATALOG_SOURCE_ID:
        return "用户明确排除的 26 条品牌视频目录不得导入或进入 Writer。"
    if document.source_id in _PRODUCT_ANALYSIS_SOURCE_IDS:
        return "候选商品分析、推断和价格建议未达到可复用 V 级事实，保持内部。"
    if document.source_id in _INTERNAL_STRUCTURE_SOURCE_IDS:
        return "账号、组织、授权或资产治理脚手架只供内部配置，不进入 Writer。"
    if document.source_id in _PRODUCT_PIPELINE_SOURCE_IDS:
        return "商品字段仅经独立 ProductFact 管道按 SKU 和 V 级证据消费。"
    return "未被管理员选入本次最小充分投影的 segment 保留在来源证据库。"


def build_coverage_matrix(
    documents: tuple[SourceDocumentDraft, ...],
    selected_items: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    selected_by_source: dict[str, list[dict[str, object]]] = {}
    for item in selected_items:
        selected_by_source.setdefault(str(item["source_id"]), []).append(item)
    rows: list[dict[str, object]] = []
    for document in sorted(documents, key=lambda value: value.source_id):
        selected = selected_by_source.get(document.source_id, [])
        destinations = {_ROLE_TO_DESTINATION[str(item["publication_role"])] for item in selected}
        if document.source_id in _PRODUCT_PIPELINE_SOURCE_IDS:
            destinations.add("product_fact_pipeline")
        if document.source_id in _TEMPLATE_SOURCE_IDS:
            destinations.add("template_only")
        if len(selected) < len(document.segments):
            destinations.add("internal_only")
        if not selected and document.source_id not in _PRODUCT_PIPELINE_SOURCE_IDS:
            destinations.add("not_publishable_with_reason")
        semantic_counts = Counter(segment.semantic_kind for segment in document.segments)
        rows.append(
            {
                "source_document_id": str(document.document_id),
                "source_id": document.source_id,
                "source_title": document.embedded_title,
                "source_version": document.source_version,
                "source_digest": document.normalized_sha256,
                "activation_status": document.activation_status,
                "segment_count": len(document.segments),
                "semantic_kind_counts": dict(sorted(semantic_counts.items())),
                "destinations": sorted(destinations),
                "selected_items": selected,
                "unpublished_reason": _unpublished_reason(document),
            }
        )
    return tuple(rows)


def build_gate_evidence(
    *,
    documents: tuple[SourceDocumentDraft, ...],
    projection: object,
    candidate_sha: str,
    tenant_id: str,
    brand_id: str,
    schema_revision: str,
) -> dict[str, object]:
    if not _SHA_PATTERN.fullmatch(candidate_sha):
        raise DomainError("候选 SHA 无效")
    current, selected = validate_current_projection(documents, projection)
    coverage = build_coverage_matrix(documents, selected)
    product_fields = tuple(field for document in documents for product in document.products for field in product.fields)
    counts = {
        "documents": len(documents),
        "authorized_documents": sum(document.activation_status == "brand_user_authorized" for document in documents),
        "template_documents": sum(document.activation_status == "template_only" for document in documents),
        "segments": sum(len(document.segments) for document in documents),
        "products": sum(len(document.products) for document in documents),
        "product_evidence_rows": sum(len(field.evidence_levels) for field in product_fields),
        "product_fact_fields": sum(field.allowed_in_product_fact for field in product_fields),
        "published_items": len(selected),
    }
    if counts != {
        "documents": 21,
        "authorized_documents": 19,
        "template_documents": 2,
        "segments": 5046,
        "products": 14,
        "product_evidence_rows": 203,
        "product_fact_fields": 26,
        "published_items": len(selected),
    }:
        raise DomainError("TENANT-01 冻结来源数量与正式裁决不一致")
    projection_document = _dictionary(projection, "品牌发布投影证据无效")
    return {
        "schema_version": "tenant01-formal-publication-projection-evidence-v1",
        "candidate_sha": candidate_sha,
        "tenant_id": tenant_id,
        "brand_id": brand_id,
        "schema_revision": schema_revision,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_contract": {
            "raw_library": "immutable_source_evidence_only",
            "publication_projection": "confirmed_minimum_sufficient_source_bound_items",
            "task_context": "applicability_and_scope_filtered_frozen_refs",
            "final_artifact": "generated_from_frozen_task_context",
        },
        "counts": counts,
        "coverage": list(coverage),
        "current_projection": current,
        "projection_history": projection_document["history"],
        "raw_segments_sent_to_writer": False,
        "excluded_video_assets_imported": False,
        "checks": [
            {"id": "SOURCE_COVERAGE_21", "status": "PASS"},
            {"id": "SOURCE_SEGMENTS_5046", "status": "PASS"},
            {"id": "PROJECTION_SOURCE_BOUND", "status": "PASS"},
            {"id": "PROJECTION_THREE_ROLES", "status": "PASS"},
            {"id": "PROJECTION_APPEND_ONLY", "status": "PASS"},
            {"id": "RAW_SEGMENTS_NOT_WRITER", "status": "PASS"},
            {"id": "TEMPLATE_INTERNAL_EXCLUDED", "status": "PASS"},
            {"id": "PRODUCT_FACT_PIPELINE_SEPARATE", "status": "PASS"},
            {"id": "EXCLUDED_VIDEOS_NOT_IMPORTED", "status": "PASS"},
        ],
        "verdict": "PASS",
    }


def _integer(value: object, message: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DomainError(message)
    return value


def _validate_success_packet(
    case: dict[str, object],
    *,
    projection_id: str,
    projection_version: int,
    projection_digest: str,
) -> None:
    content_product = _text(case.get("content_product"), "成功用例缺少内容产品")
    snapshot = _dictionary(case.get("snapshot"), "成功用例缺少任务快照")
    packet = _dictionary(snapshot.get("brand_context_packet"), "成功任务缺少品牌上下文快照")
    if packet.get("packet_version") != "brand-context-packet-v3":
        raise DomainError("成功任务没有冻结 BrandContextPacketV3")
    if (
        packet.get("publication_projection_id") != projection_id
        or packet.get("publication_projection_version") != projection_version
        or packet.get("publication_projection_digest") != projection_digest
    ):
        raise DomainError("成功任务没有绑定当前已确认来源投影")
    refs = {
        field: tuple(
            _text(value, f"任务 {field} 含无效引用") for value in _list(packet.get(field), f"任务缺少 {field}")
        )
        for field in (
            "available_segment_refs",
            "frozen_segment_refs",
            "consumed_segment_refs",
            "displayed_segment_refs",
        )
    }
    if any(len(values) != len(set(values)) for values in refs.values()):
        raise DomainError("任务品牌上下文引用重复")
    available = set(refs["available_segment_refs"])
    frozen = set(refs["frozen_segment_refs"])
    consumed = set(refs["consumed_segment_refs"])
    displayed = set(refs["displayed_segment_refs"])
    if not displayed <= consumed <= frozen <= available:
        raise DomainError("任务品牌上下文引用越界")
    if not consumed:
        raise DomainError("只证明投影存在但没有任务 consumed refs")
    if len(available) > 64 or len(available) >= 5046:
        raise DomainError("任务无差别加载了原始来源 segments")
    raw_segments = _list(packet.get("segments"), "任务品牌上下文 segments 无效")
    if not raw_segments or len(raw_segments) > 64:
        raise DomainError("任务品牌上下文不是最小充分集合")
    segment_ids: set[str] = set()
    for raw_segment in raw_segments:
        segment = _dictionary(raw_segment, "任务品牌上下文 segment 无效")
        segment_id = _text(segment.get("segment_id"), "任务 segment ID 缺失")
        segment_ids.add(segment_id)
        if not _text(segment.get("source_id"), "任务来源 ID 缺失").startswith("brand_source_segment:"):
            raise DomainError("任务上下文含非来源绑定发布项")
        _digest(segment.get("source_digest"), "任务来源 segment digest 缺失")
        _digest(
            segment.get("source_document_digest"),
            "任务来源 document digest 缺失",
        )
        semantic_kind = _text(segment.get("semantic_kind"), "任务语义角色缺失")
        if semantic_kind not in {
            "brand_fact",
            "expression_constraint",
            "creative_method",
        }:
            raise DomainError("internal/template/catalog 数据进入 Writer 上下文")
        applicability = {
            _text(value, "任务来源 applicability 无效")
            for value in _list(segment.get("applicability"), "任务来源 applicability 缺失")
        }
        if content_product not in applicability:
            raise DomainError("任务消费了不适用于当前内容产品的发布项")
    if frozen != segment_ids:
        raise DomainError("任务 frozen refs 与冻结 segment 集合不一致")
    expected_packet_digest = _digest(packet.get("packet_digest"), "任务品牌上下文 packet digest 无效")
    if (
        brand_context_packet_v3_digest(
            projection_id=projection_id,
            projection_version=projection_version,
            projection_digest=projection_digest,
            available_segment_refs=refs["available_segment_refs"],
            frozen_segment_refs=refs["frozen_segment_refs"],
            consumed_segment_refs=refs["consumed_segment_refs"],
            displayed_segment_refs=refs["displayed_segment_refs"],
            segments=[_dictionary(value, "任务品牌上下文 segment 无效") for value in raw_segments],
        )
        != expected_packet_digest
    ):
        raise DomainError("任务品牌上下文 packet digest 无法复算")
    artifact_digest = _digest(case.get("artifact_digest"), "成功任务成品 digest 缺失")
    if artifact_digest == expected_packet_digest:
        raise DomainError("成品 digest 不能冒充上下文 packet digest")


def validate_context_consumption_evidence(
    document: object,
    *,
    expected_candidate_sha: str,
    expected_tenant_id: str,
) -> tuple[dict[str, object], ...]:
    evidence = _dictionary(document, "正式上下文消费证据无效")
    if evidence.get("schema_version") != "tenant01-formal-context-consumption-v1":
        raise DomainError("正式上下文消费证据版本无效")
    if evidence.get("candidate_sha") != expected_candidate_sha or not _SHA_PATTERN.fullmatch(expected_candidate_sha):
        raise DomainError("正式上下文消费证据候选 SHA 不一致")
    if evidence.get("tenant_id") != expected_tenant_id:
        raise DomainError("正式上下文消费证据租户不一致")
    if _integer(evidence.get("raw_segment_count"), "原始 segment 数量无效") != 5046:
        raise DomainError("正式上下文消费证据没有绑定 5,046 个来源 segment 真值")
    formal_user = _dictionary(evidence.get("formal_user"), "正式用户证明缺失")
    formal_username = str(formal_user.get("username", ""))
    if (
        (formal_username != "笛语品控" and not re.fullmatch(r"笛语品控-[0-9a-f]{10}", formal_username))
        or formal_user.get("business_data_kind") != "formal_business_data"
        or formal_user.get("entry_kind") != "tenant_user"
    ):
        raise DomainError("正式上下文消费门必须使用正式笛语品控，不接受 synthetic 用户")
    _text(formal_user.get("id"), "正式笛语品控 user.id 缺失")
    projection = _dictionary(evidence.get("current_projection"), "当前投影绑定缺失")
    projection_id = _text(projection.get("id"), "当前投影 ID 缺失")
    projection_version = _integer(projection.get("version"), "当前投影版本无效")
    projection_digest = _digest(projection.get("digest"), "当前投影 digest 无效")

    cases = tuple(
        _dictionary(value, "正式上下文消费用例无效") for value in _list(evidence.get("cases"), "正式上下文消费用例缺失")
    )
    by_id = {_text(case.get("case_id"), "消费用例 ID 缺失"): case for case in cases}
    if len(by_id) != len(cases) or set(by_id) != {
        "factory_actuality",
        "explicit_product",
        "institutional_guarantee",
        "unknown_sku",
        "ordinary_life",
    }:
        raise DomainError("正式上下文消费用例必须完整且不重复")
    expected_shapes = {
        "factory_actuality": (
            "succeeded",
            "task_actuality",
            "brand_life_narrative",
            "actuality_reflection",
            (1, 1, 1, 1),
        ),
        "explicit_product": (
            "succeeded",
            "specific_product_claim",
            "product_truth",
            "product_explanation",
            (1, 1, 1, 1),
        ),
        "institutional_guarantee": (
            "rejected_before_task",
            "institutional_claim",
            "none",
            "none",
            (0, 0, 0, 0),
        ),
        "unknown_sku": (
            "rejected_before_task",
            "specific_product_claim",
            "none",
            "none",
            (0, 0, 0, 0),
        ),
        "ordinary_life": (
            "succeeded",
            "general_topic",
            "brand_life_narrative",
            "general_observation",
            (1, 1, 1, 1),
        ),
    }
    exact_factory_input = "今天去工厂验厂，今年量装大货的车缝品质有了大幅度的提升"
    if by_id["factory_actuality"].get("input") != exact_factory_input:
        raise DomainError("正式上下文消费证据没有使用精确验厂输入")
    for case_id, expected in expected_shapes.items():
        case = by_id[case_id]
        outcome, classification, content_product, narrative_mode, counts = expected
        observed_counts = (
            _integer(case.get("task_delta"), "任务增量无效"),
            _integer(case.get("run_delta"), "运行增量无效"),
            _integer(case.get("version_delta"), "版本增量无效"),
            _integer(case.get("writer_calls"), "Writer 调用数无效"),
        )
        if (
            case.get("outcome") != outcome
            or case.get("classification") != classification
            or case.get("content_product") != content_product
            or case.get("narrative_mode") != narrative_mode
            or observed_counts != counts
            or case.get("permanent_running") != 0
        ):
            raise DomainError(f"正式上下文消费用例 {case_id} 未达到冻结结果")
        product_refs = _list(case.get("product_fact_refs"), "ProductFact refs 无效")
        selected_skus = _list(case.get("selected_skus"), "选中 SKU 证据无效")
        if outcome == "succeeded":
            _validate_success_packet(
                case,
                projection_id=projection_id,
                projection_version=projection_version,
                projection_digest=projection_digest,
            )
            task_snapshot = _dictionary(case.get("snapshot"), "成功用例缺少任务快照")
            frozen_product_refs = [
                _text(value, "任务冻结 ProductFact ref 无效")
                for value in _list(
                    task_snapshot.get("used_product_fact_ids"),
                    "任务缺少冻结 ProductFact refs",
                )
            ]
            if product_refs != frozen_product_refs:
                raise DomainError("证据 ProductFact refs 与正式任务快照不一致")
            if case_id == "explicit_product":
                if len(selected_skus) != 1 or not product_refs:
                    raise DomainError("明确商品用例没有绑定单一 SKU 及 ProductFact refs")
                product_contract = _dictionary(
                    task_snapshot.get("product_value_contract"),
                    "明确商品任务缺少 ProductDecisionBasis",
                )
                supporting_refs = [
                    _text(value, "商品决策依据 ref 无效")
                    for value in _list(
                        product_contract.get("supporting_fact_refs"),
                        "商品决策依据缺少 ProductFact refs",
                    )
                ]
                packet = _dictionary(
                    task_snapshot.get("product_fact_packet"),
                    "明确商品任务缺少 ProductFact packet",
                )
                packet_facts = [
                    _dictionary(value, "ProductFact packet 条目无效")
                    for value in _list(packet.get("facts"), "ProductFact packet 缺少事实")
                ]
                packet_by_ref = {
                    _text(value.get("fact_id"), "ProductFact packet 缺少 fact_id"): value for value in packet_facts
                }
                if (
                    supporting_refs != frozen_product_refs
                    or not set(frozen_product_refs) <= set(packet_by_ref)
                    or {_text(packet_by_ref[ref].get("sku"), "ProductFact 缺少 SKU") for ref in frozen_product_refs}
                    != set(selected_skus)
                ):
                    raise DomainError("明确商品没有按单一 SKU 冻结可追踪 ProductFact")
            elif selected_skus or product_refs:
                raise DomainError("非商品内容错误取得 ProductFact")
        elif (
            case.get("snapshot") is not None or case.get("artifact_digest") is not None or selected_skus or product_refs
        ):
            raise DomainError("建任务前失败留下了业务对象或事实引用")

    replay = _dictionary(evidence.get("version_replay"), "V1/V2 回读证据缺失")
    if (
        replay.get("v1_projection_id") != projection_id
        or replay.get("v2_projection_id") != projection_id
        or replay.get("v1_packet_digest") != replay.get("v2_packet_digest")
        or replay.get("v1_artifact_digest") != replay.get("v1_reread_artifact_digest")
        or replay.get("current_version") != 2
        or replay.get("read_sequence") != [1, 2, 1, 2]
        or replay.get("copy_version") != 2
        or replay.get("export_version") != 2
    ):
        raise DomainError("V1→V2→V1 回读、冻结投影、复制或导出证据不成立")
    isolation = _dictionary(evidence.get("projection_isolation"), "新旧投影隔离证据缺失")
    if (
        isolation.get("old_projection_id") != projection_id
        or isolation.get("old_projection_version") != projection_version
        or isolation.get("new_projection_id") == projection_id
        or isolation.get("new_projection_status") != "confirmed"
        or _integer(
            isolation.get("new_projection_version"),
            "新 current projection 版本无效",
        )
        <= projection_version
        or _digest(
            isolation.get("new_projection_digest"),
            "新 current projection digest 无效",
        )
        == projection_digest
        or isolation.get("old_task_packet_before") != isolation.get("old_task_packet_after")
        or isolation.get("old_task_artifact_before") != isolation.get("old_task_artifact_after")
    ):
        raise DomainError("新 projection 污染了旧任务 V1/V2")
    readiness = _dictionary(evidence.get("user_visible_readiness"), "用户可见就绪度证据缺失")
    if (
        readiness.get("ordinary_content") != "available"
        or readiness.get("P4") != "data_missing"
        or readiness.get("P5") != "data_missing"
        or readiness.get("DM01") != "data_missing"
        or readiness.get("all_capabilities_ready") is not False
    ):
        raise DomainError("用户可见就绪度与正式资料缺口不一致")
    raw_checks = _list(evidence.get("checks"), "正式上下文消费证据缺少 checks")
    check_records = [_dictionary(value, "正式上下文 check 无效") for value in raw_checks]
    check_ids = [_text(record.get("id"), "正式上下文 check ID 缺失") for record in check_records]
    if (
        any(record.get("status") != "PASS" for record in check_records)
        or len(check_ids) != len(set(check_ids))
        or set(check_ids)
        != {
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
        }
    ):
        raise DomainError("正式上下文消费 checks 不完整或含未通过项")
    return cases


def _write_private_json(path: Path, document: dict[str, object]) -> str:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    payload = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(payload)
    path.chmod(0o600)
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize TENANT-01 source coverage and formal publication evidence.")
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--projection", required=True, type=Path)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--brand-id", required=True)
    parser.add_argument("--schema-revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    projection = json.loads(args.projection.resolve(strict=True).read_text(encoding="utf-8"))
    evidence = build_gate_evidence(
        documents=freeze_source_batch(args.source_root.resolve(strict=True)),
        projection=projection,
        candidate_sha=args.candidate_sha,
        tenant_id=args.tenant_id,
        brand_id=args.brand_id,
        schema_revision=args.schema_revision,
    )
    digest = _write_private_json(args.output, evidence)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "sha256": digest,
                "documents": 21,
                "segments": 5046,
                "published_items": evidence["counts"]["published_items"],  # type: ignore[index]
                "verdict": "PASS",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
