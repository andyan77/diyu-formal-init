from __future__ import annotations

from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from src.brain.content_service import ContentService
from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.seed_demo import ACCOUNT_ID, BRAND_ID, TENANT_ID, USER_ID
from src.shared.errors import GenerationFailed
from src.shared.types import GenerationInput, TrustedScope
from src.tool.llm_gateway.stub import DeterministicP1Generator

_SEED = "下午开完一个挺正式的会，转身就拎着电脑去接孩子，站在校门口才发现自己还穿着会议那一身。"


class AiNamedTestGenerator(DeterministicP1Generator):
    @property
    def model_name(self) -> str:
        return "deepseek-v4-flash"


def test_p1_v1_v2_history_save_and_explicit_reuse() -> None:
    with TestClient(create_app(Settings.model_validate({}))) as client:
        assert client.get("/ui/select/content").status_code == 200
        created = client.post("/api/v1/content", json={"weak_seed": _SEED})
        assert created.status_code == 200
        v1 = created.json()
        assert v1["version"] == 1
        assert v1["kind"] == "content"
        assert v1["body"]

        revised = client.post(
            f"/api/v1/tasks/{v1['task_id']}/revisions",
            json={"instruction": "语气再轻一点，但保留边界和验证动作。"},
        )
        assert revised.status_code == 201
        v2 = revised.json()
        assert v2["version"] == 2
        assert v2["body"] != v1["body"]

        original = client.get(f"/api/v1/tasks/{v1['task_id']}/versions/1")
        assert original.status_code == 200
        assert original.json()["body"] == v1["body"]

        reused = client.post(
            "/api/v1/content",
            json={
                "weak_seed": "接着上一条的判断，写成另一篇独立提醒。",
            },
        )
        assert reused.status_code == 200
        assert reused.json()["task_id"] != v1["task_id"]

        saved = client.post(f"/api/v1/content-versions/{v2['version_id']}/save")
        assert saved.status_code == 200


def test_content_disclosure_uses_persisted_server_source_and_rejects_client_override(
    app_database_url: str,
) -> None:
    scope = TrustedScope(TENANT_ID, USER_ID, BRAND_ID, ACCOUNT_ID)
    service = ContentService(PostgresContentRepository(app_database_url), AiNamedTestGenerator())
    generated = service.create_from_weak_seed(scope, _SEED)
    assert generated["ai_generated"] is True
    assert generated["aigc_label"] == "AI 辅助生成"
    assert generated["aigc_release_reminder"] == "发布到当前平台前，请使用平台提供的 AI 内容声明功能；以发布页当前规则为准。"
    task_id = generated["task_id"]
    assert isinstance(task_id, str)
    assert service.fetch_version(scope, UUID(task_id), 1)["ai_generated"] is True

    with TestClient(create_app(Settings.model_validate({}))) as client:
        client.get("/ui/select/content")
        deterministic = client.post("/api/v1/content", json={"weak_seed": _SEED}).json()
        assert deterministic["ai_generated"] is False
        assert deterministic["aigc_label"] is None
        assert deterministic["aigc_release_reminder"] is None
        forged = client.post(
            "/api/v1/content",
            json={"weak_seed": _SEED, "ai_generated": True},
        )
    assert forged.status_code == 422


def test_workbench_renders_complete_artifact_without_internal_trace() -> None:
    with TestClient(create_app(Settings.model_validate({}))) as client:
        client.get("/ui/select/content")
        generated = client.post("/ui/generate", data={"weak_seed": _SEED}, follow_redirects=False)
        assert generated.status_code == 303
        page = client.get(generated.headers["location"])
        assert "内容概要" in page.text
        assert "完整文字成品" in page.text
        assert "自然导读" in page.text
        assert "完整台词/解说" in page.text
        assert "画面与动作" in page.text
        assert "字幕" in page.text
        assert "声音与制作提示" in page.text
        assert "离线确定性测试模式" in page.text
        assert "生成运行" not in page.text
        assert "提示词" not in page.text


def test_natural_chat_does_not_create_task(app_database_url: str) -> None:
    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute("SELECT COUNT(*) FROM business_tasks")
        before = cursor.fetchone()
    with TestClient(create_app(Settings.model_validate({}))) as client:
        client.get("/ui/select/content")
        responses = [
            client.post("/api/v1/content", json={"weak_seed": message})
            for message in ("hello world", "你好呀", "今天有点累")
        ]
    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute("SELECT COUNT(*) FROM business_tasks")
        after = cursor.fetchone()
    assert before is not None and after is not None
    assert all(response.status_code == 200 for response in responses)
    assert all(response.json()["kind"] == "greeting" for response in responses)
    assert all("你好" in response.json()["message"] for response in responses)
    assert before[0] == after[0]


def test_api_uses_cookie_scope_and_rejects_client_scope_switching() -> None:
    app = create_app(Settings.model_validate({}))
    with TestClient(app) as client:
        assert client.post("/api/v1/content", json={"weak_seed": "怎么穿"}).status_code == 401
        assert client.post("/ui/generate", data={"weak_seed": "怎么穿"}).status_code == 401
        client.get("/ui/select/content")
        switched = client.post(
            "/api/v1/content",
            json={"weak_seed": "怎么穿", "tenant_id": "not-accepted"},
        )
    contract = app.openapi()
    assert switched.status_code == 422
    assert "APIKeyCookie" in contract["components"]["securitySchemes"]
    assert contract["paths"]["/api/v1/content"]["post"]["responses"]["401"]
    assert contract["paths"]["/api/v1/content"]["post"]["responses"]["422"]
    ui_generate = contract["paths"]["/ui/generate"]["post"]
    assert ui_generate["responses"]["303"]
    assert ui_generate["security"]


def test_workbench_requires_cookie_before_reading_a_version() -> None:
    app = create_app(Settings.model_validate({}))
    with TestClient(app) as owner:
        owner.get("/ui/select/content")
        created = owner.post("/api/v1/content", json={"weak_seed": _SEED}).json()
    with TestClient(app) as stranger:
        response = stranger.get(f"/content?task={created['task_id']}&version=1")
    assert response.status_code == 401


def test_second_seed_and_personal_identifier_are_not_replayed() -> None:
    with TestClient(create_app(Settings.model_validate({}))) as client:
        client.get("/ui/select/content")
        golden = client.post("/api/v1/content", json={"weak_seed": _SEED}).json()
        second_seed = "下雨天骑车去上班，到了办公室还要参加下午的分享。"
        second = client.post("/api/v1/content", json={"weak_seed": second_seed}).json()
        personal = client.post(
            "/api/v1/content",
            json={"weak_seed": "一位顾客张三电话13800138000来问下雨天怎么穿。"},
        ).json()
    assert golden["body"] != second["body"]
    assert "会议" not in second["body"]
    assert "张三" not in personal["body"]
    assert "13800138000" not in personal["body"]


class FailingGenerator:
    @property
    def model_name(self) -> str:
        return "deterministic-failure"

    def route(self, request: object) -> str:
        return "dressing_decision"

    def generate(self, request: GenerationInput) -> object:
        raise GenerationFailed("测试性失败")


def test_failed_generation_records_run_but_no_partial_version(
    app_database_url: str,
) -> None:
    scope = TrustedScope(TENANT_ID, USER_ID, BRAND_ID, ACCOUNT_ID)
    service = ContentService(PostgresContentRepository(app_database_url), FailingGenerator())  # type: ignore[arg-type]
    with pytest.raises(GenerationFailed):
        service.create_from_weak_seed(scope, "下雨天骑车去上班，怎么穿才不狼狈？")

    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            """
            SELECT r.status, COUNT(v.id)
            FROM generation_runs r LEFT JOIN content_versions v ON v.run_id = r.id AND v.tenant_id = r.tenant_id
            WHERE r.tenant_id = %s AND r.model = 'deterministic-failure'
            GROUP BY r.id, r.status ORDER BY r.id DESC LIMIT 1
            """,
            (TENANT_ID,),
        )
        row = cursor.fetchone()
    assert row is not None
    status, versions = row
    assert status == "failed"
    assert versions == 0
