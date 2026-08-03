from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from importlib import import_module
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from pytest import MonkeyPatch

from src.brain.content_control_service import ContentControlService
from src.brain.content_service import ContentService
from src.brain.workbench_service import WorkbenchService
from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.content_control_repository import (
    PostgresContentControlRepository,
)
from src.infrastructure.local_object_store import LocalObjectStore
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.production_auth import ProductionAuthRepository
from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.shared.errors import DomainError, GenerationFailed
from src.shared.types import (
    GeneratedArtifact,
    GenerationInput,
    RequestedControls,
    TenantManagementScope,
    TrustedScope,
)
from src.tool.llm_gateway.stub import DeterministicContentGenerator

_PROFILE = {
    "identity_position": "品牌官方生活方式账号",
    "authority_boundary": "只表达已确认品牌事实与一般生活观察",
    "audience_relationship": "帮助关注日常穿着的人做清楚选择",
    "content_territories": "门店生活、穿着选择与品牌日常",
    "default_production_conditions": "手机实拍、门店环境、纯文字辅助",
}


class _FailingContentGenerator(DeterministicContentGenerator):
    """Fail after the service has durably created the task and running run."""

    @property
    def model_name(self) -> str:
        return "ux03-gate-b-deterministic-failure"

    def generate(self, request: GenerationInput) -> GeneratedArtifact:
        del request
        raise GenerationFailed("Gate B 受控生成失败")


def _content_persistence_counts(
    database_url: str,
    tenant_id: UUID,
) -> tuple[int, int, int, int, int]:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              (SELECT count(*) FROM business_tasks WHERE tenant_id = %s),
              (SELECT count(*) FROM generation_runs WHERE tenant_id = %s),
              (SELECT count(*) FROM content_versions WHERE tenant_id = %s),
              (SELECT count(*) FROM generation_runs
               WHERE tenant_id = %s AND status = 'failed'),
              (SELECT count(*) FROM generation_runs
               WHERE tenant_id = %s AND status = 'running')
            """,
            (tenant_id, tenant_id, tenant_id, tenant_id, tenant_id),
        )
        row = cursor.fetchone()
    assert row is not None
    tasks, runs, versions, failed_runs, running_runs = row
    return (
        int(tasks),
        int(runs),
        int(versions),
        int(failed_runs),
        int(running_runs),
    )


def _move_version_submission_outside_usage_window(
    database_url: str,
    tenant_id: UUID,
    version_id: UUID,
) -> None:
    """Move one synthetic V1 timestamp while always restoring append-only protection."""

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        trigger_disabled = False
        try:
            cursor.execute("ALTER TABLE content_versions DISABLE TRIGGER content_versions_append_only")
            trigger_disabled = True
            with connection.transaction():
                cursor.execute(
                    """
                    UPDATE content_versions
                    SET created_at = now() - interval '40 days'
                    WHERE tenant_id = %s AND id = %s AND version_number = 1
                    """,
                    (tenant_id, version_id),
                )
                assert cursor.rowcount == 1
        finally:
            if trigger_disabled:
                cursor.execute("ALTER TABLE content_versions ENABLE TRIGGER content_versions_append_only")
        cursor.execute(
            """
            SELECT trigger_record.tgenabled
            FROM pg_trigger trigger_record
            WHERE trigger_record.tgrelid = 'content_versions'::regclass
              AND trigger_record.tgname = 'content_versions_append_only'
            """
        )
        assert cursor.fetchone() == ("O",)


def _settings(database_url: str, material_root: Path) -> Settings:
    return Settings.model_validate(
        {
            "DIYU_RUNTIME_MODE": "production",
            "DIYU_APP_DATABASE_URL": database_url,
            "DIYU_SESSION_SECRET": "ux03-gate-b-local-session-secret",
            "DIYU_PUBLIC_URL": "https://diyu.example",
            "DIYU_GENERATOR_MODE": "deepseek",
            "DEEPSEEK_API_BASE_URL": "https://example.invalid",
            "DEEPSEEK_API_KEY": "local-test-placeholder",
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
            "DIYU_MATERIAL_STORAGE_ROOT": str(material_root),
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


def _run_gate_b_browser(
    app_database_url: str,
    material_root: Path,
    username: str,
    password: str,
) -> subprocess.CompletedProcess[str]:
    """Run one real Chrome against the formal React/API/PostgreSQL stack."""

    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = int(port_socket.getsockname()[1])
    base_url = f"http://127.0.0.1:{port}"
    environment = {
        **os.environ,
        "DIYU_RUNTIME_MODE": "production",
        "DIYU_APP_DATABASE_URL": app_database_url,
        "DIYU_SESSION_SECRET": "ux03-gate-b-browser-session-secret",
        "DIYU_PUBLIC_URL": "https://diyu.example",
        "DIYU_GENERATOR_MODE": "deepseek",
        "DEEPSEEK_API_BASE_URL": "https://example.invalid",
        "DEEPSEEK_API_KEY": "local-browser-placeholder",
        "DEEPSEEK_MODEL": "deepseek-v4-flash",
        "DIYU_MATERIAL_STORAGE_ROOT": str(material_root),
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
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            if server.poll() is not None:
                raise AssertionError("Gate B browser API server exited early")
            try:
                with urlopen(f"{base_url}/status", timeout=0.2) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            raise AssertionError("Gate B browser API server did not become ready")
        return subprocess.run(
            ["node", "frontend/test/ux03-gate-b-browser.mjs"],
            cwd=Path(__file__).resolve().parents[1],
            env={
                **os.environ,
                "UX03_GATE_B_BASE_URL": base_url,
                "UX03_GATE_B_USERNAME": username,
                "UX03_GATE_B_PASSWORD": password,
            },
            capture_output=True,
            text=True,
            timeout=180,
        )
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


def _create_test_operator(
    migrator_database_url: str,
    repository: ProductionAuthRepository,
    username: str,
    password: str,
) -> tuple[UUID, str]:
    operator_id = uuid4()
    secret = repository._totp_secret()
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO platform_operators
                (id, username, password_hash, totp_secret)
            VALUES (%s, %s, %s, %s)
            """,
            (
                operator_id,
                username,
                repository._password_hash(password),
                secret,
            ),
        )
    return operator_id, secret


def _delete_gate_b_fixture(
    database_url: str,
    tenant_id: UUID,
    operator_id: UUID,
) -> None:
    """Delete only this test's synthetic tenant and operations identity."""

    tenant_tables = (
        "product_media_bindings",
        "brand_publication_projection_items",
        "brand_publication_projections",
        "activity_events",
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
        "brand_library_entry_organizations",
        "brand_library_entry_versions",
        "brand_library_entries",
        "brand_product_scope_organizations",
        "brand_product_versions",
        "brand_products",
        "material_asset_scope_organizations",
        "material_asset_versions",
        "material_assets",
        "users",
        "brand_audiences",
        "brands",
        "organizations",
    )
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        # This fresh tenant is created solely by this test but exercises the formal
        # consumer path. Mark only its disposable tasks for the existing guarded
        # maintenance deletion; no production or shared fixture row is touched.
        cursor.execute(
            "UPDATE business_tasks SET business_data_kind = "
            "'synthetic_business_fixture' WHERE tenant_id = %s",
            (tenant_id,),
        )
        cursor.execute(
            "UPDATE content_accounts SET business_data_kind = "
            "'synthetic_business_fixture' WHERE tenant_id = %s",
            (tenant_id,),
        )
        cursor.execute(
            "SELECT id FROM product_media_bindings WHERE tenant_id = %s ORDER BY id",
            (tenant_id,),
        )
        for (binding_id,) in cursor.fetchall():
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                (str(tenant_id),),
            )
            cursor.execute(
                "SELECT set_config('diyu.product_media_binding_maintenance', 'delete_synthetic_fixture', true)"
            )
            cursor.execute(
                "SELECT set_config("
                "'diyu.product_media_binding_maintenance_transaction_id', "
                "pg_current_xact_id()::text, true)"
            )
            cursor.execute(
                "SELECT set_config('diyu.product_media_binding_maintenance_tenant_id', %s, true)",
                (str(tenant_id),),
            )
            cursor.execute(
                "SELECT set_config('diyu.product_media_binding_maintenance_binding_id', %s, true)",
                (str(binding_id),),
            )
            cursor.execute(
                "DELETE FROM product_media_bindings WHERE tenant_id = %s AND id = %s",
                (tenant_id, binding_id),
            )
        cursor.execute(
            "SELECT id FROM content_versions WHERE tenant_id = %s ORDER BY id",
            (tenant_id,),
        )
        for (version_id,) in cursor.fetchall():
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                (str(tenant_id),),
            )
            cursor.execute("SELECT set_config('diyu.content_version_maintenance', 'delete_synthetic_fixture', true)")
            cursor.execute(
                "SELECT set_config('diyu.content_version_maintenance_transaction_id', pg_current_xact_id()::text, true)"
            )
            cursor.execute(
                "SELECT set_config('diyu.content_version_maintenance_tenant_id', %s, true)",
                (str(tenant_id),),
            )
            cursor.execute(
                "SELECT set_config('diyu.content_version_maintenance_version_id', %s, true)",
                (str(version_id),),
            )
            cursor.execute(
                "DELETE FROM content_versions WHERE tenant_id = %s AND id = %s",
                (tenant_id, version_id),
            )
        cursor.execute(
            "DELETE FROM content_items WHERE tenant_id = %s",
            (tenant_id,),
        )
        cursor.execute(
            "DELETE FROM generation_runs WHERE tenant_id = %s",
            (tenant_id,),
        )
        cursor.execute(
            "DELETE FROM content_series_items WHERE tenant_id = %s",
            (tenant_id,),
        )
        cursor.execute(
            "DELETE FROM business_tasks WHERE tenant_id = %s",
            (tenant_id,),
        )
        cursor.execute(
            "DELETE FROM content_series WHERE tenant_id = %s",
            (tenant_id,),
        )
        cursor.execute(
            "DELETE FROM display_stores WHERE tenant_id = %s",
            (tenant_id,),
        )
        cursor.execute(
            "UPDATE brand_library_entries SET current_version_id = NULL WHERE tenant_id = %s",
            (tenant_id,),
        )
        cursor.execute(
            "UPDATE brand_products SET current_version_id = NULL WHERE tenant_id = %s",
            (tenant_id,),
        )
        cursor.execute(
            "UPDATE material_assets SET current_version_id = NULL WHERE tenant_id = %s",
            (tenant_id,),
        )
        cursor.execute(
            "UPDATE content_accounts SET current_expression_profile_id = NULL WHERE tenant_id = %s",
            (tenant_id,),
        )
        cursor.execute(
            "UPDATE brands SET current_publication_projection_id = NULL WHERE tenant_id = %s",
            (tenant_id,),
        )
        immutable_triggers = {
            "brand_publication_projection_items": (
                "brand_publication_projection_items_immutable"
            ),
            "brand_library_entry_versions": ("brand_library_entry_versions_immutable"),
            "brand_product_versions": "brand_product_versions_immutable",
            "material_asset_versions": "material_asset_versions_immutable",
        }
        for table in tenant_tables:
            trigger = immutable_triggers.get(table)
            if trigger is not None:
                cursor.execute(
                    f"ALTER TABLE {table} DISABLE TRIGGER {trigger}"  # noqa: S608 - fixed allowlist
                )
            try:
                cursor.execute(
                    f"DELETE FROM {table} WHERE tenant_id = %s",  # noqa: S608 - fixed allowlist
                    (tenant_id,),
                )
            finally:
                if trigger is not None:
                    cursor.execute(
                        f"ALTER TABLE {table} ENABLE TRIGGER {trigger}"  # noqa: S608 - fixed allowlist
                    )
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
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        for table in (
            "content_versions",
            "content_items",
            "generation_runs",
            "business_tasks",
            "content_series_items",
            "content_series",
            "display_stores",
        ):
            cursor.execute(
                f"SELECT count(*) FROM {table} WHERE tenant_id = %s",  # noqa: S608
                (tenant_id,),
            )
            assert cursor.fetchone() == (0,), table
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
        assert cursor.fetchone() == (0,)
        cursor.execute("SELECT count(*) FROM tenants WHERE id = %s", (tenant_id,))
        assert cursor.fetchone() == (0,)
        for table in ("platform_sessions", "ops_audit_events"):
            cursor.execute(
                f"SELECT count(*) FROM {table} WHERE operator_id = %s",  # noqa: S608
                (operator_id,),
            )
            assert cursor.fetchone() == (0,), table
        cursor.execute(
            "SELECT count(*) FROM platform_operators WHERE id = %s",
            (operator_id,),
        )
        assert cursor.fetchone() == (0,)


def test_gate_b_brand_scope_usage_and_readiness_journey(
    app_database_url: str,
    migrator_database_url: str,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """One fresh tenant must carry all six Gate B outcomes and their isolation bait."""

    repository = ProductionAuthRepository(app_database_url)
    suffix = uuid4().hex[:10]
    ops_username = f"ux03-b-ops-{suffix}"
    ops_password = "ux03-gate-b-ops-password"
    operator_id, secret = _create_test_operator(
        migrator_database_url,
        repository,
        ops_username,
        ops_password,
    )
    object_store = LocalObjectStore(str(tmp_path / "materials"))
    api_module = import_module("src.gateway.api.app")
    monkeypatch.setattr(
        api_module,
        "build_workbench_service",
        lambda _: WorkbenchService(
            PostgresWorkbenchRepository(app_database_url),
            object_store,
        ),
    )
    monkeypatch.setattr(
        api_module,
        "build_content_control_service",
        lambda _: ContentControlService(
            PostgresContentControlRepository(app_database_url),
            object_store,
        ),
    )
    app = create_app(_settings(app_database_url, tmp_path / "materials"))
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
                    "tenant_name": f"UX03 Gate B 品牌公司 {suffix}",
                    "administrator_name": "Gate B 首位管理员",
                    "administrator_username": f"ux03-b-admin-{suffix}",
                },
            )
            assert created.status_code == 201
            tenant = created.json()
            tenant_id = UUID(tenant["tenant_id"])
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM brands WHERE tenant_id = %s",
                (tenant_id,),
            )
            brand_row = cursor.fetchone()
            assert brand_row is not None
            brand_id = UUID(str(brand_row[0]))

        with TestClient(app, base_url="https://diyu.example") as admin:
            admin_password = "ux03-gate-b-admin-password"
            _activate(admin, tenant["activation_url"], admin_password)
            _login(
                admin,
                tenant["username"],
                admin_password,
                "/tenant-admin/login",
            )
            headquarters = admin.get("/api/v1/tenant-management/organizations").json()[0]
            east = admin.post(
                "/api/v1/tenant-management/organizations",
                json={
                    "name": "华东区域",
                    "organization_level": "region",
                    "parent_organization_id": headquarters["id"],
                },
            )
            assert east.status_code == 201
            east_store = admin.post(
                "/api/v1/tenant-management/organizations",
                json={
                    "name": "柯桥门店",
                    "organization_level": "operating_unit",
                    "parent_organization_id": east.json()["id"],
                },
            )
            assert east_store.status_code == 201
            south = admin.post(
                "/api/v1/tenant-management/organizations",
                json={
                    "name": "华南区域",
                    "organization_level": "region",
                    "parent_organization_id": headquarters["id"],
                },
            )
            assert south.status_code == 201
            south_store = admin.post(
                "/api/v1/tenant-management/organizations",
                json={
                    "name": "华南门店",
                    "organization_level": "operating_unit",
                    "parent_organization_id": south.json()["id"],
                },
            )
            assert south_store.status_code == 201
            baseline = admin.get("/api/v1/admin/brand-expression").json()
            confirmed = admin.post(
                "/api/v1/admin/brand-expression/confirm",
                json={"draft": f"{baseline['draft']}\n资料范围按账号负责团队确定。"},
            )
            assert confirmed.status_code == 200

            members: dict[str, dict[str, object]] = {}
            for label, organization in (
                ("总部", headquarters),
                ("柯桥", east_store.json()),
                ("华南", south_store.json()),
            ):
                response = admin.post(
                    "/api/v1/tenant-management/users",
                    json={
                        "display_name": f"{label}内容用户",
                        "username": f"ux03-b-{label}-{suffix}",
                        "organization_id": organization["id"],
                        "entry_type": "tenant_user",
                        "capabilities": [],
                        "publishing_identity_ids": [],
                        "expression_profile_maintenance_account_ids": [],
                    },
                )
                assert response.status_code == 201, response.text
                members[label] = response.json()

            accounts: dict[str, dict[str, object]] = {}
            for label, organization in (
                ("总部", headquarters),
                ("柯桥", east_store.json()),
                ("华南", south_store.json()),
            ):
                response = admin.post(
                    "/api/v1/tenant-management/publishing-accounts",
                    json={
                        "name": f"{label}逻辑发布账号",
                        "channel": "抖音",
                        "content_role_name": f"{label}品牌表达",
                        "speaker_kind": "institutional_account",
                        "operator_id": members[label]["user_id"],
                        "control_organization_id": organization["id"],
                        "operator_can_maintain_expression_profile": True,
                        "initial_profile": _PROFILE,
                    },
                )
                assert response.status_code == 201, response.text
                accounts[label] = response.json()
            south_xhs = admin.post(
                "/api/v1/tenant-management/platform-carriers",
                json={
                    "source_account_id": accounts["华南"]["id"],
                    "name": "华南逻辑发布账号 · 小红书",
                    "channel": "小红书",
                    "operator_id": members["华南"]["user_id"],
                    "confirm_internal_carrier": True,
                },
            )
            assert south_xhs.status_code == 201, south_xhs.text
            cross_organization_use = admin.patch(
                f"/api/v1/tenant-management/users/{members['总部']['user_id']}/grants",
                json={
                    "entry_type": "tenant_user",
                    "capabilities": ["content"],
                    "publishing_identity_ids": [
                        accounts["总部"]["id"],
                        accounts["柯桥"]["id"],
                    ],
                    "expression_profile_maintenance_account_ids": [accounts["总部"]["id"]],
                },
            )
            assert cross_organization_use.status_code == 200
            for label in ("总部", "华南"):
                removed_execution_path = admin.patch(
                    f"/api/v1/tenant-management/users/{members[label]['user_id']}/grants",
                    json={
                        "entry_type": "tenant_user",
                        "capabilities": [],
                        "publishing_identity_ids": [],
                        "expression_profile_maintenance_account_ids": [],
                    },
                )
                assert removed_execution_path.status_code == 200

            # Preview is not a formal record; explicit confirmation creates immutable V1.
            east_reference_payload = {
                "category": "organization_fact",
                "title": "华东门店表达参考",
                "source_note": "品牌管理员根据门店确认资料录入",
                "content": "华东区域内容可以引用本区域确认的门店信息。",
                "version": "V1",
                "visibility_scope": "organizations",
                "organization_ids": [east.json()["id"]],
            }
            preview = admin.post(
                "/api/v1/tenant-management/brand-library/preview",
                json=east_reference_payload,
            )
            assert preview.status_code == 200
            assert preview.json()["saved"] is False
            assert (
                admin.post(
                    "/api/v1/tenant-management/brand-library/preview",
                    json={**east_reference_payload, "unknown_field": True},
                ).status_code
                == 422
            )
            assert (
                admin.post(
                    "/api/v1/tenant-management/brand-library",
                    json=east_reference_payload,
                ).status_code
                == 422
            )
            invalid_store_scope = admin.post(
                "/api/v1/tenant-management/brand-library",
                json={
                    **east_reference_payload,
                    "confirm_as_current": True,
                    "organization_ids": [east_store.json()["id"]],
                },
            )
            assert invalid_store_scope.status_code == 422
            assert "区域" in invalid_store_scope.json()["detail"]
            assert admin.get("/api/v1/tenant-management/brand-library").json() == []
            reference = admin.post(
                "/api/v1/tenant-management/brand-library",
                json={**east_reference_payload, "confirm_as_current": True},
            )
            assert reference.status_code == 201, reference.text
            reference_id = reference.json()["id"]
            v2_reference = admin.post(
                f"/api/v1/tenant-management/brand-library/{reference_id}/versions",
                json={
                    **{key: value for key, value in east_reference_payload.items() if key != "category"},
                    "content": "华东区域内容只引用本区域已经确认的门店信息。",
                    "version": "V2",
                },
            )
            assert v2_reference.status_code == 200, v2_reference.text
            history = admin.get(f"/api/v1/tenant-management/brand-library/{reference_id}/versions")
            assert [item["version_number"] for item in history.json()] == [2, 1]
            immutable_update_failed = False
            try:
                with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('app.tenant_id', %s, true)",
                        (str(tenant_id),),
                    )
                    cursor.execute(
                        "UPDATE brand_library_entry_versions "
                        "SET content = '不可变更' "
                        "WHERE tenant_id = %s AND entry_id = %s",
                        (tenant_id, reference_id),
                    )
            except psycopg.Error:
                immutable_update_failed = True
            assert immutable_update_failed, "资料历史版本必须在数据库层不可变"
            retired = admin.put(
                f"/api/v1/tenant-management/brand-library/{reference_id}/enabled",
                json={"enabled": False},
            )
            assert retired.status_code == 200
            restored = admin.put(
                f"/api/v1/tenant-management/brand-library/{reference_id}/enabled",
                json={"enabled": True},
            )
            assert restored.status_code == 200
            assert restored.json()["current_version_id"] == v2_reference.json()["current_version_id"]

            south_reference = admin.post(
                "/api/v1/tenant-management/brand-library",
                json={
                    **east_reference_payload,
                    "title": "华南兄弟区域诱饵资料",
                    "content": "只供华南区域账号使用。",
                    "organization_ids": [south.json()["id"]],
                    "confirm_as_current": True,
                },
            )
            assert south_reference.status_code == 201

            import_preview = admin.post(
                "/api/v1/tenant-management/brand-products/preview",
                json={
                    "source_format": "csv",
                    "content": (
                        "sku,display_name,category,material_or_structure\nEAST-01,华东门店针织衫,服装,针织结构\n"
                    ),
                },
            )
            assert import_preview.status_code == 200
            assert import_preview.json()["saved"] is False
            assert (
                admin.post(
                    "/api/v1/tenant-management/brand-products/preview",
                    json={
                        "source_format": "csv",
                        "content": "sku,display_name\nEAST-01,华东门店针织衫\n",
                        "unknown_field": True,
                    },
                ).status_code
                == 422
            )
            product_payload = {
                "sku": "EAST-01",
                "display_name": "华东门店针织衫",
                "category": "服装",
                "colors": [],
                "material_or_structure": "针织结构",
                "silhouette": "",
                "observable_features": "",
                "source_note": "品牌管理员确认的商品资料",
                "applicability": "当前华东区域内容",
                "confirm_as_current_brand_fact": True,
                "visibility_scope": "organizations",
                "organization_ids": [east.json()["id"]],
            }
            invalid_store_product = admin.put(
                "/api/v1/tenant-management/brand-products",
                json={
                    **product_payload,
                    "sku": "INVALID-STORE-SCOPE",
                    "display_name": "非法门店范围商品",
                    "organization_ids": [east_store.json()["id"]],
                },
            )
            assert invalid_store_product.status_code == 422
            assert "区域" in invalid_store_product.json()["detail"]

            south_product = admin.put(
                "/api/v1/tenant-management/brand-products",
                json={
                    **product_payload,
                    "sku": "SOUTH-ONLY",
                    "display_name": "华南区域限定商品",
                    "applicability": "仅华南区域",
                    "organization_ids": [south.json()["id"]],
                },
            )
            assert south_product.status_code == 200

            misaligned = admin.get("/api/v1/admin/readiness")
            assert misaligned.status_code == 200, misaligned.text
            misaligned_items = {item["id"]: item for item in misaligned.json()["items"]}
            assert misaligned_items["non_product_content"]["status"] == "available"
            assert misaligned_items["product_facts"]["status"] != "available"
            assert misaligned_items["platform_recompile"]["status"] != "available"
            assert all(
                "华南兄弟区域诱饵资料" not in detail["source"]
                for item in misaligned_items.values()
                for detail in item["evidence_details"]
            )

            product_v1 = admin.put(
                "/api/v1/tenant-management/brand-products",
                json=product_payload,
            )
            assert product_v1.status_code == 200, product_v1.text
            product_v2 = admin.put(
                "/api/v1/tenant-management/brand-products",
                json={
                    **product_payload,
                    "observable_features": "圆领",
                    "applicability": "当前华东区域内容 V2",
                },
            )
            assert product_v2.status_code == 200, product_v2.text
            product_history = admin.get("/api/v1/tenant-management/brand-products/EAST-01/versions")
            assert [item["fact_version"] for item in product_history.json()] == [2, 1]
            product_retired = admin.put(
                "/api/v1/tenant-management/brand-products/EAST-01/enabled",
                json={"enabled": False},
            )
            assert product_retired.status_code == 200
            assert (
                admin.put(
                    "/api/v1/tenant-management/brand-products/EAST-01/enabled",
                    json={"enabled": True},
                ).status_code
                == 200
            )

            east_xhs = admin.post(
                "/api/v1/tenant-management/platform-carriers",
                json={
                    "source_account_id": accounts["柯桥"]["id"],
                    "name": "柯桥逻辑发布账号 · 小红书",
                    "channel": "小红书",
                    "operator_id": members["柯桥"]["user_id"],
                    "confirm_internal_carrier": True,
                },
            )
            assert east_xhs.status_code == 201
            aligned = admin.get("/api/v1/admin/readiness")
            assert aligned.status_code == 200
            aligned_items = {item["id"]: item for item in aligned.json()["items"]}
            assert aligned_items["product_facts"]["status"] == "available"
            assert aligned_items["platform_recompile"]["status"] == "available"

            # A store, a qualified member and a display product must meet in the
            # same execution organization. Three brand-level counts cannot be
            # combined into a false-positive DM01 path.
            display_store_id = uuid4()
            with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO display_stores
                        (id, tenant_id, brand_id, control_organization_id,
                         execution_organization_id, name, profile_version,
                         rail_profile)
                    VALUES (%s, %s, %s, %s, %s,
                            '柯桥门店双层挂杆', '1.0', %s)
                    """,
                    (
                        display_store_id,
                        tenant_id,
                        brand_id,
                        headquarters["id"],
                        east_store.json()["id"],
                        Jsonb(
                            {
                                "schema": "dm01-wall-double-rail-v1",
                                "upper_comfort_capacity": 8,
                                "lower_comfort_capacity": 8,
                            }
                        ),
                    ),
                )
                cursor.execute(
                    """
                    INSERT INTO display_access_grants
                        (id, tenant_id, user_id, enabled)
                    VALUES (%s, %s, %s, true)
                    """,
                    (
                        uuid4(),
                        tenant_id,
                        members["华南"]["user_id"],
                    ),
                )
            management_scope = TenantManagementScope(
                tenant_id=tenant_id,
                brand_id=brand_id,
                user_id=UUID(str(tenant["administrator_id"])),
            )
            workbench_repository = PostgresWorkbenchRepository(app_database_url)
            south_display_product = workbench_repository.save_management_product(
                management_scope,
                "SOUTH-DISPLAY",
                "华南陈列限定上装",
                {"display_family": "upper"},
                "tenant_confirmed",
                "华南区域管理员确认的陈列商品事实",
                "仅华南区域陈列",
                "organizations",
                (UUID(str(south.json()["id"])),),
            )
            dm01_misaligned = admin.get("/api/v1/admin/readiness")
            assert dm01_misaligned.status_code == 200
            dm01_misaligned_item = next(
                item for item in dm01_misaligned.json()["items"] if item["id"] == "dm01_display"
            )
            assert dm01_misaligned_item["status"] != "available"

            east_display_product = workbench_repository.save_management_product(
                management_scope,
                "EAST-DISPLAY",
                "华东陈列上装",
                {"display_family": "upper"},
                "tenant_confirmed",
                "华东区域管理员确认的陈列商品事实",
                "当前华东区域陈列",
                "organizations",
                (UUID(str(east.json()["id"])),),
            )
            with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO display_access_grants
                        (id, tenant_id, user_id, enabled)
                    VALUES (%s, %s, %s, true)
                    """,
                    (
                        uuid4(),
                        tenant_id,
                        members["柯桥"]["user_id"],
                    ),
                )
            dm01_aligned = admin.get("/api/v1/admin/readiness")
            assert dm01_aligned.status_code == 200
            dm01_aligned_item = next(item for item in dm01_aligned.json()["items"] if item["id"] == "dm01_display")
            assert dm01_aligned_item["status"] == "available"
            assert any(
                detail["resource_id"] == east_display_product["id"]
                and detail["version_id"] == east_display_product["current_version_id"]
                for detail in dm01_aligned_item["evidence_details"]
            )
            assert all(
                detail["resource_id"] != south_display_product["id"] for detail in dm01_aligned_item["evidence_details"]
            )

            material = admin.post(
                "/api/v1/tenant-management/organization-materials",
                json={
                    "organization_id": east_store.json()["id"],
                    "title": "华东门店官方环境说明",
                    "filename": "east-store.txt",
                    "content_type": "text/plain",
                    "content_base64": "5Y2O5Lic6Zeo5bqX5aSW6KeC6K+05piO",
                    "declares_identifiable_minor": False,
                    "reference_note": "门店管理员确认的官方素材",
                    "visibility_scope": "organizations",
                    "organization_ids": [east.json()["id"]],
                },
            )
            assert material.status_code == 201, material.text
            material_id = material.json()["id"]
            invalid_store_material = admin.post(
                "/api/v1/tenant-management/organization-materials",
                json={
                    "organization_id": east_store.json()["id"],
                    "title": "非法门店范围素材",
                    "filename": "invalid-store-scope.txt",
                    "content_type": "text/plain",
                    "content_base64": "5LiN5bqU5L+d5a2Y",
                    "declares_identifiable_minor": False,
                    "reference_note": "指定区域不能直接绑定门店",
                    "visibility_scope": "organizations",
                    "organization_ids": [east_store.json()["id"]],
                },
            )
            assert invalid_store_material.status_code == 422
            assert "区域" in invalid_store_material.json()["detail"]
            material_v2 = admin.post(
                f"/api/v1/tenant-management/organization-materials/{material_id}/versions",
                json={
                    "title": "华东门店官方环境说明",
                    "reference_note": "门店管理员复核的官方素材说明 V2",
                    "visibility_scope": "organizations",
                    "organization_ids": [east.json()["id"]],
                },
            )
            assert material_v2.status_code == 200, material_v2.text
            assert [
                item["version"]
                for item in admin.get(f"/api/v1/tenant-management/organization-materials/{material_id}/versions").json()
            ] == [2, 1]
            assert (
                admin.put(
                    f"/api/v1/tenant-management/organization-materials/{material_id}/enabled",
                    json={"enabled": False},
                ).status_code
                == 200
            )
            assert (
                admin.put(
                    f"/api/v1/tenant-management/organization-materials/{material_id}/enabled",
                    json={"enabled": True},
                ).status_code
                == 200
            )
            delegated_grant = admin.patch(
                f"/api/v1/tenant-management/users/{members['柯桥']['user_id']}/grants",
                json={
                    "entry_type": "tenant_user",
                    "capabilities": ["content"],
                    "publishing_identity_ids": [accounts["柯桥"]["id"]],
                    "expression_profile_maintenance_account_ids": [
                        accounts["柯桥"]["id"]
                    ],
                    "grants_material_maintenance": True,
                },
            )
            assert delegated_grant.status_code == 200, delegated_grant.text

            with TestClient(app, base_url="https://diyu.example") as material_user:
                material_password = "ux03-gate-b-material-user-password"
                _activate(
                    material_user,
                    str(members["柯桥"]["activation_url"]),
                    material_password,
                )
                _login(
                    material_user,
                    str(members["柯桥"]["username"]),
                    material_password,
                    "/login",
                )
                assert material_user.get("/organization-materials").status_code == 200
                delegated = material_user.post(
                    "/api/v1/user/organization-materials",
                    json={
                        "title": "柯桥团队维护说明",
                        "filename": "team-note.txt",
                        "content_type": "text/plain",
                        "content_base64": "5p+l5qGl5Zui6Zif5a6Y5pa56K+05piO",
                        "declares_identifiable_minor": False,
                        "reference_note": "由获授权成员维护",
                    },
                )
                assert delegated.status_code == 201, delegated.text
                delegated_id = delegated.json()["id"]
                listed_delegated = material_user.get(
                    "/api/v1/user/organization-materials"
                )
                assert listed_delegated.status_code == 200
                assert delegated_id in {item["id"] for item in listed_delegated.json()}
                saved_delegated_version = material_user.post(
                    f"/api/v1/user/organization-materials/{delegated_id}/versions",
                    json={
                        "title": "柯桥团队维护说明 V2",
                        "reference_note": "由获授权成员复核说明",
                        "visibility_scope": "organizations",
                        "organization_ids": [east_store.json()["id"]],
                    },
                )
                assert saved_delegated_version.status_code == 200, saved_delegated_version.text
                assert (
                    material_user.put(
                        f"/api/v1/user/organization-materials/{delegated_id}/enabled",
                        json={"enabled": False},
                    ).status_code
                    == 200
                )
                assert (
                    material_user.put(
                        f"/api/v1/user/organization-materials/{delegated_id}/enabled",
                        json={"enabled": True},
                    ).status_code
                    == 200
                )

            with TestClient(app, base_url="https://diyu.example") as unauthorized_user:
                unauthorized_password = "ux03-gate-b-no-material-password"
                _activate(
                    unauthorized_user,
                    str(members["华南"]["activation_url"]),
                    unauthorized_password,
                )
                _login(
                    unauthorized_user,
                    str(members["华南"]["username"]),
                    unauthorized_password,
                    "/login",
                )
                assert unauthorized_user.get(
                    "/api/v1/user/organization-materials"
                ).status_code == 422

            # Runtime access derives from each logical account's control organization.
            with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
                bait_brand_id = uuid4()
                bait_entry_id = uuid4()
                bait_version_id = uuid4()
                cursor.execute(
                    """
                    INSERT INTO brands
                        (id, tenant_id, name, positioning,
                         decision_order, tone)
                    VALUES (%s, %s, '另一品牌诱饵', '不得进入当前品牌',
                            '隔离优先', '隔离')
                    """,
                    (bait_brand_id, tenant_id),
                )
                cursor.execute(
                    """
                    INSERT INTO brand_library_entries
                        (id, tenant_id, brand_id, category, title,
                         source_note, content, version, status,
                         visibility_scope, updated_by)
                    VALUES (%s, %s, %s, 'reference', '另一品牌诱饵资料',
                            '隔离测试', '不得泄漏', 'V1', 'active',
                            'brand_all', %s)
                    """,
                    (
                        bait_entry_id,
                        tenant_id,
                        bait_brand_id,
                        UUID(str(tenant["administrator_id"])),
                    ),
                )
                cursor.execute(
                    """
                    INSERT INTO brand_library_entry_versions
                        (id, tenant_id, brand_id, entry_id,
                         version_number, version_label, category, title,
                         source_note, content, visibility_scope, created_by)
                    VALUES (%s, %s, %s, %s, 1, 'V1', 'reference',
                            '另一品牌诱饵资料', '隔离测试', '不得泄漏',
                            'brand_all', %s)
                    """,
                    (
                        bait_version_id,
                        tenant_id,
                        bait_brand_id,
                        bait_entry_id,
                        UUID(str(tenant["administrator_id"])),
                    ),
                )
                cursor.execute(
                    "UPDATE brand_library_entries SET current_version_id = %s WHERE tenant_id = %s AND id = %s",
                    (bait_version_id, tenant_id, bait_entry_id),
                )
            restored_south_execution_path = admin.patch(
                f"/api/v1/tenant-management/users/{members['华南']['user_id']}/grants",
                json={
                    "entry_type": "tenant_user",
                    "capabilities": ["content"],
                    "publishing_identity_ids": [accounts["华南"]["id"]],
                    "expression_profile_maintenance_account_ids": [],
                },
            )
            assert restored_south_execution_path.status_code == 200
            restored_cross_organization_path = admin.patch(
                f"/api/v1/tenant-management/users/{members['总部']['user_id']}/grants",
                json={
                    "entry_type": "tenant_user",
                    "capabilities": ["content"],
                    "publishing_identity_ids": [
                        accounts["总部"]["id"],
                        accounts["柯桥"]["id"],
                    ],
                    "expression_profile_maintenance_account_ids": [accounts["总部"]["id"]],
                },
            )
            assert restored_cross_organization_path.status_code == 200
            east_scope = TrustedScope(
                tenant_id=tenant_id,
                brand_id=brand_id,
                account_id=UUID(str(east_xhs.json()["id"])),
                user_id=UUID(str(members["柯桥"]["user_id"])),
            )
            south_scope = TrustedScope(
                tenant_id=tenant_id,
                brand_id=brand_id,
                account_id=UUID(str(accounts["华南"]["id"])),
                user_id=UUID(str(members["华南"]["user_id"])),
            )
            cross_organization_user_scope = TrustedScope(
                tenant_id=tenant_id,
                brand_id=brand_id,
                account_id=UUID(str(accounts["柯桥"]["id"])),
                user_id=UUID(str(members["总部"]["user_id"])),
            )
            content_repository = PostgresContentRepository(app_database_url)
            east_context = content_repository.load_brand_context(
                east_scope,
                "graphic",
                "手机实拍",
            )
            south_context = content_repository.load_brand_context(
                south_scope,
                "graphic",
                "手机实拍",
            )
            assert "华东门店表达参考" in "\n".join(east_context.brand_reference_context)
            assert "华东门店表达参考" in "\n".join(
                content_repository.load_brand_context(
                    cross_organization_user_scope,
                    "graphic",
                    "手机实拍",
                ).brand_reference_context
            )
            assert "华东门店表达参考" not in "\n".join(south_context.brand_reference_context)
            assert "另一品牌诱饵资料" not in "\n".join(east_context.brand_reference_context)
            with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
                cursor.execute(
                    "SELECT tenant_id, brand_id, id, created_by FROM business_tasks WHERE tenant_id <> %s LIMIT 1",
                    (tenant_id,),
                )
                other_tenant_task = cursor.fetchone()
            if other_tenant_task is not None:
                cross_tenant_scope = TrustedScope(
                    tenant_id=UUID(str(other_tenant_task[0])),
                    brand_id=brand_id,
                    account_id=UUID(str(accounts["柯桥"]["id"])),
                    user_id=UUID(str(members["柯桥"]["user_id"])),
                )
                try:
                    content_repository.load_brand_context(
                        cross_tenant_scope,
                        "graphic",
                        "手机实拍",
                    )
                except DomainError:
                    pass
                else:
                    raise AssertionError("跨租户作用域不应读取当前品牌资料")
            east_products = content_repository.load_product_facts(
                east_scope,
                "请介绍 EAST-01",
            )
            assert [item.fact_version for item in east_products] == [2]
            assert [item.sku for item in content_repository.load_product_facts(
                east_scope,
                "请介绍 华东门店针织衫",
            )] == ["EAST-01"]
            for invalid_reference in (
                "请介绍 EAST-010",
                "请介绍 XEAST-01",
                "请介绍 EAST-01、完全未知商品",
            ):
                with pytest.raises(DomainError, match="完整"):
                    content_repository.load_product_facts(
                        east_scope,
                        invalid_reference,
                    )
            assert (
                content_repository.load_product_facts(
                    south_scope,
                    "请介绍 EAST-01",
                )
                == ()
            )
            assert (
                content_repository.load_product_facts(
                    east_scope,
                    "今天不知道发什么",
                )
                == ()
            )
            control_repository = PostgresContentControlRepository(app_database_url)
            assert control_repository.selected_materials(
                east_scope,
                (UUID(material_id),),
            )
            assert control_repository.selected_materials(east_scope, ()) == ()
            try:
                control_repository.selected_materials(
                    south_scope,
                    (UUID(material_id),),
                )
            except DomainError as exc:
                assert "不能使用" in str(exc)
            else:
                raise AssertionError("兄弟区域不应读取华东组织素材")

            # One deterministic task freezes exactly the selected versions. Later
            # versions and retirements must not change its same-goal revision.
            content_service = ContentService(
                content_repository,
                DeterministicContentGenerator(),
                ContentControlService(control_repository, object_store),
            )
            first = content_service.create_from_weak_seed(
                east_scope,
                "请用 EAST-01 写一条商品内容",
                target="xiaohongshu_graphic",
                controls=RequestedControls(
                    material_ids=(UUID(material_id),),
                ),
            )
            assert first["kind"] == "content", first
            first_task_id = UUID(str(first["task_id"]))
            with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
                cursor.execute(
                    "SELECT content_context_snapshot FROM business_tasks WHERE tenant_id = %s AND id = %s",
                    (tenant_id, first_task_id),
                )
                frozen_row = cursor.fetchone()
                assert frozen_row is not None
                frozen_snapshot = frozen_row[0]
            assert frozen_snapshot["product_facts"][0]["fact_version"] == 2
            assert frozen_snapshot["material_snapshots"][0]["reference_version"] == 2
            assert frozen_snapshot["brand_reference_context"] == []
            assert frozen_snapshot["brand_context_packet"]["packet_version"] == "brand-context-packet-v3"
            assert frozen_snapshot["brand_context_packet"]["publication_projection_id"]
            assert any(
                item["semantic_kind"] == "expression_constraint"
                for item in frozen_snapshot["brand_context_packet"]["segments"]
            )

            reference_v3 = admin.post(
                f"/api/v1/tenant-management/brand-library/{reference_id}/versions",
                json={
                    "title": "华东门店表达参考",
                    "source_note": "品牌管理员第三次复核",
                    "content": "这是后续任务才应消费的 V3。",
                    "version": "V3",
                    "visibility_scope": "organizations",
                    "organization_ids": [east.json()["id"]],
                },
            )
            assert reference_v3.status_code == 200
            assert (
                admin.put(
                    f"/api/v1/tenant-management/brand-library/{reference_id}/enabled",
                    json={"enabled": False},
                ).status_code
                == 200
            )
            product_v3 = admin.put(
                "/api/v1/tenant-management/brand-products",
                json={
                    **product_payload,
                    "observable_features": "圆领与后续确认细节",
                    "applicability": "后续新任务 V3",
                },
            )
            assert product_v3.status_code == 200
            assert (
                admin.put(
                    "/api/v1/tenant-management/brand-products/EAST-01/enabled",
                    json={"enabled": False},
                ).status_code
                == 200
            )
            material_v3 = admin.post(
                f"/api/v1/tenant-management/organization-materials/{material_id}/versions",
                json={
                    "title": "华东门店官方环境说明",
                    "reference_note": "后续任务才应读取的素材说明 V3",
                    "visibility_scope": "organizations",
                    "organization_ids": [east.json()["id"]],
                },
            )
            assert material_v3.status_code == 200
            assert (
                admin.put(
                    f"/api/v1/tenant-management/organization-materials/{material_id}/enabled",
                    json={"enabled": False},
                ).status_code
                == 200
            )
            current_after_retirement = content_repository.load_brand_context(
                east_scope,
                "graphic",
                "手机实拍",
            )
            assert "华东门店表达参考" not in "\n".join(current_after_retirement.brand_reference_context)
            assert (
                content_repository.load_product_facts(
                    east_scope,
                    "请介绍 EAST-01",
                )
                == ()
            )
            try:
                control_repository.selected_materials(
                    east_scope,
                    (UUID(material_id),),
                )
            except DomainError:
                pass
            else:
                raise AssertionError("已停用组织素材不应进入新任务")
            content_service.revise(
                east_scope,
                first_task_id,
                "换个讲法，保留原来的资料边界",
                target="xiaohongshu_graphic",
            )
            with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
                cursor.execute(
                    "SELECT content_context_snapshot FROM business_tasks WHERE tenant_id = %s AND id = %s",
                    (tenant_id, first_task_id),
                )
                revised_row = cursor.fetchone()
                assert revised_row is not None
                revised_snapshot = revised_row[0]
            assert revised_snapshot["product_facts"] == frozen_snapshot["product_facts"]
            assert revised_snapshot["material_snapshots"] == frozen_snapshot["material_snapshots"]
            assert revised_snapshot["brand_reference_context"] == frozen_snapshot["brand_reference_context"]
            assert (
                admin.put(
                    f"/api/v1/tenant-management/brand-library/{reference_id}/enabled",
                    json={"enabled": True},
                ).status_code
                == 200
            )
            assert (
                admin.put(
                    "/api/v1/tenant-management/brand-products/EAST-01/enabled",
                    json={"enabled": True},
                ).status_code
                == 200
            )
            assert (
                admin.put(
                    f"/api/v1/tenant-management/organization-materials/{material_id}/enabled",
                    json={"enabled": True},
                ).status_code
                == 200
            )

            # A series continuation is a later-position task that actually
            # committed V1. Failed tasks, first items, revisions, platform
            # adaptations and out-of-window V1 submissions must not inflate it.
            series_b = workbench_repository.create_series(
                east_scope,
                "只有首篇的系列",
                "验证首篇不算续写",
            )
            content_service.create_from_weak_seed(
                east_scope,
                "请生成这个系列的第一篇一般观察",
                target="xiaohongshu_graphic",
                series_id=UUID(str(series_b["id"])),
                series_position=1,
                primary_product_override="brand_life_narrative",
            )
            first_only_usage = admin.get("/api/v1/tenant-management/team-usage?window_days=7")
            assert first_only_usage.status_code == 200
            assert first_only_usage.json()["activity"]["series_continuations"] == 0
            persistence_before_failure = _content_persistence_counts(
                migrator_database_url,
                tenant_id,
            )
            failed_content_service = ContentService(
                content_repository,
                _FailingContentGenerator(),
                ContentControlService(control_repository, object_store),
            )
            with pytest.raises(GenerationFailed, match="受控生成失败"):
                failed_content_service.create_from_weak_seed(
                    east_scope,
                    "请生成这个系列的第二篇，但本次受控失败",
                    target="xiaohongshu_graphic",
                    series_id=UUID(str(series_b["id"])),
                    series_position=2,
                    primary_product_override="brand_life_narrative",
                )
            persistence_after_failure = _content_persistence_counts(
                migrator_database_url,
                tenant_id,
            )
            assert persistence_after_failure == (
                persistence_before_failure[0] + 1,
                persistence_before_failure[1] + 1,
                persistence_before_failure[2],
                persistence_before_failure[3] + 1,
                0,
            )
            failed_second_usage = admin.get("/api/v1/tenant-management/team-usage?window_days=7")
            assert failed_second_usage.status_code == 200
            assert failed_second_usage.json()["activity"]["series_continuations"] == 0
            series_a = workbench_repository.create_series(
                east_scope,
                "近七日两篇系列",
                "验证首篇与续篇口径",
            )
            content_service.create_from_weak_seed(
                east_scope,
                "请生成系列第一篇，写一般门店观察",
                target="xiaohongshu_graphic",
                series_id=UUID(str(series_a["id"])),
                series_position=1,
                primary_product_override="brand_life_narrative",
            )
            successful_second = content_service.create_from_weak_seed(
                east_scope,
                "请生成系列第二篇，延续一般门店观察",
                target="xiaohongshu_graphic",
                series_id=UUID(str(series_a["id"])),
                series_position=2,
                primary_product_override="brand_life_narrative",
            )
            successful_second_usage = admin.get("/api/v1/tenant-management/team-usage?window_days=7")
            assert successful_second_usage.status_code == 200
            assert successful_second_usage.json()["activity"]["series_continuations"] == 1
            content_service.revise(
                east_scope,
                UUID(str(successful_second["task_id"])),
                "换一种自然表达，不改变系列位置",
                target="xiaohongshu_graphic",
            )
            after_revision_usage = admin.get("/api/v1/tenant-management/team-usage?window_days=7")
            assert after_revision_usage.status_code == 200
            assert after_revision_usage.json()["activity"]["series_continuations"] == 1
            east_douyin_scope = TrustedScope(
                tenant_id=tenant_id,
                brand_id=brand_id,
                account_id=UUID(str(accounts["柯桥"]["id"])),
                user_id=UUID(str(members["柯桥"]["user_id"])),
            )
            platform_adaptation = content_service.create_from_weak_seed(
                east_douyin_scope,
                "将当前系列第二篇适配为抖音视频",
                reuse_version_id=UUID(str(successful_second["version_id"])),
                target="douyin_video",
                series_id=UUID(str(series_a["id"])),
                series_position=3,
            )
            assert "version_id" in platform_adaptation
            with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT parent_version_id
                    FROM business_tasks
                    WHERE tenant_id = %s AND id = %s
                    """,
                    (tenant_id, platform_adaptation["task_id"]),
                )
                assert cursor.fetchone() == (UUID(str(successful_second["version_id"])),)
            after_adaptation_usage = admin.get("/api/v1/tenant-management/team-usage?window_days=7")
            assert after_adaptation_usage.status_code == 200
            assert after_adaptation_usage.json()["activity"]["series_continuations"] == 1
            series_c = workbench_repository.create_series(
                east_scope,
                "窗口外续篇系列",
                "验证时间窗口",
            )
            content_service.create_from_weak_seed(
                east_scope,
                "请生成窗口系列第一篇一般观察",
                target="xiaohongshu_graphic",
                series_id=UUID(str(series_c["id"])),
                series_position=1,
                primary_product_override="brand_life_narrative",
            )
            old_second = content_service.create_from_weak_seed(
                east_scope,
                "请生成窗口系列第二篇一般观察",
                target="xiaohongshu_graphic",
                series_id=UUID(str(series_c["id"])),
                series_position=2,
                primary_product_override="brand_life_narrative",
            )
            assert "version_id" in old_second, old_second
            _move_version_submission_outside_usage_window(
                migrator_database_url,
                tenant_id,
                UUID(str(old_second["version_id"])),
            )

            # One bounded event set proves that 7/30-day windows and event kinds
            # are not interchangeable. No prompt or content body is stored here.
            with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
                for days, event_type in (
                    (5, "content.conversation"),
                    (15, "content.conversation"),
                    (5, "content.rate_limited"),
                    (40, "content.rate_limited"),
                ):
                    cursor.execute(
                        """
                        INSERT INTO activity_events
                            (id, tenant_id, actor_id, event_type,
                             entity_type, entity_id, created_at)
                        VALUES (%s, %s, %s, %s, 'formal_identity', %s, %s)
                        """,
                        (
                            uuid4(),
                            tenant_id,
                            UUID(str(tenant["administrator_id"])),
                            event_type,
                            UUID(str(tenant["administrator_id"])),
                            datetime.now(timezone.utc) - timedelta(days=days),
                        ),
                    )
            usage_7 = admin.get("/api/v1/tenant-management/team-usage?window_days=7")
            usage_30 = admin.get("/api/v1/tenant-management/team-usage?window_days=30")
            assert usage_7.status_code == usage_30.status_code == 200
            assert usage_7.json()["activity"]["conversations"] == 1
            assert usage_30.json()["activity"]["conversations"] == 2
            assert usage_7.json()["activity"]["rate_limited"] == 1
            assert usage_30.json()["activity"]["rate_limited"] == 1
            assert usage_7.json()["activity"]["revisions"] == 2
            assert usage_7.json()["activity"]["series_continuations"] == 1
            assert usage_30.json()["activity"]["series_continuations"] == 1
            assert usage_7.json()["activity"]["first_generations"] == 6
            assert usage_7.json()["activity"]["successful_runs"] == 9
            assert usage_7.json()["activity"]["failed_runs"] == 1
            assert usage_7.json()["members"]["logged_in"] >= 1
            assert usage_7.json()["members"]["product_active"] >= 1
            assert usage_7.json()["provider_usage"]["is_complete_billing_total"] is False

            for label in ("总部", "华南"):
                removed_non_east_path = admin.patch(
                    f"/api/v1/tenant-management/users/{members[label]['user_id']}/grants",
                    json={
                        "entry_type": "tenant_user",
                        "capabilities": [],
                        "publishing_identity_ids": [],
                        "expression_profile_maintenance_account_ids": [],
                    },
                )
                assert removed_non_east_path.status_code == 200
            readiness = admin.get("/api/v1/admin/readiness")
            assert readiness.status_code == 200
            diagnosis = readiness.json()["items"]
            assert {item["id"] for item in diagnosis} == {
                "non_product_content",
                "product_facts",
                "continuous_series",
                "platform_recompile",
                "dm01_display",
                "first_creation",
            }
            non_product = next(item for item in diagnosis if item["id"] == "non_product_content")
            assert non_product["status"] == "available"
            assert "不依赖具体商品事实" in non_product["unaffected"][0]
            assert all(item["contract_version"] == "ux03-readiness-v3" for item in diagnosis)
            assert all("evidence_details" in item for item in diagnosis)
            evidence_details = [detail for item in diagnosis for detail in item["evidence_details"]]
            assert evidence_details
            assert all(detail["resource_id"] for detail in evidence_details)
            assert all(detail["scope"] for detail in evidence_details)
            assert all("项" not in detail["version"] for detail in evidence_details)
            assert all(detail.get("updated_at") or detail.get("updated_at_label") for detail in evidence_details)
            assert all(
                "华南兄弟区域诱饵资料" not in detail["source"]
                and "另一品牌诱饵资料" not in detail["source"]
                and "华南陈列限定上装" not in detail["source"]
                for detail in evidence_details
            )
            product_diagnosis = next(item for item in diagnosis if item["id"] == "product_facts")
            assert product_diagnosis["status"] == "available"
            assert any(
                detail["version_id"]
                for detail in product_diagnosis["evidence_details"]
                if detail["source"].startswith("华东")
            )
            if os.environ.get("DIYU_RUN_UX03_GATE_B_BROWSER") == "1":
                browser = _run_gate_b_browser(
                    app_database_url,
                    tmp_path / "materials",
                    str(tenant["username"]),
                    admin_password,
                )
                assert browser.returncode == 0, (
                    f"formal Gate B Chrome journey failed:\n{browser.stdout}\n{browser.stderr}"
                )
                assert '"failures":[]' in browser.stdout.replace(" ", "")
    finally:
        if tenant_id is not None:
            _delete_gate_b_fixture(
                migrator_database_url,
                tenant_id,
                operator_id,
            )
