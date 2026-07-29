from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from src.brain.content_expression import (
    AXIS_ORDER,
    CAPABILITY_STATES,
    COMPACT_STATES,
    DECLARED_SOURCE_TARGETS,
    load_catalog,
    load_inventory,
    read_natural_text,
    reconcile_sources,
)
from src.composition.bootstrap import build_content_control_service
from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.production_auth import ProductionAuthRepository, TenantSession
from src.infrastructure.seed_demo import (
    ACCOUNT_ID,
    ORG_ID,
    STORE_CONTENT_ACCOUNT_ID,
    STORE_CONTENT_USER_ID,
    TENANT_ADMIN_USER_ID,
    TENANT_ID,
    USER_ID,
)
from src.shared.narrative import legacy_frame
from src.shared.types import GeneratedArtifact, GenerationInput
from src.tool.llm_gateway.deepseek import BoundaryContext, DeepSeekGenerator
from src.tool.llm_gateway.stub import DeterministicContentGenerator

_FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "src" / "app" / "CreatorApp.tsx"
_FRONTEND_INTERACTION = Path(__file__).resolve().parents[1] / "frontend" / "test" / "interaction.test.tsx"
_CATALOG_DIR = Path(__file__).resolve().parents[1] / "config" / "content_expression"
_SEED = "开完一个正式会议后还要接孩子，这一身怎么穿才不用中途反复整理？"
_STYLE_HUMOUR = "CAT-STYLE-PERSONA-06"
_STYLE_PRACTICAL = "CAT-STYLE-PERSONA-01"
_TOPIC_COMMUTE = "CAT-TOPIC-OCCASION-01"
_MECHANISM_STEPS = "CAT-GENRE-TUTORIAL-01"
_BODY_RELATED = "CAT-TOPIC-BODY-01"
_SEGMENTS = {
    "identity_position": "我们代表笛语的总部内容账号说话，不冒充门店店员或顾客。",
    "authority_boundary": "只讲已确认的品牌立场与商品资料；没有来源的经历不写成事实。",
    "audience_relationship": "长期服务愿意认真挑选衣服的人，保持平等、不施压的关系。",
    "content_territories": "穿衣处境、商品取舍与品牌立场三类内容可以长期经营。",
    "default_production_conditions": "一名创作者、一部手机、普通室内或门店。",
}


def _content_client(app: Any, entry: str = "/ui/select/content") -> TestClient:
    client = TestClient(app)
    client.get(entry)
    return client


def _rows(app_database_url: str, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    with (
        psycopg.connect(app_database_url, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def _counts(app_database_url: str) -> tuple[int, int, int]:
    row = _rows(
        app_database_url,
        "SELECT (SELECT count(*) FROM business_tasks) AS tasks, "
        "(SELECT count(*) FROM generation_runs) AS runs, "
        "(SELECT count(*) FROM content_versions) AS versions",
        (),
    )[0]
    return int(row["tasks"]), int(row["runs"]), int(row["versions"])


def _snapshot(app_database_url: str, task_id: str) -> dict[str, Any]:
    row = _rows(
        app_database_url,
        "SELECT content_context_snapshot FROM business_tasks WHERE id = %s",
        (task_id,),
    )[0]
    snapshot = row["content_context_snapshot"]
    assert isinstance(snapshot, dict)
    return snapshot


def _receipt(app_database_url: str, task_id: str) -> dict[str, Any]:
    row = _rows(
        app_database_url,
        "SELECT input_receipt FROM generation_runs WHERE task_id = %s ORDER BY started_at LIMIT 1",
        (task_id,),
    )[0]
    receipt = row["input_receipt"]
    assert isinstance(receipt, dict)
    return receipt


def _latest_receipt(app_database_url: str, task_id: str) -> dict[str, Any]:
    row = _rows(
        app_database_url,
        "SELECT input_receipt FROM generation_runs WHERE task_id = %s ORDER BY started_at DESC LIMIT 1",
        (task_id,),
    )[0]
    receipt = row["input_receipt"]
    assert isinstance(receipt, dict)
    return receipt


def _clear_preference(app_database_url: str, user_id: UUID) -> None:
    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute("SELECT set_config('app.user_id', %s, true)", (str(user_id),))
        cursor.execute(
            "DELETE FROM user_creation_preferences WHERE tenant_id = %s AND user_id = %s",
            (str(TENANT_ID), str(user_id)),
        )


def _unassigned_operator(app_database_url: str, label: str) -> str:
    repository = ProductionAuthRepository(app_database_url)
    return repository.create_tenant_user(
        TenantSession(TENANT_ID, TENANT_ADMIN_USER_ID, "tenant-admin"),
        f"{label}-{uuid4().hex[:8]}",
        f"control-scope-{uuid4().hex[:12]}",
        ORG_ID,
        None,
        grants_tenant_management=False,
        grants_material_maintenance=False,
    )["user_id"]


# ---- A. versioned catalog and honest source reconciliation ------------------------------


def test_catalog_is_versioned_reconciled_and_only_shows_runnable_options() -> None:
    inventory = load_inventory()
    catalog = load_catalog()
    identifiers = [str(record["stable_id"]) for record in inventory]
    assert len(identifiers) == len(set(identifiers))
    assert all(str(record["capability_state"]) in CAPABILITY_STATES for record in inventory)
    assert all(str(record["catalog_version"]) == catalog.catalog_version for record in inventory)

    summary, gaps = reconcile_sources(inventory)
    assert summary["风格"] == {"defined": 20, "declared_target": 20, "source_gaps": 0}
    assert summary["题材"] == {"defined": 55, "declared_target": 55, "source_gaps": 0}
    # The frozen research enumeration only defines 41 of the 44 declared genre positions, so the
    # three missing positions are registered as gaps instead of being invented.
    assert summary["体裁"] == {"defined": 41, "declared_target": 44, "source_gaps": 3}
    assert set(gaps) == {
        "CAT-SOURCE-GAP-GENRE-001",
        "CAT-SOURCE-GAP-GENRE-002",
        "CAT-SOURCE-GAP-GENRE-003",
    }
    assert sum(item["defined"] for item in summary.values()) == 116
    assert sum(item["declared_target"] for item in summary.values()) == 119
    assert {state: sum(record["capability_state"] == state for record in inventory) for state in CAPABILITY_STATES} == {
        "verified": 10,
        "composable": 64,
        "experimental": 6,
        "unsupported": 38,
        "explicitly_out_of_scope": 1,
    }

    by_id = {str(record["stable_id"]): record for record in inventory}
    for gap in gaps:
        assert by_id[gap]["visible_in_compact_v1"] is False
        assert by_id[gap]["gap_type"] == "source_gap"
        assert "F10" in str(by_id[gap]["destination"])

    redirected_after_m7_2b = {
        "CAT-TOPIC-TEACH-07",
        "CAT-TOPIC-NEWITEM-01",
        "CAT-TOPIC-NEWITEM-06",
        "CAT-TOPIC-TREND-01",
        "CAT-TOPIC-STORE-02",
        "CAT-TOPIC-STORE-05",
        "CAT-GENRE-VLOG-01",
        "CAT-GENRE-INTERACT-01",
        "CAT-GENRE-INTERACT-06",
    }
    for stable_id in redirected_after_m7_2b:
        record = by_id[stable_id]
        assert record["capability_state"] == "unsupported"
        assert record["visible_in_compact_v1"] is False
        assert "F10" in str(record["destination"])
        assert "M7-2B" not in str(record["destination"])
    assert all(
        "M7-2B" not in str(record["destination"]) for record in inventory if record["capability_state"] == "unsupported"
    )
    deferred_states = {"unsupported", "explicitly_out_of_scope"}
    allowed_destinations = {"F03", "F06", "F07", "F08", "F10"}
    assert all(
        any(destination in str(record["destination"]) for destination in allowed_destinations)
        for record in inventory
        if record["capability_state"] in deferred_states
    )

    visible = {str(record["stable_id"]) for record in inventory if record["visible_in_compact_v1"] is True}
    assert {entry.stable_id for entry in catalog.entries} == visible
    assert all(entry.capability_state in COMPACT_STATES for entry in catalog.entries)
    assert [axis.key for axis in catalog.axes] == list(AXIS_ORDER)
    assert len(catalog.entries) < len(inventory) // 2
    assert {family for family, _, _ in DECLARED_SOURCE_TARGETS} == set(summary)


def test_catalog_endpoint_hides_body_options_and_react_never_hardcodes_the_catalog() -> None:
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as client:
        payload = client.get("/api/v1/content/expression-catalog").json()
    assert payload["catalog_version"] == load_catalog().catalog_version
    assert [axis["key"] for axis in payload["axes"]] == list(AXIS_ORDER)
    assert payload["body_related_enabled"] is False
    options = [option for axis in payload["axes"] for option in axis["options"]]
    assert options and all(option["body_related"] is False for option in options)
    assert all(option["capability_state"] in COMPACT_STATES for option in options)

    source = _FRONTEND.read_text(encoding="utf-8")
    assert "/api/v1/content/expression-catalog" in source
    assert not [entry.stable_id for entry in load_catalog().entries if entry.stable_id in source]
    assert "ZX-C218" not in source


def test_tenant_administrators_have_no_global_catalog_write_surface() -> None:
    app = create_app(Settings.model_validate({}))
    schema = app.openapi()
    catalog_paths = {path: set(methods) for path, methods in schema["paths"].items() if "expression-catalog" in path}
    assert catalog_paths == {"/api/v1/content/expression-catalog": {"get"}}


# ---- B. account expression profile versions and permissions -----------------------------


def test_profile_versions_are_immutable_and_only_the_control_organization_may_write(
    app_database_url: str,
) -> None:
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as owner:
        first = owner.get("/api/v1/content/account-expression-profile").json()
        assert first["can_maintain"] is True
        assert set(first["segment_labels"]) == set(_SEGMENTS)

        created = owner.post("/api/v1/content/account-expression-profile/versions", json=_SEGMENTS)
        assert created.status_code == 201
        version_one = created.json()
        after_first = owner.get("/api/v1/content/account-expression-profile").json()
        assert after_first["current"]["version"] == version_one["version"]
        assert after_first["draft"] is None

        changed = dict(_SEGMENTS)
        changed["content_territories"] = "本轮把内容领地收敛为穿衣处境与商品取舍两类。"
        second = owner.post("/api/v1/content/account-expression-profile/versions", json=changed).json()
        assert second["version"] == version_one["version"] + 1
        current = owner.get("/api/v1/content/account-expression-profile").json()["current"]
        assert current["version"] == second["version"]

    kept = _rows(
        app_database_url,
        "SELECT version, content_territories FROM account_expression_profile_versions "
        "WHERE account_id = %s AND version IN (%s, %s) ORDER BY version",
        (str(ACCOUNT_ID), version_one["version"], second["version"]),
    )
    assert [row["content_territories"] for row in kept] == [
        _SEGMENTS["content_territories"],
        changed["content_territories"],
    ]

    with _content_client(app, "/ui/select/content-store") as store:
        assert store.get("/api/v1/content/account-expression-profile").json()["can_maintain"] is False
        assert store.post("/api/v1/content/account-expression-profile/versions", json=_SEGMENTS).status_code == 422
    with _content_client(app, "/ui/select/external-content") as external:
        # The grant allows profile maintenance, but the person's organization does not control
        # the account, so the write still fails closed.
        assert external.get("/api/v1/content/account-expression-profile").json()["can_maintain"] is False
        assert external.post("/api/v1/content/account-expression-profile/versions", json=_SEGMENTS).status_code == 422


def test_headquarters_administrator_cannot_maintain_another_control_organizations_account() -> None:
    app = create_app(Settings.model_validate({}))
    with TestClient(app) as manager:
        manager.get("/ui/select/admin")
        own = manager.get(f"/api/v1/tenant-management/publishing-accounts/{ACCOUNT_ID}/expression-profile").json()
        assert own["can_maintain"] is True
        other = manager.get(
            f"/api/v1/tenant-management/publishing-accounts/{STORE_CONTENT_ACCOUNT_ID}/expression-profile"
        ).json()
        assert other["can_maintain"] is False
        assert (
            manager.post(
                f"/api/v1/tenant-management/publishing-accounts/{STORE_CONTENT_ACCOUNT_ID}/expression-profile/versions",
                json=_SEGMENTS,
            ).status_code
            == 422
        )
        missing = manager.get(f"/api/v1/tenant-management/publishing-accounts/{uuid4()}/expression-profile")
        assert missing.status_code == 422
        assert manager.get("/api/v1/content/account-expression-profile").status_code == 403


# ---- C. private creation preference ------------------------------------------------------


def test_private_preference_is_owner_only_and_never_written_by_generation(
    app_database_url: str,
) -> None:
    _clear_preference(app_database_url, USER_ID)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as owner:
        assert owner.get("/api/v1/user/creation-preferences").json()["exists"] is False
        owner.post("/api/v1/content", json={"weak_seed": _SEED})
        assert owner.get("/api/v1/user/creation-preferences").json()["exists"] is False

        saved = owner.put(
            "/api/v1/user/creation-preferences",
            json={
                "enabled": True,
                "direction_defaults": {"style": _STYLE_HUMOUR},
                "collaboration_note": "平时更喜欢自然口语。",
                "body_related_opt_in": False,
            },
        ).json()
        assert saved["exists"] is True
        again = owner.put(
            "/api/v1/user/creation-preferences",
            json={"enabled": True, "direction_defaults": {"style": _STYLE_HUMOUR}},
        ).json()
        assert again["version"] == saved["version"] + 1

        # Applied by default, and truly not read when the person asks for this one time only.
        applied = owner.post("/api/v1/content", json={"weak_seed": _SEED}).json()
        assert applied["applied_direction"]
        bypassed = owner.post("/api/v1/content", json={"weak_seed": _SEED, "use_personal_preferences": False}).json()
        assert bypassed["applied_direction"] == []
        assert _snapshot(app_database_url, bypassed["task_id"])["private_preference_mode"] == "temporarily_bypassed"
        assert _snapshot(app_database_url, applied["task_id"])["private_preference_mode"] == "applied"

        disabled = owner.put(
            "/api/v1/user/creation-preferences",
            json={"enabled": False, "direction_defaults": {"style": _STYLE_HUMOUR}},
        ).json()
        assert disabled["enabled"] is False
        off = owner.post("/api/v1/content", json={"weak_seed": _SEED}).json()
        assert off["applied_direction"] == []
        assert _snapshot(app_database_url, off["task_id"])["private_preference_mode"] == "disabled"

    other_user = _rows(
        app_database_url,
        "SELECT count(*) AS visible FROM user_creation_preferences",
        (),
    )
    # A transaction that never presents a trusted person sees nothing at all.
    assert int(other_user[0]["visible"]) == 0
    with psycopg.connect(app_database_url, row_factory=dict_row) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute("SELECT set_config('app.user_id', %s, true)", (str(STORE_CONTENT_USER_ID),))
        cursor.execute("SELECT count(*) AS visible FROM user_creation_preferences")
        row = cursor.fetchone()
        assert row is not None and int(row["visible"]) == 0

    with _content_client(app) as owner:
        before_series = len(owner.get("/api/v1/content/series").json())
        before_materials = len(owner.get("/api/v1/materials").json())
        before_profile = owner.get("/api/v1/content/account-expression-profile").json()["current"]
        removed = owner.delete("/api/v1/user/creation-preferences").json()
        assert removed["deleted"] is True
        assert owner.get("/api/v1/user/creation-preferences").json()["exists"] is False
        assert len(owner.get("/api/v1/content/series").json()) == before_series
        assert len(owner.get("/api/v1/materials").json()) == before_materials
        assert owner.get("/api/v1/content/account-expression-profile").json()["current"] == before_profile


# ---- D/E. creative direction and transparent brand translation ---------------------------


def test_direction_reaches_generation_and_a_soft_conflict_stays_visible(
    app_database_url: str,
) -> None:
    _clear_preference(app_database_url, USER_ID)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as client:
        plain = client.post("/api/v1/content", json={"weak_seed": _SEED}).json()
        assert plain["kind"] == "content"
        assert plain["translation_notice"] is None
        assert plain["applied_direction"] == []

        directed = client.post(
            "/api/v1/content",
            json={
                "weak_seed": _SEED,
                "creative_direction": {
                    "catalog_version": load_catalog().catalog_version,
                    "selections": {
                        "topic": _TOPIC_COMMUTE,
                        "mechanism": _MECHANISM_STEPS,
                        "style": _STYLE_HUMOUR,
                    },
                    "custom_text": "结尾自然收住就行。",
                },
            },
        ).json()
        assert directed["kind"] == "content"
        # The user's own choice survives, and the brand boundary is explained, not applied silently.
        assert "幽默玩梗" in directed["translation_notice"]
        assert "克制的冷幽默" in directed["translation_notice"]
        assert "你还可以继续改。" in directed["translation_notice"]
        assert "克制的冷幽默" in directed["applied_direction"]
        assert "幽默玩梗" not in directed["body"]
        assert "本次创作方向" in directed["body"]
        assert "结尾自然收住就行。" in directed["body"]

        snapshot = _snapshot(app_database_url, directed["task_id"])
        original = {item["stable_id"]: item["label"] for item in snapshot["original_direction"]["selections"]}
        applied = {item["stable_id"]: item["applied_label"] for item in snapshot["applied_direction"]}
        assert original[_STYLE_HUMOUR] == "幽默玩梗"
        assert applied[_STYLE_HUMOUR] == "克制的冷幽默"
        assert snapshot["catalog_version"] == load_catalog().catalog_version
        assert snapshot["translation_notice"] == directed["translation_notice"]

        receipt = _receipt(app_database_url, directed["task_id"])
        assert receipt["catalog_version"] == load_catalog().catalog_version
        assert {item["stable_id"] for item in receipt["creative_direction"]} == {
            _TOPIC_COMMUTE,
            _MECHANISM_STEPS,
            _STYLE_HUMOUR,
        }

        stale = client.post(
            "/api/v1/content",
            json={
                "weak_seed": _SEED,
                "creative_direction": {"catalog_version": "content-expression-catalog-v0"},
            },
        )
        assert stale.status_code == 422


def test_body_related_directions_stay_hidden_until_the_person_turns_them_on(
    app_database_url: str,
) -> None:
    _clear_preference(app_database_url, USER_ID)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as client:
        options = client.get("/api/v1/content/expression-catalog").json()
        assert _BODY_RELATED not in json.dumps(options, ensure_ascii=False)

        refused = client.post(
            "/api/v1/content",
            json={
                "weak_seed": _SEED,
                "creative_direction": {"selections": {"topic": _BODY_RELATED}},
            },
        )
        assert refused.status_code == 422
        assert "体型" in refused.json()["detail"]

        client.put(
            "/api/v1/user/creation-preferences",
            json={"enabled": True, "body_related_opt_in": True},
        )
        opened = client.get("/api/v1/content/expression-catalog").json()
        assert opened["body_related_enabled"] is True
        assert _BODY_RELATED in json.dumps(opened, ensure_ascii=False)
        accepted = client.post(
            "/api/v1/content",
            json={
                "weak_seed": _SEED,
                "creative_direction": {
                    "selections": {"topic": _BODY_RELATED},
                    "body_related_opt_in": True,
                },
            },
        )
        assert accepted.status_code == 200
    _clear_preference(app_database_url, USER_ID)


# ---- F. this-task legal references --------------------------------------------------------


def test_only_explicitly_selected_in_scope_references_enter_the_task(
    app_database_url: str,
) -> None:
    _clear_preference(app_database_url, USER_ID)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as owner:
        text_asset = owner.post(
            "/api/v1/materials/personal",
            json={
                "title": "上周整理的通勤观察",
                "filename": "notes.txt",
                "content_type": "text/plain",
                "content_base64": base64.b64encode("通勤路上最常见的问题是外套一坐就皱。".encode()).decode("ascii"),
            },
        ).json()
        described = owner.post(
            "/api/v1/materials/personal",
            json={
                "title": "外套细节照",
                "filename": "coat.jpg",
                "content_type": "image/jpeg",
                "content_base64": base64.b64encode(b"not-decoded-bytes").decode("ascii"),
                "reference_note": "照片里只有一件深灰外套的袖口。",
            },
        ).json()
        silent = owner.post(
            "/api/v1/materials/personal",
            json={
                "title": "没有说明的原件",
                "filename": "silent.jpg",
                "content_type": "image/jpeg",
                "content_base64": base64.b64encode(b"still-not-decoded").decode("ascii"),
            },
        ).json()

        without = owner.post("/api/v1/content", json={"weak_seed": _SEED}).json()
        assert "上周整理的通勤观察" not in without["body"]
        assert _snapshot(app_database_url, without["task_id"])["material_refs"] == []

        with_text = owner.post(
            "/api/v1/content",
            json={"weak_seed": _SEED, "material_ids": [text_asset["id"], described["id"]]},
        ).json()
        assert "上周整理的通勤观察" in with_text["body"]
        assert "外套细节照" in with_text["body"]
        refs = _snapshot(app_database_url, with_text["task_id"])["material_refs"]
        assert {item["asset_id"] for item in refs} == {text_asset["id"], described["id"]}
        assert all(item["reference_version"] == 1 for item in refs)
        assert {item["asset_id"] for item in _receipt(app_database_url, with_text["task_id"])["material_refs"]} == {
            text_asset["id"],
            described["id"],
        }

        undescribed = owner.post("/api/v1/content", json={"weak_seed": _SEED, "material_ids": [silent["id"]]})
        assert undescribed.status_code == 422
        assert "可读说明" in undescribed.json()["detail"]

    with _content_client(app, "/ui/select/content-store") as store:
        stolen = store.post("/api/v1/content", json={"weak_seed": _SEED, "material_ids": [text_asset["id"]]})
        assert stolen.status_code == 422


# ---- G. opportunities, plan and unmet capability requests ---------------------------------


def test_opportunities_and_plan_never_create_a_task_and_a_request_changes_nothing(
    app_database_url: str,
) -> None:
    _clear_preference(app_database_url, USER_ID)
    app = create_app(Settings.model_validate({}))
    before = _counts(app_database_url)
    catalog_digest = (
        (_CATALOG_DIR / "catalog-v1.json").read_bytes(),
        (_CATALOG_DIR / "capability-inventory-v1.jsonl").read_bytes(),
    )
    activations = _rows(app_database_url, "SELECT count(*) AS total FROM system_asset_activations", ())
    profile_before = _rows(
        app_database_url,
        "SELECT count(*) AS total FROM account_expression_profile_versions",
        (),
    )

    with _content_client(app) as client:
        opportunities = client.post("/api/v1/content/opportunities").json()
        assert len(opportunities["items"]) >= 2
        assert all(item["id"].startswith("OPP-") for item in opportunities["items"])
        assert all(item["seed_text"] for item in opportunities["items"])
        assert client.post("/api/v1/content/opportunities").json() == opportunities

        saved = client.put(
            "/api/v1/content/plan",
            json={"items": [{"title": "先讲一次通勤处境", "note": "本周内", "selections": {}}]},
        ).json()
        assert saved["document"]["items"][0]["title"] == "先讲一次通勤处境"
        assert client.get("/api/v1/content/plan").json()["document"] == saved["document"]

        created = client.post(
            "/api/v1/content/unmet-capability-requests",
            json={
                "request_text": "我想按平台搜索热度选题，但现在没有这个能力。",
                "creative_direction": {"selections": {"topic": _TOPIC_COMMUTE}},
            },
        )
        assert created.status_code == 201
        assert created.json()["gap_type"] == "unclassified"
        assert created.json()["status"] == "received"
        mine = client.get("/api/v1/content/unmet-capability-requests").json()
        assert created.json()["stable_request_id"] in {item["stable_request_id"] for item in mine}

    assert _counts(app_database_url) == before
    assert (
        (_CATALOG_DIR / "catalog-v1.json").read_bytes(),
        (_CATALOG_DIR / "capability-inventory-v1.jsonl").read_bytes(),
    ) == catalog_digest
    assert _rows(app_database_url, "SELECT count(*) AS total FROM system_asset_activations", ()) == activations
    assert (
        _rows(
            app_database_url,
            "SELECT count(*) AS total FROM account_expression_profile_versions",
            (),
        )
        == profile_before
    )

    with _content_client(app, "/ui/select/content-store") as store:
        assert store.get("/api/v1/content/unmet-capability-requests").json() == []


# ---- H. frozen snapshot, replay and fail-closed revision ----------------------------------


def test_a_revision_replays_its_own_frozen_conditions(app_database_url: str) -> None:
    _clear_preference(app_database_url, USER_ID)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as client:
        client.post("/api/v1/content/account-expression-profile/versions", json=_SEGMENTS)
        frozen_version = client.get("/api/v1/content/account-expression-profile").json()["current"]["version"]
        created = client.post(
            "/api/v1/content",
            json={
                "weak_seed": _SEED,
                "creative_direction": {"selections": {"style": _STYLE_HUMOUR}},
            },
        ).json()
        assert _SEGMENTS["identity_position"] in created["body"]
        # The internal version number is a receipt field, never visible artifact text.
        assert f"V{frozen_version}" not in created["body"]
        assert _receipt(app_database_url, created["task_id"])["account_expression_profile_version"] == frozen_version

        moved_on = dict(_SEGMENTS)
        moved_on["identity_position"] = "换了一版之后的表达身份说明。"
        newer = client.post("/api/v1/content/account-expression-profile/versions", json=moved_on).json()
        assert newer["version"] == frozen_version + 1

        revised = client.post(
            f"/api/v1/tasks/{created['task_id']}/revisions",
            json={"instruction": "把结尾改短一点，其他不动。"},
        ).json()
        assert revised["version"] == 2
        # The later profile version must not leak into an existing task.
        assert _SEGMENTS["identity_position"] in revised["body"]
        assert "换了一版之后的表达身份说明。" not in revised["body"]
        assert "克制的冷幽默" in revised["body"]
        assert (
            _latest_receipt(app_database_url, created["task_id"])["account_expression_profile_version"]
            == frozen_version
        )

        # Reopening any stored version keeps the transparent translation it was produced with.
        reopened = client.get(f"/api/v1/tasks/{created['task_id']}/versions/1").json()
        assert "克制的冷幽默" in reopened["translation_notice"]
        assert "克制的冷幽默" in reopened["applied_direction"]
        history = client.get(f"/api/v1/content/tasks/{created['task_id']}/versions").json()
        assert all("克制的冷幽默" in item["translation_notice"] for item in history)


def test_a_task_without_a_frozen_content_context_can_no_longer_be_revised(
    app_database_url: str,
) -> None:
    _clear_preference(app_database_url, USER_ID)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as client:
        created = client.post("/api/v1/content", json={"weak_seed": _SEED}).json()
        with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
            cursor.execute(
                "UPDATE business_tasks SET content_context_snapshot = NULL WHERE id = %s",
                (created["task_id"],),
            )
        before = _counts(app_database_url)
        refused = client.post(
            f"/api/v1/tasks/{created['task_id']}/revisions",
            json={"instruction": "请再改一版。"},
        )
        assert refused.status_code == 201
        assert refused.json() == {
            "kind": "question",
            "message": "这条历史内容没有保留完整的创作条件，请按当前输入新建一条。",
        }
        assert _counts(app_database_url) == before
        readable = client.get(f"/api/v1/tasks/{created['task_id']}/versions/1")
        assert readable.status_code == 200

        fresh = client.post("/api/v1/content", json={"weak_seed": _SEED}).json()
        again = client.post(
            f"/api/v1/tasks/{fresh['task_id']}/revisions",
            json={"instruction": "把结尾改短一点，其他不动。"},
        ).json()
        assert again["version"] == 2


def test_legacy_tasks_keep_a_backfilled_snapshot_without_a_pretended_profile(
    app_database_url: str,
) -> None:
    rows = _rows(
        app_database_url,
        "SELECT content_context_snapshot AS snapshot FROM business_tasks "
        "WHERE content_context_snapshot ->> 'schema' = 'content-context-snapshot-legacy-v1' LIMIT 5",
        (),
    )
    for row in rows:
        snapshot = row["snapshot"]
        assert snapshot["account_expression_profile_version"] is None
        assert snapshot["legacy_content_role"] is True
        assert snapshot["catalog_version"] is None
        assert snapshot["private_preference_mode"] == "legacy_absent"


# ---- frontend minimum closure -------------------------------------------------------------


def test_frontend_keeps_natural_input_first_and_two_mobile_surfaces() -> None:
    source = _FRONTEND.read_text(encoding="utf-8")
    assert "创作方向（可选）" in source
    assert "本次素材（可选）" in source
    assert source.count('setMobileView("conversation")') >= 2
    assert source.count('setMobileView("artifact")') >= 2
    assert "设置页" not in source
    assert "上下文" not in source
    assert "实际操作人" not in source
    assert "translation_notice" in source
    assert 'if (!("task_id" in payload))' in source
    assert "已经保存为你的默认方向" in source
    assert "collaboration_note: preference.collaboration_note" in source
    # The interaction test mounts the formal bootstrap entry and drives these contracts.
    assert _FRONTEND_INTERACTION.exists()
    checks = _FRONTEND_INTERACTION.read_text(encoding="utf-8")
    for behaviour in (
        "空态不应常驻巨大成品面板",
        "首屏只展开题材、风格、形式",
        "默认目录必须完全来自服务端",
        "体型方向只能由本人显式保存后开启",
        "创作壳不得混入租户管理业务 DOM",
    ):
        assert behaviour in checks


def test_no_backend_only_field_reaches_the_visible_artifact(app_database_url: str) -> None:
    _clear_preference(app_database_url, USER_ID)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as client:
        client.post("/api/v1/content/account-expression-profile/versions", json=_SEGMENTS)
        created = client.post(
            "/api/v1/content",
            json={
                "weak_seed": _SEED,
                "creative_direction": {"selections": {"topic": _TOPIC_COMMUTE}},
            },
        ).json()
    body = str(created["body"])
    for leaked in ("CAT-", "OPP-", "content-expression-catalog-v", created["task_id"], created["version_id"]):
        assert leaked not in body
    snapshot = _snapshot(app_database_url, created["task_id"])
    # Preference state is owner-scoped; a tenant-scoped snapshot keeps task conditions only.
    assert "body_related_opt_in" not in snapshot["original_direction"]
    assert "direction_defaults" not in json.dumps(snapshot, ensure_ascii=False)
    assert "collaboration_note" not in json.dumps(snapshot, ensure_ascii=False)


def test_account_creation_only_records_an_explicitly_declared_control_organization(
    app_database_url: str,
) -> None:
    operator_id = _unassigned_operator(app_database_url, "控制组织回归操作者")
    app = create_app(Settings.model_validate({}))
    with TestClient(app) as manager:
        manager.get("/ui/select/admin")
        organizations = manager.get("/api/v1/tenant-management/control-organizations").json()
        own = next(item for item in organizations if item["id"] == str(ORG_ID))
        name = f"控制组织回归账号-{uuid4().hex[:8]}"
        created = manager.post(
            "/api/v1/tenant-management/publishing-accounts",
            json={
                "name": name,
                "channel": "抖音",
                "content_role_name": f"控制组织回归表达身份-{uuid4().hex[:8]}",
                "voice_boundary": "只用于验证新建账号只接受明确指定的控制组织。",
                "operator_id": operator_id,
                "control_organization_id": own["id"],
            },
        )
        assert created.status_code == 201
        account_id = created.json()["id"]
        profile = manager.get(f"/api/v1/tenant-management/publishing-accounts/{account_id}/expression-profile").json()
        assert profile["control_organization_source"] == "declared"
        assert profile["can_maintain"] is True
        assert profile["can_declare"] is False
        saved = manager.post(
            f"/api/v1/tenant-management/publishing-accounts/{account_id}/expression-profile/versions",
            json=_SEGMENTS,
        )
        assert saved.status_code == 201
        assert saved.json()["version"] == 1


def test_same_name_account_idempotency_compares_the_control_organization(
    app_database_url: str,
) -> None:
    operator_id = _unassigned_operator(app_database_url, "幂等控制组织操作者")
    app = create_app(Settings.model_validate({}))
    with TestClient(app) as manager:
        manager.get("/ui/select/admin")
        organizations = manager.get("/api/v1/tenant-management/control-organizations").json()
        own = next(item for item in organizations if item["id"] == str(ORG_ID))
        other = next(item for item in organizations if item["id"] != own["id"])
        name = f"幂等控制组织账号-{uuid4().hex[:8]}"
        payload = {
            "name": name,
            "channel": "抖音",
            "content_role_name": f"幂等控制组织表达身份-{uuid4().hex[:8]}",
            "voice_boundary": "只用于验证同名幂等比较包含控制组织。",
            "operator_id": operator_id,
            "control_organization_id": own["id"],
        }
        first = manager.post("/api/v1/tenant-management/publishing-accounts", json=payload)
        assert first.status_code == 201
        same = manager.post("/api/v1/tenant-management/publishing-accounts", json=payload)
        assert same.status_code == 201
        assert same.json()["id"] == first.json()["id"]
        # Control organization decides who may maintain the profile, so a repeat that names a
        # different one is refused instead of quietly returning the existing account.
        moved = manager.post(
            "/api/v1/tenant-management/publishing-accounts",
            json={**payload, "control_organization_id": other["id"]},
        )
        assert moved.status_code == 422
        assert "控制组织" in moved.json()["detail"]
        undeclared = manager.post(
            "/api/v1/tenant-management/publishing-accounts",
            json={key: value for key, value in payload.items() if key != "control_organization_id"},
        )
        assert undeclared.status_code == 422


# ---- 1. control organization attribution and atomic authorisation ------------------------


def _account_control_source(app_database_url: str, account_id: str) -> tuple[str, str | None]:
    row = _rows(
        app_database_url,
        "SELECT control_organization_source, control_organization_id FROM content_accounts WHERE id = %s",
        (account_id,),
    )[0]
    control = row["control_organization_id"]
    return str(row["control_organization_source"]), (str(control) if control else None)


def _set_control_organization(app_database_url: str, account_id: str, organization_id: str | None, source: str) -> None:
    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            "UPDATE content_accounts SET control_organization_id = %s, "
            "control_organization_source = %s WHERE tenant_id = %s AND id = %s",
            (organization_id, source, str(TENANT_ID), account_id),
        )


def test_an_inferred_control_organization_grants_nothing_until_it_is_declared(
    app_database_url: str,
) -> None:
    operator_id = _unassigned_operator(app_database_url, "未声明控制组织操作者")
    app = create_app(Settings.model_validate({}))
    with TestClient(app) as manager:
        manager.get("/ui/select/admin")
        organizations = manager.get("/api/v1/tenant-management/control-organizations").json()
        own = next(item for item in organizations if item["id"] == str(ORG_ID))
        created = manager.post(
            "/api/v1/tenant-management/publishing-accounts",
            json={
                "name": f"未声明控制组织账号-{uuid4().hex[:8]}",
                "channel": "抖音",
                "content_role_name": f"未声明控制组织表达身份-{uuid4().hex[:8]}",
                "voice_boundary": "只用于验证推断值不授予任何维护资格。",
                "operator_id": operator_id,
            },
        )
        assert created.status_code == 201
        account_id = created.json()["id"]
        assert _account_control_source(app_database_url, account_id) == ("unset", None)

        url = f"/api/v1/tenant-management/publishing-accounts/{account_id}/expression-profile"
        undeclared = manager.get(url).json()
        assert undeclared["can_maintain"] is False
        assert undeclared["can_declare"] is True
        assert manager.post(f"{url}/versions", json=_SEGMENTS).status_code == 422

        # Exactly the state the migration leaves behind: a value inferred from a creation event.
        _set_control_organization(app_database_url, account_id, own["id"], "inferred")
        inferred = manager.get(url).json()
        assert inferred["control_organization"] == own["name"]
        assert inferred["control_organization_source"] == "inferred"
        assert inferred["can_maintain"] is False
        refused = manager.post(f"{url}/versions", json=_SEGMENTS)
        assert refused.status_code == 422
        assert "控制组织" in refused.json()["detail"]

        declared = manager.post(
            f"/api/v1/tenant-management/publishing-accounts/{account_id}/control-organization",
            json={"organization_id": own["id"]},
        )
        assert declared.status_code == 200
        assert declared.json()["control_organization_source"] == "declared"
        assert manager.get(url).json()["can_maintain"] is True
        assert manager.post(f"{url}/versions", json=_SEGMENTS).status_code == 201

        # Declared once, and it leaves its own trace; there is no new approval flow.
        again = manager.post(
            f"/api/v1/tenant-management/publishing-accounts/{account_id}/control-organization",
            json={"organization_id": own["id"]},
        )
        assert again.status_code == 422
    events = _rows(
        app_database_url,
        "SELECT count(*) AS total FROM activity_events "
        "WHERE event_type = 'publishing_account.control_organization_declared' AND entity_id = %s",
        (account_id,),
    )
    assert int(events[0]["total"]) == 1


def test_a_write_recheck_refuses_after_the_maintenance_grant_is_revoked(
    app_database_url: str,
) -> None:
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as owner:
        assert owner.get("/api/v1/content/account-expression-profile").json()["can_maintain"] is True
        with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
            cursor.execute(
                "UPDATE auth_grants SET can_maintain_expression_profile = false "
                "WHERE tenant_id = %s AND user_id = %s AND account_id = %s",
                (str(TENANT_ID), str(USER_ID), str(ACCOUNT_ID)),
            )
        try:
            # The earlier read said yes; the write decides for itself, inside its own transaction.
            refused = owner.post("/api/v1/content/account-expression-profile/versions", json=_SEGMENTS)
            assert refused.status_code == 422
        finally:
            with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
                cursor.execute(
                    "UPDATE auth_grants SET can_maintain_expression_profile = true "
                    "WHERE tenant_id = %s AND user_id = %s AND account_id = %s",
                    (str(TENANT_ID), str(USER_ID), str(ACCOUNT_ID)),
                )


def test_a_current_profile_pointer_cannot_name_another_accounts_profile(
    app_database_url: str,
) -> None:
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as owner:
        owner.post("/api/v1/content/account-expression-profile/versions", json=_SEGMENTS)
    foreign = _rows(
        app_database_url,
        "SELECT id FROM account_expression_profile_versions WHERE account_id = %s LIMIT 1",
        (str(ACCOUNT_ID),),
    )[0]["id"]
    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            cursor.execute(
                "UPDATE content_accounts SET current_expression_profile_id = %s WHERE tenant_id = %s AND id = %s",
                (str(foreign), str(TENANT_ID), str(STORE_CONTENT_ACCOUNT_ID)),
            )


# ---- 2. the frozen content role really is replayed ----------------------------------------


def test_a_revision_keeps_the_frozen_content_role_after_the_account_is_renamed(
    app_database_url: str,
) -> None:
    _clear_preference(app_database_url, USER_ID)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as client:
        created = client.post("/api/v1/content", json={"weak_seed": _SEED}).json()
        snapshot = _snapshot(app_database_url, created["task_id"])
        frozen_role = str(snapshot["content_role"])
        frozen_boundary = str(snapshot["content_role_boundary"])
        assert frozen_role
        assert frozen_boundary
        assert _receipt(app_database_url, created["task_id"])["content_role"] == frozen_role

        renamed = f"{frozen_role}（改名后）"
        with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
            cursor.execute(
                "UPDATE content_roles SET name = %s, voice_boundary = %s WHERE tenant_id = %s AND name = %s",
                (renamed, "改名后的表达边界，只用于这次反证。", str(TENANT_ID), frozen_role),
            )
        try:
            revised = client.post(
                f"/api/v1/tasks/{created['task_id']}/revisions",
                json={"instruction": "把结尾改短一点，其他不动。"},
            ).json()
            assert revised["version"] == 2
            # A rename changes what the next new task says; it must not rewrite this one.
            assert _latest_receipt(app_database_url, created["task_id"])["content_role"] == frozen_role
            fresh = client.post("/api/v1/content", json={"weak_seed": _SEED}).json()
            assert _receipt(app_database_url, fresh["task_id"])["content_role"] == renamed
        finally:
            with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
                cursor.execute(
                    "UPDATE content_roles SET name = %s, voice_boundary = %s WHERE tenant_id = %s AND name = %s",
                    (frozen_role, frozen_boundary, str(TENANT_ID), renamed),
                )


# ---- 3. private preference: soft note, bypass session and three axis states ---------------


def test_the_collaboration_note_reaches_generation_and_no_tenant_record(
    app_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_preference(app_database_url, USER_ID)
    note = "我平时更喜欢先说结论，再给一个具体例子。"
    seen: list[str] = []
    original = DeterministicContentGenerator.generate

    def capture(self: DeterministicContentGenerator, request: GenerationInput) -> GeneratedArtifact:
        seen.append(request.collaboration_note)
        return original(self, request)

    monkeypatch.setattr(DeterministicContentGenerator, "generate", capture)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as client:
        client.put(
            "/api/v1/user/creation-preferences",
            json={"enabled": True, "collaboration_note": note},
        )
        created = client.post("/api/v1/content", json={"weak_seed": _SEED}).json()
    assert seen[-1] == note
    snapshot = _snapshot(app_database_url, created["task_id"])
    receipt = _receipt(app_database_url, created["task_id"])
    # It steered the work, and it stayed out of every tenant-visible record.
    assert note not in json.dumps(snapshot, ensure_ascii=False)
    assert note not in json.dumps(receipt, ensure_ascii=False)
    assert receipt["writer_model"] == "deterministic-content-test-stub"
    assert receipt["reviewer_model"] == "deterministic-content-test-stub"
    assert note not in str(created["body"])
    assert snapshot["private_preference_mode"] == "applied"
    _clear_preference(app_database_url, USER_ID)


def test_the_collaboration_note_never_becomes_material_the_product_talks_about(
    app_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_preference(app_database_url, USER_ID)
    note = "我平时更喜欢先说结论，再给一个具体例子。"
    captured: list[GenerationInput] = []
    original = DeterministicContentGenerator.generate

    def capture(self: DeterministicContentGenerator, request: GenerationInput) -> GeneratedArtifact:
        captured.append(request)
        return original(self, request)

    monkeypatch.setattr(DeterministicContentGenerator, "generate", capture)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as client:
        client.put(
            "/api/v1/user/creation-preferences",
            json={"enabled": True, "collaboration_note": note},
        )
        created = client.post("/api/v1/content", json={"weak_seed": _SEED}).json()
        revised = client.post(
            f"/api/v1/tasks/{created['task_id']}/revisions",
            json={"instruction": "第二句更短一点，其他不动。"},
        ).json()
    for produced in (created, revised):
        for field in ("outline", "body"):
            assert note not in str(produced[field])
            assert "先说结论" not in str(produced[field])

    # The same adapter boundary the real model is given: the note steers the writing there, and
    # it is handed over as a working instruction, never as material the product may talk about.
    adapter = DeepSeekGenerator(
        "https://example.invalid",
        "test-key",
        "deepseek-test",
    )
    initial_frame = captured[0].narrative_frame or legacy_frame(
        tuple(
            f"source:product:{product.sku}"
            for product in captured[0].products
        )
    )
    initial_context = BoundaryContext.from_request(
        captured[0], initial_frame
    )
    prompt = adapter._writer_prompt(
        captured[0],
        initial_frame,
        initial_context,
        adapter._narrative_skeleton(
            captured[0], initial_frame, initial_context
        ),
    )
    assert note in prompt
    assert "私人协作偏好说明只调整协作方式与表达取舍，成品中不得出现它的原文、转述或对它的解释" in prompt
    # A revision replays frozen conditions, so the note is not even offered to the model.
    revised_frame = captured[-1].narrative_frame or legacy_frame(
        tuple(
            f"source:product:{product.sku}"
            for product in captured[-1].products
        )
    )
    revised_context = BoundaryContext.from_request(
        captured[-1], revised_frame
    )
    assert note not in adapter._writer_prompt(
        captured[-1],
        revised_frame,
        revised_context,
        adapter._narrative_skeleton(
            captured[-1], revised_frame, revised_context
        ),
    )
    _clear_preference(app_database_url, USER_ID)


def test_a_cross_goal_adaptation_never_re_reads_todays_private_preference(
    app_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_preference(app_database_url, USER_ID)
    note = "我平时更喜欢先说结论。"
    seen: list[str] = []
    original = DeterministicContentGenerator.generate

    def capture(self: DeterministicContentGenerator, request: GenerationInput) -> GeneratedArtifact:
        seen.append(request.collaboration_note)
        return original(self, request)

    monkeypatch.setattr(DeterministicContentGenerator, "generate", capture)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as client:
        client.put(
            "/api/v1/user/creation-preferences",
            json={
                "enabled": True,
                "direction_defaults": {"style": _STYLE_HUMOUR},
                "collaboration_note": note,
            },
        )
        source = client.post("/api/v1/content", json={"weak_seed": _SEED, "target": "douyin_video"}).json()
        assert source["applied_direction"] == ["克制的冷幽默"]
        assert seen[-1] == note

        adapted = client.post(
            f"/api/v1/tasks/{source['task_id']}/revisions",
            json={
                "instruction": "改成小红书图文，保留事实与判断。",
                "target": "xiaohongshu_graphic",
                "source_target": "douyin_video",
            },
        )
        assert adapted.status_code == 201
        result = adapted.json()
        assert result["task_id"] != source["task_id"]
        # Adapting a task to another goal is still that task's revision: today's saved default
        # and today's collaboration note stay out of it.
        assert result["applied_direction"] == []
        assert seen[-1] == ""
        assert _snapshot(app_database_url, result["task_id"])["private_preference_mode"] == "temporarily_bypassed"

        # A same-goal revision keeps replaying the snapshot, in an ordinary session and in a
        # temporary preference-free one; the revision endpoint reads that session header too.
        for headers in ({}, {"X-Diyu-Preference-Session": "bypass"}):
            revised = client.post(
                f"/api/v1/tasks/{source['task_id']}/revisions",
                json={"instruction": "第二句更短一点，其他不动。", "target": "douyin_video"},
                headers=headers,
            )
            assert revised.status_code == 201
            assert revised.json()["applied_direction"] == ["克制的冷幽默"]
            assert seen[-1] == ""
    _clear_preference(app_database_url, USER_ID)


def test_a_temporary_preference_free_session_neither_reads_nor_writes_the_preference(
    app_database_url: str,
) -> None:
    _clear_preference(app_database_url, USER_ID)
    app = create_app(Settings.model_validate({}))
    bypass = {"X-Diyu-Preference-Session": "bypass"}
    with _content_client(app) as client:
        saved = client.put(
            "/api/v1/user/creation-preferences",
            json={
                "enabled": True,
                "direction_defaults": {"style": _STYLE_HUMOUR},
                "collaboration_note": "平时更喜欢自然口语。",
                "body_related_opt_in": True,
            },
        ).json()

        catalog = client.get("/api/v1/content/expression-catalog", headers=bypass).json()
        assert catalog["preference_session"] == "bypassed"
        assert catalog["body_related_enabled"] is False
        assert catalog["saved_defaults"] == {}
        assert _BODY_RELATED not in json.dumps(catalog, ensure_ascii=False)

        opportunities = client.post("/api/v1/content/opportunities", headers=bypass).json()
        assert all(item["id"].endswith("preference") is False for item in opportunities["items"])
        assert "你自己保存的私人创作偏好" not in json.dumps(opportunities, ensure_ascii=False)

        created = client.post("/api/v1/content", json={"weak_seed": _SEED}, headers=bypass).json()
        assert created["applied_direction"] == []
        assert _snapshot(app_database_url, created["task_id"])["private_preference_mode"] == "temporarily_bypassed"

        for call in (
            client.get("/api/v1/user/creation-preferences", headers=bypass),
            client.put(
                "/api/v1/user/creation-preferences",
                json={"enabled": False},
                headers=bypass,
            ),
            client.delete("/api/v1/user/creation-preferences", headers=bypass),
        ):
            assert call.status_code == 422
            assert "临时无偏好会话" in call.json()["detail"]

        after = client.get("/api/v1/user/creation-preferences").json()
        assert after["version"] == saved["version"]
        assert after["enabled"] is True
        assert after["direction_defaults"] == {"style": _STYLE_HUMOUR}
    _clear_preference(app_database_url, USER_ID)


def test_each_axis_separates_a_saved_default_an_explicit_choice_and_switching_it_off(
    app_database_url: str,
) -> None:
    _clear_preference(app_database_url, USER_ID)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as client:
        client.put(
            "/api/v1/user/creation-preferences",
            json={"enabled": True, "direction_defaults": {"style": _STYLE_HUMOUR}},
        )
        carried = client.post("/api/v1/content", json={"weak_seed": _SEED}).json()
        origins = {
            item["axis"]: item["origin"]
            for item in _snapshot(app_database_url, carried["task_id"])["original_direction"]["selections"]
        }
        assert origins["style"] == "default"
        assert "克制的冷幽默" in carried["applied_direction"]

        chosen = client.post(
            "/api/v1/content",
            json={
                "weak_seed": _SEED,
                "creative_direction": {"selections": {"style": "CAT-STYLE-PERSONA-01"}},
            },
        ).json()
        chosen_snapshot = _snapshot(app_database_url, chosen["task_id"])
        assert [item["origin"] for item in chosen_snapshot["original_direction"]["selections"]] == ["explicit"]
        assert chosen["applied_direction"] == ["干货攻略"]

        switched_off = client.post(
            "/api/v1/content",
            json={"weak_seed": _SEED, "creative_direction": {"cleared_axes": ["style"]}},
        ).json()
        off_snapshot = _snapshot(app_database_url, switched_off["task_id"])
        assert off_snapshot["original_direction"]["cleared_axes"] == ["style"]
        assert switched_off["applied_direction"] == []

        # Switching an axis off for one task never edits the saved default itself.
        kept = client.get("/api/v1/user/creation-preferences").json()
        assert kept["direction_defaults"] == {"style": _STYLE_HUMOUR}

        # Saving with nothing selected keeps what is already saved; forgetting is its own act.
        client.put(
            "/api/v1/user/creation-preferences",
            json={"enabled": True, "direction_defaults": {}},
        )
        assert client.get("/api/v1/user/creation-preferences").json()["direction_defaults"] == {"style": _STYLE_HUMOUR}
        client.put(
            "/api/v1/user/creation-preferences",
            json={"enabled": True, "direction_defaults": {}, "clear_direction_defaults": True},
        )
        assert client.get("/api/v1/user/creation-preferences").json()["direction_defaults"] == {}
    _clear_preference(app_database_url, USER_ID)


# ---- 4. user closure: unreadable originals and the operations gap entry -------------------


def test_an_original_without_a_note_cannot_be_selected_until_one_is_written(
    app_database_url: str,
) -> None:
    _clear_preference(app_database_url, USER_ID)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as client:
        created = client.post(
            "/api/v1/materials/personal",
            json={
                "title": f"待补说明的原件-{uuid4().hex[:6]}",
                "filename": "sample.png",
                "content_type": "image/png",
                "content_base64": base64.b64encode(b"not-parsed-bytes").decode("ascii"),
            },
        ).json()
        asset_id = created["id"]
        refused = client.post("/api/v1/content", json={"weak_seed": _SEED, "material_ids": [asset_id]})
        assert refused.status_code == 422
        assert "说明" in refused.json()["detail"]

        written = client.patch(
            f"/api/v1/materials/{asset_id}/reference-note",
            json={"reference_note": "这张图里是这次要讲的那条裤子的口袋位置。"},
        ).json()
        assert written["reference_note"].startswith("这张图里")
        # The note changes what a task would read, so the reference version moves with it.
        assert written["reference_version"] == created["reference_version"] + 1

        accepted = client.post("/api/v1/content", json={"weak_seed": _SEED, "material_ids": [asset_id]})
        assert accepted.status_code == 200
        client.delete(f"/api/v1/materials/{asset_id}")

    with _content_client(app, "/ui/select/content-store") as store:
        assert (
            store.patch(
                f"/api/v1/materials/{asset_id}/reference-note",
                json={"reference_note": "别人的素材不该被我改说明。"},
            ).status_code
            == 422
        )


def test_operations_can_classify_and_answer_a_gap_candidate_and_change_nothing_else(
    app_database_url: str,
) -> None:
    control = build_content_control_service(Settings.model_validate({}))
    app = create_app(Settings.model_validate({}))
    catalog_bytes = (_CATALOG_DIR / "catalog-v1.json").read_bytes()
    with _content_client(app) as client:
        submitted = client.post(
            "/api/v1/content/unmet-capability-requests",
            json={"request_text": f"我想按门店当天客流自动排内容，现在做不到。{uuid4().hex[:6]}"},
        ).json()
        before = _counts(app_database_url)

        listed = control.ops_unmet_requests()
        mine = next(item for item in listed if item["stable_request_id"] == submitted["stable_request_id"])
        assert mine["tenant_id"] == str(TENANT_ID)
        assert mine["status"] == "received"

        answered = control.ops_classify_unmet_request(
            submitted["stable_request_id"],
            "generation_method",
            "answered",
            "这条属于生成方法缺口，已登记，不进入当前里程碑。",
        )
        assert answered["status"] == "answered"

        back = client.get("/api/v1/content/unmet-capability-requests").json()
        seen = next(item for item in back if item["stable_request_id"] == submitted["stable_request_id"])
        assert seen["gap_type"] == "generation_method"
        assert seen["status"] == "answered"
        assert seen["response_text"].startswith("这条属于生成方法缺口")

        # A candidate is a candidate: it changes no task, no run, no version and no catalog.
        assert _counts(app_database_url) == before
        assert (_CATALOG_DIR / "catalog-v1.json").read_bytes() == catalog_bytes
        catalog_after = client.get("/api/v1/content/expression-catalog").json()
        assert catalog_after["catalog_version"] == load_catalog().catalog_version


# ---- 5. natural language that names a declared label -------------------------------------


def test_free_text_naming_a_declared_label_reuses_the_visible_translation(
    app_database_url: str,
) -> None:
    _clear_preference(app_database_url, USER_ID)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as client:
        spoken = client.post("/api/v1/content", json={"weak_seed": f"{_SEED}想幽默一点。"}).json()
        assert "幽默玩梗" in spoken["translation_notice"]
        assert "克制的冷幽默" in spoken["translation_notice"]
        assert "你说的是" in spoken["translation_notice"]
        assert "克制的冷幽默" in spoken["applied_direction"]
        origins = {
            item["axis"]: item["origin"]
            for item in _snapshot(app_database_url, spoken["task_id"])["original_direction"]["selections"]
        }
        assert origins["style"] == "natural_text"

        # An explicit choice always wins over the same axis read out of the sentence.
        explicit = client.post(
            "/api/v1/content",
            json={
                "weak_seed": f"{_SEED}想幽默一点。",
                "creative_direction": {"selections": {"style": "CAT-STYLE-PERSONA-01"}},
            },
        ).json()
        assert explicit["applied_direction"] == ["干货攻略"]


def test_a_saved_default_never_outranks_what_this_task_asks_for(
    app_database_url: str,
) -> None:
    _clear_preference(app_database_url, USER_ID)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as client:
        client.put(
            "/api/v1/user/creation-preferences",
            json={"enabled": True, "direction_defaults": {"style": _STYLE_PRACTICAL}},
        )
        spoken = client.post("/api/v1/content", json={"weak_seed": f"{_SEED}这次不要干货，想幽默一点。"}).json()
        # A saved default is a standing convenience, so what this task asks for outranks it.
        assert spoken["applied_direction"] == ["克制的冷幽默"]
        assert "干货" not in str(spoken["translation_notice"])
        origins = {
            item["axis"]: item["origin"]
            for item in _snapshot(app_database_url, spoken["task_id"])["original_direction"]["selections"]
        }
        assert origins == {"style": "natural_text"}

        # Refusing the default is itself a requirement for this task: it drops for this run and
        # nothing is put in its place.
        dropped = client.post("/api/v1/content", json={"weak_seed": f"{_SEED}这次不要干货。"}).json()
        assert dropped["applied_direction"] == []
        assert dropped["translation_notice"] is None

        # The saved default itself is untouched; only an explicit save may change it.
        kept = client.post("/api/v1/content", json={"weak_seed": _SEED}).json()
        assert kept["applied_direction"] == ["干货攻略"]
        assert client.get("/api/v1/user/creation-preferences").json()["direction_defaults"] == {
            "style": _STYLE_PRACTICAL
        }
    _clear_preference(app_database_url, USER_ID)


def test_refusing_a_declared_label_is_never_read_as_choosing_it(
    app_database_url: str,
) -> None:
    catalog = load_catalog()
    for phrase in (
        "这次不要幽默玩梗",
        "不想要幽默玩梗",
        "别用幽默玩梗",
        "不用幽默玩梗",
        "取消幽默玩梗",
    ):
        reading = read_natural_text(catalog, phrase)
        assert reading.wanted == {}, phrase
        assert _STYLE_HUMOUR in reading.refused, phrase
    # The refusal words are read as words, not as a style detector: an ordinary sentence that
    # happens to contain one still chooses normally.
    wanted = read_natural_text(catalog, "不用中途整理，想幽默一点").wanted
    assert wanted["style"].stable_id == _STYLE_HUMOUR

    _clear_preference(app_database_url, USER_ID)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as client:
        plain = client.post("/api/v1/content", json={"weak_seed": f"{_SEED}这次不要幽默玩梗。"}).json()
        assert plain["applied_direction"] == []
        assert plain["translation_notice"] is None

        client.put(
            "/api/v1/user/creation-preferences",
            json={"enabled": True, "direction_defaults": {"style": _STYLE_HUMOUR}},
        )
        refused = client.post("/api/v1/content", json={"weak_seed": f"{_SEED}这次不要幽默玩梗。"}).json()
        # Neither the label the person declined nor its restrained translation may appear.
        assert refused["applied_direction"] == []
        assert refused["translation_notice"] is None
        frozen = _snapshot(app_database_url, refused["task_id"])
        assert frozen["applied_direction"] == []
        assert frozen["original_direction"]["selections"] == []
        assert "幽默" not in json.dumps(frozen["applied_direction"], ensure_ascii=False)
    _clear_preference(app_database_url, USER_ID)


def test_free_text_that_cannot_be_mapped_is_kept_exactly_as_written(
    app_database_url: str,
) -> None:
    _clear_preference(app_database_url, USER_ID)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as client:
        written = client.post("/api/v1/content", json={"weak_seed": f"{_SEED}希望读起来像清晨的散步。"}).json()
        assert written["translation_notice"] is None
        assert written["applied_direction"] == []
        assert _snapshot(app_database_url, written["task_id"])["original_direction"]["selections"] == []


def test_a_body_related_word_in_free_text_only_gets_one_plain_suggestion(
    app_database_url: str,
) -> None:
    _clear_preference(app_database_url, USER_ID)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as client:
        spoken = client.post("/api/v1/content", json={"weak_seed": f"{_SEED}最好还能显瘦。"})
        assert spoken.status_code == 200
        body = spoken.json()
        assert "显高显瘦" in body["translation_notice"]
        assert "按你原话保留" in body["translation_notice"]
        # Nothing was applied and nothing was substituted; the person still decides.
        assert body["applied_direction"] == []


@pytest.mark.parametrize("axis", list(AXIS_ORDER))
def test_every_axis_is_optional_and_has_at_most_one_choice(axis: str) -> None:
    catalog = load_catalog()
    entries = [entry for entry in catalog.entries if entry.axis == axis]
    assert entries, axis
    assert len({entry.label for entry in entries}) == len(entries)
