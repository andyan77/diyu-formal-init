from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.seed_demo import ACCOUNT_ID, ACCOUNT_ROLE_ID, ROLE_ID, TENANT_ID
from src.infrastructure.system_asset_catalog import import_system_asset_catalog
from tests.conftest import SIBLING_ACCOUNT_ID, SIBLING_BRAND_ID, SIBLING_USER_ID

_SEED = "下午开完一个挺正式的会，转身去接孩子。"
_GOVERNANCE = (
    Path(__file__).resolve().parents[1]
    / "首批领域数据库知识数据"
    / "第五批：评测与导入包"
    / "12-系统资产运行治理-v1.json"
)


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
    assert {
        item
        for item in activated
        if item in {"B-TPO-001", "C-COMMUTE-001", "D-DIRECT-001", "D-CRAFT-001"}
    } == {
        "B-TPO-001",
        "C-COMMUTE-001",
        "D-CRAFT-001",
        "D-DIRECT-001",
    }


def test_generation_save_and_reuse_do_not_change_system_knowledge_catalog(app_database_url: str) -> None:
    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT a.asset_id, a.status, a.valid_until, a.superseded_by, x.consumer, x.applicability
            FROM system_domain_assets a LEFT JOIN system_asset_activations x ON x.asset_id = a.asset_id
            ORDER BY a.asset_id
            """
        )
        before = cursor.fetchall()

    with TestClient(create_app(Settings.model_validate({}))) as client:
        assert client.get("/ui/select/content").status_code == 200
        created = client.post("/api/v1/content", json={"weak_seed": _SEED})
        assert created.status_code == 200
        saved = client.post(f"/api/v1/content-versions/{created.json()['version_id']}/save")
        assert saved.status_code == 200
        reused = client.post("/api/v1/content", json={"weak_seed": "接着上一条的判断，写成另一篇独立提醒。"})
        assert reused.status_code == 200

    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT a.asset_id, a.status, a.valid_until, a.superseded_by, x.consumer, x.applicability
            FROM system_domain_assets a LEFT JOIN system_asset_activations x ON x.asset_id = a.asset_id
            ORDER BY a.asset_id
            """
        )
        after = cursor.fetchall()
    assert after == before


def test_catalog_reconciles_activation_set_and_rolls_back_invalid_governance(
    migrator_database_url: str,
    tmp_path: Path,
) -> None:
    governance = json.loads(_GOVERNANCE.read_text(encoding="utf-8"))
    changed = deepcopy(governance)
    changed["assets"] = [asset for asset in changed["assets"] if asset["asset_id"] != "B-TPO-001"]
    changed_path = tmp_path / "without-b-tpo.json"
    changed_path.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
    try:
        import_system_asset_catalog(changed_path)
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT asset_id FROM system_asset_activations WHERE asset_id = 'B-TPO-001'")
            assert cursor.fetchone() is None
            cursor.execute("SELECT status FROM system_domain_assets WHERE asset_id = 'B-TPO-001'")
            assert cursor.fetchone() == ("review_candidate",)

        invalid = deepcopy(changed)
        invalid["assets"][0]["superseded_by"] = "UNKNOWN-ASSET"
        invalid_path = tmp_path / "invalid-governance.json"
        invalid_path.write_text(json.dumps(invalid, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(RuntimeError):
            import_system_asset_catalog(invalid_path)
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT asset_id FROM system_asset_activations WHERE asset_id = 'B-TPO-001'")
            assert cursor.fetchone() is None
    finally:
        import_system_asset_catalog()


def test_runtime_excludes_expired_and_superseded_active_assets(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    cases = (
        (
            "UPDATE system_domain_assets SET valid_until = %s WHERE asset_id = 'B-TPO-001'",
            "2000-01-01",
            "UPDATE system_domain_assets SET valid_until = NULL WHERE asset_id = 'B-TPO-001'",
        ),
        (
            "UPDATE system_domain_assets SET superseded_by = %s WHERE asset_id = 'B-TPO-001'",
            "D-DIRECT-001",
            "UPDATE system_domain_assets SET superseded_by = NULL WHERE asset_id = 'B-TPO-001'",
        ),
    )
    for apply, value, restore in cases:
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute(apply, (value,))
        try:
            with TestClient(create_app(Settings.model_validate({}))) as client:
                client.get("/ui/select/content")
                created = client.post("/api/v1/content", json={"weak_seed": _SEED})
                assert created.status_code == 200
            with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
                cursor.execute(
                    "SELECT used_assets FROM generation_runs WHERE task_id = %s ORDER BY started_at DESC LIMIT 1",
                    (created.json()["task_id"],),
                )
                row = cursor.fetchone()
            assert row is not None
            assert "B-TPO-001" not in {asset["asset_id"] for asset in row[0]}
        finally:
            with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
                cursor.execute(restore)


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
    assert {
        asset["asset_id"]
        for asset in not_applicable_row[0]
        if not asset["asset_id"].startswith("E-")
    } == {
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
