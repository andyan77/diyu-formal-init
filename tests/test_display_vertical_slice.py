from __future__ import annotations

import psycopg
from fastapi.testclient import TestClient

from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.seed_demo import TENANT_ID

_INVENTORY = "今天这组墙可用：ZX-C218 3 件、ZX-S104 3 件、ZX-K126 4 件、ZX-P211 3 件、ZX-V113 3 件、ZX-Q117 4 件。"
_FEEDBACK = (
    "左侧主焦点和下杆都没问题；右上正挂袖子压到旁边马甲，最靠近的一件不好拿。其他位置都没变。"
)


def test_display_v1_v2_preserves_history_and_records_dm01_assets(app_database_url: str) -> None:
    with TestClient(create_app(Settings.model_validate({}))) as client:
        assert client.get("/display").status_code == 200
        created = client.post("/api/v1/display", json={"inventory_text": _INVENTORY})
        assert created.status_code == 200
        v1 = created.json()
        assert v1["version"] == 1
        assert "15 件上墙" in v1["body"]
        revised = client.post(
            f"/api/v1/display-tasks/{v1['task_id']}/revisions", json={"feedback": _FEEDBACK}
        )
        assert revised.status_code == 201
        v2 = revised.json()
        assert v2["version"] == 2
        assert "14 件上墙" in v2["body"]
        assert (
            client.get(f"/api/v1/display-tasks/{v1['task_id']}/versions/1").json()["body"]
            == v1["body"]
        )
        changed = client.post(
            "/api/v1/display", json={"inventory_text": _INVENTORY.replace("ZX-C218 3", "ZX-C218 1")}
        )
        assert "取消同款右侧回应" in changed.json()["body"]
    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            "SELECT used_assets FROM display_generation_runs WHERE task_id=%s ORDER BY started_at LIMIT 1",
            (v1["task_id"],),
        )
        row = cursor.fetchone()
    assert row is not None
    assert len(row[0]) == 11
    assert all(item["asset_id"].startswith(("G-", "GM-")) for item in row[0])
