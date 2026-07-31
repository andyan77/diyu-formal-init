from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from src.brain.display_contract import assert_display_complete
from src.brain.display_service import DisplayService
from src.brain.display_text import compile_display_body
from src.brain.dm01_display_compiler import (
    DM01DisplayCompiler,
    parse_hard_requirements,
    required_inventory_gap,
)
from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.display_repository import PostgresDisplayRepository
from src.infrastructure.dm01_store_seed import DM01StoreSeedWriter
from src.infrastructure.seed_demo import BRAND_ID, STORE_ORG_ID, STORE_USER_ID, TENANT_ID
from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.shared.errors import DomainError, GenerationFailed
from src.shared.types import (
    DisplayContext,
    DisplayGenerationInput,
    DisplayScope,
    GeneratedDisplayArtifact,
    TenantManagementScope,
)

_INVENTORY = "今天这组墙可用：ZX-C218 3 件、ZX-S104 3 件、ZX-K126 4 件、ZX-P211 3 件、ZX-V113 3 件、ZX-Q117 4 件。"
_FEEDBACK = "中间上杆 ZX-V113 太挤，请减少一件；其他内容不变。"
_BANNED_VISIBLE_WORDS = (
    "确认人",
    "确认日期",
    "系统代录",
    "代录",
    "业务指定",
    "已确认商品",
    "授权",
    "审批",
    "批准",
    "是否采用",
    "阿丹",
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
    assert row[1]["task_expression_version"] == "1.0"
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
    assert "20 件；建议 15 件上墙，5 件不上墙" in str(result["body"])

    context = PostgresDisplayRepository(app_database_url).load_context(scope)
    assert context is not None
    artifact = DM01DisplayCompiler().generate(DisplayGenerationInput(uuid4(), uuid4(), _INVENTORY_PAIRS, context, ()))
    invalid_plan = deepcopy(artifact.plan)
    zones = invalid_plan["layout"]["zones"]  # type: ignore[index]
    zones["center"]["upper"] = zones["center"]["lower"]
    zones["center"]["lower"] = []
    with pytest.raises(GenerationFailed):
        assert_display_complete(replace(artifact, plan=invalid_plan), _INVENTORY_PAIRS)


def test_no_display_surface_shows_confirmation_or_authorisation_wording(app_database_url: str) -> None:
    """Success text, refusal text, questions and the page itself must all stay reference-advice only."""
    surfaces: list[str] = []
    with TestClient(create_app(Settings.model_validate({}))) as client:
        client.get("/ui/select/display")
        surfaces.append(client.get("/display").text)
        surfaces.append(str(client.post("/api/v1/display", json={"inventory_text": _INVENTORY}).json()))
        refused = client.post("/api/v1/display", json={"inventory_text": "今天想聊聊搭配。"})
        assert refused.status_code == 422
        surfaces.append(refused.text)
        narrowed = client.post("/api/v1/display", json={"inventory_text": "今天这组墙可用：ZX-C218 1 件。"})
        surfaces.append(narrowed.text)
        surfaces.append(client.post("/api/v1/display", json={"inventory_text": "今天这组墙可用：ZX-P211 2 件。"}).text)

    scope = DisplayScope(TENANT_ID, STORE_USER_ID, BRAND_ID, STORE_ORG_ID)
    context = PostgresDisplayRepository(app_database_url).load_context(scope)
    assert context is not None
    over_capacity = deepcopy(dict(context.rail_profile))
    over_capacity["upper_comfort_capacity"] = 1
    with pytest.raises(GenerationFailed) as capacity_failure:
        assert_display_complete(
            DM01DisplayCompiler().generate(
                DisplayGenerationInput(
                    uuid4(), uuid4(), _INVENTORY_PAIRS, replace(context, rail_profile=over_capacity), ()
                )
            ),
            _INVENTORY_PAIRS,
        )
    surfaces.append(str(capacity_failure.value))
    with pytest.raises(GenerationFailed) as focus_failure:
        broken = DM01DisplayCompiler().generate(DisplayGenerationInput(uuid4(), uuid4(), _INVENTORY_PAIRS, context, ()))
        zones = cast(dict[str, dict[str, object]], cast(dict[str, object], broken.plan["layout"])["zones"])
        for zone in zones.values():
            for slot in cast(list[dict[str, object]], zone["upper"]):
                slot["mount"] = "side_hang"
        assert_display_complete(broken, _INVENTORY_PAIRS)
    surfaces.append(str(focus_failure.value))

    for surface in surfaces:
        for banned in _BANNED_VISIBLE_WORDS:
            assert banned not in surface, f"{banned} leaked into: {surface[:200]}"


def _keqiao_record() -> dict[str, object]:
    raw = json.loads(Path("config/task_inputs/diyu_clothing_keqiao_dm01_v1.json").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return cast(dict[str, object], raw)


def _keqiao_context(record: dict[str, object]) -> tuple[DisplayContext, tuple[tuple[str, int], ...]]:
    task_input = cast(dict[str, object], record["task_input"])
    items = cast(list[dict[str, object]], task_input["products"])
    products = tuple((cast(str, item["sku"]), item) for item in items)
    inventory = tuple((cast(str, item["sku"]), cast(int, item["quantity"])) for item in items)
    context = DisplayContext(
        "笛语服饰",
        "浙江分公司",
        "笛语服饰管理员",
        cast(str, task_input["version"]),
        cast(dict[str, object], task_input["expression"]),
        "笛语柯桥店",
        cast(str, record["structure_version"]),
        cast(dict[str, object], record["rail_profile"]),
        products,
    )
    return context, inventory


def test_keqiao_task_snapshot_compiles_a_conserving_reference_plan_without_zx_or_confirmation() -> None:
    context, inventory = _keqiao_context(_keqiao_record())
    compiler = DM01DisplayCompiler()
    artifact = compiler.generate(DisplayGenerationInput(uuid4(), uuid4(), inventory, context, ()))
    assert_display_complete(artifact, inventory)
    body = compile_display_body(context, artifact.plan, revision=False)

    mounted = cast(dict[str, int], artifact.plan["mounted"])
    unmounted = cast(dict[str, int], artifact.plan["unmounted"])
    assert sum(mounted.values()) == 18
    assert sum(unmounted.values()) == 12
    assert all(mounted[sku] + unmounted[sku] == amount for sku, amount in inventory)
    assert "笛语柯桥店墙面挂杆参考执行方案" in body
    assert "上杆右侧约三分之一" in body
    assert "右侧（主焦点）" in body
    assert "女童浅绿机能叠穿马甲（DIYU-CSPU-007）" in body
    assert "女童自然度假白色连衣裙（DIYU-CSPU-006）" in body
    assert "左侧（较弱回应）" in body
    assert "男童深蓝轻学院长款衬衫（DIYU-CSPU-005）" in body
    assert "左侧、右侧；用于避开长款上下重叠" in body
    assert "侧挂保持正常可抽取间距，主正挂两侧各留约一个衣架宽的视觉边界。" in body
    assert "执行步骤" in body
    assert "ZX-" not in body
    for banned in _BANNED_VISIBLE_WORDS:
        assert banned not in body
    assert "这是根据本次库存和现场条件整理的文字参考方案" in body


def test_reference_plan_never_asks_for_confirmation_and_accepts_a_changed_inventory() -> None:
    context, inventory = _keqiao_context(_keqiao_record())
    compiler = DM01DisplayCompiler()

    changed = tuple(
        (sku, amount - 1 if sku == "DIYU-CSPU-007" else amount) for sku, amount in inventory if sku != "DIYU-CSPU-008"
    ) + (("DIYU-CSPU-999", 2),)
    assert required_inventory_gap(changed, context) is None
    changed_artifact = compiler.generate(DisplayGenerationInput(uuid4(), uuid4(), changed, context, ()))
    assert_display_complete(changed_artifact, changed)
    changed_body = compile_display_body(context, changed_artifact.plan, revision=False)
    assert "DIYU-CSPU-999" in changed_body
    assert "本次没有陈列资料的商品" in changed_body
    assert cast(dict[str, int], changed_artifact.plan["mounted"])["DIYU-CSPU-999"] == 0

    without_focus = tuple((sku, amount) for sku, amount in inventory if sku not in {"DIYU-CSPU-006", "DIYU-CSPU-007"})
    assert required_inventory_gap(without_focus, context) is None
    narrowed = compiler.generate(DisplayGenerationInput(uuid4(), uuid4(), without_focus, context, ()))
    assert_display_complete(narrowed, without_focus)
    focus = cast(dict[str, object], cast(dict[str, object], narrowed.plan["layout"])["focus_contract"])
    assert focus["focus_source"] == "system_narrowed"
    assert "系统已在当前商品里重新选择主焦点" in compile_display_body(context, narrowed.plan, revision=False)

    no_suggestion = replace(context, task_expression={"schema": "dm01-wall-double-rail-v1", "theme": "无建议主题"})
    assert required_inventory_gap(inventory, no_suggestion) is None
    system_chosen = compiler.generate(DisplayGenerationInput(uuid4(), uuid4(), inventory, no_suggestion, ()))
    assert_display_complete(system_chosen, inventory)
    chosen_focus = cast(dict[str, object], cast(dict[str, object], system_chosen.plan["layout"])["focus_contract"])
    assert chosen_focus["focus_source"] == "system_narrowed"
    assert chosen_focus["secondary_present"] is False

    hard = parse_hard_requirements("今天这组墙可用：DIYU-CSPU-002 4 件；DIYU-CSPU-006 必须留在主焦点。")
    assert hard == frozenset({"DIYU-CSPU-006"})
    question = required_inventory_gap(without_focus, context, hard)
    assert question is not None
    assert "DIYU-CSPU-006" in question
    for banned in ("确认人", "授权", "审批", "代录"):
        assert banned not in question
    assert required_inventory_gap(inventory, context, hard) is None


_DISPLAY_OPERATOR = "本地夹具陈列操作员"


def _seed_local_scope_fixture(migrator_database_url: str, suffix: str) -> dict[str, str]:
    """A local-only tenant shell so this task snapshot can run end to end; not the production tenant."""
    tenant_name = f"柯桥参考方案本地夹具-{suffix}"
    control_name = f"{tenant_name}管理组织"
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("INSERT INTO tenants (id, name) VALUES (gen_random_uuid(), %s) RETURNING id", (tenant_name,))
        row = cursor.fetchone()
        assert row is not None
        tenant_id = str(row[0])
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
        cursor.execute(
            "INSERT INTO organizations (id, tenant_id, name) VALUES (gen_random_uuid(), %s, %s) RETURNING id",
            (tenant_id, control_name),
        )
        organization = cursor.fetchone()
        assert organization is not None
        cursor.execute(
            "INSERT INTO brands (id, tenant_id, name, positioning, decision_order, tone) "
            "VALUES (gen_random_uuid(), %s, %s, '本地夹具', '本地夹具', '本地夹具')",
            (tenant_id, tenant_name),
        )
    return {"tenant_id": tenant_id, "tenant_name": tenant_name, "control_name": control_name}


def _seeded_display_scope(
    migrator_database_url: str,
    suffix: str,
    record_overrides: dict[str, object] | None = None,
) -> tuple[dict[str, str], DisplayScope, str]:
    """Seed a store, then qualify one display operator exactly as production resolves a scope."""
    fixture = _seed_local_scope_fixture(migrator_database_url, suffix)
    record = {
        **_keqiao_record(),
        "record_id": f"DIYU-STORE-KQ-WALL-01-{suffix}",
        "tenant_name": fixture["tenant_name"],
        "brand_name": fixture["tenant_name"],
        "control_organization_name": fixture["control_name"],
        "execution_organization_name": f"浙江分公司-{suffix}",
        **(record_overrides or {}),
    }
    seed = DM01StoreSeedWriter(migrator_database_url).seed(record)
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (fixture["tenant_id"],))
        cursor.execute(
            "SELECT brand_id, execution_organization_id, current_task_input->>'default_inventory_text' "
            "FROM display_stores WHERE tenant_id=%s AND id=%s",
            (fixture["tenant_id"], str(seed.store_id)),
        )
        store = cursor.fetchone()
        assert store is not None
        cursor.execute(
            "INSERT INTO users (id, tenant_id, organization_id, display_name) "
            "VALUES (gen_random_uuid(), %s, %s, %s) RETURNING id",
            (fixture["tenant_id"], str(store[1]), _DISPLAY_OPERATOR),
        )
        operator = cursor.fetchone()
        assert operator is not None
    scope = DisplayScope(
        UUID(fixture["tenant_id"]),
        UUID(str(operator[0])),
        UUID(str(store[0])),
        UUID(str(store[1])),
    )
    product_writer = PostgresWorkbenchRepository(migrator_database_url)
    management_scope = TenantManagementScope(
        scope.tenant_id,
        scope.user_id,
        scope.brand_id,
    )
    task_products = cast(list[dict[str, object]], cast(dict[str, object], record["task_input"])["products"])
    for product in task_products:
        sku = cast(str, product["sku"])
        facts = {
            key: value
            for key, value in product.items()
            if key not in {"sku", "quantity", "name"}
        }
        product_writer.save_management_product(
            management_scope,
            sku,
            cast(str, product["name"]),
            facts,
            "synthetic_business_fixture",
            "本地 DM01 正式商品纵向夹具",
            "本地测试租户",
        )
    return fixture, scope, str(store[2])


def test_store_seed_is_idempotent_and_creates_no_task_or_version(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    suffix = uuid4().hex[:10]
    fixture, _, inventory_text = _seeded_display_scope(migrator_database_url, suffix)
    record = {
        **_keqiao_record(),
        "record_id": f"DIYU-STORE-KQ-WALL-01-{suffix}",
        "tenant_name": fixture["tenant_name"],
        "brand_name": fixture["tenant_name"],
        "control_organization_name": fixture["control_name"],
        "execution_organization_name": f"浙江分公司-{suffix}",
    }
    repeated = DM01StoreSeedWriter(migrator_database_url).seed(record)
    assert repeated.product_count == 11
    assert inventory_text.startswith("本次任务可用：DIYU-CSPU-007 3 件")
    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (fixture["tenant_id"],))
        cursor.execute(
            "SELECT (SELECT count(*) FROM display_stores WHERE tenant_id=%s), "
            "(SELECT count(*) FROM display_tasks WHERE tenant_id=%s), "
            "(SELECT count(*) FROM display_generation_runs WHERE tenant_id=%s), "
            "(SELECT count(*) FROM display_artifact_versions WHERE tenant_id=%s)",
            (fixture["tenant_id"],) * 4,
        )
        counts = cursor.fetchone()
    assert counts == (1, 0, 0, 0)


def test_task_snapshot_runs_end_to_end_and_a_new_inventory_is_never_blocked(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    suffix = uuid4().hex[:10]
    fixture, scope, inventory_text = _seeded_display_scope(migrator_database_url, suffix)
    repository = PostgresDisplayRepository(app_database_url)
    service = DisplayService(repository, DM01DisplayCompiler())

    v1 = service.create(scope, inventory_text)
    assert v1["kind"] == "display"
    assert v1["version"] == 1
    body = str(v1["body"])
    assert "笛语柯桥店墙面挂杆参考执行方案" in body
    assert "本次任务库存共 30 件；建议" in body
    assert _DISPLAY_OPERATOR not in body
    for banned in _BANNED_VISIBLE_WORDS:
        assert banned not in body

    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (fixture["tenant_id"],))
        cursor.execute(
            "SELECT rail_profile, current_task_input FROM display_stores WHERE tenant_id=%s",
            (fixture["tenant_id"],),
        )
        store = cursor.fetchone()
        cursor.execute("SELECT count(*) FROM display_policies WHERE tenant_id=%s", (fixture["tenant_id"],))
        policies = cursor.fetchone()
        cursor.execute("SELECT count(*) FROM brand_products WHERE tenant_id=%s", (fixture["tenant_id"],))
        long_term_products = cursor.fetchone()
        cursor.execute(
            "SELECT input_receipt FROM display_generation_runs WHERE tenant_id=%s AND task_id=%s",
            (fixture["tenant_id"], v1["task_id"]),
        )
        receipt = cursor.fetchone()
    assert store is not None and policies is not None and long_term_products is not None
    assert store[1]["source"] == "user_task_snapshot"
    assert policies[0] == 0
    assert long_term_products[0] == 11
    assert receipt is not None
    assert receipt[0]["operator"] == _DISPLAY_OPERATOR
    assert "field_executor" not in receipt[0] and "submitted_by" not in receipt[0]

    changed_inventory = (
        "今天这组墙可用：DIYU-CSPU-007 2 件、DIYU-CSPU-006 4 件、DIYU-CSPU-005 3 件、"
        "DIYU-CSPU-011 3 件、DIYU-CSPU-002 4 件、DIYU-CGRP-001 2 件。"
    )
    v1_again = service.create(scope, changed_inventory)
    assert v1_again["kind"] == "display"
    assert v1_again["version"] == 1
    assert v1_again["task_id"] != v1["task_id"]
    assert "本次任务库存共 18 件" in str(v1_again["body"])

    v2 = service.revise(
        scope,
        UUID(str(v1["task_id"])),
        "【测试夹具·非真实门店反馈】中间上杆 DIYU-CSPU-002 太挤，请减少一件；其他内容不变。",
    )
    assert v2["version"] == 2
    assert "仅将中间上杆" in str(v2["body"])
    assert service.fetch_version(scope, UUID(str(v1["task_id"])), 1)["body"] == body
    assert service.fetch_version(scope, UUID(str(v1_again["task_id"])), 1)["version"] == 1
    with pytest.raises(DomainError):
        service.fetch_version(scope, UUID(str(v1_again["task_id"])), 2)

    foreign_tenant = replace(scope, tenant_id=TENANT_ID)
    assert service.create(foreign_tenant, inventory_text)["kind"] == "question"
    assert repository.load_context(replace(scope, brand_id=BRAND_ID)) is None
    assert repository.load_context(replace(scope, organization_id=STORE_ORG_ID)) is None
    with pytest.raises(DomainError):
        repository.load_task_context(replace(scope, brand_id=BRAND_ID), UUID(str(v1["task_id"])))
    with pytest.raises(DomainError):
        service.fetch_version(foreign_tenant, UUID(str(v1["task_id"])), 1)


def test_a_revision_replays_its_own_task_snapshot_not_the_current_store_seed(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    suffix = uuid4().hex[:10]
    fixture, scope, inventory_text = _seeded_display_scope(migrator_database_url, suffix)
    service = DisplayService(PostgresDisplayRepository(app_database_url), DM01DisplayCompiler())
    v1 = service.create(scope, inventory_text)
    v1_body = str(v1["body"])
    assert "本次没有说明主题，按现有商品关系组织" in v1_body

    record = _keqiao_record()
    task_input = cast(dict[str, object], record["task_input"])
    expression = {**cast(dict[str, object], task_input["expression"]), "theme": "换季后的全新默认主题"}
    products = [
        item
        for item in cast(list[dict[str, object]], task_input["products"])
        if item["sku"] not in {"DIYU-CSPU-002", "DIYU-CSPU-008"}
    ]
    rail_profile = {**cast(dict[str, object], record["rail_profile"]), "upper_comfort_capacity": 9}
    _seed_store_update(
        migrator_database_url,
        fixture,
        suffix,
        {
            "rail_profile": rail_profile,
            "task_input": {"version": "KQ-WALL-01-task-换季", "expression": expression, "products": products},
        },
    )

    v2 = service.revise(
        scope,
        UUID(str(v1["task_id"])),
        "【测试夹具·非真实门店反馈】中间上杆 DIYU-CSPU-002 太挤，请减少一件；其他内容不变。",
    )
    v2_body = str(v2["body"])
    assert v2["version"] == 2
    assert "本次没有说明主题，按现有商品关系组织" in v2_body
    assert "换季后的全新默认主题" not in v2_body
    assert "男童灰色自然工装宽松短袖（DIYU-CSPU-002）" in v2_body
    assert "女童灰色松弛针织开衫（DIYU-CSPU-008）" in v2_body
    assert "上杆、下杆分别不超过 16 / 14 件舒适容量" in v2_body
    assert service.fetch_version(scope, UUID(str(v1["task_id"])), 1)["body"] == v1_body

    fresh = service.create(scope, "今天这组墙可用：DIYU-CSPU-007 3 件、DIYU-CSPU-006 4 件、DIYU-CGRP-001 2 件。")
    assert "换季后的全新默认主题" not in str(fresh["body"])
    assert "本次没有说明主题，按现有商品关系组织" in str(fresh["body"])


def test_a_task_without_a_frozen_snapshot_can_no_longer_be_revised(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    """A task that kept no conditions must fail closed, never borrow whatever the store holds now."""
    suffix = uuid4().hex[:10]
    fixture, scope, inventory_text = _seeded_display_scope(migrator_database_url, suffix)
    service = DisplayService(PostgresDisplayRepository(app_database_url), DM01DisplayCompiler())
    legacy = service.create(scope, inventory_text)
    legacy_body = str(legacy["body"])
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (fixture["tenant_id"],))
        cursor.execute(
            "UPDATE display_tasks SET context_snapshot=NULL WHERE tenant_id=%s AND id=%s",
            (fixture["tenant_id"], legacy["task_id"]),
        )
        assert cursor.rowcount == 1

    seeded_input = cast(dict[str, object], _keqiao_record()["task_input"])
    _seed_store_update(
        migrator_database_url,
        fixture,
        suffix,
        {
            "task_input": {
                "version": "KQ-WALL-01-task-换季",
                "expression": {
                    **cast(dict[str, object], seeded_input["expression"]),
                    "theme": "换季后的全新默认主题",
                },
                "products": seeded_input["products"],
            }
        },
    )
    before = _display_counts(app_database_url, fixture["tenant_id"])
    refused = service.revise(
        scope,
        UUID(str(legacy["task_id"])),
        "【测试夹具·非真实门店反馈】中间上杆 DIYU-CSPU-002 太挤，请减少一件；其他内容不变。",
    )
    assert refused == {
        "kind": "question",
        "message": "这份历史方案没有保留完整的任务条件，请按当前库存新建一份方案。",
    }
    for banned in _BANNED_VISIBLE_WORDS:
        assert banned not in str(refused["message"])
    assert _display_counts(app_database_url, fixture["tenant_id"]) == before
    assert service.fetch_version(scope, UUID(str(legacy["task_id"])), 1)["body"] == legacy_body
    with pytest.raises(DomainError):
        service.fetch_version(scope, UUID(str(legacy["task_id"])), 2)

    fresh = service.create(scope, inventory_text)
    revised = service.revise(
        scope,
        UUID(str(fresh["task_id"])),
        "【测试夹具·非真实门店反馈】中间上杆 DIYU-CSPU-002 太挤，请减少一件；其他内容不变。",
    )
    assert revised["version"] == 2
    assert "换季后的全新默认主题" not in str(revised["body"])
    assert "本次没有说明主题，按现有商品关系组织" in str(revised["body"])


def _display_counts(app_database_url: str, tenant_id: str) -> tuple[int, ...]:
    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
        cursor.execute(
            "SELECT (SELECT count(*) FROM display_tasks WHERE tenant_id=%s), "
            "(SELECT count(*) FROM display_generation_runs WHERE tenant_id=%s), "
            "(SELECT count(*) FROM display_artifact_versions WHERE tenant_id=%s)",
            (tenant_id,) * 3,
        )
        counts = cursor.fetchone()
    assert counts is not None
    return tuple(int(value) for value in counts)


def _seed_store_update(
    migrator_database_url: str,
    fixture: dict[str, str],
    suffix: str,
    overrides: dict[str, object],
) -> None:
    DM01StoreSeedWriter(migrator_database_url).seed(
        {
            **_keqiao_record(),
            "record_id": f"DIYU-STORE-KQ-WALL-01-{suffix}",
            "tenant_name": fixture["tenant_name"],
            "brand_name": fixture["tenant_name"],
            "control_organization_name": fixture["control_name"],
            "execution_organization_name": f"浙江分公司-{suffix}",
            **overrides,
        }
    )


def test_a_failed_generation_leaves_no_half_version(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    class FailingCompiler(DM01DisplayCompiler):
        def generate(self, request: DisplayGenerationInput) -> GeneratedDisplayArtifact:
            del request
            raise GenerationFailed("本次不生成任何半成品")

    suffix = uuid4().hex[:10]
    fixture, scope, inventory_text = _seeded_display_scope(migrator_database_url, suffix)
    service = DisplayService(PostgresDisplayRepository(app_database_url), FailingCompiler())
    with pytest.raises(GenerationFailed):
        service.create(scope, inventory_text)
    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (fixture["tenant_id"],))
        cursor.execute("SELECT count(*) FROM display_artifact_versions WHERE tenant_id=%s", (fixture["tenant_id"],))
        versions = cursor.fetchone()
        cursor.execute(
            "SELECT status FROM display_generation_runs WHERE tenant_id=%s",
            (fixture["tenant_id"],),
        )
        runs = cursor.fetchall()
    assert versions is not None and versions[0] == 0
    assert [row[0] for row in runs] == ["failed"]
