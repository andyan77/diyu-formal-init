from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

import src.gateway.api.app as app_module
from src.brain.content_service import ContentService
from src.brain.workbench_service import WorkbenchService
from src.composition.bootstrap import build_content_control_service
from src.gateway.api.settings import Settings
from src.infrastructure.local_object_store import LocalObjectStore
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.production_auth import MODEL_REQUEST_DUPLICATE_WINDOW_SECONDS
from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.shared.errors import DomainError
from src.tool.run_tenant01_formal_vertical import (
    FormalBoundaryGenerator,
    _dictionary,
    _login,
    _settings,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SERIES_INPUT = "下雨天走回家的时候，忽然觉得慢一点也没有关系"
_P5_INPUT = "请为两件商品生成一条商品视觉成品"


def _head_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write_private(path: Path, document: dict[str, object]) -> str:
    if path.exists():
        raise DomainError("正式支持面证据已存在，拒绝静默覆盖")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    payload = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(payload)
    path.chmod(0o600)
    if path.stat().st_mode & 0o077:
        raise DomainError("正式支持面证据权限不是 0600")
    return hashlib.sha256(payload).hexdigest()


def _stream(
    client: TestClient,
    *,
    account_id: str,
    message: str,
    request_id: str | None = None,
    product_media_intent: bool = False,
    series_id: str | None = None,
    series_position: int | None = None,
    creative_direction: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    response = client.post(
        "/api/v1/content/stream",
        json={
            "message": message,
            "conversation": [],
            "publishing_identity_id": account_id,
            "target": "douyin_video",
            "material_ids": [],
            "product_media_intent": product_media_intent,
            "series_id": series_id,
            "series_position": series_position,
            "creative_direction": creative_direction,
            "interaction_mode": "generate",
            "direct_generate": True,
            "request_id": request_id or str(uuid4()),
        },
    )
    if response.status_code != 200:
        raise DomainError(f"正式支持面流式入口失败 ({response.status_code})")
    return [
        _dictionary(json.loads(line), "正式支持面流式事件无效") for line in response.text.splitlines() if line.strip()
    ]


def _business_counts(database_url: str, tenant_id: UUID) -> dict[str, int]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.execute(
            "SELECT set_config('app.tenant_id', %s, true)",
            (str(tenant_id),),
        )
        row = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM business_tasks WHERE tenant_id=%s) AS tasks,
              (SELECT count(*) FROM generation_runs WHERE tenant_id=%s) AS runs,
              (SELECT count(*) FROM content_versions WHERE tenant_id=%s) AS versions,
              (SELECT count(*) FROM generation_runs
                WHERE tenant_id=%s AND status='running') AS running,
              (SELECT count(*) FROM display_tasks WHERE tenant_id=%s) AS display_tasks,
              (SELECT count(*) FROM display_artifact_versions
                WHERE tenant_id=%s) AS display_versions
            """,
            (tenant_id, tenant_id, tenant_id, tenant_id, tenant_id, tenant_id),
        ).fetchone()
    if row is None:
        raise DomainError("正式支持面业务对象计数无法读取")
    return {
        key: int(row[key])
        for key in (
            "tasks",
            "runs",
            "versions",
            "running",
            "display_tasks",
            "display_versions",
        )
    }


def _scope_params(account_id: str) -> dict[str, str]:
    return {
        "target": "douyin_video",
        "publishing_identity_id": account_id,
    }


def _profile_segments(profile: dict[str, object]) -> dict[str, str]:
    current = _dictionary(profile.get("current"), "正式账号画像 current 缺失")
    raw_segments = current.get("segments")
    segments = _dictionary(raw_segments, "正式账号画像五段缺失") if raw_segments is not None else current
    keys = (
        "identity_position",
        "authority_boundary",
        "audience_relationship",
        "content_territories",
        "default_production_conditions",
    )
    values = {key: str(segments.get(key, "")).strip() for key in keys}
    if any(not value for value in values.values()):
        raise DomainError("正式账号画像五段不完整")
    return values


def run(
    *,
    database_url: str,
    credentials_path: Path,
    context_evidence_path: Path,
    output_path: Path,
    candidate_sha: str,
) -> dict[str, object]:
    if _head_sha() != candidate_sha:
        raise DomainError("正式支持面候选 SHA 与当前 HEAD 不一致")
    if output_path.exists():
        raise DomainError("正式支持面证据已存在，拒绝静默覆盖")
    credentials = _dictionary(
        json.loads(credentials_path.read_text(encoding="utf-8")),
        "正式支持面凭据文件无效",
    )
    context_evidence = _dictionary(
        json.loads(context_evidence_path.read_text(encoding="utf-8")),
        "正式支持面上下文证据无效",
    )
    if (
        credentials.get("candidate_sha") != candidate_sha
        or context_evidence.get("candidate_sha") != candidate_sha
        or credentials.get("tenant_id") != context_evidence.get("tenant_id")
        or context_evidence.get("verdict") != "PASS"
    ):
        raise DomainError("正式支持面凭据、上下文证据或候选 SHA 不一致")
    if credentials_path.stat().st_mode & 0o077:
        raise DomainError("正式支持面凭据权限不是 0600")
    tenant_id = UUID(str(credentials["tenant_id"]))
    account_id = str(credentials["account_id"])
    cases = {
        str(item["case_id"]): item
        for item in cast(
            list[dict[str, object]],
            context_evidence.get("cases", []),
        )
    }
    factory_task_id = str(_dictionary(cases.get("factory_actuality"), "正式验厂任务证据缺失")["task_id"])

    object_root = output_path.parent / ".formal-surface-objects"
    if object_root.exists():
        raise DomainError("正式支持面临时对象目录已存在")
    generator = FormalBoundaryGenerator()
    original_content_builder = cast(
        Callable[[Settings], ContentService],
        app_module.build_content_service,  # type: ignore[attr-defined]
    )
    original_workbench_builder = cast(
        Callable[[Settings], WorkbenchService],
        app_module.build_workbench_service,  # type: ignore[attr-defined]
    )

    def content_builder(settings: Settings) -> ContentService:
        return ContentService(
            PostgresContentRepository(settings.app_database_url),
            generator,
            build_content_control_service(settings),
        )

    def workbench_builder(settings: Settings) -> WorkbenchService:
        return WorkbenchService(
            PostgresWorkbenchRepository(settings.app_database_url),
            LocalObjectStore(str(object_root)),
            runtime_sha=candidate_sha,
        )

    app_module.build_content_service = content_builder  # type: ignore[attr-defined]
    app_module.build_workbench_service = workbench_builder  # type: ignore[attr-defined]
    try:
        app = app_module.create_app(_settings(database_url, candidate_sha))
    finally:
        app_module.build_content_service = original_content_builder  # type: ignore[attr-defined,assignment]
        app_module.build_workbench_service = original_workbench_builder  # type: ignore[attr-defined,assignment]

    checks: list[dict[str, object]] = []
    details: dict[str, object] = {}
    try:
        with TestClient(app, base_url="https://diyu.example") as public:
            public_statuses = {
                route: public.get(route, follow_redirects=False).status_code
                for route in (
                    "/",
                    "/login",
                    "/tenant-admin/login",
                    "/ops/login",
                    "/status",
                )
            }
            if any(status != 200 for status in public_statuses.values()):
                raise DomainError("正式公共、登录或状态入口不可用")
            invalid = public.post(
                "/api/v1/content/stream",
                json={
                    "message": "未认证边界验证",
                    "conversation": [],
                    "publishing_identity_id": str(uuid4()),
                    "target": "douyin_video",
                    "interaction_mode": "generate",
                    "direct_generate": True,
                },
            )
            if invalid.status_code != 401 or invalid.json().get("error_code") != "AUTH_REQUIRED":
                raise DomainError("未认证请求没有稳定 AUTH_REQUIRED")
            details["public_auth"] = public_statuses
            checks.append({"id": "PUBLIC_AUTH_AND_STATUS", "status": "PASS"})

        with TestClient(app, base_url="https://diyu.example") as admin:
            _login(
                admin,
                "/tenant-admin/login",
                str(credentials["admin_username"]),
                str(credentials["admin_password"]),
            )
            wrong_entry = admin.get("/user", follow_redirects=False)
            if wrong_entry.status_code != 403 or admin.get("/api/v1/session/context").status_code != 200:
                raise DomainError("管理员错入口没有保留有效会话")
            usage_7 = admin.get(
                "/api/v1/tenant-management/team-usage",
                params={"window_days": 7},
            )
            usage_30 = admin.get(
                "/api/v1/tenant-management/team-usage",
                params={"window_days": 30},
            )
            if (
                usage_7.status_code != 200
                or usage_30.status_code != 200
                or usage_7.json().get("window_days") != 7
                or usage_30.json().get("window_days") != 30
            ):
                raise DomainError("团队使用 7/30 日真实摘要不可用")
            checks.extend(
                (
                    {"id": "WRONG_ENTRY_SESSION_PRESERVED", "status": "PASS"},
                    {"id": "TEAM_USAGE_7_30", "status": "PASS"},
                )
            )

            marker = uuid4().hex[:8]
            created_org = admin.post(
                "/api/v1/tenant-management/organizations",
                json={
                    "name": f"正式支持面空组织-{marker}",
                    "organization_level": "unspecified",
                    "parent_organization_id": None,
                    "as_synthetic_business_fixture": False,
                },
            )
            if created_org.status_code != 201:
                raise DomainError("正式组织 API 创建失败")
            organization_id = str(created_org.json()["id"])
            changed_org = admin.patch(
                f"/api/v1/tenant-management/organizations/{organization_id}",
                json={
                    "name": f"正式支持面空组织已修改-{marker}",
                    "organization_level": "region",
                    "parent_organization_id": credentials["headquarters_organization_id"],
                },
            )
            if changed_org.status_code != 200:
                raise DomainError("正式组织 API 修改失败")
            disabled_org = admin.put(
                f"/api/v1/tenant-management/organizations/{organization_id}/enabled",
                json={"enabled": False},
            )
            control_orgs = admin.get("/api/v1/tenant-management/control-organizations")
            if disabled_org.status_code != 200 or any(
                item.get("id") == organization_id for item in cast(list[dict[str, object]], control_orgs.json())
            ):
                raise DomainError("已停用组织仍进入新的业务选择器")
            restored_org = admin.put(
                f"/api/v1/tenant-management/organizations/{organization_id}/enabled",
                json={"enabled": True},
            )
            referenced_disable = admin.put(
                f"/api/v1/tenant-management/organizations/{credentials['headquarters_organization_id']}/enabled",
                json={"enabled": False},
            )
            if (
                restored_org.status_code != 200
                or referenced_disable.status_code != 422
                or referenced_disable.json().get("error_code") != "ORGANIZATION_IN_USE"
            ):
                raise DomainError("组织恢复或被引用组织的失败关闭不成立")
            details["organization_lifecycle"] = {
                "created": True,
                "updated": True,
                "disabled_excluded": True,
                "restored": True,
                "referenced_error_code": "ORGANIZATION_IN_USE",
            }
            checks.append({"id": "ORGANIZATION_LIFECYCLE_API", "status": "PASS"})

            profile_response = admin.get(
                f"/api/v1/tenant-management/publishing-accounts/{account_id}/expression-profile"
            )
            if profile_response.status_code != 200:
                raise DomainError("正式账号画像不可读取")
            profile = _dictionary(profile_response.json(), "正式账号画像无效")
            segments = _profile_segments(profile)
            segments["identity_position"] += "；正式支持面版本验证"
            saved_profile = admin.post(
                f"/api/v1/tenant-management/publishing-accounts/{account_id}/expression-profile/versions",
                json=segments,
            )
            profile_versions = admin.get(
                f"/api/v1/tenant-management/publishing-accounts/{account_id}/expression-profile/versions"
            )
            if (
                saved_profile.status_code != 201
                or profile_versions.status_code != 200
                or len(profile_versions.json()) < 2
            ):
                raise DomainError("正式五段画像 V1→V2→历史不可用")
            checks.append({"id": "ACCOUNT_PROFILE_V1_V2_HISTORY", "status": "PASS"})

            library_payload = {
                "category": "reference",
                "title": f"正式支持面资料-{marker}",
                "source_note": "正式支持面有界生命周期验证",
                "content": "这条临时资料只用于验证预览、版本和停用消费者。",
                "version": "V1",
                "visibility_scope": "brand_all",
                "organization_ids": [],
            }
            preview = admin.post(
                "/api/v1/tenant-management/brand-library/preview",
                json=library_payload,
            )
            created_entry = admin.post(
                "/api/v1/tenant-management/brand-library",
                json=library_payload | {"status": "active", "confirm_as_current": True},
            )
            if preview.status_code != 200 or created_entry.status_code != 201:
                raise DomainError("正式品牌资料预览或确认失败")
            entry_id = str(created_entry.json()["id"])
            new_entry_version = admin.post(
                f"/api/v1/tenant-management/brand-library/{entry_id}/versions",
                json={key: value for key, value in library_payload.items() if key != "category"}
                | {
                    "title": f"正式支持面资料已修改-{marker}",
                    "version": "V2",
                },
            )
            entry_versions = admin.get(f"/api/v1/tenant-management/brand-library/{entry_id}/versions")
            disabled_entry = admin.put(
                f"/api/v1/tenant-management/brand-library/{entry_id}/enabled",
                json={"enabled": False},
            )
            if (
                new_entry_version.status_code != 200
                or entry_versions.status_code != 200
                or len(entry_versions.json()) != 2
                or disabled_entry.status_code != 200
            ):
                raise DomainError(
                    "正式品牌资料版本或停用生命周期失败 "
                    f"(version={new_entry_version.status_code}, "
                    f"history={entry_versions.status_code}/"
                    f"{len(entry_versions.json()) if entry_versions.status_code == 200 else -1}, "
                    f"disable={disabled_entry.status_code})"
                )
            checks.append({"id": "BRAND_LIBRARY_LIFECYCLE", "status": "PASS"})

            material_bytes = b"bounded formal organization material lifecycle"
            material_payload = {
                "organization_id": credentials["headquarters_organization_id"],
                "title": f"正式支持面组织素材-{marker}",
                "filename": "formal-surface.txt",
                "content_type": "text/plain",
                "content_base64": base64.b64encode(material_bytes).decode(),
                "declares_identifiable_minor": False,
                "reference_note": "仅验证组织素材生命周期，不进入 Writer。",
                "visibility_scope": "brand_all",
                "organization_ids": [],
            }
            created_material = admin.post(
                "/api/v1/tenant-management/organization-materials",
                json=material_payload,
            )
            if created_material.status_code != 201:
                raise DomainError("正式组织素材上传失败")
            asset_id = str(created_material.json()["id"])
            material_version = admin.post(
                f"/api/v1/tenant-management/organization-materials/{asset_id}/versions",
                json={
                    "title": f"正式支持面组织素材已修改-{marker}",
                    "reference_note": "已复核的生命周期说明，不进入 Writer。",
                    "visibility_scope": "brand_all",
                    "organization_ids": [],
                },
            )
            disabled_material = admin.put(
                f"/api/v1/tenant-management/organization-materials/{asset_id}/enabled",
                json={"enabled": False},
            )
            restored_material = admin.put(
                f"/api/v1/tenant-management/organization-materials/{asset_id}/enabled",
                json={"enabled": True},
            )
            deleted_material = admin.delete(f"/api/v1/tenant-management/organization-materials/{asset_id}")
            if any(
                response.status_code != 200
                for response in (
                    material_version,
                    disabled_material,
                    restored_material,
                    deleted_material,
                )
            ):
                raise DomainError("正式组织素材版本、停用、恢复或删除失败")
            checks.append({"id": "ORGANIZATION_MATERIAL_LIFECYCLE", "status": "PASS"})

            products = admin.get("/api/v1/tenant-management/brand-products")
            product_versions = admin.get("/api/v1/tenant-management/brand-products/DIYU-CSPU-004/versions")
            readiness = admin.get("/api/v1/admin/readiness")
            if (
                products.status_code != 200
                or len(products.json()) != 14
                or product_versions.status_code != 200
                or not product_versions.json()
                or readiness.status_code != 200
            ):
                raise DomainError("正式商品事实或动态就绪度不可读取")
            guide = _dictionary(readiness.json(), "正式动态就绪度无效")
            data_items = {
                str(item["id"]): item
                for item in cast(
                    list[dict[str, object]],
                    guide.get("tenant_data_items", []),
                )
            }
            if {
                str(data_items[key]["state"])
                for key in (
                    "tenant_local_content",
                    "tenant_visual_content",
                    "tenant_dm01",
                )
            } != {"data_missing"}:
                raise DomainError("P4/P5/DM01 当前资料缺口漂移")
            checks.append({"id": "PRODUCT_AND_READINESS_TRUTH", "status": "PASS"})
            admin.post("/tenant-admin/logout", follow_redirects=False)

        with TestClient(app, base_url="https://diyu.example") as content:
            _login(
                content,
                "/login",
                str(credentials["content_username"]),
                str(credentials["content_password"]),
            )
            wrong_entry = content.get("/tenant-admin", follow_redirects=False)
            if wrong_entry.status_code != 403 or content.get("/api/v1/session/context").status_code != 200:
                raise DomainError("租户用户错入口没有保留有效会话")

            scoped = _scope_params(account_id)
            material_payload = {
                "title": "正式支持面私人素材",
                "filename": "private-note.txt",
                "content_type": "text/plain",
                "content_base64": base64.b64encode(b"bounded private material lifecycle").decode(),
                "declares_identifiable_minor": False,
                "reference_note": "仅本人可见的生命周期验证。",
            }
            personal_material = content.post(
                "/api/v1/materials/personal",
                params=scoped,
                json=material_payload,
            )
            if personal_material.status_code != 201:
                raise DomainError("正式私人素材上传失败")
            personal_asset_id = str(personal_material.json()["id"])
            personal_list = content.get("/api/v1/materials", params=scoped)
            note_update = content.patch(
                f"/api/v1/materials/{personal_asset_id}/reference-note",
                params=scoped,
                json={"reference_note": "本人复核后的说明。"},
            )
            personal_delete = content.delete(
                f"/api/v1/materials/{personal_asset_id}",
                params=scoped,
            )
            if (
                personal_list.status_code != 200
                or not any(
                    item.get("id") == personal_asset_id for item in cast(list[dict[str, object]], personal_list.json())
                )
                or note_update.status_code != 200
                or personal_delete.status_code != 200
            ):
                raise DomainError("正式私人素材读取、说明或删除失败")
            checks.append({"id": "PRIVATE_MATERIAL_LIFECYCLE", "status": "PASS"})

            series = content.post(
                "/api/v1/content/series",
                params=scoped,
                json={
                    "title": f"正式支持面连续系列-{marker}",
                    "premise": "保持真实日常观察，但每篇形成新的判断。",
                },
            )
            if series.status_code != 201:
                raise DomainError("正式连续系列创建失败")
            series_id = str(series.json()["id"])
            added = content.post(
                f"/api/v1/content/series/{series_id}/items",
                params=scoped,
                json={"task_id": factory_task_id, "position": 1},
            )
            if added.status_code != 200:
                raise DomainError("正式历史任务加入系列失败")

            catalog_response = content.get(
                "/api/v1/content/expression-catalog",
                params=scoped,
            )
            if catalog_response.status_code != 200:
                raise DomainError("正式可选创作方向不可读取")
            catalog = _dictionary(catalog_response.json(), "正式创作方向目录无效")
            axes = cast(list[dict[str, object]], catalog.get("axes", []))
            selected_axis = next(
                (
                    axis
                    for axis in axes
                    if isinstance(axis.get("options"), list) and cast(list[object], axis["options"])
                ),
                None,
            )
            if selected_axis is None:
                raise DomainError("正式创作方向目录没有可选项")
            selected_entry = _dictionary(
                cast(list[object], selected_axis["options"])[0],
                "正式创作方向条目无效",
            )
            creative_direction = {
                "catalog_version": catalog["catalog_version"],
                "selections": {str(selected_axis["key"]): str(selected_entry["stable_id"])},
                "cleared_axes": [],
                "custom_text": "",
                "body_related_opt_in": False,
            }

            before_p5 = _business_counts(database_url, tenant_id)
            intake_before = generator.intake_calls
            writer_before = generator.writer_calls
            p5 = _stream(
                content,
                account_id=account_id,
                message=_P5_INPUT,
                product_media_intent=True,
            )
            after_p5 = _business_counts(database_url, tenant_id)
            if (
                p5[-1].get("event") != "conversation"
                or p5[-1].get("kind") != "question"
                or "当前没有足够的正式商品图片/视频及商品绑定" not in str(p5[-1].get("message"))
                or after_p5 != before_p5
                or generator.intake_calls != intake_before
                or generator.writer_calls != writer_before
            ):
                raise DomainError("P5 无媒体没有在任务和 Writer 前失败关闭")
            checks.append({"id": "P5_NO_MEDIA_ZERO_OBJECTS", "status": "PASS"})

            retry_id = str(uuid4())
            rate_limited = _stream(
                content,
                account_id=account_id,
                message=_SERIES_INPUT,
                request_id=retry_id,
                series_id=series_id,
                series_position=2,
                creative_direction=creative_direction,
            )
            if (
                rate_limited[-1].get("event") != "failed"
                or rate_limited[-1].get("error_code") != "RATE_LIMITED"
                or rate_limited[-1].get("failure_stage") != "rate_limit"
                or rate_limited[-1].get("retryable") is not True
            ):
                raise DomainError("正式 429 没有稳定错误码、阶段和可重试标记")
            retry_before = _business_counts(database_url, tenant_id)
            time.sleep(MODEL_REQUEST_DUPLICATE_WINDOW_SECONDS + 0.05)
            retried = _stream(
                content,
                account_id=account_id,
                message=_SERIES_INPUT,
                request_id=retry_id,
                series_id=series_id,
                series_position=2,
                creative_direction=creative_direction,
            )
            retry_after = _business_counts(database_url, tenant_id)
            replayed = _stream(
                content,
                account_id=account_id,
                message=_SERIES_INPUT,
                request_id=retry_id,
                series_id=series_id,
                series_position=2,
                creative_direction=creative_direction,
            )
            replay_after = _business_counts(database_url, tenant_id)
            if (
                retried[-1].get("event") != "completed"
                or replayed[-1].get("event") != "completed"
                or retry_after["tasks"] - retry_before["tasks"] != 1
                or retry_after["runs"] - retry_before["runs"] != 1
                or retry_after["versions"] - retry_before["versions"] != 1
                or replay_after != retry_after
                or retry_after["running"] != 0
            ):
                raise DomainError("429 后同 request_id 重试或幂等重放产生重复对象")
            series_task_id = str(
                _dictionary(
                    retried[-1].get("result"),
                    "正式系列生成结果缺失",
                )["task_id"]
            )
            event_names = {str(item.get("event")) for item in retried if item.get("event")}
            if not {"received", "compiling_context", "completed"} <= event_names:
                raise DomainError("正式生成阶段事件不完整")
            with psycopg.connect(database_url, row_factory=dict_row) as connection:
                connection.execute(
                    "SELECT set_config('app.tenant_id', %s, true)",
                    (str(tenant_id),),
                )
                series_task = connection.execute(
                    "SELECT series_id, series_position, content_context_snapshot "
                    "FROM business_tasks WHERE tenant_id=%s AND id=%s",
                    (tenant_id, UUID(series_task_id)),
                ).fetchone()
            if (
                series_task is None
                or str(series_task["series_id"]) != series_id
                or int(series_task["series_position"]) != 2
                or not isinstance(series_task["content_context_snapshot"], dict)
                or not _dictionary(
                    series_task["content_context_snapshot"],
                    "正式系列任务快照无效",
                ).get("series_context")
                or not _dictionary(
                    series_task["content_context_snapshot"],
                    "正式系列任务快照无效",
                ).get("applied_direction")
            ):
                raise DomainError("正式系列或可选创作方向没有冻结进任务快照")
            listed_series = content.get(
                "/api/v1/content/series",
                params=scoped,
            )
            current_series = next(
                item for item in cast(list[dict[str, object]], listed_series.json()) if item["id"] == series_id
            )
            task_ids = [str(item["task_id"]) for item in cast(list[dict[str, object]], current_series["items"])]
            reordered = content.put(
                f"/api/v1/content/series/{series_id}/items",
                params=scoped,
                json={"task_ids": list(reversed(task_ids))},
            )
            reset = content.post(
                f"/api/v1/content/series/{series_id}/reset",
                params=scoped,
            )
            if (
                listed_series.status_code != 200
                or len(task_ids) != 2
                or reordered.status_code != 200
                or reset.status_code != 200
                or reset.json().get("items") != []
            ):
                raise DomainError("正式连续系列创建、编排或重置失败")
            checks.extend(
                (
                    {"id": "CREATIVE_DIRECTION_FROZEN", "status": "PASS"},
                    {"id": "GENERATION_STAGES", "status": "PASS"},
                    {"id": "SERIES_FROZEN_CONTEXT", "status": "PASS"},
                    {"id": "RATE_LIMIT_RETRY_IDEMPOTENT", "status": "PASS"},
                )
            )

            display_before = _business_counts(database_url, tenant_id)
            display_denied = content.get("/display", follow_redirects=False)
            display_after = _business_counts(database_url, tenant_id)
            if (
                display_denied.status_code not in {403, 422}
                or display_after != display_before
                or content.get("/api/v1/session/context").status_code != 200
            ):
                raise DomainError("DM01 无门店/无资格没有零对象且保留会话")
            checks.append({"id": "DM01_DATA_MISSING_ZERO_OBJECTS", "status": "PASS"})

            content.post("/tenant-admin/logout?next=user", follow_redirects=False)
            expired = content.get("/api/v1/session/context")
            if expired.status_code != 401 or expired.json().get("error_code") != "AUTH_REQUIRED":
                raise DomainError("真正会话失效没有回到 AUTH_REQUIRED")
            checks.append({"id": "SESSION_EXPIRY_CLASSIFIED", "status": "PASS"})

        final_counts = _business_counts(database_url, tenant_id)
        if final_counts["running"] != 0:
            raise DomainError("正式支持面完成后仍有永久 running")
        capability_matrix = _dictionary(
            guide.get("capability_matrix"),
            "正式支持面无法读取能力矩阵",
        )
        schema_revision = str(capability_matrix.get("schema_revision", ""))
        if not schema_revision:
            raise DomainError("正式支持面无法读取 schema revision")
        document: dict[str, object] = {
            "schema_version": "tenant01-formal-supported-surface-evidence-v1",
            "candidate_sha": candidate_sha,
            "tenant_id": str(tenant_id),
            "schema_revision": schema_revision,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "context_evidence_sha256": hashlib.sha256(context_evidence_path.read_bytes()).hexdigest(),
            "checks": checks,
            "details": details,
            "generator_evidence_scope": "controlled_pre_freeze_service_boundary_only",
            "model_quality_proven": False,
            "permanent_running": final_counts["running"],
            "raw_source_text_logged": False,
            "credentials_logged": False,
            "verdict": "PASS",
        }
        payload = json.dumps(document, ensure_ascii=False, sort_keys=True)
        for field in ("admin_password", "content_password"):
            if str(credentials[field]) in payload:
                raise DomainError("正式支持面证据意外包含凭据")
        digest = _write_private(output_path, document)
    finally:
        if object_root.exists():
            shutil.rmtree(object_root)

    return {
        "candidate_sha": candidate_sha,
        "tenant_id": str(tenant_id),
        "checks": len(checks),
        "output": str(output_path),
        "sha256": digest,
        "permanent_running": final_counts["running"],
        "verdict": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the bounded local formal TENANT-01 supported-surface proof.")
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--context-evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--candidate-sha", required=True)
    args = parser.parse_args()
    database_url = os.environ.get("DIYU_APP_DATABASE_URL", "")
    if not database_url:
        raise DomainError("缺少本地正式应用数据库连接")
    result = run(
        database_url=database_url,
        credentials_path=args.credentials.resolve(strict=True),
        context_evidence_path=args.context_evidence.resolve(strict=True),
        output_path=args.output.resolve(),
        candidate_sha=args.candidate_sha,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
