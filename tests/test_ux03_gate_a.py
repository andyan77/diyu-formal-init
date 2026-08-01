from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.gateway.api.app import create_app
from src.gateway.api.contracts import (
    CreatePlatformCarrierRequest,
    CreatePublishingAccountRequest,
    CreateTenantUserRequest,
)
from src.gateway.api.settings import Settings
from src.infrastructure.production_auth import ProductionAuthRepository
from src.infrastructure.tenant_source_importer import TenantSourceImporter
from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.shared.types import TenantManagementScope

_FRONTEND_ADMIN = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "app" / "TenantAdminApp.tsx"
)
_PROFILE = {
    "identity_position": "以当前品牌的正式内容账号身份出现。",
    "authority_boundary": "只讲已确认品牌立场，不代替门店或顾客陈述经历。",
    "audience_relationship": "与受众保持平等、克制且可持续的交流关系。",
    "content_territories": "长期解释品牌选择、生活观察与穿着关系。",
    "default_production_conditions": "一名创作者、一部手机和普通室内条件。",
}
def _settings(database_url: str) -> Settings:
    return Settings.model_validate(
        {
            "DIYU_RUNTIME_MODE": "production",
            "DIYU_APP_DATABASE_URL": database_url,
            "DIYU_SESSION_SECRET": "ux03-gate-a-local-session-secret",
            "DIYU_PUBLIC_URL": "https://diyu.example",
            "DIYU_GENERATOR_MODE": "deepseek",
            "DEEPSEEK_API_BASE_URL": "https://example.invalid",
            "DEEPSEEK_API_KEY": "local-test-placeholder",
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
            "DIYU_S3_ENDPOINT_URL": "http://127.0.0.1:9000",
            "DIYU_S3_BUCKET": "diyu-test",
            "DIYU_S3_ACCESS_KEY_ID": "local-test-placeholder",
            "DIYU_S3_SECRET_ACCESS_KEY": "local-test-placeholder",
        }
    )


def _activate(client: TestClient, url: str, password: str) -> None:
    response = client.post(
        urlsplit(url).path,
        content=f"password={password}&password_confirm={password}",
        follow_redirects=False,
    )
    assert response.status_code == 303


def _login(client: TestClient, username: str, password: str, path: str) -> None:
    response = client.post(
        path,
        content=f"username={username}&password={password}",
        follow_redirects=False,
    )
    assert response.status_code == 303


def _create_test_operator(
    migrator_database_url: str,
    repository: ProductionAuthRepository,
    username: str,
    password: str,
) -> tuple[UUID, str]:
    """Create one isolated operations identity for the formal API fixture."""

    operator_id = uuid4()
    secret = repository._totp_secret()
    with psycopg.connect(
        migrator_database_url
    ) as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO platform_operators "
            "(id, username, password_hash, totp_secret) "
            "VALUES (%s, %s, %s, %s)",
            (
                operator_id,
                username,
                repository._password_hash(password),
                secret,
            ),
        )
    return operator_id, secret


def _content_persistence_counts(database_url: str, tenant_id: UUID) -> tuple[int, int, int]:
    """Count the append-only content rows owned by one bounded tenant."""

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        counts: list[int] = []
        for table in ("business_tasks", "generation_runs", "content_versions"):
            cursor.execute(
                f"SELECT count(*) FROM {table} WHERE tenant_id = %s",  # noqa: S608 - fixed allowlist
                (tenant_id,),
            )
            row = cursor.fetchone()
            assert row is not None
            counts.append(int(row[0]))
    return counts[0], counts[1], counts[2]


def _delete_gate_a_fixture(
    database_url: str,
    tenant_id: UUID,
    operator_id: UUID,
) -> None:
    """Remove exactly the tenant and operator created by this bounded test."""

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        for table in (
            "brand_product_field_evidence",
            "brand_product_versions",
            "brand_source_segments",
            "brand_source_document_versions",
        ):
            cursor.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")  # noqa: S608
        cursor.execute(
            "DELETE FROM activity_events WHERE tenant_id = %s",
            (tenant_id,),
        )
        cursor.execute(
            "UPDATE content_accounts SET current_expression_profile_id = NULL "
            "WHERE tenant_id = %s",
            (tenant_id,),
        )
        cursor.execute(
            "UPDATE brand_products SET current_version_id = NULL WHERE tenant_id = %s",
            (tenant_id,),
        )
        cursor.execute(
            "UPDATE brand_source_documents SET current_version_id = NULL WHERE tenant_id = %s",
            (tenant_id,),
        )
        for table in (
            "brand_product_field_evidence",
            "brand_product_versions",
            "brand_products",
            "brand_source_segments",
            "brand_source_document_versions",
            "brand_source_documents",
            "account_expression_profile_versions",
            "account_content_roles",
            "auth_grants",
            "tenant_management_grants",
            "display_access_grants",
            "organization_material_maintainers",
            "content_accounts",
            "content_roles",
            "brand_expression_baselines",
            "tenant_sessions",
            "user_activation_tokens",
            "user_credentials",
            "users",
            "brand_audiences",
            "brands",
            "organizations",
        ):
            cursor.execute(
                f"DELETE FROM {table} WHERE tenant_id = %s",  # noqa: S608 - fixed allowlist
                (tenant_id,),
            )
        for table in (
            "brand_product_field_evidence",
            "brand_product_versions",
            "brand_source_segments",
            "brand_source_document_versions",
        ):
            cursor.execute(f"ALTER TABLE {table} ENABLE TRIGGER USER")  # noqa: S608
        cursor.execute(
            "DELETE FROM ops_tenant_registry WHERE tenant_id = %s",
            (tenant_id,),
        )
        cursor.execute("DELETE FROM tenants WHERE id = %s", (tenant_id,))
        cursor.execute(
            "DELETE FROM platform_sessions WHERE operator_id = %s",
            (operator_id,),
        )
        cursor.execute(
            "DELETE FROM ops_audit_events WHERE operator_id = %s",
            (operator_id,),
        )
        cursor.execute(
            "DELETE FROM platform_operators WHERE id = %s",
            (operator_id,),
        )
    _assert_gate_a_fixture_absent(database_url, tenant_id, operator_id)


def _assert_gate_a_fixture_absent(
    database_url: str,
    tenant_id: UUID,
    operator_id: UUID,
) -> None:
    """Prove the bounded synthetic tenant and its operations identity left no residue."""

    tenant_tables = (
        "activity_events",
        "brand_product_field_evidence",
        "brand_product_versions",
        "brand_products",
        "brand_source_segments",
        "brand_source_document_versions",
        "brand_source_documents",
        "account_expression_profile_versions",
        "account_content_roles",
        "auth_grants",
        "tenant_management_grants",
        "display_access_grants",
        "organization_material_maintainers",
        "content_accounts",
        "content_roles",
        "brand_expression_baselines",
        "tenant_sessions",
        "user_activation_tokens",
        "user_credentials",
        "users",
        "brand_audiences",
        "brands",
        "organizations",
    )
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        for table in tenant_tables:
            cursor.execute(
                f"SELECT count(*) FROM {table} WHERE tenant_id = %s",  # noqa: S608 - fixed allowlist
                (tenant_id,),
            )
            assert cursor.fetchone() == (0,), table
        cursor.execute(
            "SELECT count(*) FROM ops_tenant_registry WHERE tenant_id = %s",
            (tenant_id,),
        )
        assert cursor.fetchone() == (0,), "ops_tenant_registry"
        cursor.execute("SELECT count(*) FROM tenants WHERE id = %s", (tenant_id,))
        assert cursor.fetchone() == (0,), "tenants"
        for table in (
            "platform_sessions",
            "ops_audit_events",
            "platform_operators",
        ):
            column = "id" if table == "platform_operators" else "operator_id"
            cursor.execute(
                f"SELECT count(*) FROM {table} WHERE {column} = %s",  # noqa: S608 - fixed allowlist
                (operator_id,),
            )
            assert cursor.fetchone() == (0,), table


def _import_tenant01_sources(
    app_database_url: str,
    migrator_database_url: str,
    tenant: dict[str, object],
) -> TenantManagementScope:
    tenant_id = UUID(str(tenant["tenant_id"]))
    source_root_value = os.environ.get("DIYU_TENANT01_SOURCE_ROOT")
    assert source_root_value, "explicit TENANT-01 browser run requires its private source root"
    source_root = Path(source_root_value)
    assert source_root.is_dir()
    with psycopg.connect(
        migrator_database_url
    ) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT id FROM brands WHERE tenant_id = %s", (tenant_id,))
        brand_row = cursor.fetchone()
        assert brand_row is not None
        brand_id = UUID(str(brand_row[0]))
    import_scope = TenantManagementScope(
        tenant_id,
        UUID(str(tenant["administrator_id"])),
        brand_id,
    )
    tenant_importer = TenantSourceImporter(app_database_url)
    import_result = tenant_importer.apply(
        tenant_importer.dry_run(import_scope, source_root)
    )
    assert import_result["inserted_documents"] == 21
    assert import_result["inserted_products"] == 14
    imported_workbench = PostgresWorkbenchRepository(app_database_url)
    assert len(imported_workbench.brand_library_entries(import_scope)) == 21
    assert len(imported_workbench.management_products(import_scope)) == 14
    return import_scope


def test_publishing_account_and_platform_contracts_are_strict() -> None:
    account = CreatePublishingAccountRequest.model_validate(
        {
            "name": "总部品牌账号",
            "channel": "抖音",
            "content_role_name": "品牌官方",
            "operator_id": str(uuid4()),
        }
    )
    assert account.channel == "抖音"
    with pytest.raises(ValidationError):
        CreatePublishingAccountRequest.model_validate(
            {
                "name": "总部品牌账号",
                "channel": "抖音",
                "content_role_name": "品牌官方",
                "operator_id": str(uuid4()),
                "target": "douyin_video",
            }
        )

    source_id = uuid4()
    operator_id = uuid4()
    for channel in ("抖音", "小红书", "微信视频号"):
        carrier = CreatePlatformCarrierRequest.model_validate(
            {
                "source_account_id": str(source_id),
                "name": f"总部品牌账号 · {channel}",
                "channel": channel,
                "operator_id": str(operator_id),
                "confirm_internal_carrier": True,
            }
        )
        assert carrier.channel == channel
    for invalid in (
        {"channel": "微信号"},
        {"channel": "微信视频号", "target": "wechat_channels_video"},
    ):
        with pytest.raises(ValidationError):
            CreatePlatformCarrierRequest.model_validate(
                {
                    "source_account_id": str(source_id),
                    "name": "错误载体",
                    "operator_id": str(operator_id),
                    "confirm_internal_carrier": True,
                    **invalid,
                }
            )

    frontend = _FRONTEND_ADMIN.read_text(encoding="utf-8")
    assert '.replace(/图文|视频/g, "")' not in frontend
    assert "publishingChannelForTarget(createForm.target)" in frontend
    assert "publishingChannelForTarget(targetForm.target)" in frontend

    legacy_user = CreateTenantUserRequest.model_validate(
        {
            "display_name": "兼容用户",
            "username": "legacy-user",
            "grants_expression_profile_maintenance": True,
        }
    )
    assert "expression_profile_maintenance_account_ids" not in legacy_user.model_fields_set
    explicit_user = CreateTenantUserRequest.model_validate(
        {
            "display_name": "新合同用户",
            "username": "explicit-user",
            "expression_profile_maintenance_account_ids": [],
        }
    )
    assert "expression_profile_maintenance_account_ids" in explicit_user.model_fields_set


def test_zero_tenant_users_can_prepare_one_identity_with_four_targets(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    repository = ProductionAuthRepository(app_database_url)
    suffix = uuid4().hex[:10]
    ops_username = f"tenant01-zero-users-ops-{suffix}"
    ops_password = "tenant01-zero-users-ops-password"
    operator_id, secret = _create_test_operator(
        migrator_database_url,
        repository,
        ops_username,
        ops_password,
    )
    app = create_app(_settings(app_database_url))
    tenant_id: UUID | None = None
    try:
        with TestClient(app, base_url="https://diyu.example") as ops:
            login = ops.post(
                "/ops/login",
                content=(
                    f"username={ops_username}&password={ops_password}"
                    f"&totp_code={repository._totp_code(secret, int(time.time() // 30))}"
                ),
                follow_redirects=False,
            )
            assert login.status_code == 303
            created = ops.post(
                "/api/v1/ops/tenants",
                json={
                    "tenant_name": f"TENANT-01 零用户租户 {suffix}",
                    "administrator_name": "首位管理员",
                    "administrator_username": f"tenant01-admin-{suffix}",
                },
            )
            assert created.status_code == 201
            tenant = created.json()
            tenant_id = UUID(tenant["tenant_id"])

        with TestClient(app, base_url="https://diyu.example") as admin:
            admin_password = "tenant01-zero-users-admin-password"
            _activate(admin, tenant["activation_url"], admin_password)
            _login(admin, tenant["username"], admin_password, "/tenant-admin/login")
            baseline = admin.get("/api/v1/admin/brand-expression").json()
            confirmed = admin.post(
                "/api/v1/admin/brand-expression/confirm",
                json={"draft": f"{baseline['draft']}\n由品牌管理员确认。"},
            )
            assert confirmed.status_code == 200
            company = admin.get("/api/v1/tenant-management/organizations").json()[0]
            account = admin.post(
                "/api/v1/tenant-management/publishing-accounts",
                json={
                    "name": "正式官方逻辑发布账号",
                    "channel": "抖音",
                    "content_role_name": "品牌官方表达身份",
                    "speaker_kind": "institutional_account",
                    "control_organization_id": company["id"],
                    "operator_can_maintain_expression_profile": False,
                    "initial_profile": _PROFILE,
                },
            )
            assert account.status_code == 201
            account_id = account.json()["id"]
            for channel in ("小红书", "微信视频号"):
                target = admin.post(
                    "/api/v1/tenant-management/platform-carriers",
                    json={
                        "source_account_id": account_id,
                        "name": f"正式官方逻辑发布账号 · {channel}",
                        "channel": channel,
                        "confirm_internal_carrier": True,
                    },
                )
                assert target.status_code == 201
                assert target.json()["operator_id"] is None
            listed = admin.get(
                "/api/v1/tenant-management/publishing-accounts"
            ).json()
            assert len(listed) == 1
            assert {
                target["target"] for target in listed[0]["platform_targets"]
            } == {
                "douyin_video",
                "xiaohongshu_graphic",
                "xiaohongshu_video",
                "wechat_channels_video",
            }
            user_count_before = admin.get(
                "/api/v1/tenant-management/users"
            ).json()
            unavailable_store = admin.post(
                "/api/v1/tenant-management/users",
                json={
                    "display_name": "无正式门店的陈列用户",
                    "username": f"tenant01-display-{suffix}",
                    "organization_id": company["id"],
                    "entry_type": "tenant_user",
                    "capabilities": ["display"],
                    "publishing_identity_ids": [],
                    "expression_profile_maintenance_account_ids": [],
                    "display_store_ids": [str(uuid4())],
                },
            )
            assert unavailable_store.status_code == 422
            assert "门店" in unavailable_store.json()["detail"]
            assert admin.get("/api/v1/tenant-management/users").json() == user_count_before

        assert tenant_id is not None
        with psycopg.connect(
            migrator_database_url
        ) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM users WHERE tenant_id = %s AND entry_kind = 'tenant_user'",
                (tenant_id,),
            )
            assert cursor.fetchone() == (0,)
            cursor.execute(
                "SELECT count(*) FROM auth_grants WHERE tenant_id = %s",
                (tenant_id,),
            )
            assert cursor.fetchone() == (0,)
            cursor.execute(
                "SELECT count(*) FILTER (WHERE carrier_of_account_id IS NULL), "
                "count(*) FILTER (WHERE enabled AND platform_enabled), "
                "count(DISTINCT current_expression_profile_id) "
                "FROM content_accounts WHERE tenant_id = %s",
                (tenant_id,),
            )
            assert cursor.fetchone() == (1, 3, 1)
    finally:
        if tenant_id is not None:
            _delete_gate_a_fixture(migrator_database_url, tenant_id, operator_id)


def test_new_tenant_identity_account_and_platform_journey(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    repository = ProductionAuthRepository(app_database_url)
    suffix = uuid4().hex[:10]
    ops_username = f"ux03-ops-{suffix}"
    ops_password = "ux03-ops-password-is-long"
    operator_id, secret = _create_test_operator(
        migrator_database_url,
        repository,
        ops_username,
        ops_password,
    )
    app = create_app(_settings(app_database_url))
    tenant_id: UUID | None = None
    try:
        with TestClient(app, base_url="https://diyu.example") as ops:
            response = ops.post(
                "/ops/login",
                content=(
                    f"username={ops_username}&password={ops_password}"
                    f"&totp_code={repository._totp_code(secret, int(time.time() // 30))}"
                ),
                follow_redirects=False,
            )
            assert response.status_code == 303
            created = ops.post(
                "/api/v1/ops/tenants",
                json={
                    "tenant_name": f"UX03 全新租户 {suffix}",
                    "administrator_name": "首位租户管理员",
                    "administrator_username": f"ux03-admin-{suffix}",
                },
            )
            assert created.status_code == 201
            tenant = created.json()
            tenant_id = UUID(tenant["tenant_id"])
            assert tenant["activation_url"].startswith(
                "https://diyu.example/activate/"
            )

        admin_password = "ux03-admin-password-is-long"
        with TestClient(app, base_url="https://diyu.example") as admin:
            _activate(admin, tenant["activation_url"], admin_password)
            _login(
                admin,
                tenant["username"],
                admin_password,
                "/tenant-admin/login",
            )
            assert admin.get("/tenant-admin").status_code == 200
            assert admin.get("/content").status_code == 403

            baseline = admin.get("/api/v1/admin/brand-expression").json()
            onboarding = admin.get(
                "/api/v1/tenant-management/onboarding-prefill"
            ).json()
            assert baseline["status"] == "draft"
            assert set(onboarding["account_profile_candidate"]) == set(_PROFILE)
            assert "保存前必须由管理员纠正" in onboarding[
                "account_profile_candidate_source"
            ]

            company = admin.get(
                "/api/v1/tenant-management/organizations"
            ).json()[0]
            store = admin.post(
                "/api/v1/tenant-management/organizations",
                json={
                    "name": f"UX03 门店 {suffix}",
                    "organization_level": "operating_unit",
                },
            )
            assert store.status_code == 201
            store = store.json()

            hq_username = f"ux03-hq-{suffix}"
            store_username = f"ux03-store-{suffix}"
            hq_member = admin.post(
                "/api/v1/tenant-management/users",
                json={
                    "display_name": "总部内容用户",
                    "username": hq_username,
                    "organization_id": company["id"],
                    "entry_type": "tenant_user",
                    "capabilities": [],
                    "publishing_identity_ids": [],
                    "expression_profile_maintenance_account_ids": [],
                },
            ).json()
            store_member = admin.post(
                "/api/v1/tenant-management/users",
                json={
                    "display_name": "门店内容用户",
                    "username": store_username,
                    "organization_id": store["id"],
                    "entry_type": "tenant_user",
                    "capabilities": [],
                    "publishing_identity_ids": [],
                    "expression_profile_maintenance_account_ids": [],
                },
            ).json()

            hq_account_payload = {
                "name": "总部逻辑发布账号",
                "channel": "抖音",
                "content_role_name": "总部品牌表达身份",
                "speaker_kind": "institutional_account",
                "operator_id": hq_member["user_id"],
                "control_organization_id": company["id"],
                "operator_can_maintain_expression_profile": False,
                "initial_profile": _PROFILE,
            }
            refused = admin.post(
                "/api/v1/tenant-management/publishing-accounts",
                json=hq_account_payload,
            )
            assert refused.status_code == 422
            assert "确认当前品牌表达草案" in refused.json()["detail"]

            revised_baseline = (
                str(baseline["draft"])
                + "\n本次确认：账号表达应区分总部与门店的现实来源。"
            )
            confirmed = admin.post(
                "/api/v1/admin/brand-expression/confirm",
                json={"draft": revised_baseline},
            )
            assert confirmed.status_code == 200
            assert admin.get("/api/v1/admin/brand-expression").json()[
                "status"
            ] == "confirmed"

            mismatched_maintenance_payload = {
                "name": "跨组织维护权反证账号",
                "channel": "小红书",
                "content_role_name": "跨组织维护权反证身份",
                "speaker_kind": "institutional_account",
                "operator_id": store_member["user_id"],
                "control_organization_id": company["id"],
                "operator_can_maintain_expression_profile": True,
                "initial_profile": _PROFILE,
            }
            mismatched_maintenance = admin.post(
                "/api/v1/tenant-management/publishing-accounts",
                json=mismatched_maintenance_payload,
            )
            assert mismatched_maintenance.status_code == 422
            assert "负责团队" in mismatched_maintenance.json()["detail"]
            without_control = admin.post(
                "/api/v1/tenant-management/publishing-accounts",
                json={
                    **mismatched_maintenance_payload,
                    "name": "没有控制组织的维护权反证账号",
                    "content_role_name": "没有控制组织的维护权反证身份",
                    "control_organization_id": None,
                },
            )
            assert without_control.status_code == 422
            nonexistent_operator = admin.post(
                "/api/v1/tenant-management/publishing-accounts",
                json={
                    **mismatched_maintenance_payload,
                    "name": "不存在使用者反证账号",
                    "content_role_name": "不存在使用者反证身份",
                    "operator_id": str(uuid4()),
                    "operator_can_maintain_expression_profile": False,
                },
            )
            assert nonexistent_operator.status_code == 422
            with psycopg.connect(
                migrator_database_url
            ) as connection, connection.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*) FROM content_accounts "
                    "WHERE tenant_id = %s AND name IN (%s, %s, %s)",
                    (
                        tenant_id,
                        "跨组织维护权反证账号",
                        "没有控制组织的维护权反证账号",
                        "不存在使用者反证账号",
                    ),
                )
                assert cursor.fetchone() == (0,)
                cursor.execute(
                    "SELECT count(*) FROM auth_grants grant_record "
                    "JOIN content_accounts account "
                    "ON account.tenant_id = grant_record.tenant_id "
                    "AND account.id = grant_record.account_id "
                    "WHERE grant_record.tenant_id = %s "
                    "AND account.name = %s",
                    (tenant_id, "跨组织维护权反证账号"),
                )
                assert cursor.fetchone() == (0,)

            hq_account_response = admin.post(
                "/api/v1/tenant-management/publishing-accounts",
                json=hq_account_payload,
            )
            assert hq_account_response.status_code == 201
            hq_account_id = hq_account_response.json()["id"]
            store_profile = {
                **_PROFILE,
                "identity_position": "以当前门店的正式内容账号身份出现。",
                "authority_boundary": "只讲门店已确认边界，不代替总部或顾客陈述经历。",
            }
            store_account_response = admin.post(
                "/api/v1/tenant-management/publishing-accounts",
                json={
                    "name": "门店逻辑发布账号",
                    "channel": "小红书",
                    "content_role_name": "门店内容表达身份",
                    "speaker_kind": "institutional_account",
                    "operator_id": store_member["user_id"],
                    "control_organization_id": store["id"],
                    "operator_can_maintain_expression_profile": True,
                    "initial_profile": store_profile,
                },
            )
            assert store_account_response.status_code == 201
            store_account_id = store_account_response.json()["id"]

            hq_carrier_ids: list[str] = []
            for channel in ("小红书", "微信视频号"):
                carrier = admin.post(
                    "/api/v1/tenant-management/platform-carriers",
                    json={
                        "source_account_id": hq_account_id,
                        "name": f"总部逻辑发布账号 · {channel}",
                        "channel": channel,
                        "operator_id": hq_member["user_id"],
                        "confirm_internal_carrier": True,
                    },
                )
                assert carrier.status_code == 201
                assert carrier.json()["carrier_of_account_id"] == hq_account_id
                hq_carrier_ids.append(carrier.json()["id"])

            hq_grants = admin.patch(
                f"/api/v1/tenant-management/users/{hq_member['user_id']}/grants",
                json={
                    "entry_type": "tenant_user",
                    "capabilities": ["content"],
                    "publishing_identity_ids": [hq_account_id],
                    "expression_profile_maintenance_account_ids": [],
                },
            )
            assert hq_grants.status_code == 200
            store_grants = admin.patch(
                f"/api/v1/tenant-management/users/{store_member['user_id']}/grants",
                json={
                    "entry_type": "tenant_user",
                    "capabilities": ["content"],
                    "publishing_identity_ids": [store_account_id],
                },
            )
            assert store_grants.status_code == 200

            accounts = {
                item["id"]: item
                for item in admin.get(
                    "/api/v1/tenant-management/publishing-accounts?include_archived=true"
                ).json()
            }
            assert accounts[hq_account_id]["profile"]["version"] == 1
            assert accounts[store_account_id]["profile"]["version"] == 1
            assert accounts[hq_account_id]["control_organization"]["id"] == company[
                "id"
            ]
            assert accounts[store_account_id]["control_organization"]["id"] == store[
                "id"
            ]
            hq_targets = {
                target["target"]
                for target in accounts[hq_account_id]["platform_targets"]
                if target["enabled"]
            }
            assert hq_targets == {
                "douyin_video",
                "xiaohongshu_graphic",
                "xiaohongshu_video",
                "wechat_channels_video",
            }
            store_targets = {
                target["target"]
                for target in accounts[store_account_id]["platform_targets"]
                if target["enabled"]
            }
            assert store_targets == {
                "xiaohongshu_graphic",
                "xiaohongshu_video",
            }

            operators = {
                item["id"]: item
                for item in admin.get(
                    "/api/v1/tenant-management/operators?include_archived=true"
                ).json()
            }
            hq_grant = operators[hq_member["user_id"]]["account_grants"][0]
            store_grant = operators[store_member["user_id"]]["account_grants"][0]
            assert hq_grant["can_maintain_expression_profile"] is False
            assert store_grant["can_maintain_expression_profile"] is True
            assert operators[hq_member["user_id"]]["manages_tenant"] is False

            cross_tenant = admin.put(
                f"/api/v1/tenant-management/users/{hq_member['user_id']}/"
                f"publishing-accounts/{uuid4()}/profile-maintenance",
                json={"enabled": True},
            )
            assert cross_tenant.status_code == 422

            renamed = admin.patch(
                f"/api/v1/tenant-management/publishing-accounts/{hq_account_id}",
                json={
                    "name": "总部品牌逻辑发布账号",
                    "control_organization_id": company["id"],
                },
            )
            assert renamed.status_code == 200
            account_disabled = admin.put(
                f"/api/v1/tenant-management/publishing-accounts/"
                f"{hq_account_id}/enabled",
                json={"enabled": False},
            )
            assert account_disabled.status_code == 200
            disabled_history = admin.get(
                f"/api/v1/tenant-management/publishing-accounts/"
                f"{hq_account_id}/expression-profile/versions"
            )
            assert disabled_history.status_code == 200
            assert disabled_history.json()[0]["version"] == 1
            edited_with_disabled_grant = admin.patch(
                f"/api/v1/tenant-management/users/{hq_member['user_id']}",
                json={
                    "display_name": "总部内容负责人",
                    "organization_id": company["id"],
                },
            )
            assert edited_with_disabled_grant.status_code == 200
            preserved_disabled_grant = admin.patch(
                f"/api/v1/tenant-management/users/{hq_member['user_id']}/grants",
                json={
                    "entry_type": "tenant_user",
                    "capabilities": ["content"],
                    "publishing_identity_ids": [hq_account_id],
                    "expression_profile_maintenance_account_ids": [],
                },
            )
            assert preserved_disabled_grant.status_code == 200
            hq_operator = next(
                item
                for item in admin.get(
                    "/api/v1/tenant-management/operators?include_archived=true"
                ).json()
                if item["id"] == hq_member["user_id"]
            )
            assert hq_operator["display_name"] == "总部内容负责人"
            assert hq_operator["account_grants"] == [
                {
                    "account_id": hq_account_id,
                    "account_name": "总部品牌逻辑发布账号",
                    "account_enabled": False,
                    "can_maintain_expression_profile": False,
                }
            ]
            removed_disabled_grant = admin.patch(
                f"/api/v1/tenant-management/users/{hq_member['user_id']}/grants",
                json={
                    "entry_type": "tenant_user",
                    "capabilities": [],
                    "publishing_identity_ids": [],
                    "expression_profile_maintenance_account_ids": [],
                },
            )
            assert removed_disabled_grant.status_code == 200
            illegal_disabled_add = admin.patch(
                f"/api/v1/tenant-management/users/{hq_member['user_id']}/grants",
                json={
                    "entry_type": "tenant_user",
                    "capabilities": ["content"],
                    "publishing_identity_ids": [hq_account_id],
                    "expression_profile_maintenance_account_ids": [],
                },
            )
            assert illegal_disabled_add.status_code == 422
            account_restored = admin.put(
                f"/api/v1/tenant-management/publishing-accounts/"
                f"{hq_account_id}/enabled",
                json={"enabled": True},
            )
            assert account_restored.status_code == 200
            reassigned_after_restore = admin.patch(
                f"/api/v1/tenant-management/users/{hq_member['user_id']}/grants",
                json={
                    "entry_type": "tenant_user",
                    "capabilities": ["content"],
                    "publishing_identity_ids": [hq_account_id],
                    "expression_profile_maintenance_account_ids": [],
                },
            )
            assert reassigned_after_restore.status_code == 200

            moved_member = admin.patch(
                f"/api/v1/tenant-management/users/{store_member['user_id']}",
                json={
                    "display_name": "门店内容负责人",
                    "organization_id": company["id"],
                },
            )
            assert moved_member.status_code == 200
            moved_operator = next(
                item
                for item in admin.get(
                    "/api/v1/tenant-management/operators?include_archived=true"
                ).json()
                if item["id"] == store_member["user_id"]
            )
            assert moved_operator["organization_id"] == company["id"]
            assert moved_operator["account_grants"][0][
                "can_maintain_expression_profile"
            ] is False
            moved_back = admin.patch(
                f"/api/v1/tenant-management/users/{store_member['user_id']}",
                json={
                    "display_name": "门店内容负责人",
                    "organization_id": store["id"],
                },
            )
            assert moved_back.status_code == 200
            maintenance_restored = admin.put(
                f"/api/v1/tenant-management/users/{store_member['user_id']}/"
                f"publishing-accounts/{store_account_id}/profile-maintenance",
                json={"enabled": True},
            )
            assert maintenance_restored.status_code == 200

            hq_password = "ux03-hq-password-is-long"
            store_password = "ux03-store-password-is-long"
            _activate(admin, hq_member["activation_url"], hq_password)
            _activate(admin, store_member["activation_url"], store_password)

        with TestClient(app, base_url="https://diyu.example") as hq_user:
            _login(hq_user, hq_username, hq_password, "/login")
            assert hq_user.get("/user").status_code == 200
            assert hq_user.get("/tenant-admin").status_code == 403
            portal = hq_user.get("/api/v1/session/context").json()
            assert portal["identity"]["operator"] == "总部内容负责人"
            assert portal["identity"]["organization"] == company["name"]
            identities = hq_user.get(
                "/api/v1/content/publishing-identities"
            ).json()
            assert len(identities) == 1
            identity = identities[0]
            assert identity["id"] == hq_account_id
            assert identity["control_organization"] == company["name"]
            assert identity["profile_version"] == 1
            assert identity["can_maintain_profile"] is False
            profile_ids = set()
            for target in (
                "douyin_video",
                "xiaohongshu_graphic",
                "xiaohongshu_video",
                "wechat_channels_video",
            ):
                profile = hq_user.get(
                    "/api/v1/content/account-expression-profile",
                    params={
                        "publishing_identity_id": hq_account_id,
                        "target": target,
                    },
                )
                assert profile.status_code == 200
                profile_ids.add(profile.json()["current"]["profile_id"])
            assert len(profile_ids) == 1

            denied_profile_update = hq_user.post(
                "/api/v1/content/account-expression-profile/versions",
                params={"publishing_identity_id": hq_account_id},
                json={**_PROFILE, "content_territories": "未经授权的画像更新。"},
            )
            assert denied_profile_update.status_code == 422

        with TestClient(app, base_url="https://diyu.example") as store_user:
            _login(store_user, store_username, store_password, "/login")
            store_identity = store_user.get(
                "/api/v1/content/publishing-identities"
            ).json()[0]
            assert store_identity["id"] == store_account_id
            assert store_identity["control_organization"] == store["name"]
            assert store_identity["can_maintain_profile"] is True
            updated_profile = store_user.post(
                "/api/v1/content/account-expression-profile/versions",
                params={"publishing_identity_id": store_account_id},
                json={
                    **store_profile,
                    "content_territories": "门店日常、在地回应和已确认商品取舍。",
                },
            )
            assert updated_profile.status_code == 201
            assert updated_profile.json()["version"] == 2
            v2_profiles = []
            for target in ("xiaohongshu_graphic", "xiaohongshu_video"):
                current_profile = store_user.get(
                    "/api/v1/content/account-expression-profile",
                    params={
                        "publishing_identity_id": store_account_id,
                        "target": target,
                    },
                )
                assert current_profile.status_code == 200
                assert current_profile.json()["can_maintain"] is True
                assert current_profile.json()["current"]["version"] == 2
                v2_profiles.append(
                    current_profile.json()["current"]["profile_id"]
                )
            assert len(set(v2_profiles)) == 1
            wrong_account = store_user.post(
                "/api/v1/content/account-expression-profile/versions",
                params={"publishing_identity_id": hq_account_id},
                json={
                    **store_profile,
                    "content_territories": "不应写入错误账号。",
                },
            )
            assert wrong_account.status_code == 422
            carrier_as_identity = store_user.get(
                "/api/v1/content/account-expression-profile",
                params={"publishing_identity_id": hq_carrier_ids[0]},
            )
            assert carrier_as_identity.status_code == 422

        with TestClient(app, base_url="https://diyu.example") as admin:
            _login(
                admin,
                tenant["username"],
                admin_password,
                "/tenant-admin/login",
            )
            versions = admin.get(
                f"/api/v1/tenant-management/publishing-accounts/"
                f"{store_account_id}/expression-profile/versions"
            )
            assert [item["version"] for item in versions.json()] == [2, 1]

            cross_organization_usage = admin.post(
                "/api/v1/tenant-management/publishing-accounts",
                json={
                    "name": "跨组织仅使用账号",
                    "channel": "抖音",
                    "content_role_name": "跨组织仅使用身份",
                    "speaker_kind": "institutional_account",
                    "operator_id": store_member["user_id"],
                    "control_organization_id": company["id"],
                    "operator_can_maintain_expression_profile": False,
                    "initial_profile": _PROFILE,
                },
            )
            assert cross_organization_usage.status_code == 201

            accounts = {
                item["id"]: item
                for item in admin.get(
                    "/api/v1/tenant-management/publishing-accounts?include_archived=true"
                ).json()
            }
            wechat = next(
                target
                for target in accounts[hq_account_id]["platform_targets"]
                if target["target"] == "wechat_channels_video"
            )
            disabled = admin.put(
                f"/api/v1/tenant-management/platform-carriers/"
                f"{wechat['account_id']}/enabled",
                json={"enabled": False},
            )
            assert disabled.status_code == 200
            with psycopg.connect(
                migrator_database_url
            ) as connection, connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, enabled, platform_enabled FROM content_accounts "
                    "WHERE tenant_id = %s AND id = %s",
                    (tenant_id, wechat["account_id"]),
                )
                assert cursor.fetchone() == (
                    UUID(wechat["account_id"]),
                    False,
                    False,
                )
            restored_carrier = admin.post(
                "/api/v1/tenant-management/platform-carriers",
                json={
                    "source_account_id": hq_account_id,
                    "name": "总部逻辑发布账号 · 微信视频号",
                    "channel": "微信视频号",
                    "operator_id": hq_member["user_id"],
                    "confirm_internal_carrier": True,
                },
            )
            assert restored_carrier.status_code == 201
            assert restored_carrier.json()["id"] == wechat["account_id"]

            disabled_member = admin.post(
                f"/api/v1/tenant-management/users/{hq_member['user_id']}/disable"
            )
            assert disabled_member.status_code == 200
            restored_member = admin.post(
                f"/api/v1/tenant-management/users/{hq_member['user_id']}/restore"
            )
            assert restored_member.status_code == 200
            restored_password = "ux03-hq-restored-password-is-long"
            _activate(
                admin,
                restored_member.json()["activation_url"],
                restored_password,
            )
            reassigned = admin.patch(
                f"/api/v1/tenant-management/users/{hq_member['user_id']}/grants",
                json={
                    "entry_type": "tenant_user",
                    "capabilities": ["content"],
                    "publishing_identity_ids": [hq_account_id],
                    "expression_profile_maintenance_account_ids": [],
                },
            )
            assert reassigned.status_code == 200

        with TestClient(app, base_url="https://diyu.example") as restored_user:
            old_login = restored_user.post(
                "/login",
                content=f"username={hq_username}&password={hq_password}",
                follow_redirects=False,
            )
            assert old_login.status_code == 401
            _login(restored_user, hq_username, restored_password, "/login")
            assert restored_user.get("/user").status_code == 200
    finally:
        if tenant_id is not None:
            _delete_gate_a_fixture(
                migrator_database_url,
                tenant_id,
                operator_id,
            )


def test_formal_react_new_tenant_gate_a_journey(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    """Run the bounded real-browser gate only when explicitly requested."""

    if os.environ.get("DIYU_RUN_UX03_BROWSER") != "1":
        pytest.skip("set DIYU_RUN_UX03_BROWSER=1 for the formal Chrome journey")
    frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    assert (frontend_dist / "index.html").is_file()

    repository = ProductionAuthRepository(app_database_url)
    suffix = uuid4().hex[:8]
    ops_username = f"ux03-browser-ops-{suffix}"
    ops_password = f"UX03-browser-ops-{suffix}-password"
    operator_id, secret = _create_test_operator(
        migrator_database_url,
        repository,
        ops_username,
        ops_password,
    )
    app = create_app(_settings(app_database_url))
    tenant_id: UUID | None = None
    server: subprocess.Popen[bytes] | None = None
    try:
        with TestClient(app, base_url="https://diyu.example") as ops:
            login = ops.post(
                "/ops/login",
                content=(
                    f"username={ops_username}&password={ops_password}"
                    f"&totp_code={repository._totp_code(secret, int(time.time() // 30))}"
                ),
                follow_redirects=False,
            )
            assert login.status_code == 303
            created = ops.post(
                "/api/v1/ops/tenants",
                json={
                    "tenant_name": f"UX03 浏览器新租户 {suffix}",
                    "administrator_name": "浏览器首位管理员",
                    "administrator_username": f"ux03-browser-admin-{suffix}",
                },
            )
            assert created.status_code == 201
            tenant = created.json()
            tenant_id = UUID(tenant["tenant_id"])

        _import_tenant01_sources(app_database_url, migrator_database_url, tenant)

        with socket.socket() as port_socket:
            port_socket.bind(("127.0.0.1", 0))
            port = int(port_socket.getsockname()[1])
        base_url = f"http://127.0.0.1:{port}"
        server_environment = {
            **os.environ,
            "DIYU_RUNTIME_MODE": "production",
            "DIYU_APP_DATABASE_URL": app_database_url,
            "DIYU_SESSION_SECRET": f"ux03-browser-session-{suffix}",
            "DIYU_PUBLIC_URL": "https://diyu.example",
            "DIYU_GENERATOR_MODE": "deepseek",
            "DEEPSEEK_API_BASE_URL": "https://example.invalid",
            "DEEPSEEK_API_KEY": "local-browser-placeholder",
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
            "DIYU_S3_ENDPOINT_URL": "http://127.0.0.1:9000",
            "DIYU_S3_BUCKET": "diyu-test",
            "DIYU_S3_ACCESS_KEY_ID": "local-browser-placeholder",
            "DIYU_S3_SECRET_ACCESS_KEY": "local-browser-placeholder",
        }
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "src.gateway.api.app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=server_environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            if server.poll() is not None:
                pytest.fail("formal browser API server exited before readiness")
            try:
                with urlopen(f"{base_url}/status", timeout=0.2) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("formal browser API server did not become ready")

        browser = subprocess.run(
            ["node", "frontend/test/ux03-gate-a-browser.mjs"],
            cwd=Path(__file__).resolve().parents[1],
            env={
                **os.environ,
                "UX03_BASE_URL": base_url,
                "UX03_PUBLIC_URL": "https://diyu.example",
                "UX03_ADMIN_ACTIVATION_PATH": urlsplit(
                    tenant["activation_url"]
                ).path,
                "UX03_ADMIN_USERNAME": tenant["username"],
                "UX03_ADMIN_PASSWORD": f"UX03-browser-admin-{suffix}-password",
                "UX03_SUFFIX": suffix,
            },
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert browser.returncode == 0, (
            f"formal Chrome journey failed:\n{browser.stdout}\n{browser.stderr}"
        )
        assert '"failures": []' in browser.stdout

        with psycopg.connect(
            migrator_database_url
        ) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM content_accounts "
                "WHERE tenant_id = %s AND carrier_of_account_id IS NULL "
                "AND name = %s",
                (tenant_id, f"总部逻辑发布账号 {suffix}"),
            )
            account_row = cursor.fetchone()
            assert account_row is not None
            headquarters_account_id = UUID(str(account_row[0]))

        before_visual_preflight = _content_persistence_counts(
            migrator_database_url,
            tenant_id,
        )
        with TestClient(app, base_url="https://diyu.example") as creator:
            _login(
                creator,
                f"ux03-browser-hq-{suffix}",
                f"UX03-browser-HQ-{suffix}-password",
                "/login",
            )
            visual = creator.post(
                "/api/v1/content/stream",
                json={
                    "message": "请用两件商品做一条商品视觉关系图文。",
                    "conversation": [],
                    "publishing_identity_id": str(headquarters_account_id),
                    "target": "xiaohongshu_graphic",
                    "material_ids": [],
                    "product_media_intent": True,
                    "interaction_mode": "generate",
                    "direct_generate": True,
                    "request_id": str(uuid4()),
                },
            )
            assert visual.status_code == 200
            events = [
                json.loads(line)
                for line in visual.text.splitlines()
                if line.strip()
            ]
            assert any(
                event["event"] == "conversation"
                and event["kind"] == "question"
                and "选择两件不同商品" in event["message"]
                and "已登记图片" in event["message"]
                for event in events
            )
            assert not any(event["event"] == "completed" for event in events)
        assert _content_persistence_counts(
            migrator_database_url,
            tenant_id,
        ) == before_visual_preflight

        with psycopg.connect(
            migrator_database_url
        ) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM users WHERE tenant_id = %s",
                (tenant_id,),
            )
            assert cursor.fetchone() == (3,)
            cursor.execute(
                "SELECT count(*) FROM content_accounts WHERE tenant_id = %s "
                "AND carrier_of_account_id IS NULL",
                (tenant_id,),
            )
            assert cursor.fetchone() == (2,)
            cursor.execute(
                "SELECT count(*) FROM content_accounts WHERE tenant_id = %s "
                "AND enabled AND platform_enabled",
                (tenant_id,),
            )
            assert cursor.fetchone() == (4,)
            cursor.execute(
                "SELECT array_agg(DISTINCT can_maintain_expression_profile "
                "ORDER BY can_maintain_expression_profile) "
                "FROM auth_grants WHERE tenant_id = %s AND enabled",
                (tenant_id,),
            )
            assert cursor.fetchone() == ([False, True],)
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        if tenant_id is not None:
            _delete_gate_a_fixture(
                migrator_database_url,
                tenant_id,
                operator_id,
            )
