from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.production_auth import ProductionAuthRepository, TenantSession
from src.infrastructure.seed_demo import (
    STORE_CONTENT_ACCOUNT_ID,
    STORE_CONTENT_USER_ID,
    TENANT_ID,
)
from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.shared.errors import GenerationFailed
from src.shared.types import GenerationInput, TenantManagementScope
from src.tool.llm_gateway.stub import DeterministicContentGenerator


def _row(
    database_url: str,
    sql: str,
    params: tuple[object, ...],
) -> dict[str, Any]:
    with (
        psycopg.connect(database_url, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(sql, params)
        row = cursor.fetchone()
    assert row is not None
    return dict(row)


def test_series_generation_freezes_real_prior_versions_and_revisions_replay_them(
    app_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[GenerationInput] = []
    original = DeterministicContentGenerator.generate

    def capture(
        self: DeterministicContentGenerator,
        request: GenerationInput,
    ) -> Any:
        captured.append(request)
        return original(self, request)

    monkeypatch.setattr(DeterministicContentGenerator, "generate", capture)
    with TestClient(create_app(Settings.model_validate({}))) as client:
        client.get("/ui/select/content")
        created = client.post(
            "/api/v1/content/series",
            json={
                "title": f"M7-2B 连续系列 {uuid4()}",
                "premise": "每篇从同一个长期问题的不同侧面继续。",
            },
        ).json()
        first = client.post(
            "/api/v1/content",
            json={
                "weak_seed": "写一条内容：走进门店只想自己看看，沉默也应该被尊重。",
                "series_id": created["id"],
                "series_position": 1,
            },
        )
        assert first.status_code == 200
        first_value = first.json()
        assert captured[-1].series_context is not None
        assert captured[-1].series_context.prior_entries == ()

        second = client.post(
            "/api/v1/content",
            json={
                "weak_seed": "接着这个系列做下一篇，换一个现实处境继续这个判断。",
                "series_id": created["id"],
            },
        )
        assert second.status_code == 200
        second_value = second.json()
        frozen = captured[-1].series_context
        assert frozen is not None
        assert frozen.target_position == 2
        assert [str(item.version_id) for item in frozen.prior_entries] == [first_value["version_id"]]
        assert frozen.prior_entries[0].body == first_value["body"]

        reset = client.post(
            f"/api/v1/content/series/{created['id']}/reset",
            json={},
        )
        assert reset.status_code == 200
        revised = client.post(
            f"/api/v1/tasks/{second_value['task_id']}/revisions",
            json={
                "instruction": "判断保留，改成一人面对手机能自然说出的版本。",
                "target": "douyin_video",
                "source_target": "douyin_video",
            },
        )
        assert revised.status_code == 201
        replayed = captured[-1].series_context
        assert replayed == frozen
        assert client.get(f"/api/v1/content/tasks/{second_value['task_id']}/versions").json()[0]["version"] == 2


def test_failed_series_generation_writes_no_series_item_or_partial_version(
    app_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(
        self: DeterministicContentGenerator,
        request: GenerationInput,
    ) -> Any:
        del self, request
        raise GenerationFailed("定向失败")

    monkeypatch.setattr(DeterministicContentGenerator, "generate", fail)
    with TestClient(create_app(Settings.model_validate({}))) as client:
        client.get("/ui/select/content")
        series = client.post(
            "/api/v1/content/series",
            json={"title": f"失败原子性 {uuid4()}", "premise": "只验证失败边界。"},
        ).json()
        response = client.post(
            "/api/v1/content",
            json={
                "weak_seed": "写一条内容，验证失败时不进入系列。",
                "series_id": series["id"],
            },
        )
        assert response.status_code == 422
        current = next(item for item in client.get("/api/v1/content/series").json() if item["id"] == series["id"])
        assert current["items"] == []
    audit = _row(
        app_database_url,
        """
        SELECT run.status,
               (SELECT count(*) FROM content_versions version
                WHERE version.task_id = task.id) AS versions,
               (SELECT count(*) FROM content_series_items item
                WHERE item.task_id = task.id) AS series_items
        FROM business_tasks task
        JOIN generation_runs run
          ON run.task_id = task.id AND run.tenant_id = task.tenant_id
        WHERE task.weak_seed = %s
        ORDER BY task.created_at DESC
        LIMIT 1
        """,
        ("写一条内容，验证失败时不进入系列。",),
    )
    assert audit == {"status": "failed", "versions": 0, "series_items": 0}


def test_product_revision_replays_the_brand_confirmed_fact_version(
    app_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[GenerationInput] = []
    original = DeterministicContentGenerator.generate

    def capture(
        self: DeterministicContentGenerator,
        request: GenerationInput,
    ) -> Any:
        captured.append(request)
        return original(self, request)

    monkeypatch.setattr(DeterministicContentGenerator, "generate", capture)
    sku = f"PILOT-{uuid4().hex[:8].upper()}"
    with TestClient(create_app(Settings.model_validate({}))) as manager:
        manager.get("/ui/select/admin")
        saved = manager.put(
            "/api/v1/tenant-management/brand-products",
            json={
                "sku": sku,
                "display_name": "本轮真实商品",
                "category": "短外套",
                "colors": ["炭灰"],
                "material_or_structure": "双层结构",
                "silhouette": "直身短轮廓",
                "observable_features": "正面一排纽扣",
                "source_note": "当前品牌商品负责人当面提供",
                "applicability": "当前品牌正式内容",
                "confirm_as_current_brand_fact": True,
            },
        )
        assert saved.status_code == 200
        assert saved.json()["fact_version"] == 1

    with TestClient(create_app(Settings.model_validate({}))) as content:
        content.get("/ui/select/content")
        first = content.post(
            "/api/v1/content",
            json={"weak_seed": f"请解释商品 {sku} 的真实取舍。"},
        )
        assert first.status_code == 200
        task_id = first.json()["task_id"]
        assert captured[-1].products[0].fact_version == 1

    with TestClient(create_app(Settings.model_validate({}))) as manager:
        manager.get("/ui/select/admin")
        changed = manager.put(
            "/api/v1/tenant-management/brand-products",
            json={
                "sku": sku,
                "display_name": "本轮真实商品",
                "category": "短外套",
                "colors": ["炭灰", "深绿"],
                "material_or_structure": "双层结构",
                "silhouette": "直身短轮廓",
                "observable_features": "正面一排纽扣",
                "source_note": "当前品牌商品负责人补充",
                "applicability": "当前品牌正式内容",
                "confirm_as_current_brand_fact": True,
            },
        )
        assert changed.json()["fact_version"] == 2

    with TestClient(create_app(Settings.model_validate({}))) as content:
        content.get("/ui/select/content")
        revised = content.post(
            f"/api/v1/tasks/{task_id}/revisions",
            json={
                "instruction": "把解释说得更自然，事实不变。",
                "target": "douyin_video",
                "source_target": "douyin_video",
            },
        )
        assert revised.status_code == 201
        assert captured[-1].products[0].fact_version == 1
        snapshot = _row(
            app_database_url,
            "SELECT content_context_snapshot FROM business_tasks WHERE id = %s",
            (task_id,),
        )["content_context_snapshot"]
        assert snapshot["product_facts"][0]["fact_version"] == 1
        assert snapshot["product_facts"][0]["source_kind"] == "brand_user_confirmed"


def test_platform_scope_uses_the_explicit_carrier_relation(
    app_database_url: str,
) -> None:
    settings = Settings.model_validate({})
    carrier_id: UUID | None = None
    try:
        with TestClient(create_app(settings)) as manager:
            manager.get("/ui/select/admin")
            store_operator = next(
                item
                for item in manager.get("/api/v1/tenant-management/operators").json()
                if item["id"] == str(STORE_CONTENT_USER_ID)
            )
            created = manager.post(
                "/api/v1/tenant-management/platform-carriers",
                json={
                    "source_account_id": str(STORE_CONTENT_ACCOUNT_ID),
                    "name": "折线之间·南城店账号·小红书",
                    "channel": "小红书",
                    "operator_id": store_operator["id"],
                    "confirm_internal_carrier": True,
                },
            )
            assert created.status_code == 201
            carrier_id = UUID(created.json()["id"])

        repository = ProductionAuthRepository(settings.app_database_url)
        identity = TenantSession(TENANT_ID, STORE_CONTENT_USER_ID, "tenant-user")
        assert repository.content_scope(identity, "xiaohongshu_graphic").account_id == carrier_id
        assert repository.content_scope(identity, "douyin_video").account_id == STORE_CONTENT_ACCOUNT_ID
    finally:
        if carrier_id is not None:
            with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
                cursor.execute(
                    "DELETE FROM auth_grants WHERE tenant_id = %s AND account_id = %s",
                    (TENANT_ID, carrier_id),
                )
                cursor.execute(
                    "DELETE FROM account_content_roles WHERE tenant_id = %s AND account_id = %s",
                    (TENANT_ID, carrier_id),
                )
                cursor.execute(
                    "DELETE FROM content_accounts WHERE tenant_id = %s AND id = %s",
                    (TENANT_ID, carrier_id),
                )


def test_demo_acceptance_index_is_manager_scoped_and_uses_no_fallback_fixture() -> None:
    settings = Settings.model_validate({})
    with TestClient(create_app(settings)) as manager:
        manager.get("/ui/select/admin")
        response = manager.get("/api/v1/tenant-management/demo-content-index")
        assert response.status_code == 200
        assert response.json() == {
            "fixture_status": "not_ready",
            "fixture_label": "等深模拟业务资料",
            "boundary": (
                "组织关系、账号画像、商品和内容均为演示资料；生产代码、正式数据库、"
                "租户隔离和模型调用路径按正式能力运行。它不代表真实员工、真实在售"
                "商品、真实门店经营、真实发布或市场结果。"
            ),
            "safe_entry": (
                "由租户管理员为对应演示操作者生成一次性重置链接；本人设置独立密码"
                "后进入内容工作台。系统不提供共享密码，也不连接任何内容平台。"
            ),
            "identities": [],
        }

    with TestClient(create_app(settings)) as content_user:
        content_user.get("/ui/select/content")
        denied = content_user.get("/api/v1/tenant-management/demo-content-index")
        assert denied.status_code == 403


def test_demo_platform_index_selects_and_exposes_the_latest_complete_source_group() -> None:
    source_v4_id = uuid4()
    source_v6_id = uuid4()
    account_id = uuid4()

    def source_version(version: int, version_id: UUID) -> dict[str, object]:
        return {
            "version_id": str(version_id),
            "version": version,
            "title": "同一对衣服，三种配色主次",
            "body": "两件完整商品在同平面、同距离形成三种主次关系。",
            "platform": "抖音",
            "media": "视频",
            "ai_generated": True,
            "aigc_label": "AI 辅助生成",
            "aigc_release_reminder": "发布前请使用平台 AI 内容声明功能。",
            "translation_notice": "",
            "applied_direction": ["克制的冷幽默", "多图合集"],
            "created_at": datetime(2026, 7, 26, tzinfo=timezone.utc).isoformat(),
        }

    def platform_row(
        channel: str,
        parent_version_id: UUID,
        created_at: datetime,
    ) -> dict[str, object]:
        return {
            "id": uuid4(),
            "version_number": 1,
            "outline": f"{channel}平台版本",
            "body": "两件完整商品在同平面、同距离形成三种主次关系。",
            "created_at": created_at,
            "model": "deepseek-v4-flash",
            "content_context_snapshot": {},
            "channel": channel,
            "media_format": "graphic" if channel == "小红书" else "video",
            "parent_version_id": parent_version_id,
        }

    rows = [
        platform_row(
            "小红书",
            source_v6_id,
            datetime(2026, 7, 26, 2, tzinfo=timezone.utc),
        ),
        platform_row(
            "微信视频号",
            source_v6_id,
            datetime(2026, 7, 26, 2, tzinfo=timezone.utc),
        ),
        platform_row(
            "小红书",
            source_v4_id,
            datetime(2026, 7, 26, 1, tzinfo=timezone.utc),
        ),
        platform_row(
            "微信视频号",
            source_v4_id,
            datetime(2026, 7, 26, 1, tzinfo=timezone.utc),
        ),
    ]

    class DemoCursor:
        def execute(self, _query: str, _params: tuple[object, ...]) -> None:
            return None

        def fetchall(self) -> list[dict[str, object]]:
            return rows

    repository = PostgresWorkbenchRepository("postgresql://unused")
    projected = repository._demo_platform_versions(
        cast(Any, DemoCursor()),
        TenantManagementScope(TENANT_ID, uuid4(), uuid4()),
        account_id,
        [
            {
                "position": 3,
                "series_code": "H3",
                "versions": [
                    source_version(4, source_v4_id),
                    source_version(6, source_v6_id),
                ],
            }
        ],
    )

    assert len(projected) == 3
    source = next(item for item in projected if item["platform"] == "抖音")
    children = [item for item in projected if item["platform"] != "抖音"]
    assert source["version"] == 6
    assert source["source_label"] == "H3 V6"
    assert source["source_version_id"] == str(source_v6_id)
    assert source["parent_version_id"] is None
    assert {item["parent_version_id"] for item in children} == {str(source_v6_id)}
    assert {item["source_version_id"] for item in children} == {str(source_v6_id)}
    assert {item["source_label"] for item in children} == {"H3 V6"}
