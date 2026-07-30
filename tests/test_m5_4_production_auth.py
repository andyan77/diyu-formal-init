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
            "DIYU_PUBLIC_URL": "https://diyuai.cc",
            "DIYU_GENERATOR_MODE": "deepseek",
            "DEEPSEEK_API_BASE_URL": "https://example.invalid",
            "DEEPSEEK_API_KEY": "not-a-real-key",
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
            "QWEN_REVIEWER_API_BASE_URL": "https://qwen.example.invalid",
            "DASHSCOPE_API_KEY": "not-a-real-qwen-key",
            "QWEN_REVIEWER_MODEL": "qwen3.7-max-2026-05-20",
            "DIYU_S3_ENDPOINT_URL": "http://127.0.0.1:9000",
            "DIYU_S3_BUCKET": "diyu-test",
            "DIYU_S3_ACCESS_KEY_ID": "test-access-key",
            "DIYU_S3_SECRET_ACCESS_KEY": "test-secret-key",
        }
    )


def test_production_requires_writer_but_no_reviewer_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QWEN_REVIEWER_API_BASE_URL", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_REVIEWER_MODEL", raising=False)
    configured = Settings.model_validate(
        {
            "DIYU_RUNTIME_MODE": "production",
            "DIYU_APP_DATABASE_URL": "postgresql://example.invalid/diyu",
            "DIYU_SESSION_SECRET": "production-test-session-secret",
            "DIYU_PUBLIC_URL": "https://diyuai.cc",
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
    assert configured.deepseek_model == "deepseek-v4-flash"
    assert not hasattr(configured, "qwen_reviewer_model")


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
        content_login = client.get("/login")
        assert "内容创作" in content_login.text
        assert "totp_code" not in content_login.text
        admin_login = client.get("/tenant-admin/login")
        assert "品牌管理" in admin_login.text
        assert "totp_code" not in admin_login.text
        assert "忘记密码" in admin_login.text
        ops_login = client.get("/ops/login")
        assert "笛语运维" in ops_login.text
        assert "name='totp_code'" in ops_login.text
        assert "身份验证器 6 位码" in ops_login.text
        activation_page = client.get(f"/activate/{admin_activation}")
        assert '"activation_purpose": "activate"' in activation_page.text
        assert "设置笛语密码" in activation_page.text
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


def test_ux02_admin_provisions_and_disables_content_user_with_trusted_full_url(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    _clear_auth_state(migrator_database_url)
    repository = ProductionAuthRepository(app_database_url)
    admin_username = f"ux02-admin-{uuid4().hex[:10]}"
    admin_token = repository.bootstrap_existing_tenant_admin(
        TENANT_ID,
        TENANT_ADMIN_USER_ID,
        admin_username,
    )
    app = create_app(_settings(app_database_url))
    admin_password = "ux02-admin-password-is-long"
    user_password = "ux02-user-password-is-long"
    username = f"ux02-user-{uuid4().hex[:10]}"

    with TestClient(app, base_url="https://diyuai.cc") as admin:
        activated = admin.post(
            f"/activate/{admin_token}",
            content=f"password={admin_password}",
            follow_redirects=False,
        )
        assert activated.status_code == 303
        signed_in = admin.post(
            "/tenant-admin/login",
            content=f"username={admin_username}&password={admin_password}",
            follow_redirects=False,
        )
        assert signed_in.status_code == 303

        missing_account = admin.post(
            "/api/v1/tenant-management/users",
            json={
                "display_name": f"UX-02 缺账号反证-{uuid4().hex[:8]}",
                "username": f"ux02-missing-{uuid4().hex[:10]}",
                "organization_id": str(ORG_ID),
                "entry_type": "tenant_user",
                "capabilities": ["content"],
                "publishing_identity_ids": [],
            },
        )
        assert missing_account.status_code == 422

        mixed_admin = admin.post(
            "/api/v1/tenant-management/users",
            json={
                "display_name": f"UX-02 混合入口反证-{uuid4().hex[:8]}",
                "username": f"ux02-mixed-{uuid4().hex[:10]}",
                "organization_id": str(ORG_ID),
                "entry_type": "tenant_admin",
                "grants_tenant_management": True,
                "capabilities": ["content"],
                "publishing_identity_ids": [str(ACCOUNT_ID)],
            },
        )
        assert mixed_admin.status_code == 422

        created_response = admin.post(
            "/api/v1/tenant-management/users",
            headers={"host": "attacker.invalid"},
            json={
                "display_name": f"UX-02 内容成员-{uuid4().hex[:8]}",
                "username": username,
                "organization_id": str(ORG_ID),
                "entry_type": "tenant_user",
                "capabilities": ["content"],
                "publishing_identity_ids": [str(ACCOUNT_ID)],
            },
        )
        assert created_response.status_code == 201
        created = created_response.json()
        assert created["activation_link"].startswith("/activate/")
        assert created["activation_url"] == (
            f"https://diyuai.cc{created['activation_link']}"
        )
        assert "attacker.invalid" not in created["activation_url"]

        with TestClient(app, base_url="https://diyuai.cc") as new_browser:
            activated_user = new_browser.post(
                created["activation_url"],
                content=f"password={user_password}",
                follow_redirects=False,
            )
            assert activated_user.status_code == 303
            assert activated_user.headers["location"] == "/login"
            user_login = new_browser.post(
                "/login",
                content=f"username={username}&password={user_password}",
                follow_redirects=False,
            )
            assert user_login.status_code == 303
            assert new_browser.get("/user").status_code == 200
            content_page = new_browser.get("/content")
            assert content_page.status_code == 200
            assert str(ACCOUNT_ID) in content_page.text

            disabled = admin.post(
                f"/api/v1/tenant-management/users/{created['user_id']}/disable"
            )
            assert disabled.status_code == 200
            stale = new_browser.get("/user", follow_redirects=False)
            assert stale.status_code == 303
            assert stale.headers["location"] == "/login"
            refused_login = new_browser.post(
                "/login",
                content=f"username={username}&password={user_password}",
            )
            assert refused_login.status_code == 401


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
    app = create_app(_settings(app_database_url))
    with TestClient(app, base_url="https://diyuai.cc") as client:
        reset_page = client.get(f"/activate/{second_reset}")
        assert reset_page.status_code == 200
        assert '"activation_purpose": "reset"' in reset_page.text
        assert "重新设置密码" in reset_page.text
    with pytest.raises(DomainError, match="无效或已过期"):
        repository.complete_activation(first_reset, "first-link-must-not-work")
    assert repository.complete_activation(second_reset, "second-link-works-once") == "tenant-user"
    with pytest.raises(DomainError, match="无效或已过期"):
        repository.complete_activation(second_reset, "second-link-must-not-work-twice")
    with TestClient(app, base_url="https://diyuai.cc") as client:
        used_reset_page = client.get(f"/activate/{second_reset}")
        assert '"activation_purpose": "reset"' in used_reset_page.text
        assert "重新设置密码" in used_reset_page.text
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


def test_tenant_admin_changes_password_without_exposing_or_keeping_old_sessions(
    app_database_url: str, migrator_database_url: str
) -> None:
    _clear_auth_state(migrator_database_url)
    repository = ProductionAuthRepository(app_database_url)
    username = f"password-admin-{uuid4().hex[:10]}"
    activation = repository.bootstrap_existing_tenant_admin(
        TENANT_ID,
        TENANT_ADMIN_USER_ID,
        username,
    )
    initial_password = "synthetic-initial-password"
    replacement_password = "synthetic-replacement-password"
    repository.complete_activation(activation, initial_password)
    identity = repository.authenticate_tenant_user(
        username,
        initial_password,
        "tenant-admin",
    )
    assert identity is not None
    second_session = repository.create_tenant_session(identity)

    app = create_app(_settings(app_database_url))
    with TestClient(app, base_url="https://diyuai.cc") as client:
        signed_in = client.post(
            "/tenant-admin/login",
            content=f"username={username}&password={initial_password}",
            follow_redirects=False,
        )
        assert signed_in.status_code == 303

        wrong_current = client.post(
            "/api/v1/auth/password",
            json={
                "current_password": "synthetic-wrong-password",
                "password": replacement_password,
            },
        )
        assert wrong_current.status_code == 401
        assert wrong_current.json() == {"detail": "当前密码不正确"}
        assert client.get("/tenant-admin").status_code == 200
        assert repository.load_tenant_session(second_session) == identity

        changed = client.post(
            "/api/v1/auth/password",
            json={
                "current_password": initial_password,
                "password": replacement_password,
            },
        )
        assert changed.status_code == 200
        assert changed.json() == {"changed": True}
        assert repository.load_tenant_session(second_session) is None
        stale_api = client.get("/api/v1/tenant-management/operators")
        assert stale_api.status_code == 401
        assert stale_api.headers["content-type"].startswith("application/json")

        assert (
            repository.authenticate_tenant_user(
                username,
                initial_password,
                "tenant-admin",
            )
            is None
        )
        assert (
            client.post(
                "/tenant-admin/login",
                content=f"username={username}&password={initial_password}",
                follow_redirects=False,
            ).status_code
            == 401
        )
        signed_in_again = client.post(
            "/tenant-admin/login",
            content=f"username={username}&password={replacement_password}",
            follow_redirects=False,
        )
        assert signed_in_again.status_code == 303
        assert signed_in_again.headers["location"] == "/tenant-admin"


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
