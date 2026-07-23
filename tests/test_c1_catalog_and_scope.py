from __future__ import annotations

from dataclasses import replace

import psycopg
from fastapi.testclient import TestClient

from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.seed_demo import ACCOUNT_ID, ACCOUNT_ROLE_ID, ROLE_ID, TENANT_ID
from tests.conftest import SIBLING_ACCOUNT_ID, SIBLING_BRAND_ID, SIBLING_USER_ID

_SEED = "下午开完一个挺正式的会，转身去接孩子。"


def test_catalog_is_idempotent_and_keeps_p1_and_dm01_activations_separate(
    migrator_database_url: str,
) -> None:
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
    assert active == 41
    assert len(activated) == 41
    assert {item for item in activated if item in {"B-TPO-001", "C-COMMUTE-001", "D-DIRECT-001", "D-CRAFT-001"}} == {
        "B-TPO-001",
        "C-COMMUTE-001",
        "D-CRAFT-001",
        "D-DIRECT-001",
    }


def test_run_records_only_applicable_active_asset_versions(app_database_url: str) -> None:
    with TestClient(create_app(Settings.model_validate({}))) as client:
        client.get("/ui/select/content")
        created = client.post("/api/v1/content", json={"weak_seed": _SEED})
        assert created.status_code == 200
        not_applicable = client.post(
            "/api/v1/content", json={"weak_seed": "下雨天骑车去上班，怎么穿才不狼狈？"}
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
    assert {"B-TPO-001", "C-COMMUTE-001", "D-DIRECT-001", "D-CRAFT-001"}.issubset(
        {asset["asset_id"] for asset in row[0]}
    )
    assert {asset["asset_id"] for asset in row[0] if asset["asset_id"].startswith("E-")} == {
        "E-FORM-001",
        "E-RESOURCE-002",
        "E-RESOURCE-003",
        "E-SOUND-001",
        "E-TIME-001",
        "E-VISUAL-001",
        "E-VISUAL-003",
    }
    assert not_applicable_row is not None
    assert {asset["asset_id"] for asset in not_applicable_row[0] if not asset["asset_id"].startswith("E-")} == {
        "D-DIRECT-001",
        "D-CRAFT-001",
    }
    assert {asset["schema_version"] for asset in row[0]} == {"diyu_global_asset_v0.2"}


def test_same_tenant_other_brand_account_and_user_cannot_access_content() -> None:
    primary = Settings.model_validate({})
    sibling = replace(
        primary,
        demo_user_id=SIBLING_USER_ID,
        demo_brand_id=SIBLING_BRAND_ID,
        demo_account_id=SIBLING_ACCOUNT_ID,
    )
    with TestClient(create_app(primary)) as owner:
        owner.get("/ui/select/content")
        created = owner.post("/api/v1/content", json={"weak_seed": _SEED}).json()
    with TestClient(create_app(sibling)) as other:
        other.get("/ui/select/content")
        read = other.get(f"/api/v1/tasks/{created['task_id']}/versions/1")
        revise = other.post(
            f"/api/v1/tasks/{created['task_id']}/revisions", json={"instruction": "改写一下"}
        )
        save = other.post(f"/api/v1/content-versions/{created['version_id']}/save")
        reuse = other.post(
            "/api/v1/content",
            json={"weak_seed": "明确继续", "reuse_version_id": created["version_id"]},
        )
    assert [read.status_code, revise.status_code, save.status_code, reuse.status_code] == [
        422,
        422,
        422,
        422,
    ]


def test_account_rejects_a_content_role_owned_by_another_same_tenant_brand(
    migrator_database_url: str,
) -> None:
    rogue_role_id = "00000000-0000-0000-0000-000000000052"
    rogue_link_id = "00000000-0000-0000-0000-000000000062"
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute("DELETE FROM account_content_roles WHERE id = %s", (ACCOUNT_ROLE_ID,))
        cursor.execute(
            """
            INSERT INTO content_roles (id, tenant_id, brand_id, name, voice_boundary)
            VALUES (%s, %s, %s, '错误品牌角色', '不得进入主品牌账号')
            ON CONFLICT (id) DO NOTHING
            """,
            (rogue_role_id, TENANT_ID, SIBLING_BRAND_ID),
        )
        cursor.execute(
            """
            INSERT INTO account_content_roles (id, tenant_id, account_id, content_role_id)
            VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
            """,
            (rogue_link_id, TENANT_ID, ACCOUNT_ID, rogue_role_id),
        )
    try:
        with TestClient(create_app(Settings.model_validate({}))) as client:
            client.get("/ui/select/content")
            response = client.post("/api/v1/content", json={"weak_seed": _SEED})
        assert response.status_code == 422
    finally:
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
            cursor.execute("DELETE FROM account_content_roles WHERE id = %s", (rogue_link_id,))
            cursor.execute("DELETE FROM content_roles WHERE id = %s", (rogue_role_id,))
            cursor.execute(
                """
                INSERT INTO account_content_roles (id, tenant_id, account_id, content_role_id)
                VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
                """,
                (ACCOUNT_ROLE_ID, TENANT_ID, ACCOUNT_ID, ROLE_ID),
            )
