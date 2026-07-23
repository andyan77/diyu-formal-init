from __future__ import annotations

import psycopg
from fastapi.testclient import TestClient

from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.seed_demo import TENANT_ID

_SEED = "下午开完一个挺正式的会，转身就拎着电脑去接孩子。"
_INVENTORY = "今天这组墙可用：ZX-C218 3 件、ZX-S104 3 件、ZX-K126 4 件、ZX-P211 3 件、ZX-V113 3 件、ZX-Q117 4 件。"
_DISPLAY_REQUEST = "请按门店本次库存给出双层挂杆的上下杆、数量和执行步骤。"
_CONTENT_REQUEST = "请生成一条面向顾客发布的抖音口播和拍摄脚本。"


def _counts(database_url: str) -> tuple[int, int, int, int]:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            "SELECT (SELECT COUNT(*) FROM business_tasks), (SELECT COUNT(*) FROM generation_runs), "
            "(SELECT COUNT(*) FROM display_tasks), (SELECT COUNT(*) FROM display_generation_runs)"
        )
        row = cursor.fetchone()
    assert row is not None
    return (int(row[0]), int(row[1]), int(row[2]), int(row[3]))


def test_two_application_entries_bind_identity_and_reject_cross_application_calls(
    app_database_url: str,
) -> None:
    app = create_app(Settings.model_validate({}))
    with TestClient(app) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "租户用户入口" in home.text
        assert "租户管理入口" in home.text
        assert "总部内容运营甲" not in home.text
        assert client.post("/api/v1/content", json={"weak_seed": _SEED}).status_code == 401

        client.get("/ui/select/content")
        content = client.get("/content")
        for value in ("总部内容运营甲", "折线之间总部", "品牌母账号·抖音", "总部零售/服务专家"):
            assert value in content.text
        content_v1 = client.post("/api/v1/content", json={"weak_seed": _SEED}).json()
        assert (
            client.post("/api/v1/display", json={"inventory_text": _INVENTORY}).status_code == 403
        )

        client.get("/ui/select/display")
        display = client.get("/display")
        for value in ("南城店陈列执行甲", "折线之间·南城店", "墙面双层挂杆执行方案"):
            assert value in display.text
        display_v1 = client.post("/api/v1/display", json={"inventory_text": _INVENTORY}).json()
        assert display_v1["version"] == 1
        assert client.post("/api/v1/content", json={"weak_seed": _SEED}).status_code == 403

        client.get("/ui/select/content")
        assert client.get(f"/api/v1/tasks/{content_v1['task_id']}/versions/1").status_code == 200
        client.get("/ui/select/display")
        assert (
            client.get(f"/api/v1/display-tasks/{display_v1['task_id']}/versions/1").status_code
            == 200
        )


def test_clear_wrong_application_requests_only_offer_a_switch(app_database_url: str) -> None:
    app = create_app(Settings.model_validate({}))
    with TestClient(app) as client:
        client.get("/ui/select/content")
        before = _counts(app_database_url)
        content_handoff = client.post("/api/v1/content", json={"weak_seed": _DISPLAY_REQUEST})
        assert content_handoff.status_code == 200
        assert content_handoff.json() == {
            "kind": "handoff",
            "message": "这是给门店内部执行的陈列任务，请切换到陈列搭配。",
        }
        assert _counts(app_database_url) == before

        client.get("/ui/select/display")
        display_handoff = client.post("/api/v1/display", json={"inventory_text": _CONTENT_REQUEST})
        assert display_handoff.status_code == 200
        assert display_handoff.json() == {
            "kind": "handoff",
            "message": "这是面向外部受众的内容任务，请切换到内容生产。",
        }
        assert _counts(app_database_url) == before
        ordinary = client.post("/api/v1/display", json={"inventory_text": "今天想聊聊搭配。"})
        assert ordinary.status_code == 422


def test_openapi_and_client_scope_injection_keep_application_bound() -> None:
    app = create_app(Settings.model_validate({}))
    with TestClient(app) as client:
        client.get("/ui/select/content")
        injected = client.post(
            "/api/v1/content?organization_id=other",
            json={"weak_seed": _SEED, "user_id": "not-accepted"},
        )
        assert injected.status_code == 422
        client.get("/ui/select/display")
        display_injected = client.post(
            "/api/v1/display?tenant_id=other",
            json={"inventory_text": _INVENTORY, "organization_id": "not-accepted"},
        )
        assert display_injected.status_code == 422
    contract = app.openapi()
    for path in ("/api/v1/content", "/api/v1/display"):
        operation = contract["paths"][path]["post"]
        assert operation["security"]
        assert operation["responses"]["401"]
        assert operation["responses"]["403"]
