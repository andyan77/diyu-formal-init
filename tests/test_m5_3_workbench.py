from __future__ import annotations

import base64
from uuid import uuid4

from fastapi.testclient import TestClient

from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings

_SEED = "请解释 ZX-C218 的双面不等于一件顶两件，保留两面完整外观与样衣分量的边界。"


def test_workbench_context_and_onboarding_are_server_scoped() -> None:
    app = create_app(Settings.model_validate({}))
    with TestClient(app) as user:
        user.get("/ui/select/user")
        portal = user.get("/user")
        assert portal.status_code == 200
        assert "/ui/select/admin" not in portal.text
        user.get("/ui/select/content")
        context = user.get("/api/v1/session/context")
        assert context.status_code == 200
        payload = context.json()
        assert payload["application"] == "content"
        assert payload["identity"]["operator"] == "总部内容运营甲"
        assert "account_id" not in str(payload)
        assert user.get("/tenant-admin").status_code == 403
        assert user.get("/api/v1/admin/readiness").status_code == 403

    with TestClient(app) as manager:
        manager.get("/ui/select/admin")
        management = manager.get("/api/v1/session/context")
        assert management.json()["application"] == "tenant_management"
        assert manager.get("/content").status_code == 403
        assert manager.get("/api/v1/content/tasks").status_code == 403
        assert manager.get("/ui/select/content").status_code == 403
        assert manager.get("/ui/select/user").status_code == 403
        readiness = manager.get("/api/v1/admin/readiness").json()
        assert {item["id"] for item in readiness["items"]} == {
            "brand_expression",
            "account_role",
            "organization_materials",
        }
        baseline = manager.get("/api/v1/admin/brand-expression").json()
        confirmed = manager.post(
            "/api/v1/admin/brand-expression/confirm",
            json={"draft": baseline["draft"]},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "confirmed"


def test_dual_qualified_person_stays_one_identity_and_external_operator_never_shares_an_account_login() -> (
    None
):
    app = create_app(Settings.model_validate({}))
    with TestClient(app) as dual:
        dual.get("/ui/select/dual-user")
        user_context = dual.get("/api/v1/session/context").json()
        assert user_context["identity"]["operator"] == "总部内容与租户管理兼任甲"
        assert "/ui/select/admin" not in dual.get("/user").text
        dual.get("/ui/select/content")
        assert dual.get("/content").status_code == 200
        dual.get("/ui/select/dual-admin")
        management_context = dual.get("/api/v1/session/context").json()
        assert management_context["identity"]["operator"] == user_context["identity"]["operator"]
        assert "/ui/select/content" not in dual.get("/tenant-admin").text

    with TestClient(app) as external:
        external.get("/ui/select/external-content")
        external_context = external.get("/api/v1/session/context").json()
        assert external_context["identity"]["operator"] == "外部代运营乙"
        assert external.get("/tenant-admin").status_code == 403

    with TestClient(app) as manager:
        manager.get("/ui/select/admin")
        operators = manager.get("/api/v1/tenant-management/operators").json()
        external_operator = next(
            item for item in operators if item["display_name"] == "外部代运营乙"
        )
        assert external_operator["publishing_accounts"] == "折线之间品牌母账号·抖音"
        account = manager.get("/api/v1/tenant-management/publishing-accounts").json()[0]
        created = manager.post(
            "/api/v1/tenant-management/operators",
            json={"display_name": f"临时协作者-{uuid4()}", "account_id": account["id"]},
        )
        assert created.status_code == 201
        assert created.json()["shared_password"] is False


def test_each_user_can_only_update_one_default_persona_record() -> None:
    with TestClient(create_app(Settings.model_validate({}))) as client:
        client.get("/ui/select/user")
        first = client.post(
            "/api/v1/user/default-persona",
            json={"name": "我的唯一默认表达", "boundary": "仅说明本人当前能承担的协作位置。"},
        )
        second = client.post(
            "/api/v1/user/default-persona",
            json={
                "name": "我的唯一默认表达（更新）",
                "boundary": "仍只维护这一份本人默认表达人设。",
            },
        )
        assert first.status_code == second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        assert second.json()["version"] == first.json()["version"] + 1


def test_series_is_explicitly_created_inserted_reordered_and_reset() -> None:
    with TestClient(create_app(Settings.model_validate({}))) as client:
        client.get("/ui/select/content")
        first = client.post("/api/v1/content", json={"weak_seed": _SEED}).json()
        second = client.post(
            "/api/v1/content", json={"weak_seed": _SEED + " 换成小红书视频。"}
        ).json()
        created = client.post(
            "/api/v1/content/series",
            json={
                "title": f"M5-3 连续观察 {uuid4()}",
                "premise": "每一集由用户明确决定是否承接前情。",
            },
        )
        assert created.status_code == 201
        series_id = created.json()["id"]
        assert (
            client.post(
                f"/api/v1/content/series/{series_id}/items", json={"task_id": first["task_id"]}
            ).status_code
            == 200
        )
        inserted = client.post(
            f"/api/v1/content/series/{series_id}/items",
            json={"task_id": second["task_id"], "position": 1},
        )
        assert inserted.status_code == 200
        assert [item["task_id"] for item in inserted.json()["items"]] == [
            second["task_id"],
            first["task_id"],
        ]
        reordered = client.put(
            f"/api/v1/content/series/{series_id}/items",
            json={"task_ids": [first["task_id"], second["task_id"]]},
        )
        assert reordered.status_code == 200
        reset = client.post(f"/api/v1/content/series/{series_id}/reset", json={})
        assert reset.status_code == 200
        assert reset.json()["items"] == []


def _material_payload(
    title: str, filename: str, content_type: str, raw: bytes, *, minor: bool = False
) -> dict[str, object]:
    return {
        "title": title,
        "filename": filename,
        "content_type": content_type,
        "content_base64": base64.b64encode(raw).decode("ascii"),
        "declares_identifiable_minor": minor,
    }


def test_materials_keep_private_and_organization_entries_separate_and_reject_known_minor() -> None:
    with TestClient(create_app(Settings.model_validate({}))) as headquarters:
        headquarters.get("/ui/select/content")
        rejected = headquarters.post(
            "/api/v1/materials/personal",
            json=_material_payload("不应保存", "child.png", "image/png", b"original", minor=True),
        )
        assert rejected.status_code == 422
        personal = headquarters.post(
            "/api/v1/materials/personal",
            json=_material_payload("门店空镜参考", "store.png", "image/png", b"original"),
        )
        assert personal.status_code == 201
        organization = headquarters.post(
            "/api/v1/materials/organization",
            json=_material_payload("总部商品静物", "product.mov", "video/quicktime", b"original"),
        )
        assert organization.status_code == 201
        listed = headquarters.get("/api/v1/materials").json()
        assert {item["scope"] for item in listed} >= {"personal", "organization"}
        assert headquarters.delete(f"/api/v1/materials/{personal.json()['id']}").json() == {
            "deleted": True
        }
        text = headquarters.post(
            "/api/v1/materials/personal",
            json=_material_payload("搭配文字备注", "notes.txt", "text/plain", b"reference note"),
        )
        assert text.status_code == 201
        assert text.json()["media_type"] == "text"
        assert len(text.json()["checksum_sha256"]) == 64

    with TestClient(create_app(Settings.model_validate({}))) as store:
        store.get("/ui/select/content-store")
        denied = store.post(
            "/api/v1/materials/organization",
            json=_material_payload("越权组织素材", "store.png", "image/png", b"original"),
        )
        assert denied.status_code == 422
