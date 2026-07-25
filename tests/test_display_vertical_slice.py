from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import cast
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from src.brain.display_contract import assert_display_complete
from src.brain.display_service import DisplayService
from src.brain.display_text import compile_display_body
from src.brain.dm01_display_compiler import DM01DisplayCompiler, required_inventory_gap
from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.display_repository import PostgresDisplayRepository
from src.infrastructure.seed_demo import BRAND_ID, STORE_ORG_ID, STORE_USER_ID, TENANT_ID
from src.shared.errors import GenerationFailed
from src.shared.types import DisplayContext, DisplayGenerationInput, DisplayScope

_INVENTORY = "今天这组墙可用：ZX-C218 3 件、ZX-S104 3 件、ZX-K126 4 件、ZX-P211 3 件、ZX-V113 3 件、ZX-Q117 4 件。"
_FEEDBACK = "中间上杆 ZX-V113 太挤，请减少一件；其他内容不变。"
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
        assert client.get("/ui/select/display").status_code == 200
        created = client.post("/api/v1/display", json={"inventory_text": _INVENTORY})
        assert created.status_code == 200
        v1 = created.json()
        assert v1["version"] == 1
        assert "15 件上墙" in v1["body"]
        assert "20 件" in v1["body"]
        revised = client.post(f"/api/v1/display-tasks/{v1['task_id']}/revisions", json={"feedback": _FEEDBACK})
        assert revised.status_code == 201
        v2 = revised.json()
        assert v2["version"] == 2
        assert "14 件上墙" in v2["body"]
        assert "6 件不上墙" in v2["body"]
        assert "炭灰短马甲（ZX-V113）×1（侧挂）" in v2["body"]
        assert "仅将中间上杆" in v2["body"]
        assert client.get(f"/api/v1/display-tasks/{v1['task_id']}/versions/1").json()["body"] == v1["body"]
        changed = client.post("/api/v1/display", json={"inventory_text": _INVENTORY.replace("ZX-C218 3", "ZX-C218 1")})
        assert "右侧（较弱回应）：上杆 明确留空" in changed.json()["body"]
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
    artifact = DM01DisplayCompiler().generate(DisplayGenerationInput(uuid4(), uuid4(), _INVENTORY_PAIRS, context, ()))
    invalid_plan = deepcopy(artifact.plan)
    zones = invalid_plan["layout"]["zones"]  # type: ignore[index]
    zones["center"]["upper"] = zones["center"]["lower"]
    zones["center"]["lower"] = []
    with pytest.raises(GenerationFailed):
        assert_display_complete(replace(artifact, plan=invalid_plan), _INVENTORY_PAIRS)


def test_real_keqiao_v1_uses_confirmed_snapshot_without_zx_or_long_term_product_facts() -> None:
    raw = json.loads(Path("config/confirmed_inputs/diyu_clothing_keqiao_dm01_v1.json").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    record = cast(dict[str, object], raw)
    policy = cast(dict[str, object], record["policy"])
    rail_profile = {
        **cast(dict[str, object], record["rail_profile"]),
        "confirmation": {
            "confirmed_by": "阿丹",
            "confirmed_at": "2026-07-25",
            "system_submitted_by": "笛语服饰管理员",
        },
        "inventory_snapshot": {
            "record_id": record["record_id"],
            "record_version": record["record_version"],
            "enforce_exact": True,
            "items": record["inventory"],
        },
    }
    items = cast(list[dict[str, object]], record["inventory"])
    products = tuple((cast(str, item["sku"]), item) for item in items)
    inventory = tuple((cast(str, item["sku"]), cast(int, item["confirmed_quantity"])) for item in items)
    context = DisplayContext(
        "笛语服饰",
        "浙江分公司",
        "阿丹",
        "笛语服饰管理员",
        cast(str, record["record_version"]),
        policy,
        "笛语柯桥店",
        cast(str, record["record_version"]),
        rail_profile,
        products,
    )
    compiler = DM01DisplayCompiler()
    artifact = compiler.generate(DisplayGenerationInput(uuid4(), uuid4(), inventory, context, ()))
    assert_display_complete(artifact, inventory)
    body = compile_display_body(context, artifact.plan, revision=False)

    assert sum(cast(dict[str, int], artifact.plan["mounted"]).values()) == 18
    assert sum(cast(dict[str, int], artifact.plan["unmounted"]).values()) == 12
    assert "上杆右侧约三分之一" in body
    assert "右侧（主焦点）" in body
    assert "女童浅绿机能叠穿马甲（DIYU-CSPU-007）" in body
    assert "女童自然度假白色连衣裙（DIYU-CSPU-006）" in body
    assert "左侧（较弱回应）" in body
    assert "男童深蓝轻学院长款衬衫（DIYU-CSPU-005）" in body
    assert "左侧、右侧；用于避开长款上下重叠" in body
    assert "执行步骤" in body
    assert "ZX-" not in body

    changed = tuple((sku, amount - 1 if sku == "DIYU-CSPU-007" else amount) for sku, amount in inventory)
    assert "已确认 3 件" in str(required_inventory_gap(changed, context))
