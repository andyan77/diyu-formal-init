from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

from scripts.gated.brand_matrix_importer import (
    CONTENT_TERRITORY_AMENDMENT_ID,
    QUALITY_CONTROL_SOURCE_SHA256,
    BrandMatrixImporter,
)
from src.brain.content_service import ContentService
from src.infrastructure.gatec_queries import PROJECTION_TASK_CONTEXT_SQL
from src.shared.content_territory import (
    QUALITY_DEMO_AUTHORITY_CLASS,
    QUALITY_DEMO_SUBJECT_TYPE,
    missing_mission_evidence_question,
)
from src.shared.types import (
    BrandContext,
    BrandContextPacketV3,
    BrandContextSegment,
    ProductFact,
    TrustedScope,
)
from src.tool.run_tenant01_formal_vertical import _candidate_item_from_current

_ROOT = Path(__file__).parents[1]
_QUALITY_SOURCE = _ROOT / "docs/BRAND-MATRIX-01/素材草案-v0/05-品控记录汇编-演示补充.md"
_CONTRACT = _ROOT / "docs/BRAND-MATRIX-01/GateA-素材合同/import-contract.json"
_MANIFEST = _ROOT / "docs/BRAND-MATRIX-01/GateA-素材合同/import-manifest.json"
_DEEPSEEK = _ROOT / "src/tool/llm_gateway/deepseek.py"


def _packet(*segments: BrandContextSegment) -> BrandContextPacketV3:
    refs = tuple(segment.segment_id for segment in segments)
    return BrandContextPacketV3(
        packet_version="brand-context-packet-v3",
        packet_digest="a" * 64,
        publication_projection_id="projection-gatee-r1",
        publication_projection_version=2,
        publication_projection_digest="b" * 64,
        available_segment_refs=refs,
        frozen_segment_refs=refs,
        consumed_segment_refs=(),
        displayed_segment_refs=(),
        segments=segments,
    )


def _h04_context(packet: BrandContextPacketV3) -> BrandContext:
    return BrandContext(
        brand_name="笛语",
        positioning="真实、自然、有审美判断",
        decision_order="先事实后判断",
        tone="克制",
        account_name="H04 品控纪实账号",
        operator_name="品控操作人",
        organization_name="笛语总部",
        content_role_name="H04 品控纪实",
        content_role_boundary="只讲可追溯的品控过程",
        audience_description="关注商品过程的人",
        strategy_version="v2",
        platform="抖音",
        media_format="视频",
        production_conditions="原创口播",
        context_packet=packet,
    )


def _quality_segment() -> BrandContextSegment:
    return BrandContextSegment(
        segment_id="quality:item:1",
        source_document_id="quality:document",
        source_document_version_id="quality:document:v1",
        source_id="brand_source_segment:quality:1",
        source_version="demo-v1",
        semantic_kind="brand_fact",
        evidence_level="confirmed_publication",
        visibility_scope="headquarters",
        digest="c" * 64,
        exact_text="演示品控记录（仅演示，不得当作真实批次证据）：成衣中检环节按规程完成。",
        applicability=("product_truth",),
        authority_class=QUALITY_DEMO_AUTHORITY_CLASS,
        semantic_subject_type=QUALITY_DEMO_SUBJECT_TYPE,
        semantic_subject_id="account:h04/DIYU-CSPU-013",
        claim_key="DEMO-QC-013-2607-01",
    )


def test_quality_source_is_digest_locked_and_extracts_four_writer_records() -> None:
    assert hashlib.sha256(_QUALITY_SOURCE.read_bytes()).hexdigest() == QUALITY_CONTROL_SOURCE_SHA256
    importer = BrandMatrixImporter(
        "postgresql://unused",
        contract_path=_CONTRACT,
        manifest_path=_MANIFEST,
        windows_source_root=Path("/unused"),
        repository_root=_ROOT,
    )
    records = importer._quality_control_records()
    assert len(records) == 5
    assert sum(record.publishable for record in records) == 4
    assert next(record for record in records if record.record_id == "DEMO-QCX-2608-003").publishable is False
    assert all("仅演示，不得当作真实批次证据" in record.exact_text for record in records)


def test_gate_a_contract_change_is_append_only_and_names_the_new_consumer() -> None:
    contract = json.loads(_CONTRACT.read_text(encoding="utf-8"))
    assert contract["amendments"][0] == {
        "amendment_id": "AMD-2026-0808-01",
        "target_document_id": "DIYU-BRAND-BASELINE-001",
        "target_anchor": "§3.5表达幅度表地域程度行",
        "from_version": "v1",
        "to_version": "v2",
        "change_summary": "区域和门店账号由不模仿方言人设升级为可以模仿方言人设；事实与合规边界不变",
        "approved_by": "founder",
        "approved_at": "2026-08-08",
        "source_anchor": "素材草案-v0/09 §4",
        "consumer": "Gate D import and scenario 7",
        "status": "approved_not_imported",
    }
    assert len(contract["amendments"]) == 2
    assert contract["amendments"][1]["amendment_id"] == CONTENT_TERRITORY_AMENDMENT_ID
    assert contract["amendments"][1]["status"] == "approved_import_extension"


def test_h04_p2_missing_mission_source_questions_before_provider_or_task() -> None:
    context = _h04_context(_packet())
    selected = _h04_context(_packet())
    repository = Mock()
    repository.load_brand_context.return_value = context
    repository.load_product_facts.return_value = (
        ProductFact("DIYU-CSPU-013", {"category": "儿童外套"}, display_name="儿童外套"),
    )
    repository.select_brand_context_for_task.return_value = selected
    generator = Mock()
    service = ContentService(repository, generator)
    scope = TrustedScope(uuid4(), uuid4(), uuid4(), uuid4())

    result = service.create_from_weak_seed(
        scope,
        "出厂之前你们都检查什么？以 DIYU-CSPU-013 为例。",
        primary_product_override="product_truth",
    )

    assert result["kind"] == "question"
    assert "缺少可消费的检查环节或品控记录" in str(result["message"])
    generator.generate.assert_not_called()
    repository.load_active_assets.assert_not_called()
    repository.create_task_and_running_run.assert_not_called()


def test_h04_p2_quality_source_opens_the_mission_gate_and_is_account_scoped() -> None:
    assert missing_mission_evidence_question(
        _h04_context(_packet(_quality_segment())),
        "product_truth",
        (ProductFact("DIYU-CSPU-013", {"category": "儿童外套"}),),
    ) is None
    assert "split_part(item.semantic_subject_id, '/', 1) = root_account.id::text" in PROJECTION_TASK_CONTEXT_SQL


def test_tenant01_vertical_replays_v2_business_fields_without_governance_forgery() -> None:
    item = _candidate_item_from_current(
        {
            "source_segment_id": str(uuid4()),
            "publication_role": "public_brand_fact",
            "published_text": "笛语从真实穿衣问题出发。",
            "applicability": ["brand_life_narrative"],
            "visibility_scope": "brand_all",
            "scope_organization_ids": [],
            "effective_at": "2026-08-09T00:00:00+00:00",
            "expires_at": None,
            "semantic_subject_type": "brand",
            "claim_key": "identity",
            "authority_class": "headquarters_formal",
            "source_digest": "d" * 64,
        }
    )

    assert item["fact_subject"] == "brand_identity"
    assert item["organization_ids"] == []
    assert "authority_class" not in item
    assert "source_digest" not in item

    legacy_item = _candidate_item_from_current(
        {
            "source_segment_id": str(uuid4()),
            "source_id": "DIYU-BRAND-BASELINE-001",
            "source_locator": "line:49",
            "publication_role": "public_brand_fact",
            "published_text": "笛语帮助家庭中的每一个人保有自己的样子。",
            "applicability": ["product_truth"],
            "visibility_scope": "brand_all",
            "scope_organization_ids": [],
            "effective_at": None,
            "expires_at": None,
        },
        legacy_effective_at="2026-08-09T00:00:00+00:00",
    )
    assert legacy_item["fact_subject"] == "brand_positioning"
    assert legacy_item["effective_at"] == "2026-08-09T00:00:00+00:00"


def test_all_writer_paths_keep_brand_relevance_out_of_the_content_job() -> None:
    source = _DEEPSEEK.read_text(encoding="utf-8")
    assert "品牌和账号关系通过本题" not in source
    assert "本篇必须让受众从作品本身读出当前账号为什么会说这段话" not in source
    assert source.count("找不到自然关联时") >= 2
