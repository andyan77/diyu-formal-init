from __future__ import annotations

import time
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient

from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.production_auth import ProductionAuthRepository, TenantSession
from src.infrastructure.seed_demo import ACCOUNT_ID, ORG_ID, TENANT_ADMIN_USER_ID, TENANT_ID


def _settings(database_url: str) -> Settings:
    return Settings.model_validate(
        {
            "DIYU_RUNTIME_MODE": "production",
            "DIYU_APP_DATABASE_URL": database_url,
            "DIYU_SESSION_SECRET": "production-test-session-secret",
            "DIYU_GENERATOR_MODE": "deepseek",
            "DEEPSEEK_API_BASE_URL": "https://example.invalid",
            "DEEPSEEK_API_KEY": "not-a-real-key",
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
            "DIYU_S3_ENDPOINT_URL": "http://127.0.0.1:9000",
            "DIYU_S3_BUCKET": "diyu-test",
            "DIYU_S3_ACCESS_KEY_ID": "test-access-key",
            "DIYU_S3_SECRET_ACCESS_KEY": "test-secret-key",
        }
    )


def _clear_auth_state(migrator_database_url: str) -> None:
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("DELETE FROM ops_audit_events")
        cursor.execute("DELETE FROM tenant_sessions")
        cursor.execute("DELETE FROM user_activation_tokens")
        cursor.execute("DELETE FROM user_credentials")
        cursor.execute("DELETE FROM platform_sessions")
        cursor.execute("DELETE FROM platform_operators")


def test_production_login_activation_and_entry_boundaries(app_database_url: str, migrator_database_url: str) -> None:
    _clear_auth_state(migrator_database_url)
    repository = ProductionAuthRepository(app_database_url)
    admin_activation = repository.bootstrap_existing_tenant_admin(TENANT_ID, TENANT_ADMIN_USER_ID, "formal-admin")
    app = create_app(_settings(app_database_url))
    with TestClient(app, base_url="https://diyuai.cc") as client:
        assert client.get("/", follow_redirects=False).headers["location"] == "/login"
        assert client.get("/ui/select/content").status_code == 404
        activated = client.post(
            f"/activate/{admin_activation}",
            content="password=a-long-enough-password",
            follow_redirects=False,
        )
        assert activated.status_code == 303
        assert activated.headers["location"] == "/tenant-admin/login"
        signed_in = client.post(
            "/tenant-admin/login",
            content="username=formal-admin&password=a-long-enough-password",
            follow_redirects=False,
        )
        assert signed_in.status_code == 303
        assert signed_in.headers["location"] == "/tenant-admin"
        assert client.get("/tenant-admin").status_code == 200
        assert client.get("/user").status_code == 403
        display_name = f"重复自然人-{uuid4().hex[:8]}"
        first = client.post(
            "/api/v1/tenant-management/users",
            json={"display_name": display_name, "username": f"first-{uuid4().hex[:10]}"},
        )
        assert first.status_code == 201
        duplicate = client.post(
            "/api/v1/tenant-management/users",
            json={"display_name": display_name, "username": f"second-{uuid4().hex[:10]}"},
        )
        assert duplicate.status_code == 422


def test_production_created_user_uses_one_time_link_and_cannot_escalate(
    app_database_url: str, migrator_database_url: str
) -> None:
    _clear_auth_state(migrator_database_url)
    repository = ProductionAuthRepository(app_database_url)
    manager = TenantSession(TENANT_ID, TENANT_ADMIN_USER_ID, "tenant-admin")
    username = f"operator-{uuid4().hex[:12]}"
    created = repository.create_tenant_user(
        manager,
        f"正式内容操作人-{uuid4().hex[:8]}",
        username,
        ORG_ID,
        ACCOUNT_ID,
        grants_tenant_management=False,
        grants_material_maintenance=True,
    )
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT organization_id FROM organization_material_maintainers WHERE tenant_id = %s AND user_id = %s",
            (TENANT_ID, UUID(created["user_id"])),
        )
        assert cursor.fetchone() == (ORG_ID,)
    app = create_app(_settings(app_database_url))
    with TestClient(app, base_url="https://diyuai.cc") as client:
        activated = client.post(
            f"/activate/{created['activation_token']}",
            content="password=another-long-password",
            follow_redirects=False,
        )
        assert activated.status_code == 303
        assert activated.headers["location"] == "/login"
        assert (
            client.post(
                "/login",
                content=f"username={username}&password=another-long-password",
                follow_redirects=False,
            ).status_code
            == 303
        )
        assert client.get("/user").status_code == 200
        assert client.get("/tenant-admin").status_code == 403
        repository.disable_tenant_user(manager, UUID(created["user_id"]))
        assert client.get("/user").status_code == 401
        assert (
            client.post(
                f"/activate/{created['activation_token']}",
                content="password=one-more-long-password",
                follow_redirects=False,
            ).status_code
            == 422
        )


def test_platform_operator_requires_totp_and_can_provision_a_tenant_shell(
    app_database_url: str, migrator_database_url: str
) -> None:
    _clear_auth_state(migrator_database_url)
    repository = ProductionAuthRepository(app_database_url)
    _, provisioning_uri = repository.bootstrap_operator("ops-formal", "ops-password-is-long")
    secret = parse_qs(urlsplit(provisioning_uri).query)["secret"][0]
    code = repository._totp_code(secret, int(time.time() // 30))
    operator = repository.authenticate_operator("ops-formal", "ops-password-is-long", code)
    assert operator is not None
    created = repository.provision_tenant(
        operator,
        f"新租户-{uuid4().hex[:8]}",
        "首位管理员",
        f"admin-{uuid4().hex[:8]}",
    )
    assert created["tenant_id"]
    assert created["activation_token"]
    summary = repository.runtime_summary(operator)
    registered_tenants = summary["registered_tenants"]
    assert isinstance(registered_tenants, (int, float))
    assert registered_tenants >= 1
    assert "content_runs" in summary
