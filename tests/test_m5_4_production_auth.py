from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.production_auth import ProductionAuthRepository, TenantSession
from src.infrastructure.seed_demo import ACCOUNT_ID, ORG_ID, TENANT_ADMIN_USER_ID, TENANT_ID
from src.shared.errors import DomainError


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
        public_home = client.get("/", follow_redirects=False)
        assert public_home.status_code == 200
        assert public_home.headers["content-type"].startswith("text/html")
        assert '"application": "public"' in public_home.text
        assert "开始创作" in public_home.text
        tenant_admin_entry = client.get("/tenant-admin", follow_redirects=False)
        assert tenant_admin_entry.status_code == 303
        assert tenant_admin_entry.headers["location"] == "/tenant-admin/login"
        demo_entry = client.get("/tenant-admin?section=demo", follow_redirects=False)
        assert demo_entry.status_code == 303
        assert demo_entry.headers["location"] == "/tenant-admin/login?next=demo"
        assert "name='next' value='demo'" in client.get("/tenant-admin/login?next=demo").text
        failed_login = client.post(
            "/tenant-admin/login",
            content="username=not-an-admin&password=not-the-password",
        )
        assert failed_login.status_code == 401
        assert failed_login.headers["content-type"].startswith("text/html")
        assert "这次没有登录成功" in failed_login.text
        assert "/tenant-admin/login" in failed_login.text
        assert '{"detail":' not in failed_login.text
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
        client.post("/tenant-admin/logout")
        demo_signed_in = client.post(
            "/tenant-admin/login",
            content=("username=formal-admin&password=a-long-enough-password&next=demo"),
            follow_redirects=False,
        )
        assert demo_signed_in.status_code == 303
        assert demo_signed_in.headers["location"] == "/tenant-admin?section=demo"
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
        refused = client.get("/tenant-admin")
        assert refused.status_code == 403
        assert refused.headers["content-type"].startswith("text/html")
        assert "当前账号没有租户管理资格" in refused.text
        assert "返回内容入口" in refused.text
        assert "/tenant-admin/logout" in refused.text
        assert "租户管理入口资格" not in refused.text
        signed_out = client.post("/tenant-admin/logout", follow_redirects=False)
        assert signed_out.status_code == 303
        assert signed_out.headers["location"] == "/tenant-admin/login"
        assert client.get("/tenant-admin", follow_redirects=False).status_code == 303
        repository.disable_tenant_user(manager, UUID(created["user_id"]))
        disabled_entry = client.get("/user", follow_redirects=False)
        assert disabled_entry.status_code == 303
        assert disabled_entry.headers["location"] == "/login"
        assert (
            client.post(
                f"/activate/{created['activation_token']}",
                content="password=one-more-long-password",
                follow_redirects=False,
            ).status_code
            == 422
        )


def test_new_reset_link_invalidates_previous_link_and_activation_revokes_sessions(
    app_database_url: str, migrator_database_url: str
) -> None:
    _clear_auth_state(migrator_database_url)
    repository = ProductionAuthRepository(app_database_url)
    manager = TenantSession(TENANT_ID, TENANT_ADMIN_USER_ID, "tenant-admin")
    username = f"reset-once-{uuid4().hex[:12]}"
    created = repository.create_tenant_user(
        manager,
        f"一次性链接反证-{uuid4().hex[:8]}",
        username,
        ORG_ID,
        ACCOUNT_ID,
        grants_tenant_management=False,
        grants_material_maintenance=False,
    )
    user_id = UUID(created["user_id"])
    repository.complete_activation(created["activation_token"], "initial-password-is-long")
    identity = repository.authenticate_tenant_user(username, "initial-password-is-long", "tenant-user")
    assert identity is not None
    old_session = repository.create_tenant_session(identity)

    first_reset = repository.create_reset_token(manager, user_id)
    second_reset = repository.create_reset_token(manager, user_id)
    with pytest.raises(DomainError, match="无效或已过期"):
        repository.complete_activation(first_reset, "first-link-must-not-work")
    assert repository.complete_activation(second_reset, "second-link-works-once") == "tenant-user"
    with pytest.raises(DomainError, match="无效或已过期"):
        repository.complete_activation(second_reset, "second-link-must-not-work-twice")
    assert repository.load_tenant_session(old_session) is None
    new_identity = repository.authenticate_tenant_user(username, "second-link-works-once", "tenant-user")
    assert new_identity is not None
    new_session = repository.create_tenant_session(new_identity)
    assert repository.load_tenant_session(new_session) == new_identity

    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM user_activation_tokens WHERE tenant_id = %s AND user_id = %s AND used_at IS NULL",
            (TENANT_ID, user_id),
        )
        assert cursor.fetchone() == (0,)
        cursor.execute(
            "SELECT event_type FROM activity_events "
            "WHERE tenant_id = %s AND entity_id = %s AND event_type LIKE 'password.%%' "
            "ORDER BY created_at",
            (TENANT_ID, user_id),
        )
        events = {str(row[0]) for row in cursor.fetchall()}
    assert {
        "password.pending_links_invalidated_on_issue",
        "password.reset_issued",
        "password.pending_links_invalidated_on_use",
        "password.activated_or_reset",
    } <= events


def test_activation_paths_are_redacted_and_edge_access_logs_are_disabled(
    app_database_url: str,
    migrator_database_url: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _clear_auth_state(migrator_database_url)
    repository = ProductionAuthRepository(app_database_url)
    activation = repository.bootstrap_existing_tenant_admin(TENANT_ID, TENANT_ADMIN_USER_ID, "redaction-admin")
    caplog.set_level(logging.INFO, logger="diyu.runtime")
    app = create_app(_settings(app_database_url))
    with TestClient(app, base_url="https://diyuai.cc") as client:
        assert client.get(f"/activate/{activation}").status_code == 200
    request_events = [json.loads(record.message) for record in caplog.records if record.name == "diyu.runtime"]
    assert request_events[-1]["path"] == "/activate/:token"

    root = Path(__file__).resolve().parents[1]
    for name in ("diyuai.cc.conf", "diyuai.cc-maintenance.conf"):
        nginx = (root / "deploy" / "nginx" / name).read_text(encoding="utf-8")
        assert nginx.count("location ^~ /activate/") == 2
        assert nginx.count("access_log off;") == 2
        assert nginx.count("error_log /dev/null crit;") == 2
        assert nginx.count('add_header Referrer-Policy "no-referrer" always;') == 2
    application_nginx = (root / "deploy" / "nginx" / "diyuai.cc.conf").read_text(encoding="utf-8")
    http_activation = application_nginx.split("location ^~ /activate/ {", maxsplit=1)[1].split("}", maxsplit=1)[0]
    assert "$request_uri" not in http_activation
    assert "return 303 https://$host/;" in http_activation
    compose = (root / "docker-compose.production.yml").read_text(encoding="utf-8")
    assert "--no-access-log" in compose


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
