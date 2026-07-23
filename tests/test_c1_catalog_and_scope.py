from __future__ import annotations

from dataclasses import replace

import psycopg
from fastapi.testclient import TestClient

from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.seed_demo import TENANT_ID
from tests.conftest import SIBLING_ACCOUNT_ID, SIBLING_BRAND_ID, SIBLING_USER_ID

_SEED = "下午开完一个挺正式的会，转身去接孩子。"


def test_catalog_is_idempotent_and_only_four_assets_are_active(migrator_database_url: str) -> None:
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE status = 'active') FROM system_domain_assets"
        )
        row = cursor.fetchone()
        cursor.execute("SELECT asset_id FROM system_asset_activations ORDER BY asset_id")
        activated = [row[0] for row in cursor.fetchall()]
    assert row is not None
    count, active = row
    assert count == 243
    assert active == 4
    assert activated == ["B-TPO-001", "C-COMMUTE-001", "D-CRAFT-001", "D-DIRECT-001"]


def test_run_records_only_applicable_active_asset_versions(app_database_url: str) -> None:
    with TestClient(create_app(Settings.model_validate({}))) as client:
        client.get("/")
        created = client.post("/api/v1/content", json={"weak_seed": _SEED})
        assert created.status_code == 200
        not_applicable = client.post(
            "/api/v1/content", json={"weak_seed": "下雨天骑车去上班，下午参加分享。"}
        )
        assert not_applicable.status_code == 200
    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            """
            SELECT used_assets FROM generation_runs
            WHERE task_id = %s ORDER BY started_at DESC LIMIT 1
            """,
            (created.json()["task_id"],),
        )
        row = cursor.fetchone()
        cursor.execute(
            """
            SELECT used_assets FROM generation_runs
            WHERE task_id = %s ORDER BY started_at DESC LIMIT 1
            """,
            (not_applicable.json()["task_id"],),
        )
        not_applicable_row = cursor.fetchone()
    assert row is not None
    assert {asset["asset_id"] for asset in row[0]} == {
        "B-TPO-001",
        "C-COMMUTE-001",
        "D-DIRECT-001",
        "D-CRAFT-001",
    }
    assert {asset["schema_version"] for asset in row[0]} == {"diyu_global_asset_v0.2"}
    assert not_applicable_row is not None
    assert {asset["asset_id"] for asset in not_applicable_row[0]} == {
        "D-DIRECT-001",
        "D-CRAFT-001",
    }


def test_same_tenant_other_brand_account_and_user_cannot_access_content() -> None:
    primary = Settings.model_validate({})
    sibling = replace(
        primary,
        demo_user_id=SIBLING_USER_ID,
        demo_brand_id=SIBLING_BRAND_ID,
        demo_account_id=SIBLING_ACCOUNT_ID,
    )
    with TestClient(create_app(primary)) as owner:
        owner.get("/")
        created = owner.post("/api/v1/content", json={"weak_seed": _SEED}).json()
    with TestClient(create_app(sibling)) as other:
        other.get("/")
        read = other.get(f"/api/v1/tasks/{created['task_id']}/versions/1")
        revise = other.post(
            f"/api/v1/tasks/{created['task_id']}/revisions", json={"instruction": "改写一下"}
        )
        save = other.post(f"/api/v1/content-versions/{created['version_id']}/save")
        reuse = other.post(
            "/api/v1/content",
            json={"weak_seed": "明确继续", "reuse_saved_version_id": created["version_id"]},
        )
    assert [read.status_code, revise.status_code, save.status_code, reuse.status_code] == [
        422,
        422,
        422,
        422,
    ]
