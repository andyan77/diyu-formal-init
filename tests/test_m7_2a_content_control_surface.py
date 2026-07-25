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
    reconcile_sources,
)
from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.seed_demo import (
    ACCOUNT_ID,
    STORE_CONTENT_ACCOUNT_ID,
    STORE_CONTENT_USER_ID,
    TENANT_ID,
    USER_ID,
)

_FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "src" / "main.tsx"
_CATALOG_DIR = Path(__file__).resolve().parents[1] / "config" / "content_expression"
_SEED = "开完一个正式会议后还要接孩子，这一身怎么穿才不用中途反复整理？"
_STYLE_HUMOUR = "CAT-STYLE-PERSONA-06"
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
        "SELECT input_receipt FROM generation_runs WHERE task_id = %s "
        "ORDER BY started_at DESC LIMIT 1",
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
    assert len(gaps) == 3
    assert all(identifier.startswith("CAT-SOURCE-GAP-") for identifier in gaps)
    assert sum(item["defined"] for item in summary.values()) == 116
    assert sum(item["declared_target"] for item in summary.values()) == 119

    by_id = {str(record["stable_id"]): record for record in inventory}
    for gap in gaps:
        assert by_id[gap]["visible_in_compact_v1"] is False
        assert by_id[gap]["gap_type"] == "source_gap"
        assert "F10" in str(by_id[gap]["destination"])

    visible = {
        str(record["stable_id"])
        for record in inventory
        if record["visible_in_compact_v1"] is True
    }
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
    catalog_paths = {
        path: set(methods)
        for path, methods in schema["paths"].items()
        if "expression-catalog" in path
    }
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

        created = owner.post(
            "/api/v1/content/account-expression-profile/versions", json=_SEGMENTS
        )
        assert created.status_code == 201
        version_one = created.json()
        after_first = owner.get("/api/v1/content/account-expression-profile").json()
        assert after_first["current"]["version"] == version_one["version"]
        assert after_first["draft"] is None

        changed = dict(_SEGMENTS)
        changed["content_territories"] = "本轮把内容领地收敛为穿衣处境与商品取舍两类。"
        second = owner.post(
            "/api/v1/content/account-expression-profile/versions", json=changed
        ).json()
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
        assert (
            store.post("/api/v1/content/account-expression-profile/versions", json=_SEGMENTS).status_code
            == 422
        )
    with _content_client(app, "/ui/select/external-content") as external:
        # The grant allows profile maintenance, but the person's organization does not control
        # the account, so the write still fails closed.
        assert (
            external.get("/api/v1/content/account-expression-profile").json()["can_maintain"] is False
        )
        assert (
            external.post(
                "/api/v1/content/account-expression-profile/versions", json=_SEGMENTS
            ).status_code
            == 422
        )


def test_headquarters_administrator_cannot_maintain_another_control_organizations_account() -> None:
    app = create_app(Settings.model_validate({}))
    with TestClient(app) as manager:
        manager.get("/ui/select/admin")
        own = manager.get(
            f"/api/v1/tenant-management/publishing-accounts/{ACCOUNT_ID}/expression-profile"
        ).json()
        assert own["can_maintain"] is True
        other = manager.get(
            f"/api/v1/tenant-management/publishing-accounts/{STORE_CONTENT_ACCOUNT_ID}"
            "/expression-profile"
        ).json()
        assert other["can_maintain"] is False
        assert (
            manager.post(
                f"/api/v1/tenant-management/publishing-accounts/{STORE_CONTENT_ACCOUNT_ID}"
                "/expression-profile/versions",
                json=_SEGMENTS,
            ).status_code
            == 422
        )
        missing = manager.get(
            f"/api/v1/tenant-management/publishing-accounts/{uuid4()}/expression-profile"
        )
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
        bypassed = owner.post(
            "/api/v1/content", json={"weak_seed": _SEED, "use_personal_preferences": False}
        ).json()
        assert bypassed["applied_direction"] == []
        assert (
            _snapshot(app_database_url, bypassed["task_id"])["private_preference_mode"]
            == "temporarily_bypassed"
        )
        assert (
            _snapshot(app_database_url, applied["task_id"])["private_preference_mode"] == "applied"
        )

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
        assert (
            owner.get("/api/v1/content/account-expression-profile").json()["current"]
            == before_profile
        )


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
                "content_base64": base64.b64encode(
                    "通勤路上最常见的问题是外套一坐就皱。".encode()
                ).decode("ascii"),
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

        undescribed = owner.post(
            "/api/v1/content", json={"weak_seed": _SEED, "material_ids": [silent["id"]]}
        )
        assert undescribed.status_code == 422
        assert "可读说明" in undescribed.json()["detail"]

    with _content_client(app, "/ui/select/content-store") as store:
        stolen = store.post(
            "/api/v1/content", json={"weak_seed": _SEED, "material_ids": [text_asset["id"]]}
        )
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
        frozen_version = client.get("/api/v1/content/account-expression-profile").json()["current"][
            "version"
        ]
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
        assert (
            _receipt(app_database_url, created["task_id"])["account_expression_profile_version"]
            == frozen_version
        )

        moved_on = dict(_SEGMENTS)
        moved_on["identity_position"] = "换了一版之后的表达身份说明。"
        newer = client.post(
            "/api/v1/content/account-expression-profile/versions", json=moved_on
        ).json()
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
            _latest_receipt(app_database_url, created["task_id"])[
                "account_expression_profile_version"
            ]
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
        readable = client.get(
            f"/api/v1/tasks/{created['task_id']}/versions/1"
        )
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
    assert "这次参考（可选）" in source
    assert source.count('first="对话"') == 2
    assert source.count("<MobileTabs") == 2
    assert "设置页" not in source
    assert "上下文" not in source
    # The identity drawer showed the acting person twice; the summary already carries it.
    assert "实际操作人" not in source
    assert "translation_notice" in source
    # A revision may answer with a question; the artifact pane must not treat that as a version.
    assert 'if (!("task_id" in value)) { onNotice(value.message); return; }' in source
    # A saved default really steers the request, so the collapsed summary must reveal it.
    assert "你保存的默认" in source
    # Saving axis defaults must not overwrite the note written in the personal entry.
    assert 'collaboration_note: preference.data?.collaboration_note ?? ""' in source
    assert "applied_direction" in source


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


def test_account_creation_records_a_control_organization_and_a_separate_maintenance_grant() -> None:
    app = create_app(Settings.model_validate({}))
    with TestClient(app) as manager:
        manager.get("/ui/select/admin")
        created = manager.post(
            "/api/v1/tenant-management/publishing-accounts",
            json={
                "name": f"控制组织回归账号-{uuid4().hex[:8]}",
                "channel": "抖音",
                "content_role_name": f"控制组织回归表达身份-{uuid4().hex[:8]}",
                "voice_boundary": "只用于验证新建账号会记录控制组织。",
                "operator_id": str(USER_ID),
            },
        )
        assert created.status_code == 201
        account_id = created.json()["id"]
        # A brand new account must be maintainable, i.e. its control organization is not NULL.
        profile = manager.get(
            f"/api/v1/tenant-management/publishing-accounts/{account_id}/expression-profile"
        ).json()
        assert profile["can_maintain"] is True
        assert profile["control_organization"]
        saved = manager.post(
            f"/api/v1/tenant-management/publishing-accounts/{account_id}/expression-profile/versions",
            json=_SEGMENTS,
        )
        assert saved.status_code == 201
        assert saved.json()["version"] == 1


@pytest.mark.parametrize("axis", list(AXIS_ORDER))
def test_every_axis_is_optional_and_has_at_most_one_choice(axis: str) -> None:
    catalog = load_catalog()
    entries = [entry for entry in catalog.entries if entry.axis == axis]
    assert entries, axis
    assert len({entry.label for entry in entries}) == len(entries)
