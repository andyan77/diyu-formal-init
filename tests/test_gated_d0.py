from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from pydantic import ValidationError

from scripts.gated.provider_env import (
    ProviderHandshakeError,
    probe_provider_tcp_tls,
)
from scripts.gated.run_formal_acceptance import (
    PRIOR_RUNTIME_CANDIDATE_SHA,
    EvidenceGenerator,
    _load_prior_ledger,
    _performance_review_annotations,
)
from src.brain.platform_directions import direction_for
from src.gateway.api.app import create_app
from src.gateway.api.contracts import BrandPublicationProjectionCandidateRequest
from src.gateway.api.settings import Settings
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.shared.brand_publication import brand_context_packet_document
from src.shared.delivery_compiler import DELIVERY_COMPILER_V5_VERSION
from src.shared.errors import DomainError
from src.shared.publication_scope import (
    AUTHORIZATION_CONTRACT_VERSION,
    AuthorizationContractV1,
    authorization_contract_digest,
    authorization_contract_document,
)
from src.shared.types import BrandContext, BrandContextPacketV3, TenantManagementScope, TrustedScope
from src.tool.llm_gateway.deepseek import DeepSeekGenerator

_RERUN03_FACT_ID = "fact:product:gated-rerun-03"


def test_gate_d_full_retry_preserves_all_prior_provider_attempts() -> None:
    candidate_sha, records = _load_prior_ledger(
        Path("docs/BRAND-MATRIX-01/GateD-记录/provider-ledger.json"),
        expected_count=44,
    )

    assert candidate_sha == PRIOR_RUNTIME_CANDIDATE_SHA
    assert len(records) == 44
    assert records[-1]["card_id"] == "S01-P2"
    assert records[-1]["binary_result"] == "FAILED_SAFE_PROVIDER_REQUEST"
    assert records[-1]["response_sha256"] is None


def test_gate_d_provider_handshake_is_direct_and_spends_no_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[str, int], float]] = []

    class Connection:
        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    class TlsConnection(Connection):
        def version(self) -> str:
            return "TLSv1.3"

    class Context:
        def wrap_socket(
            self,
            connection: Connection,
            *,
            server_hostname: str,
        ) -> TlsConnection:
            assert isinstance(connection, Connection)
            assert server_hostname == "dashscope.aliyuncs.com"
            return TlsConnection()

    def create_connection(
        address: tuple[str, int],
        *,
        timeout: float,
    ) -> Connection:
        calls.append((address, timeout))
        return Connection()

    monkeypatch.setenv("ALL_PROXY", "socks5h://172.18.80.1:16005")
    monkeypatch.setattr("scripts.gated.provider_env.socket.create_connection", create_connection)
    monkeypatch.setattr("scripts.gated.provider_env.ssl.create_default_context", Context)

    result = probe_provider_tcp_tls(
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        timeout_seconds=3.0,
    )

    assert calls == [(("dashscope.aliyuncs.com", 443), 3.0)]
    assert result["status"] == "PASS"
    assert result["completion_requests"] == 0
    assert result["provider_budget_consumed"] == 0


def test_gate_d_provider_handshake_fails_closed_for_other_hosts() -> None:
    with pytest.raises(ProviderHandshakeError):
        probe_provider_tcp_tls("https://example.invalid/v1")


def test_gate_d_evidence_ledger_records_transport_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response: dict[str, object] = {
        "choices": [{"message": {"content": '{"ok":true}'}}],
        "usage": {},
    }

    def request(
        self: DeepSeekGenerator,
        system: str,
        prompt: str,
        max_tokens: int,
        *,
        thinking_disabled: bool = True,
        timeout_seconds: float | None = None,
    ) -> tuple[dict[str, object], int]:
        del self, system, prompt, max_tokens, thinking_disabled, timeout_seconds
        return response, 2

    monkeypatch.setattr(DeepSeekGenerator, "_request", request)
    generator = EvidenceGenerator(
        evidence_root=tmp_path,
        prior_request_count=44,
        api_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="x",
        model="deepseek-test",
        max_retries=0,
        transport_max_retries=2,
    )
    generator.begin_card("TEST-CARD")

    _, retries = generator._request("system", "prompt", 20)

    assert retries == 2
    assert generator.transport_retry_count == 2
    assert generator.ledger[0]["transport_retries"] == 2


def test_gate_d_review_package_records_bare_performance_terms_without_blocking() -> None:
    sentence = "这件外套防水又耐磨。"

    assert _performance_review_annotations("S05-R01-P1", sentence) == [
        {
            "annotation_kind": "bare_performance_term_review",
            "blocking": False,
            "card_id": "S05-R01-P1",
            "matched_term": "防水",
            "sentence": sentence,
        },
        {
            "annotation_kind": "bare_performance_term_review",
            "blocking": False,
            "card_id": "S05-R01-P1",
            "matched_term": "耐磨",
            "sentence": sentence,
        },
    ]


def _rerun03_authorization(
    subject_ref: str,
    *,
    authorization_version: str = "v1",
    single_use: bool = True,
) -> AuthorizationContractV1:
    draft = AuthorizationContractV1(
        contract_version=AUTHORIZATION_CONTRACT_VERSION,
        authorization_id=str(uuid4()),
        authorization_version=authorization_version,
        subject_ref=subject_ref,
        tenant_id=str(uuid4()),
        brand_id=str(uuid4()),
        logical_account_id=str(uuid4()),
        organization_id=str(uuid4()),
        allowed_source_digest="a" * 64,
        allowed_usage=("organization_people",),
        single_use=single_use,
        effective_at="2026-08-08T00:00:00+00:00",
        expires_at=None,
        digest="",
    )
    return replace(draft, digest=authorization_contract_digest(draft))


def _rerun03_completion_patch(
    *,
    fact_refs: object | None = None,
    quote_ids: object | None = None,
    authorization: AuthorizationContractV1 | None = None,
) -> dict[str, object]:
    normalized_quote_ids = [] if quote_ids is None else quote_ids
    publication_contract: dict[str, object] = {
        "brand_context_use": {
            "consumed_refs": normalized_quote_ids if isinstance(normalized_quote_ids, list) else [],
        },
        "brand_relevance_evidence": None,
    }
    if authorization is not None:
        publication_contract["brand_relevance_evidence"] = {
            "authorization_ref": authorization.authorization_id,
            "authorization": authorization_contract_document(authorization),
        }
    return {
        "creative_kernel_v5": {"kernel_version": "creative-kernel-v5", "units": []},
        "writer_request_v3": {"request_version": "writer-request-v3"},
        "writer_request_v3_digest": "1" * 64,
        "writer_output_v3": {"output_version": "writer-output-v3"},
        "writer_output_v3_digest": "2" * 64,
        "writer_confirmed_product_fact_refs": ([_RERUN03_FACT_ID] if fact_refs is None else fact_refs),
        "used_persona_quote_ids": normalized_quote_ids,
        "expression_plan_version": "creative-kernel-v5",
        "expression_plan_digest": "3" * 64,
        "delivery_compiler_version": DELIVERY_COMPILER_V5_VERSION,
        "writer_model": "gate-d-rerun-03-zero-provider-stub",
        "version_authorization": "deterministic-publication-v3",
        "claim_inventory_v1": [],
        "deterministic_checked_kernel_digest": "4" * 64,
        "reviewed_creative_digest": "5" * 64,
        "product_fact_packet": {
            "packet_version": "product-fact-packet-v1",
            "packet_digest": "6" * 64,
            "facts": [{"fact_id": _RERUN03_FACT_ID}],
        },
        "immutable_product_fact_blocks": [],
        "used_product_fact_ids": [_RERUN03_FACT_ID],
        "used_product_fact_block_ids": [],
        "product_fact_renderer_version": None,
        "visible_provenance": {"body": ["writer-output-v3:creative_body"]},
        "delivery_resource_refs": [],
        "media_capability_envelope": None,
        "media_capability_envelope_digest": None,
        "media_program": None,
        "media_program_digest": None,
        "product_value_contract": None,
        "product_value_contract_digest": None,
        "publication_contract": publication_contract,
        "publication_contract_digest": "7" * 64,
    }


def _rerun03_task_snapshot(patch: dict[str, object]) -> dict[str, object]:
    return {
        "narrative_frame": {"frame_version": "narrative-frame-v1"},
        "product_fact_packet": patch["product_fact_packet"],
        "publication_contract": patch["publication_contract"],
        "publication_contract_digest": patch["publication_contract_digest"],
    }


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
            BrandPublicationProjectionCandidateRequest.model_validate({"items": [valid | {forbidden: "client-forged"}]})
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


def test_gated_rerun03_completion_snapshot_commits_the_failed_shape(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/gated_rerun03_completion_snapshot_regression.json").read_text(
            encoding="utf-8"
        )
    )
    assert fixture["source_task_id"] == "3bafbf45-fb92-45ae-b832-984ef425a5f8"
    assert fixture["source_run_id"] == "27b810b8-f219-4d72-aaf8-b2b1aee1f80e"
    assert fixture["source_failure_code"] == ("PUBLICATION_V3_COMPLETION_SNAPSHOT_KEYS_REJECTED")
    _, content_scope, _, _ = _seed_d0_scope(migrator_database_url)
    patch = _rerun03_completion_patch()
    assert sorted(key for key in patch if key in PostgresContentRepository._PUBLICATION_V3_GROUNDING_KEYS) == sorted(
        cast(list[str], fixture["required_completion_fields"])
    )
    repository = PostgresContentRepository(app_database_url)
    context = BrandContext(
        brand_name="笛语",
        positioning="真实穿衣问题",
        decision_order="先事实后判断",
        tone="真实自然",
        account_name="Gate D Rerun 03 账号",
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
    task_id, run_id, _ = repository.create_task_and_running_run(
        content_scope,
        "Gate D Rerun 03 完成快照回归",
        "brand_life_narrative",
        None,
        "gate-d-rerun-03-zero-provider-stub",
        (),
        context,
        (),
        "douyin_video",
        "video",
        direction_for("douyin_video"),
        None,
        "隔离确定性测试",
        snapshot=_rerun03_task_snapshot(patch),
    )
    result = repository.complete_run_with_version(
        content_scope,
        task_id,
        run_id,
        "Gate D Rerun 03 快照落版",
        "两个合法审计字段已绑定冻结来源。",
        "gate-d-rerun-03-zero-provider-stub",
        0,
        0,
        None,
        {},
        (),
        snapshot_patch=patch,
    )

    assert result["version"] == fixture["expected_version_after_fix"] == 1
    committed_snapshot = repository.load_content_context_snapshot(content_scope, task_id)
    assert committed_snapshot is not None
    assert committed_snapshot["writer_confirmed_product_fact_refs"] == [_RERUN03_FACT_ID]
    assert committed_snapshot["used_persona_quote_ids"] == []


def test_gated_rerun03_completion_snapshot_stays_fail_closed_and_legacy_safe() -> None:
    patch = _rerun03_completion_patch()
    task_snapshot = _rerun03_task_snapshot(patch)
    merged = PostgresContentRepository._validated_completion_snapshot(
        task_snapshot,
        patch,
    )
    audit = PostgresContentRepository._version_audit_snapshot(merged, "8" * 64)
    assert audit["writer_confirmed_product_fact_refs"] == [_RERUN03_FACT_ID]
    assert audit["used_persona_quote_ids"] == []

    unknown = patch | {"unregistered_completion_field": "must-stay-closed"}
    with pytest.raises(DomainError, match="字段不完整或越界"):
        PostgresContentRepository._validated_completion_snapshot(
            task_snapshot,
            unknown,
        )
    half_grounding = dict(patch)
    half_grounding.pop("used_persona_quote_ids")
    with pytest.raises(DomainError, match="字段不完整或越界"):
        PostgresContentRepository._validated_completion_snapshot(
            task_snapshot,
            half_grounding,
        )

    legacy_patch = dict(patch)
    legacy_patch.pop("writer_confirmed_product_fact_refs")
    legacy_patch.pop("used_persona_quote_ids")
    legacy = PostgresContentRepository._validated_completion_snapshot(
        task_snapshot,
        legacy_patch,
    )
    legacy_audit = PostgresContentRepository._version_audit_snapshot(
        legacy,
        "8" * 64,
    )
    assert "writer_confirmed_product_fact_refs" not in legacy
    assert "used_persona_quote_ids" not in legacy
    assert "writer_confirmed_product_fact_refs" not in legacy_audit
    assert "used_persona_quote_ids" not in legacy_audit
    assert legacy["publication_contract_digest"] == merged["publication_contract_digest"]
    assert legacy_audit["artifact_digest"] == audit["artifact_digest"]


@pytest.mark.parametrize(
    ("patch", "message"),
    (
        (
            _rerun03_completion_patch(fact_refs=("fact:product:not-a-list",)),
            "Writer 确认商品事实引用无效",
        ),
        (
            _rerun03_completion_patch(fact_refs=["fact:product:not-frozen"]),
            "Writer 确认商品事实引用超出冻结事实包",
        ),
        (
            _rerun03_completion_patch(fact_refs=[_RERUN03_FACT_ID, _RERUN03_FACT_ID]),
            "Writer 确认商品事实引用无效",
        ),
        (
            _rerun03_completion_patch(quote_ids=["PS-S01-01"]),
            "Writer 人设原句引用超出冻结授权条目",
        ),
        (
            _rerun03_completion_patch(quote_ids=["PS-S02-05"]),
            "Writer 人设原句缺少冻结授权",
        ),
    ),
)
def test_gated_rerun03_completion_grounding_rejects_invalid_shapes(
    patch: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(DomainError, match=message):
        PostgresContentRepository._validated_completion_snapshot(
            _rerun03_task_snapshot(patch),
            patch,
        )


def test_gated_rerun03_single_use_quote_matches_frozen_authorization() -> None:
    authorization = _rerun03_authorization("PS-S02-05")
    patch = _rerun03_completion_patch(
        quote_ids=[authorization.subject_ref],
        authorization=authorization,
    )

    merged = PostgresContentRepository._validated_completion_snapshot(
        _rerun03_task_snapshot(patch),
        patch,
    )

    assert merged["used_persona_quote_ids"] == [authorization.subject_ref]


@pytest.mark.parametrize("subject_ref", ("PS-S02-05", "PS-S04-03"))
def test_gated_rerun05_repeatable_persona_quote_can_be_committed_again(
    subject_ref: str,
) -> None:
    authorization = _rerun03_authorization(
        subject_ref,
        authorization_version="v2",
        single_use=False,
    )
    patch = _rerun03_completion_patch(
        quote_ids=[authorization.subject_ref],
        authorization=authorization,
    )

    first = PostgresContentRepository._validated_completion_snapshot(
        _rerun03_task_snapshot(patch),
        patch,
    )
    second = PostgresContentRepository._validated_completion_snapshot(
        _rerun03_task_snapshot(patch),
        patch,
    )

    assert first["used_persona_quote_ids"] == [subject_ref]
    assert second["used_persona_quote_ids"] == [subject_ref]
