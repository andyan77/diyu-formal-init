from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from pydantic import ValidationError

from src.brain.platform_directions import direction_for
from src.gateway.api.app import create_app
from src.gateway.api.contracts import BrandPublicationProjectionCandidateRequest
from src.gateway.api.settings import Settings
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.shared.brand_publication import brand_context_packet_document
from src.shared.types import BrandContext, BrandContextPacketV3, TenantManagementScope, TrustedScope


def _seed_d0_scope(database_url: str) -> tuple[TenantManagementScope, TrustedScope, UUID, UUID]:
    tenant_id = uuid4()
    brand_id = uuid4()
    organization_id = uuid4()
    manager_id = uuid4()
    operator_id = uuid4()
    account_id = uuid4()
    source_document_id = uuid4()
    source_version_id = uuid4()
    source_segment_id = uuid4()
    source_text = "笛语以真实穿衣问题为起点，提供有来源且有边界的判断。"
    source_digest = hashlib.sha256(source_text.encode()).hexdigest()
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO tenants (id, name) VALUES (%s, %s)",
            (tenant_id, f"Gate D D0 隔离租户 {tenant_id.hex[:8]}"),
        )
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
        cursor.execute(
            "INSERT INTO organizations "
            "(id,tenant_id,name,organization_level,business_data_kind,enabled) "
            "VALUES (%s,%s,'Gate D 总部','company','formal_business_data',true)",
            (organization_id, tenant_id),
        )
        cursor.execute(
            "INSERT INTO brands (id,tenant_id,name,positioning,decision_order,tone) "
            "VALUES (%s,%s,'笛语','真实穿衣问题','先事实后判断','真实自然')",
            (brand_id, tenant_id),
        )
        cursor.execute(
            "INSERT INTO users "
            "(id,tenant_id,organization_id,display_name,entry_kind,business_data_kind) VALUES "
            "(%s,%s,%s,'Gate D 管理员','tenant_admin','formal_business_data'),"
            "(%s,%s,%s,'Gate D 内容操作人','tenant_user','formal_business_data')",
            (manager_id, tenant_id, organization_id, operator_id, tenant_id, organization_id),
        )
        cursor.execute(
            "INSERT INTO tenant_management_grants (id,tenant_id,user_id,enabled) VALUES (%s,%s,%s,true)",
            (uuid4(), tenant_id, manager_id),
        )
        cursor.execute(
            "INSERT INTO content_accounts "
            "(id,tenant_id,brand_id,name,channel,control_organization_id,control_organization_source,"
            "business_data_kind,enabled,platform_enabled) "
            "VALUES (%s,%s,%s,'笛语 D0 正式账号','抖音',%s,'declared','formal_business_data',true,true)",
            (account_id, tenant_id, brand_id, organization_id),
        )
        cursor.execute(
            "INSERT INTO brand_source_documents "
            "(id,tenant_id,brand_id,source_id,embedded_title,provenance_filename,source_version,original_status,"
            "activation_status,authorization_source,authorization_at,visibility_scope,status,current_version_id,created_by) "
            "VALUES (%s,%s,%s,'DIYU-BRAND-BASELINE-001','笛语品牌基线','gate-d-d0.md','v1','confirmed',"
            "'brand_user_authorized','ATT-GATEA-20260808-01',%s,'brand_all','active',NULL,%s)",
            (source_document_id, tenant_id, brand_id, datetime.now(timezone.utc), manager_id),
        )
        cursor.execute(
            "INSERT INTO brand_source_document_versions "
            "(id,tenant_id,brand_id,document_id,source_version,embedded_title,provenance_filename,original_status,"
            "activation_status,authorization_source,authorization_at,raw_sha256,normalized_sha256,source_size,"
            "source_mtime_ns,content,created_by) "
            "VALUES (%s,%s,%s,%s,'v1','笛语品牌基线','gate-d-d0.md','confirmed','brand_user_authorized',"
            "'ATT-GATEA-20260808-01',%s,%s,%s,%s,0,%s,%s)",
            (
                source_version_id,
                tenant_id,
                brand_id,
                source_document_id,
                datetime.now(timezone.utc),
                source_digest,
                source_digest,
                len(source_text.encode()),
                source_text,
                manager_id,
            ),
        )
        cursor.execute(
            "UPDATE brand_source_documents SET current_version_id=%s WHERE tenant_id=%s AND id=%s",
            (source_version_id, tenant_id, source_document_id),
        )
        cursor.execute(
            "INSERT INTO brand_source_segments "
            "(id,tenant_id,brand_id,document_id,document_version_id,segment_key,heading_path,source_locator,"
            "exact_text,semantic_kind,evidence_level,applicability,visibility_scope,digest) "
            "VALUES (%s,%s,%s,%s,%s,'brand-identity',%s,'§一 品牌身份',%s,'brand_fact','confirmed',"
            "'P1-P5','brand_all',%s)",
            (
                source_segment_id,
                tenant_id,
                brand_id,
                source_document_id,
                source_version_id,
                ["一、品牌身份"],
                source_text,
                source_digest,
            ),
        )
    return (
        TenantManagementScope(tenant_id, manager_id, brand_id),
        TrustedScope(tenant_id, operator_id, brand_id, account_id),
        source_segment_id,
        organization_id,
    )


def _v2_item(source_segment_id: UUID) -> dict[str, object]:
    return {
        "source_segment_id": source_segment_id,
        "publication_role": "public_brand_fact",
        "published_text": "笛语从真实穿衣问题出发，提供有来源且有边界的判断。",
        "applicability": ("brand_life_narrative", "local_response"),
        "visibility_scope": "brand_all",
        "organization_ids": (),
        "effective_at": datetime.now(timezone.utc) - timedelta(minutes=1),
        "expires_at": None,
        "fact_subject": "brand_identity",
    }


def test_gated_d0_v2_preview_confirm_task_snapshot_and_feedback(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    management_scope, content_scope, source_segment_id, _ = _seed_d0_scope(migrator_database_url)
    workbench = PostgresWorkbenchRepository(app_database_url)
    item = _v2_item(source_segment_id)

    preview = workbench.preview_brand_publication_candidate(management_scope, (item,))
    candidate = workbench.create_brand_publication_candidate(management_scope, (item,))
    assert preview["contract_version"] == candidate["contract_version"] == "brand-publication-projection-v2"
    assert preview["digest"] == candidate["digest"]
    candidate_items = cast(list[dict[str, object]], candidate["items"])
    assert candidate_items[0]["authority_class"] == "headquarters_formal"
    projection_id = UUID(str(candidate["id"]))
    confirmed = workbench.confirm_brand_publication_projection(management_scope, projection_id)
    assert confirmed["status"] == "confirmed"
    readback = workbench.brand_publication_projection(management_scope)
    current = readback["current"]
    assert isinstance(current, dict)
    stored_items = cast(list[dict[str, object]], current["items"])
    stored_item = stored_items[0]
    assert current["contract_version"] == "brand-publication-projection-v2"
    assert stored_item["scope_contract_version"] == "publication-item-scope-v2"
    assert stored_item["visibility_scope"] == "brand_all"
    assert stored_item["semantic_subject_type"] == "brand"
    assert stored_item["claim_key"] == "identity"
    assert stored_item["source_ref"] == str(source_segment_id)

    context = BrandContext(
        brand_name="笛语",
        positioning="真实穿衣问题",
        decision_order="先事实后判断",
        tone="真实自然",
        account_name="笛语 D0 正式账号",
        operator_name="Gate D 内容操作人",
        organization_name="Gate D 总部",
        content_role_name="品牌内容编辑",
        content_role_boundary="只使用已确认来源",
        audience_description="需要真实穿衣判断的人",
        strategy_version="v1",
        platform="抖音",
        media_format="视频",
        production_conditions="隔离确定性测试",
    )
    repository = PostgresContentRepository(app_database_url)
    selected = repository.select_brand_context_for_task(
        content_scope,
        context,
        "一次真实的品牌日常观察",
        "brand_life_narrative",
        (),
    )
    assert isinstance(selected.context_packet, BrandContextPacketV3)
    packet = selected.context_packet
    assert packet.publication_projection_id == str(projection_id)
    assert packet.publication_projection_digest == candidate["digest"]
    assert packet.frozen_segment_refs == (str(stored_item["id"]),)
    task_id, _, _ = repository.create_task_and_running_run(
        content_scope,
        "一次真实的品牌日常观察",
        "brand_life_narrative",
        None,
        "gate-d-zero-model-stub",
        (),
        selected,
        (),
        "douyin_video",
        "video",
        direction_for("douyin_video"),
        None,
        "隔离确定性测试",
        snapshot={"brand_context_packet": brand_context_packet_document(packet, include_text=True)},
    )
    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(management_scope.tenant_id),))
        cursor.execute(
            "SELECT content_context_snapshot FROM business_tasks WHERE tenant_id=%s AND id=%s",
            (management_scope.tenant_id, task_id),
        )
        snapshot_row = cursor.fetchone()
    assert snapshot_row is not None
    snapshot = snapshot_row[0]
    assert snapshot["brand_context_packet"]["segments"][0]["segment_id"] == stored_item["id"]
    observation = workbench.create_brand_feedback_observation(
        management_scope,
        task_id,
        None,
        content_scope.account_id,
        {"kind": "store_feedback", "note": "顾客更关心当天温差。"},
    )
    assert observation["candidate_status"] == "candidate"
    assert observation["promoted_to_formal_source"] is False
    observations = workbench.brand_feedback_observations(management_scope)
    assert observations[0]["id"] == observation["id"]
    assert observations[0]["promoted_to_formal_source"] is False
    next_context = repository.select_brand_context_for_task(
        content_scope,
        context,
        "反馈登记后的下一条品牌日常观察",
        "brand_life_narrative",
        (),
    )
    assert isinstance(next_context.context_packet, BrandContextPacketV3)
    assert next_context.context_packet.frozen_segment_refs == packet.frozen_segment_refs
    assert str(observation["id"]) not in next_context.context_packet.frozen_segment_refs


def test_gated_d0_api_contract_forbids_client_owned_governance_fields() -> None:
    valid = {
        "source_segment_id": str(uuid4()),
        "publication_role": "public_brand_fact",
        "published_text": "正式品牌身份。",
        "applicability": ["brand_life_narrative"],
        "visibility_scope": "brand_all",
        "organization_ids": [],
        "effective_at": "2026-08-08T00:00:00+00:00",
        "expires_at": None,
        "fact_subject": "brand_identity",
    }
    BrandPublicationProjectionCandidateRequest.model_validate({"items": [valid]})
    for forbidden in (
        "tenant_id",
        "brand_id",
        "contract_version",
        "scope_contract_version",
        "authority_class",
        "source_ref",
        "source_version",
        "source_digest",
    ):
        with pytest.raises(ValidationError):
            BrandPublicationProjectionCandidateRequest.model_validate(
                {"items": [valid | {forbidden: "client-forged"}]}
            )
    settings = Settings.model_validate(
        {
            "session_secret": "gated-d0-test-session-secret-000001",
            "demo_tenant_id": str(uuid4()),
            "demo_user_id": str(uuid4()),
            "demo_brand_id": str(uuid4()),
            "demo_account_id": str(uuid4()),
        }
    )
    paths = {str(getattr(route, "path", "")) for route in create_app(settings).routes}
    assert {
        "/api/v1/tenant-management/brand-publication/preview",
        "/api/v1/tenant-management/brand-publication/candidates",
        "/api/v1/tenant-management/brand-publication/{projection_id}/confirm",
        "/api/v1/tenant-management/brand-feedback-observations",
        "/api/v1/tenant-management/brand-relevance-governance",
    } <= paths
