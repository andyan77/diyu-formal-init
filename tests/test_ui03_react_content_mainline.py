from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import cast
from uuid import uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

import src.gateway.api.app as app_module
from src.brain.content_service import ContentService
from src.composition.bootstrap import build_content_control_service
from src.gateway.api.settings import Settings
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.production_auth import ProductionAuthRepository, TenantSession
from src.infrastructure.seed_demo import (
    ACCOUNT_ID,
    BRAND_ID,
    HEADQUARTERS_WECHAT_CHANNELS_ACCOUNT_ID,
    HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID,
    ORG_ID,
    ROLE_ID,
    STORE_CONTENT_ACCOUNT_ID,
    STORE_ORG_ID,
    TENANT_ID,
)
from src.tool.llm_gateway.stub import DeterministicContentGenerator


def _settings(database_url: str) -> Settings:
    return Settings.model_validate(
        {
            "DIYU_RUNTIME_MODE": "production",
            "DIYU_APP_DATABASE_URL": database_url,
            "DIYU_SESSION_SECRET": "ui03-production-path-session-secret",
            "DIYU_GENERATOR_MODE": "deepseek",
            "DEEPSEEK_API_BASE_URL": "https://example.invalid",
            "DEEPSEEK_API_KEY": "not-a-real-key",
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
            "DEEPSEEK_REVIEWER_MODEL": "deepseek-v4-pro",
            "DIYU_S3_ENDPOINT_URL": "http://127.0.0.1:9000",
            "DIYU_S3_BUCKET": "diyu-test",
            "DIYU_S3_ACCESS_KEY_ID": "test-access-key",
            "DIYU_S3_SECRET_ACCESS_KEY": "test-secret-key",
        }
    )


def _bootstrap(response_text: str) -> dict[str, object]:
    marker = "<script>window.__DIYU_BOOTSTRAP__="
    payload = response_text.split(marker, maxsplit=1)[1].split(";</script>", maxsplit=1)[0]
    value = json.loads(payload)
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _task_count(database_url: str) -> int:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM business_tasks WHERE tenant_id = %s",
            (TENANT_ID,),
        )
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])


def _stub_builder(settings: Settings) -> ContentService:
    return ContentService(
        PostgresContentRepository(settings.app_database_url),
        DeterministicContentGenerator(),
        build_content_control_service(settings),
    )


def test_production_session_api_and_postgres_form_one_v1_v2_v1_chain(
    app_database_url: str,
    migrator_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        app_module,
        "build_content_service",
        cast(Callable[[Settings], ContentService], _stub_builder),
    )
    headquarters_user_id = uuid4()
    store_user_id = uuid4()
    headquarters_name = f"UI-03 总部内容夹具-{headquarters_user_id.hex[:8]}"
    store_name = f"UI-03 门店内容夹具-{store_user_id.hex[:8]}"
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            """
            INSERT INTO users (id, tenant_id, organization_id, display_name)
            VALUES (%s, %s, %s, %s)
            """,
            (headquarters_user_id, TENANT_ID, ORG_ID, headquarters_name),
        )
        cursor.execute(
            """
            INSERT INTO users (id, tenant_id, organization_id, display_name)
            VALUES (%s, %s, %s, %s)
            """,
            (store_user_id, TENANT_ID, STORE_ORG_ID, store_name),
        )
        for account_id in (
            ACCOUNT_ID,
            HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID,
            HEADQUARTERS_WECHAT_CHANNELS_ACCOUNT_ID,
        ):
            cursor.execute(
                """
                INSERT INTO auth_grants
                    (id, tenant_id, user_id, account_id, role_name)
                VALUES (%s, %s, %s, %s, 'UI-03 正式内容链')
                """,
                (uuid4(), TENANT_ID, headquarters_user_id, account_id),
            )
        cursor.execute(
            """
            INSERT INTO auth_grants
                (id, tenant_id, user_id, account_id, role_name)
            VALUES (%s, %s, %s, %s, 'UI-03 门店内容链')
            """,
            (uuid4(), TENANT_ID, store_user_id, STORE_CONTENT_ACCOUNT_ID),
        )
    repository = ProductionAuthRepository(app_database_url)
    headquarters_token = repository.create_tenant_session(TenantSession(TENANT_ID, headquarters_user_id, "tenant-user"))
    store_token = repository.create_tenant_session(TenantSession(TENANT_ID, store_user_id, "tenant-user"))
    app: FastAPI = app_module.create_app(_settings(app_database_url))
    try:
        with TestClient(app, base_url="https://diyuai.cc") as client:
            client.cookies.set("diyu_session", headquarters_token)
            content_page = client.get("/content?target=xiaohongshu_graphic")
            assert content_page.status_code == 200, content_page.text
            headquarters = _bootstrap(content_page.text)
            assert headquarters["application"] == "content"
            assert headquarters["current_target"] == "xiaohongshu_graphic"
            headquarters_identity = cast(dict[str, str], headquarters["identity"])
            assert headquarters_identity["account"] == "折线之间品牌母账号·抖音"
            assert headquarters_identity["content_role"] == "总部零售/服务专家"

            catalog = client.get("/api/v1/content/expression-catalog").json()
            options = [option for axis in catalog["axes"] for option in axis["options"]]
            assert len(options) == 21
            assert all(not option["body_related"] for option in options)

            before = _task_count(migrator_database_url)
            unavailable_custom = client.post(
                "/api/v1/content",
                json={
                    "weak_seed": "请按这个方向写一条完整内容。",
                    "target": "xiaohongshu_graphic",
                    "creative_direction": {
                        "catalog_version": catalog["catalog_version"],
                        "selections": {},
                        "cleared_axes": [],
                        "custom_text": "上新直播",
                        "body_related_opt_in": False,
                    },
                },
            )
            assert unavailable_custom.status_code == 422
            assert "暂不能稳定完成" in unavailable_custom.json()["detail"]
            assert _task_count(migrator_database_url) == before

            body_option = "CAT-TOPIC-BODY-01"
            hidden_submission = client.post(
                "/api/v1/content",
                json={
                    "weak_seed": "请写一条内容，讲清楚今天这个选择。",
                    "target": "xiaohongshu_graphic",
                    "creative_direction": {
                        "catalog_version": catalog["catalog_version"],
                        "selections": {"topic": body_option},
                        "cleared_axes": [],
                        "custom_text": "",
                        "body_related_opt_in": False,
                    },
                },
            )
            assert hidden_submission.status_code == 422
            assert _task_count(migrator_database_url) == before
            # The production limiter intentionally refuses two model-bound submissions from the
            # same person inside two seconds, even when the first one fails before task creation.
            time.sleep(2.05)

            v1_response = client.post(
                "/api/v1/content",
                json={
                    "weak_seed": "走进门店只想自己看看，不用先解释，请写一条完整内容。",
                    "target": "xiaohongshu_graphic",
                    "creative_direction": {
                        "catalog_version": catalog["catalog_version"],
                        "selections": {},
                        "cleared_axes": [],
                        "custom_text": "像熟悉品牌的人自然说，不用口号。",
                        "body_related_opt_in": False,
                    },
                    "material_ids": [],
                },
            )
            assert v1_response.status_code == 200, v1_response.text
            v1 = v1_response.json()
            assert v1["version"] == 1
            assert v1["target_key"] == "xiaohongshu_graphic"
            # This integration test deliberately injects the repository's deterministic fixture
            # at the generator port, so it proves auth/API/PostgreSQL/version semantics without
            # pretending that a model ran. Real DeepSeek and AIGC disclosure evidence remains the
            # closed M7-2B/M7-3 production evidence.
            assert v1["ai_generated"] is False
            assert v1["aigc_label"] is None
            assert v1["aigc_release_reminder"] is None
            time.sleep(2.05)

            v2_response = client.post(
                f"/api/v1/tasks/{v1['task_id']}/revisions",
                json={
                    "instruction": "判断保留，但改成一人面对手机能自然说出的版本。",
                    "target": "xiaohongshu_graphic",
                    "source_target": "xiaohongshu_graphic",
                },
            )
            assert v2_response.status_code == 201, v2_response.text
            v2 = v2_response.json()
            assert v2["version"] == 2
            assert v2["version_id"] != v1["version_id"]

            replayed_v1 = client.get(f"/api/v1/tasks/{v1['task_id']}/versions/1?target=xiaohongshu_graphic")
            assert replayed_v1.status_code == 200
            assert replayed_v1.json()["version_id"] == v1["version_id"]
            assert replayed_v1.json()["body"] == v1["body"]
            history = client.get(f"/api/v1/content/tasks/{v1['task_id']}/versions?target=xiaohongshu_graphic")
            assert history.status_code == 200
            assert [item["version"] for item in history.json()] == [2, 1]

            with (
                psycopg.connect(migrator_database_url, row_factory=dict_row) as evidence_connection,
                evidence_connection.cursor() as cursor,
            ):
                cursor.execute(
                    """
                    SELECT used_assets, input_receipt
                    FROM generation_runs
                    WHERE tenant_id = %s AND task_id = %s
                    ORDER BY started_at
                    """,
                    (TENANT_ID, v1["task_id"]),
                )
                runs = cursor.fetchall()
            assert len(runs) == 2
            assert all(
                all(
                    set(asset) == {"asset_id", "schema_version"}
                    for asset in cast(list[dict[str, str]], run["used_assets"])
                )
                for run in runs
            )
            assert cast(dict[str, object], runs[0]["input_receipt"])["target"] == "xiaohongshu_graphic"

            client.cookies.set("diyu_session", store_token)
            store_page = client.get("/content?target=douyin_video")
            assert store_page.status_code == 200
            store = _bootstrap(store_page.text)
            assert store["application"] == headquarters["application"]
            store_identity = cast(dict[str, str], store["identity"])
            assert store_identity["account"] != headquarters_identity["account"]
            assert store_identity["content_role"] != headquarters_identity["content_role"]

            forbidden_admin = client.get("/tenant-admin", follow_redirects=False)
            assert forbidden_admin.status_code == 403
            assert forbidden_admin.headers["content-type"].startswith("text/html")
            assert "当前账号没有租户管理资格" in forbidden_admin.text
            forbidden_api = client.get("/api/v1/tenant-management/operators")
            assert forbidden_api.status_code == 403
            assert forbidden_api.headers["content-type"].startswith("application/json")
    finally:
        repository.revoke_tenant_session(headquarters_token)
        repository.revoke_tenant_session(store_token)


def test_content_page_resolves_a_stable_default_from_each_formal_session(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    xiaohongshu_user_id = uuid4()
    wechat_user_id = uuid4()
    douyin_user_id = uuid4()
    xiaohongshu_account_id = uuid4()
    wechat_account_id = uuid4()
    fixtures = (
        (
            xiaohongshu_user_id,
            xiaohongshu_account_id,
            ORG_ID,
            "小红书",
            "xiaohongshu_video",
        ),
        (
            wechat_user_id,
            wechat_account_id,
            ORG_ID,
            "微信视频号",
            "wechat_channels_video",
        ),
    )
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        for user_id, account_id, organization_id, channel, _ in fixtures:
            suffix = user_id.hex[:8]
            cursor.execute(
                """
                INSERT INTO users (id, tenant_id, organization_id, display_name)
                VALUES (%s, %s, %s, %s)
                """,
                (user_id, TENANT_ID, organization_id, f"UI-03 {channel}默认目标夹具-{suffix}"),
            )
            cursor.execute(
                """
                INSERT INTO content_accounts (id, tenant_id, brand_id, name, channel)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (account_id, TENANT_ID, BRAND_ID, f"UI-03 {channel}单平台账号-{suffix}", channel),
            )
            cursor.execute(
                """
                INSERT INTO auth_grants (id, tenant_id, user_id, account_id, role_name)
                VALUES (%s, %s, %s, %s, 'UI-03 单平台默认目标')
                """,
                (uuid4(), TENANT_ID, user_id, account_id),
            )
            cursor.execute(
                """
                INSERT INTO account_content_roles (id, tenant_id, account_id, content_role_id)
                VALUES (%s, %s, %s, %s)
                """,
                (uuid4(), TENANT_ID, account_id, ROLE_ID),
            )
        cursor.execute(
            """
            INSERT INTO users (id, tenant_id, organization_id, display_name)
            VALUES (%s, %s, %s, %s)
            """,
            (douyin_user_id, TENANT_ID, ORG_ID, f"UI-03 抖音默认目标夹具-{douyin_user_id.hex[:8]}"),
        )
        cursor.execute(
            """
            INSERT INTO auth_grants (id, tenant_id, user_id, account_id, role_name)
            VALUES (%s, %s, %s, %s, 'UI-03 抖音默认目标')
            """,
            (uuid4(), TENANT_ID, douyin_user_id, ACCOUNT_ID),
        )

    repository = ProductionAuthRepository(app_database_url)
    sessions = {
        user_id: repository.create_tenant_session(TenantSession(TENANT_ID, user_id, "tenant-user"))
        for user_id in (xiaohongshu_user_id, wechat_user_id, douyin_user_id)
    }
    app: FastAPI = app_module.create_app(_settings(app_database_url))
    try:
        with TestClient(app, base_url="https://diyuai.cc") as client:
            for user_id, _, _, _, expected_target in fixtures:
                client.cookies.set("diyu_session", sessions[user_id])
                assert client.get("/user").status_code == 200
                content_page = client.get("/content")
                assert content_page.status_code == 200, content_page.text
                context = _bootstrap(content_page.text)
                assert context["current_target"] == expected_target
                assert expected_target in {item["value"] for item in cast(list[dict[str, str]], context["targets"])}

            client.cookies.set("diyu_session", sessions[xiaohongshu_user_id])
            forbidden = client.get(
                "/content?target=wechat_channels_video",
                follow_redirects=False,
            )
            assert forbidden.status_code == 403
            assert forbidden.headers["content-type"].startswith("text/html")
            assert "当前账号不能使用这个入口" in forbidden.text

            client.cookies.set("diyu_session", sessions[douyin_user_id])
            douyin_page = client.get("/content")
            assert douyin_page.status_code == 200
            assert _bootstrap(douyin_page.text)["current_target"] == "douyin_video"
    finally:
        for token in sessions.values():
            repository.revoke_tenant_session(token)
