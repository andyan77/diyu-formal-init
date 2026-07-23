from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from src.brain.display_contract import assert_display_complete
from src.brain.display_service import DisplayService
from src.brain.dm01_display_compiler import DM01DisplayCompiler
from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.display_repository import PostgresDisplayRepository
from src.infrastructure.seed_demo import BRAND_ID, STORE_ORG_ID, STORE_USER_ID, TENANT_ID
from src.shared.errors import GenerationFailed
from src.shared.types import DisplayGenerationInput, DisplayScope

_INVENTORY = "今天这组墙可用：ZX-C218 3 件、ZX-S104 3 件、ZX-K126 4 件、ZX-P211 3 件、ZX-V113 3 件、ZX-Q117 4 件。"
_FEEDBACK = (
    "左侧主焦点和下杆都没问题；右上正挂袖子压到旁边马甲，最靠近的一件不好拿。其他位置都没变。"
)
_INVENTORY_PAIRS = (
    ("ZX-C218", 3),
    ("ZX-S104", 3),
    ("ZX-K126", 4),
    ("ZX-P211", 3),
    ("ZX-V113", 3),
    ("ZX-Q117", 4),
)


def test_display_v1_v2_preserves_history_and_records_dm01_assets(app_database_url: str) -> None:
    with TestClient(create_app(Settings.model_validate({}))) as client:
        assert client.get("/display").status_code == 200
        created = client.post("/api/v1/display", json={"inventory_text": _INVENTORY})
        assert created.status_code == 200
        v1 = created.json()
        assert v1["version"] == 1
        assert "15 件上墙" in v1["body"]
        assert "20 件" in v1["body"]
        revised = client.post(
            f"/api/v1/display-tasks/{v1['task_id']}/revisions", json={"feedback": _FEEDBACK}
        )
        assert revised.status_code == 201
        v2 = revised.json()
        assert v2["version"] == 2
        assert "14 件上墙" in v2["body"]
        assert "6 件不上墙" in v2["body"]
        assert "ZX-V113 ×1（侧挂）" in v2["body"]
        assert (
            client.get(f"/api/v1/display-tasks/{v1['task_id']}/versions/1").json()["body"]
            == v1["body"]
        )
        changed = client.post(
            "/api/v1/display", json={"inventory_text": _INVENTORY.replace("ZX-C218 3", "ZX-C218 1")}
        )
        assert "取消同款右侧回应" in changed.json()["body"]
        unrelated = client.post(
            f"/api/v1/display-tasks/{v1['task_id']}/revisions",
            json={"feedback": "B 区看起来有点空，先观察一下。"},
        )
        assert unrelated.status_code == 201
        assert unrelated.json()["kind"] == "question"
        assert client.get(f"/api/v1/display-tasks/{v1['task_id']}/versions/3").status_code == 422
        still_v1 = client.get(f"/api/v1/display-tasks/{v1['task_id']}/versions/1")
        assert still_v1.status_code == 200
    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            "SELECT used_assets,input_receipt,model FROM display_generation_runs WHERE task_id=%s ORDER BY started_at LIMIT 1",
            (v1["task_id"],),
        )
        row = cursor.fetchone()
    assert row is not None
    assert len(row[0]) == 11
    assert all(item["asset_id"].startswith(("G-", "GM-")) for item in row[0])
    assert row[1]["brand_standard_version"] == "1.0"
    assert row[1]["store_profile_version"] == "1.0"
    assert row[1]["inventory"]["ZX-C218"] == 3
    assert row[1]["executor"] == "dm01-rule-compiler-v1"
    assert row[2] == "dm01-rule-compiler-v1"


def test_visible_body_comes_only_from_verified_layout_and_rejects_bad_c_rail(
    app_database_url: str,
) -> None:
    class WrongBodyCompiler(DM01DisplayCompiler):
        def generate(self, request: DisplayGenerationInput):  # type: ignore[no-untyped-def]
            return replace(super().generate(request), body="错误正文：库存 17 件")

    scope = DisplayScope(TENANT_ID, STORE_USER_ID, BRAND_ID, STORE_ORG_ID)
    service = DisplayService(PostgresDisplayRepository(app_database_url), WrongBodyCompiler())
    result = service.create(scope, _INVENTORY)
    assert result["kind"] == "display"
    assert "错误正文" not in str(result["body"])
    assert "20 件；选择 15 件上墙，5 件不上墙" in str(result["body"])

    context = PostgresDisplayRepository(app_database_url).load_context(scope)
    assert context is not None
    artifact = DM01DisplayCompiler().generate(
        DisplayGenerationInput(uuid4(), uuid4(), _INVENTORY_PAIRS, context, ())
    )
    invalid_plan = deepcopy(artifact.plan)
    zones = invalid_plan["layout"]["zones"]  # type: ignore[index]
    zones["C"]["upper"] = zones["C"]["lower"]
    zones["C"]["lower"] = [{"sku": "ZX-V113", "quantity": 2, "mount": "side_hang"}]
    with pytest.raises(GenerationFailed):
        assert_display_complete(replace(artifact, plan=invalid_plan), _INVENTORY_PAIRS)
