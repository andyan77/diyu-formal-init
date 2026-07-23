from __future__ import annotations

import psycopg
from fastapi.testclient import TestClient

from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.seed_demo import (
    HEADQUARTERS_WECHAT_CHANNELS_ACCOUNT_ID,
    HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID,
    TENANT_ID,
)

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


def test_four_targets_are_complete_and_server_mapped(app_database_url: str) -> None:
    app = create_app(Settings.model_validate({}))
    expected_accounts = {
        "douyin_video": "00000000-0000-0000-0000-000000000031",
        "xiaohongshu_video": str(HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID),
        "xiaohongshu_graphic": str(HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID),
        "wechat_channels_video": str(HEADQUARTERS_WECHAT_CHANNELS_ACCOUNT_ID),
    }
    expected_headings = {
        "douyin_video": "完整观看链",
        "xiaohongshu_video": "完整观看链",
        "xiaohongshu_graphic": "图序与每张职责",
        "wechat_channels_video": "完整观看链",
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
            task_account, product, refs, media_format = _task_row(
                app_database_url, payload["task_id"]
            )
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
            store.post(
                "/api/v1/content", json={"weak_seed": _P2D, "target": "xiaohongshu_graphic"}
            ).status_code
            == 403
        )


def test_recompile_isolated_and_same_target_revisions_stay_on_one_item(
    app_database_url: str,
) -> None:
    with TestClient(create_app(Settings.model_validate({}))) as client:
        client.get("/ui/select/content")
        source = client.post(
            "/api/v1/content", json={"weak_seed": _P2D, "target": "douyin_video"}
        ).json()
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
        assert "完整发布正文" in graphic["body"]
        original = client.get(
            f"/api/v1/tasks/{source['task_id']}/versions/1?target=douyin_video"
        ).json()
        assert original["body"] == source["body"]
        task_account, product, refs, media_format = _task_row(app_database_url, graphic["task_id"])
        assert task_account == str(HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID)
        assert (product, refs, media_format) == ("product_truth", ["ZX-C218"], "graphic")
        revised = client.post(
            f"/api/v1/tasks/{graphic['task_id']}/revisions",
            json={"instruction": "我只能补拍四张。", "target": "xiaohongshu_graphic"},
        )
        assert revised.status_code == 201
        graphic_v2 = revised.json()
        assert graphic_v2["version"] == 2
        assert "只补拍四张" in graphic_v2["body"]
        assert (
            client.get(f"/api/v1/tasks/{source['task_id']}/versions/1?target=douyin_video").json()[
                "body"
            ]
            == source["body"]
        )


def test_transform_boundaries_receipts_and_silent_store_video(app_database_url: str) -> None:
    with TestClient(create_app(Settings.model_validate({}))) as headquarters:
        headquarters.get("/ui/select/content")
        source = headquarters.post(
            "/api/v1/content", json={"weak_seed": _P2D, "target": "douyin_video"}
        ).json()
        short = headquarters.post(
            f"/api/v1/tasks/{source['task_id']}/revisions",
            json={"instruction": "压成 8 秒，什么都别删。", "target": "douyin_video"},
        )
        assert short.status_code == 201
        assert "8 秒窄主题版" in short.json()["body"]
        assert (
            headquarters.get(
                f"/api/v1/tasks/{source['task_id']}/versions/1?target=douyin_video"
            ).json()["body"]
            == source["body"]
        )
        receipt = _receipt(app_database_url, source["task_id"])
        assert receipt["target"] == "douyin_video"
        assert receipt["target_platform"] == "抖音"
        assert receipt["media_format"] == "video"
        assert receipt["platform_direction_version"] == "M5-2-platform-directions-v1"
        assert "8 秒" in str(receipt["production_conditions"])
    with TestClient(create_app(Settings.model_validate({}))) as store:
        store.get("/ui/select/content-store")
        created = store.post("/api/v1/content", json={"weak_seed": _P5D, "target": "douyin_video"})
        assert created.status_code == 200
        body = created.json()["body"]
        assert "完整观看链" in body
        assert "无口播、无对白、无解说" in body
        assert "声音与制作提示" in body
        assert "图序与每张职责" not in body


def test_openapi_exposes_only_target_names_and_not_account_ids() -> None:
    contract = create_app(Settings.model_validate({})).openapi()
    schema = contract["components"]["schemas"]["CreateContentRequest"]
    assert "target" in schema["properties"]
    assert "account_id" not in schema["properties"]
