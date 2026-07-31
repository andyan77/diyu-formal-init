from __future__ import annotations

import json
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from src.brain import platform_directions
from src.brain.platform_directions import direction_for
from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.seed_demo import (
    HEADQUARTERS_WECHAT_CHANNELS_ACCOUNT_ID,
    HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID,
    TENANT_ID,
)
from src.shared.types import ContentTarget

_P2D = (
    "请解释 ZX-C218 的双面不等于一件顶两件。两面均为完整正面；两种完整外观与当前样衣分量同时存在；"
    "约 310 克差异不能全部简单归因于双面结构；品牌确认本款不以极致轻量为目标；受众不应只被双面说服。"
)
_P5D = (
    "ZX-C218 无口播、无对白、无解说：同一个人、同一身内搭、同一组动作，只改变外套朝外表面；"
    "炭灰让轮廓先进入视线，深绿细格纹让纹理先进入视线，改变整身视觉重音，不把人分成两种身份。"
)


def _task_row(database_url: str, task_id: str) -> tuple[str, str, list[str], str]:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            "SELECT account_id, primary_content_product, product_refs, media_format FROM business_tasks WHERE id = %s",
            (task_id,),
        )
        row = cursor.fetchone()
    assert row is not None
    return (str(row[0]), str(row[1]), list(row[2]), str(row[3]))


def _receipt(database_url: str, task_id: str) -> dict[str, object]:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            "SELECT input_receipt FROM generation_runs WHERE task_id = %s ORDER BY started_at DESC LIMIT 1",
            (task_id,),
        )
        row = cursor.fetchone()
    assert row is not None
    return dict(row[0])


def test_platform_directions_have_complete_honest_provenance() -> None:
    targets: tuple[ContentTarget, ...] = (
        "douyin_video",
        "xiaohongshu_video",
        "xiaohongshu_graphic",
        "wechat_channels_video",
    )
    for target in targets:
        direction = direction_for(target)
        provenance = direction.provenance
        assert direction.version == "M5-2-platform-directions-v1"
        assert direction.rule_id == f"platform-direction/{target}"
        assert direction.rule_kind == "internal_platform_media_direction"
        assert direction.applicability
        assert direction.platform_capability_source_ref.startswith("https://")
        assert "不支持本资源的编辑方向" in direction.platform_capability_source_scope
        assert len(direction.direction_digest) == 64
        assert provenance.resource_schema_version == "platform-direction-resource-v2"
        assert provenance.metadata_revision == "M7-3-platform-direction-provenance-1"
        assert provenance.source_kind == "user_confirmed_internal_product_contract"
        assert all(source.startswith("docs/") for source in provenance.source_refs)
        assert all(Path(source).is_file() for source in provenance.source_refs)
        assert provenance.official_platform_rule_version is None
        assert "没有采用平台算法权重" in provenance.official_version_note
        assert provenance.observed_or_effective_at == "2026-07-21"
        assert provenance.last_verified_at == "2026-07-26"
        assert provenance.verification_status == "verified_against_repository_sources"
        assert provenance.freshness_status == "current_for_phase_1"
        assert provenance.supersedes == ()
        assert provenance.superseded_by is None
        assert provenance.maintenance_owner == "笛语系统运维"


@pytest.mark.parametrize(
    "missing_key",
    ("official_platform_rule_version", "superseded_by"),
)
def test_platform_provenance_distinguishes_explicit_null_from_a_missing_field(
    missing_key: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.loads(platform_directions._SOURCE.read_text(encoding="utf-8"))
    del resource["provenance"][missing_key]
    source = tmp_path / "platform_directions.json"
    source.write_text(json.dumps(resource, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(platform_directions, "_SOURCE", source)

    with pytest.raises(RuntimeError, match="可选版本字段缺失"):
        direction_for("douyin_video")


def test_four_targets_are_complete_and_server_mapped(app_database_url: str) -> None:
    app = create_app(Settings.model_validate({}))
    expected_accounts = {
        "douyin_video": "00000000-0000-0000-0000-000000000031",
        "xiaohongshu_video": str(HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID),
        "xiaohongshu_graphic": str(HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID),
        "wechat_channels_video": str(HEADQUARTERS_WECHAT_CHANNELS_ACCOUNT_ID),
    }
    expected_headings = {
        "douyin_video": "完整台词/解说",
        "xiaohongshu_video": "完整台词/解说",
        "xiaohongshu_graphic": "图序与每张职责",
        "wechat_channels_video": "完整台词/解说",
    }
    with TestClient(app) as client:
        client.get("/ui/select/content")
        workbench = client.get("/content")
        for label in ("抖音视频", "小红书视频", "小红书图文", "微信视频号视频"):
            assert label in workbench.text
        for target, account_id in expected_accounts.items():
            created = client.post("/api/v1/content", json={"weak_seed": _P2D, "target": target})
            assert created.status_code == 200
            payload = created.json()
            task_account, product, refs, media_format = _task_row(app_database_url, payload["task_id"])
            assert task_account == account_id
            assert product == "product_truth"
            assert refs == ["ZX-C218"]
            assert media_format == ("graphic" if target == "xiaohongshu_graphic" else "video")
            assert expected_headings[target] in payload["body"]
            assert "B-TPO-001" not in payload["body"]
        rejected = client.post(
            "/api/v1/content",
            json={
                "weak_seed": _P2D,
                "target": "xiaohongshu_graphic",
                "account_id": "client-controlled",
            },
        )
        assert rejected.status_code == 422
    with TestClient(app) as store:
        store.get("/ui/select/content-store")
        assert (
            store.post("/api/v1/content", json={"weak_seed": _P2D, "target": "xiaohongshu_graphic"}).status_code == 403
        )


def test_recompile_isolated_and_same_target_revisions_stay_on_one_item(
    app_database_url: str,
) -> None:
    with TestClient(create_app(Settings.model_validate({}))) as client:
        client.get("/ui/select/content")
        source = client.post("/api/v1/content", json={"weak_seed": _P2D, "target": "douyin_video"}).json()
        adapted = client.post(
            "/api/v1/content",
            json={
                "weak_seed": "改成小红书图文，保留事实与判断。",
                "reuse_version_id": source["version_id"],
                "target": "xiaohongshu_graphic",
            },
        )
        assert adapted.status_code == 200
        graphic = adapted.json()
        assert graphic["task_id"] != source["task_id"]
        assert graphic["version"] == 1
        assert graphic["adapted_from"] == "由抖音视频 V1 改编"
        assert "完整正文" in graphic["body"]
        original = client.get(f"/api/v1/tasks/{source['task_id']}/versions/1?target=douyin_video").json()
        assert original["body"] == source["body"]
        task_account, product, refs, media_format = _task_row(app_database_url, graphic["task_id"])
        assert task_account == str(HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID)
        assert (product, refs, media_format) == ("product_truth", ["ZX-C218"], "graphic")
        target_history = client.get("/api/v1/content/tasks?target=xiaohongshu_graphic").json()
        persisted = next(item for item in target_history if item["task_id"] == graphic["task_id"])
        assert persisted["source_version_id"] == source["version_id"]
        revised = client.post(
            f"/api/v1/tasks/{graphic['task_id']}/revisions",
            json={"instruction": "我只能补拍四张。", "target": "xiaohongshu_graphic"},
        )
        assert revised.status_code == 201
        graphic_v2 = revised.json()
        assert graphic_v2["version"] == 2
        assert graphic_v2["adapted_from"] == "由抖音视频 V1 改编"
        assert "只补拍四张" not in graphic_v2["body"]
        assert "可选补拍建议" in graphic_v2["body"]
        assert "没有也不影响" in graphic_v2["body"]
        revision_receipt = _receipt(app_database_url, graphic["task_id"])
        assert revision_receipt["source_description"] == "由抖音视频 V1 改编"
        assert (
            client.get(f"/api/v1/content/tasks/{graphic['task_id']}/versions?target=xiaohongshu_graphic").json()[0][
                "version"
            ]
            == 2
        )
        assert (
            client.get(f"/api/v1/tasks/{source['task_id']}/versions/1?target=douyin_video").json()["body"]
            == source["body"]
        )


def test_same_target_reuse_parent_is_not_mislabeled_as_platform_adaptation(
    app_database_url: str,
) -> None:
    with TestClient(create_app(Settings.model_validate({}))) as client:
        client.get("/ui/select/content")
        source = client.post(
            "/api/v1/content",
            json={"weak_seed": _P2D, "target": "douyin_video"},
        ).json()
        separate = client.post(
            "/api/v1/content",
            json={
                "weak_seed": "另外做一条独立内容，保留商品事实并换一个讲法。",
                "reuse_version_id": source["version_id"],
                "target": "douyin_video",
            },
        )
        assert separate.status_code == 200
        separate_value = separate.json()
        assert separate_value["task_id"] != source["task_id"]
        revised = client.post(
            f"/api/v1/tasks/{separate_value['task_id']}/revisions",
            json={
                "instruction": "只把开头说得更直接。",
                "target": "douyin_video",
            },
        )
        assert revised.status_code == 201
        assert revised.json()["adapted_from"] is None
        receipt = _receipt(app_database_url, separate_value["task_id"])
        assert receipt["source_description"] is None


def test_transform_boundaries_receipts_and_silent_store_video(app_database_url: str) -> None:
    with TestClient(create_app(Settings.model_validate({}))) as headquarters:
        headquarters.get("/ui/select/content")
        source = headquarters.post("/api/v1/content", json={"weak_seed": _P2D, "target": "douyin_video"}).json()
        short = headquarters.post(
            f"/api/v1/tasks/{source['task_id']}/revisions",
            json={"instruction": "压成 8 秒，什么都别删。", "target": "douyin_video"},
        )
        assert short.status_code == 201
        assert "8 秒窄主题版" in short.json()["body"]
        assert (
            headquarters.get(f"/api/v1/tasks/{source['task_id']}/versions/1?target=douyin_video").json()["body"]
            == source["body"]
        )
        receipt = _receipt(app_database_url, source["task_id"])
        assert receipt["target"] == "douyin_video"
        assert receipt["target_platform"] == "抖音"
        assert receipt["media_format"] == "video"
        assert receipt["platform_direction_version"] == "M5-2-platform-directions-v1"
        snapshot = receipt["platform_direction_snapshot"]
        assert isinstance(snapshot, dict)
        assert snapshot["version"] == receipt["platform_direction_version"]
        assert snapshot["rule_id"] == "platform-direction/douyin_video"
        assert snapshot["rule_kind"] == "internal_platform_media_direction"
        assert snapshot["official_platform_rule_version"] is None
        assert snapshot["last_verified_at"] == "2026-07-26"
        assert snapshot["freshness_status"] == "current_for_phase_1"
        assert snapshot["maintenance_owner"] == "笛语系统运维"
        assert snapshot["direction_digest"] == direction_for("douyin_video").direction_digest
        assert "8 秒" in str(receipt["production_conditions"])
    with TestClient(create_app(Settings.model_validate({}))) as store:
        store.get("/ui/select/content-store")
        created = store.post("/api/v1/content", json={"weak_seed": _P5D, "target": "douyin_video"})
        assert created.status_code == 200
        payload = created.json()
        assert payload["kind"] == "question"
        assert "当前可用于制作的登记商品素材" in payload["message"]


def test_openapi_exposes_only_target_names_and_not_account_ids() -> None:
    contract = create_app(Settings.model_validate({})).openapi()
    schema = contract["components"]["schemas"]["CreateContentRequest"]
    assert "target" in schema["properties"]
    assert "account_id" not in schema["properties"]
