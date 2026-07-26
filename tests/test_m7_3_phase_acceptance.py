from __future__ import annotations

import json
from typing import TypedDict, cast
from uuid import uuid4

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.production_auth import ProductionAuthRepository, TenantSession
from src.infrastructure.seed_demo import (
    ACCOUNT_ID,
    HEADQUARTERS_WECHAT_CHANNELS_ACCOUNT_ID,
    HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID,
    ORG_ID,
    STORE_ORG_ID,
    TENANT_ADMIN_USER_ID,
    TENANT_ID,
)


class _BootstrapIdentity(TypedDict, total=False):
    account: str
    content_role: str
    business_data_kind: str
    store: str


class _BootstrapTarget(TypedDict):
    value: str
    label: str


class _Bootstrap(TypedDict, total=False):
    application: str
    formal_runtime: bool
    current_target: str
    identity: _BootstrapIdentity
    targets: list[_BootstrapTarget]


def _production_settings(database_url: str) -> Settings:
    return Settings.model_validate(
        {
            "DIYU_RUNTIME_MODE": "production",
            "DIYU_APP_DATABASE_URL": database_url,
            "DIYU_SESSION_SECRET": "m7-3-local-session-secret",
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


def _bootstrap(app: FastAPI, token: str, path: str) -> _Bootstrap:
    with TestClient(app, base_url="https://diyuai.cc") as client:
        client.cookies.set("diyu_session", token)
        response = client.get(path)
    assert response.status_code == 200, response.text
    marker = "<script>window.__DIYU_BOOTSTRAP__="
    serialized = response.text.split(marker, maxsplit=1)[1].split(";</script>", maxsplit=1)[0]
    payload = json.loads(serialized)
    assert isinstance(payload, dict)
    return cast(_Bootstrap, payload)


def test_formal_pages_freeze_their_route_specific_context_in_the_spa_bootstrap(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    content_user_id = uuid4()
    display_user_id = uuid4()
    admin_user_id = uuid4()
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        for user_id, organization_id, display_name in (
            (content_user_id, ORG_ID, "M7-3 路由内容夹具"),
            (display_user_id, STORE_ORG_ID, "M7-3 路由陈列夹具"),
            (admin_user_id, ORG_ID, "M7-3 路由管理夹具"),
        ):
            cursor.execute(
                "INSERT INTO users (id, tenant_id, organization_id, display_name) VALUES (%s, %s, %s, %s)",
                (user_id, TENANT_ID, organization_id, display_name),
            )
        for account_id in (
            ACCOUNT_ID,
            HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID,
            HEADQUARTERS_WECHAT_CHANNELS_ACCOUNT_ID,
        ):
            cursor.execute(
                """
                INSERT INTO auth_grants (id, tenant_id, user_id, account_id, role_name)
                VALUES (%s, %s, %s, %s, 'M7-3 路由验收')
                """,
                (uuid4(), TENANT_ID, content_user_id, account_id),
            )
        cursor.execute(
            """
            INSERT INTO tenant_management_grants (id, tenant_id, user_id)
            VALUES (%s, %s, %s)
            """,
            (uuid4(), TENANT_ID, admin_user_id),
        )
    repository = ProductionAuthRepository(app_database_url)
    identities = {
        "content": TenantSession(TENANT_ID, content_user_id, "tenant-user"),
        "display": TenantSession(TENANT_ID, display_user_id, "tenant-user"),
        "admin": TenantSession(TENANT_ID, admin_user_id, "tenant-admin"),
    }
    tokens = {name: repository.create_tenant_session(identity) for name, identity in identities.items()}
    app = create_app(_production_settings(app_database_url))
    try:
        content = _bootstrap(
            app,
            tokens["content"],
            "/content?target=xiaohongshu_graphic",
        )
        assert content["application"] == "content"
        assert content["formal_runtime"] is True
        assert content["identity"]["account"] == "折线之间品牌母账号·小红书"
        assert content["identity"]["content_role"] == "总部零售/服务专家"
        assert content["identity"]["business_data_kind"] == "formal_business_data"
        assert content["current_target"] == "xiaohongshu_graphic"
        assert [item["value"] for item in content["targets"]] == [
            "douyin_video",
            "xiaohongshu_video",
            "xiaohongshu_graphic",
            "wechat_channels_video",
        ]

        display = _bootstrap(app, tokens["display"], "/display")
        assert display["application"] == "display"
        assert display["formal_runtime"] is True
        assert display["identity"]["store"] == "折线之间·南城店"

        user = _bootstrap(app, tokens["content"], "/user")
        assert user["application"] == "tenant_user"
        assert user["formal_runtime"] is True
        assert "account" not in user["identity"]

        admin = _bootstrap(app, tokens["admin"], "/tenant-admin")
        assert admin["application"] == "tenant_management"
        assert admin["formal_runtime"] is True
        assert "account" not in admin["identity"]
    finally:
        for token in tokens.values():
            repository.revoke_tenant_session(token)
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
            cursor.execute(
                "DELETE FROM tenant_management_grants WHERE tenant_id = %s AND user_id = %s",
                (TENANT_ID, admin_user_id),
            )
            cursor.execute(
                "DELETE FROM auth_grants WHERE tenant_id = %s AND user_id = %s",
                (TENANT_ID, content_user_id),
            )
            cursor.execute(
                "DELETE FROM users WHERE tenant_id = %s AND id = ANY(%s)",
                (TENANT_ID, [content_user_id, display_user_id, admin_user_id]),
            )


def test_formal_pages_recover_to_login_without_changing_json_api_failures(
    app_database_url: str,
) -> None:
    repository = ProductionAuthRepository(app_database_url)
    admin_token = repository.create_tenant_session(
        TenantSession(TENANT_ID, TENANT_ADMIN_USER_ID, "tenant-admin")
    )
    app = create_app(_production_settings(app_database_url))
    try:
        with TestClient(app, base_url="https://diyuai.cc") as client:
            expected_logins = {
                "/user": "/login",
                "/content": "/login",
                "/display": "/login",
                "/tenant-admin": "/tenant-admin/login",
                "/ops": "/ops/login",
            }
            for path, login_path in expected_logins.items():
                response = client.get(path, follow_redirects=False)
                assert response.status_code == 303
                assert response.headers["location"] == login_path

            anonymous_api = client.get("/api/v1/content/tasks")
            assert anonymous_api.status_code == 401
            assert anonymous_api.headers["content-type"].startswith(
                "application/json"
            )
            assert "detail" in anonymous_api.json()

            client.cookies.set("diyu_session", admin_token)
            for path in ("/user", "/content", "/display"):
                forbidden_page = client.get(path, follow_redirects=False)
                assert forbidden_page.status_code == 403
                assert forbidden_page.headers["content-type"].startswith("text/html")
                assert "当前账号不能使用这个入口" in forbidden_page.text
                assert "返回租户管理入口" in forbidden_page.text
                assert "/tenant-admin/logout?next=user" in forbidden_page.text
                assert '{"detail":' not in forbidden_page.text

            forbidden_api = client.get("/api/v1/content/tasks")
            assert forbidden_api.status_code == 403
            assert forbidden_api.headers["content-type"].startswith(
                "application/json"
            )
            assert "detail" in forbidden_api.json()

            signed_out = client.post(
                "/tenant-admin/logout?next=user",
                follow_redirects=False,
            )
            assert signed_out.status_code == 303
            assert signed_out.headers["location"] == "/login"
            assert 'diyu_session="";' in signed_out.headers["set-cookie"]
            assert client.get("/content", follow_redirects=False).status_code == 303
            assert repository.load_tenant_session(admin_token) is None
    finally:
        repository.revoke_tenant_session(admin_token)
