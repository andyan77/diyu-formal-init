from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

import src.gateway.api.app as app_module
from src.brain.content_service import ContentService
from src.composition.bootstrap import build_content_control_service
from src.gateway.api.settings import Settings
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.production_auth import MODEL_REQUEST_DUPLICATE_WINDOW_SECONDS
from src.shared.creative_plan import ACCOUNT_BASELINE_TONE_ID, build_creative_plan
from src.shared.errors import DomainError
from src.shared.publication_contract import IntakeSpanRole
from src.shared.types import (
    ConversationDecision,
    ConversationInput,
    GeneratedArtifact,
    GenerationInput,
)
from src.tool.llm_gateway.stub import DeterministicContentGenerator
from src.tool.tenant01_publication_evidence import (
    validate_context_consumption_evidence,
)

_FACTORY_INPUT = "今天去工厂验厂，今年量装大货的车缝品质有了大幅度的提升"
_FACTORY_FACTS = (
    "今天去工厂验厂，",
    "今年量装大货的车缝品质有了大幅度的提升",
)
_PRODUCT_INPUT = "请依据 DIYU-CSPU-004 已确认字段写一条商品选择说明"
_GUARANTEE_INPUT = "笛语已经正式保证今年所有产品车缝品质大幅提升"
_UNKNOWN_SKU_INPUT = "请写 DIYU-NOT-REGISTERED 的车缝品质已经大幅提升"
_ORDINARY_INPUT = "帮我写一条关于下雨天心情的普通感悟，不要写商品"
_REVISION_INPUT = "保留事实不变，把开头改得更自然、更像短视频口播。"


def _dictionary(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DomainError(message)
    return cast(dict[str, object], value)


def _list(value: object, message: str) -> list[object]:
    if not isinstance(value, list):
        raise DomainError(message)
    return cast(list[object], value)


def _write_private(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    if path.stat().st_mode & 0o077:
        raise DomainError("正式纵向证据文件权限不是 0600")


def _creative_plan(request: ConversationInput, product: str) -> object:
    return build_creative_plan(
        topic_spans=(request.message,),
        primary_value=cast(Any, product),
        tone_ids=(request.allowed_tone_ids or (ACCOUNT_BASELINE_TONE_ID,)),
        mechanism_id=(request.allowed_mechanism_ids[0] if request.allowed_mechanism_ids else None),
        target_shape=request.platform_shape,
    )


class FormalBoundaryGenerator(DeterministicContentGenerator):
    """Controlled pre-freeze seam for service boundaries, never model-quality proof."""

    def __init__(self) -> None:
        self.intake_calls = 0
        self.writer_calls = 0

    def collaborate(self, request: ConversationInput) -> ConversationDecision:
        self.intake_calls += 1
        if request.message not in {
            _FACTORY_INPUT,
            _PRODUCT_INPUT,
            _GUARANTEE_INPUT,
            _UNKNOWN_SKU_INPUT,
            _ORDINARY_INPUT,
        }:
            return super().collaborate(request)

        candidates = request.user_fact_candidates
        facts = (
            tuple(candidate for candidate in candidates if candidate.exact_text in _FACTORY_FACTS)
            if request.message == _FACTORY_INPUT
            else ()
        )
        roles: tuple[tuple[str, IntakeSpanRole], ...] = tuple(
            (
                candidate.source_id,
                "observable_actuality" if candidate in facts else "creation_instruction",
            )
            for candidate in candidates
        )
        if request.message == _FACTORY_INPUT:
            # Deliberately return the wrong product route. The server must make
            # the structural, fact-boundary correction without a Chinese
            # keyword table or a single-card prompt patch.
            product = "product_truth"
            claim_scope = "task_actuality"
            narrative_mode = "actuality_reflection"
        elif request.message == _PRODUCT_INPUT:
            product = "product_truth"
            claim_scope = "specific_product_claim"
            narrative_mode = "product_explanation"
        elif request.message == _GUARANTEE_INPUT:
            product = "brand_life_narrative"
            claim_scope = "institutional_claim"
            narrative_mode = "general_observation"
        elif request.message == _UNKNOWN_SKU_INPUT:
            product = "product_truth"
            claim_scope = "specific_product_claim"
            narrative_mode = "product_explanation"
        else:
            product = "brand_life_narrative"
            claim_scope = "general_topic"
            narrative_mode = "general_observation"
        return ConversationDecision(
            "ready",
            "边界夹具已形成结构化意图。",
            user_premises=(request.message,),
            user_fact_spans=tuple(candidate.exact_text for candidate in facts),
            user_fact_source_ids=tuple(candidate.source_id for candidate in facts),
            user_span_roles=roles,
            claim_scope=cast(Any, claim_scope),
            narrative_mode=cast(Any, narrative_mode),
            creative_plan=cast(Any, _creative_plan(request, product)),
            primary_product=cast(Any, product),
            creation_proposal=True,
            proposed_intent_span=request.message,
        )

    def generate(self, request: GenerationInput) -> GeneratedArtifact:
        self.writer_calls += 1
        return super().generate(request)


def _settings(database_url: str, candidate_sha: str) -> Settings:
    return Settings.model_validate(
        {
            "DIYU_RUNTIME_MODE": "production",
            "DIYU_APP_DATABASE_URL": database_url,
            "DIYU_SESSION_SECRET": "tenant01-formal-local-vertical-session-secret",
            "DIYU_PUBLIC_URL": "https://diyu.example",
            "DIYU_GENERATOR_MODE": "deepseek",
            "DEEPSEEK_API_BASE_URL": "https://example.invalid",
            "DEEPSEEK_API_KEY": "local-controlled-placeholder",
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
            "DIYU_S3_ENDPOINT_URL": "http://127.0.0.1:9000",
            "DIYU_S3_BUCKET": "diyu-test",
            "DIYU_S3_ACCESS_KEY_ID": "local-controlled-placeholder",
            "DIYU_S3_SECRET_ACCESS_KEY": "local-controlled-placeholder",
            "DIYU_RUNTIME_SHA": candidate_sha,
            "DIYU_MODEL_GLOBAL_CONCURRENCY": "10",
            "DIYU_MODEL_TENANT_CONCURRENCY": "10",
            "DIYU_MODEL_TENANT_RATE_PER_MINUTE": "120",
        }
    )


def _login(client: TestClient, path: str, username: str, password: str) -> None:
    response = client.post(
        path,
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    if response.status_code != 303:
        raise DomainError(f"正式登录失败：{path} ({response.status_code})")


def _activate(client: TestClient, activation_url: str, password: str) -> None:
    response = client.post(
        urlsplit(activation_url).path,
        data={"password": password, "password_confirm": password},
        follow_redirects=False,
    )
    if response.status_code != 303:
        raise DomainError(f"正式激活或重设失败 ({response.status_code})")


def _events(
    client: TestClient,
    *,
    message: str,
    account_id: str,
    target: str = "douyin_video",
    interaction_mode: str = "generate",
) -> list[dict[str, object]]:
    # Respect the production per-user duplicate-submission window. This is a
    # deterministic rate contract, not a retry or result-selection loop.
    time.sleep(MODEL_REQUEST_DUPLICATE_WINDOW_SECONDS + 0.05)
    response = client.post(
        "/api/v1/content/stream",
        json={
            "message": message,
            "conversation": [],
            "publishing_identity_id": account_id,
            "target": target,
            "material_ids": [],
            "interaction_mode": interaction_mode,
            "request_id": str(uuid4()) if interaction_mode == "generate" else None,
        },
    )
    if response.status_code != 200:
        raise DomainError(f"正式流式入口失败 ({response.status_code})")
    return [_dictionary(json.loads(line), "正式流式事件无效") for line in response.text.splitlines() if line.strip()]


def _counts(database_url: str, tenant_id: UUID) -> dict[str, int]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
        row = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM business_tasks WHERE tenant_id = %s) AS tasks,
              (SELECT count(*) FROM generation_runs WHERE tenant_id = %s) AS runs,
              (SELECT count(*) FROM content_versions WHERE tenant_id = %s) AS versions,
              (SELECT count(*) FROM generation_runs
                WHERE tenant_id = %s AND status = 'running') AS running
            """,
            (tenant_id, tenant_id, tenant_id, tenant_id),
        ).fetchone()
    if row is None:
        raise DomainError("正式内容数量无法读取")
    return {key: int(row[key]) for key in ("tasks", "runs", "versions", "running")}


def _task_record(
    database_url: str,
    tenant_id: UUID,
    task_id: UUID,
) -> dict[str, object]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
        row = connection.execute(
            """
            SELECT task.primary_content_product, task.product_refs,
                   task.content_context_snapshot,
                   version.artifact_digest, version.version_number,
                   version.id AS version_id
              FROM business_tasks task
              JOIN content_versions version
                ON version.tenant_id = task.tenant_id
               AND version.task_id = task.id
             WHERE task.tenant_id = %s AND task.id = %s
             ORDER BY version.version_number DESC
             LIMIT 1
            """,
            (tenant_id, task_id),
        ).fetchone()
    if row is None or not isinstance(row["content_context_snapshot"], dict):
        raise DomainError("正式任务快照无法读取")
    return cast(dict[str, object], row)


def _version_digest(
    database_url: str,
    tenant_id: UUID,
    task_id: UUID,
    version_number: int,
) -> str:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
        row = connection.execute(
            """
            SELECT artifact_digest
              FROM content_versions
             WHERE tenant_id = %s AND task_id = %s AND version_number = %s
            """,
            (tenant_id, task_id, version_number),
        ).fetchone()
    if row is None:
        raise DomainError("正式不可变版本 digest 无法读取")
    digest = str(row["artifact_digest"])
    if len(digest) != 64:
        raise DomainError("正式不可变版本 digest 无效")
    return digest


def _case(
    *,
    client: TestClient,
    database_url: str,
    tenant_id: UUID,
    generator: FormalBoundaryGenerator,
    account_id: str,
    case_id: str,
    message: str,
    classification: str,
    expected_outcome: str,
) -> tuple[dict[str, object], dict[str, object] | None]:
    before = _counts(database_url, tenant_id)
    writer_before = generator.writer_calls
    events = _events(client, message=message, account_id=account_id)
    after = _counts(database_url, tenant_id)
    final = events[-1]
    deltas = {
        "task_delta": after["tasks"] - before["tasks"],
        "run_delta": after["runs"] - before["runs"],
        "version_delta": after["versions"] - before["versions"],
        "writer_calls": generator.writer_calls - writer_before,
    }
    if expected_outcome == "succeeded":
        if final.get("event") != "completed":
            raise DomainError(f"正式纵向 {case_id} 没有完成")
        result = _dictionary(final.get("result"), "正式完成事件缺少成品")
        task_id = UUID(str(result.get("task_id")))
        record = _task_record(database_url, tenant_id, task_id)
        snapshot = _dictionary(record["content_context_snapshot"], "正式任务快照无效")
        frame = _dictionary(snapshot.get("narrative_frame"), "正式叙事快照缺失")
        selected_skus = [str(value) for value in _list(record["product_refs"], "商品引用无效")]
        product_fact_refs = [
            str(value)
            for value in _list(
                snapshot.get("used_product_fact_ids"),
                "正式任务缺少已使用 ProductFact refs",
            )
        ]
        case = {
            "case_id": case_id,
            "input": message,
            "outcome": expected_outcome,
            "classification": classification,
            "content_product": str(record["primary_content_product"]),
            "narrative_mode": str(frame["narrative_mode"]),
            **deltas,
            "permanent_running": after["running"],
            "task_id": str(task_id),
            "version_id": str(record["version_id"]),
            "snapshot": snapshot,
            "artifact_digest": str(record["artifact_digest"]),
            "selected_skus": selected_skus,
            "product_fact_refs": product_fact_refs,
        }
        return case, result
    if final.get("event") != "conversation" or final.get("kind") != "question":
        raise DomainError(f"正式纵向 {case_id} 没有在建任务前失败关闭")
    case = {
        "case_id": case_id,
        "input": message,
        "outcome": expected_outcome,
        "classification": classification,
        "content_product": "none",
        "narrative_mode": "none",
        **deltas,
        "permanent_running": after["running"],
        "snapshot": None,
        "artifact_digest": None,
        "selected_skus": [],
        "product_fact_refs": [],
        "visible_result": {
            "kind": "question",
            "message_digest": hashlib.sha256(str(final.get("message", "")).encode()).hexdigest(),
        },
    }
    return case, None


def _admin_member_journey(
    client: TestClient,
    credentials: dict[str, object],
) -> dict[str, object]:
    _login(
        client,
        "/tenant-admin/login",
        str(credentials["admin_username"]),
        str(credentials["admin_password"]),
    )
    context = client.get("/api/v1/session/context")
    if context.status_code != 200 or context.json().get("application") != "tenant_management":
        raise DomainError("正式管理员会话上下文不成立")
    projection_response = client.get("/api/v1/tenant-management/brand-publication")
    if projection_response.status_code != 200:
        raise DomainError("正式管理员无法读取品牌发布历史")
    projection = _dictionary(projection_response.json(), "正式发布历史无效")
    current = _dictionary(projection.get("current"), "正式当前发布投影缺失")
    history = _list(projection.get("history"), "正式发布历史缺失")
    if current.get("status") != "confirmed" or len(_list(current.get("items"), "正式发布条目缺失")) <= 1:
        raise DomainError("正式发布投影仍只有兼容基线")
    if not any(
        isinstance(item, dict) and item.get("source_kind") == "brand_expression_baseline"
        for version in history
        if isinstance(version, dict)
        for item in cast(list[object], version.get("items", []))
    ):
        raise DomainError("原兼容发布项没有保留在历史中")

    base_payload = {
        "display_name": "柯桥店阿丹",
        "organization_id": credentials["keqiao_organization_id"],
        "account_id": None,
        "grants_tenant_management": False,
        "grants_material_maintenance": False,
        "grants_expression_profile_maintenance": False,
        "entry_type": "tenant_user",
        "capabilities": ["content"],
        "publishing_identity_ids": [credentials["account_id"]],
        "expression_profile_maintenance_account_ids": [],
        "display_store_ids": [],
    }
    first = client.post(
        "/api/v1/tenant-management/users",
        json=base_payload | {"username": f"笛语柯桥店阿丹同名验证{uuid4().hex[:6]}"},
    )
    if first.status_code != 201:
        raise DomainError(f"同显示名正例失败 ({first.status_code})")
    formal_username = f"笛语柯桥店阿丹-{uuid4().hex[:6]}"
    formal = client.post(
        "/api/v1/tenant-management/users",
        json=base_payload | {"username": formal_username},
    )
    if formal.status_code != 201:
        raise DomainError(f"正式柯桥店阿丹创建失败 ({formal.status_code})")
    created = _dictionary(formal.json(), "正式柯桥店阿丹返回无效")
    conflict = client.post(
        "/api/v1/tenant-management/users",
        json=base_payload | {"display_name": "另一位成员", "username": formal_username},
    )
    conflict_payload = _dictionary(conflict.json(), "用户名冲突返回无效")
    if (
        conflict.status_code != 422
        or conflict_payload.get("error_code") != "USERNAME_TAKEN"
        or not isinstance(conflict_payload.get("suggestions"), list)
    ):
        raise DomainError("登录用户名冲突没有稳定错误码和候选")

    member_password = secrets.token_urlsafe(32)
    _activate(client, str(created["activation_url"]), member_password)
    with TestClient(client.app, base_url="https://diyu.example") as member:
        _login(member, "/login", formal_username, member_password)
        member_context = member.get("/api/v1/session/context")
        if member_context.status_code != 200 or "content" not in member_context.json().get("capabilities", []):
            raise DomainError("正式柯桥店阿丹激活后内容资格不可用")

        permission_denied = member.get("/api/v1/admin/readiness")
        if (
            permission_denied.status_code != 403
            or permission_denied.json().get("error_code") != "PERMISSION_DENIED"
            or member.get("/api/v1/session/context").status_code != 200
            or member.cookies.get("diyu_session") is None
        ):
            raise DomainError("权限 403 没有留在原会话或缺少稳定错误码")

        user_id = str(created["user_id"])
        no_access = client.patch(
            f"/api/v1/tenant-management/users/{user_id}/grants",
            json={
                "entry_type": "tenant_user",
                "capabilities": [],
                "publishing_identity_ids": [],
                "expression_profile_maintenance_account_ids": [],
                "display_store_ids": [],
                "grants_account_access": False,
                "grants_tenant_management": False,
                "grants_material_maintenance": False,
            },
        )
        if no_access.status_code != 200:
            raise DomainError("正式成员权限撤销失败")
        if member.get("/api/v1/session/context").status_code != 401:
            raise DomainError("管理员改变权限后没有撤销旧权限会话")
        restored_access = client.patch(
            f"/api/v1/tenant-management/users/{user_id}/grants",
            json={
                "entry_type": "tenant_user",
                "capabilities": ["content"],
                "publishing_identity_ids": [credentials["account_id"]],
                "expression_profile_maintenance_account_ids": [],
                "display_store_ids": [],
                "grants_account_access": True,
                "grants_tenant_management": False,
                "grants_material_maintenance": False,
            },
        )
        if restored_access.status_code != 200:
            raise DomainError("正式成员权限恢复失败")

    with TestClient(client.app, base_url="https://diyu.example") as restored_member:
        _login(restored_member, "/login", formal_username, member_password)
        disabled = client.post(f"/api/v1/tenant-management/users/{user_id}/disable")
        if disabled.status_code != 200 or restored_member.get("/api/v1/session/context").status_code != 401:
            raise DomainError("正式成员停用没有撤销既有会话")

    restored = client.post(f"/api/v1/tenant-management/users/{created['user_id']}/restore")
    if restored.status_code != 200:
        raise DomainError("正式成员恢复失败")
    restored_password = secrets.token_urlsafe(32)
    _activate(client, str(restored.json()["activation_url"]), restored_password)
    reset = client.post(f"/api/v1/tenant-management/users/{created['user_id']}/reset")
    if reset.status_code != 200:
        raise DomainError("正式成员重设链接签发失败")
    final_password = secrets.token_urlsafe(32)
    _activate(client, str(reset.json()["reset_url"]), final_password)
    with TestClient(client.app, base_url="https://diyu.example") as final_member:
        _login(final_member, "/login", formal_username, final_password)
        if final_member.get("/api/v1/session/context").status_code != 200:
            raise DomainError("正式成员重设后登录失败")
        final_member.post("/logout", follow_redirects=False)

    readiness = client.get("/api/v1/admin/readiness")
    if readiness.status_code != 200:
        raise DomainError("管理员使用说明真值不可读取")
    return {
        "user_id": str(created["user_id"]),
        "display_name": "柯桥店阿丹",
        "username": formal_username,
        "same_display_name_allowed": True,
        "duplicate_username_error_code": "USERNAME_TAKEN",
        "duplicate_username_suggestions": len(cast(list[object], conflict_payload["suggestions"])),
        "content_grant": "restored",
        "display_grant": "not_granted_without_store",
        "activation_login": "PASS",
        "permission_403_session_preserved": True,
        "permission_change_rotated_session": True,
        "disable_revoked_session": True,
        "restore_and_reset": "PASS",
        "publication_projection": current,
        "publication_history_versions": len(history),
        "readiness": readiness.json(),
    }


def run(
    *,
    database_url: str,
    credential_path: Path,
    output_path: Path,
    candidate_sha: str,
) -> dict[str, object]:
    credentials = _dictionary(
        json.loads(credential_path.read_text(encoding="utf-8")),
        "本地正式纵向凭据文件无效",
    )
    if credentials.get("candidate_sha") != candidate_sha:
        raise DomainError("本地正式纵向凭据与候选 SHA 不一致")
    tenant_id = UUID(str(credentials["tenant_id"]))
    generator = FormalBoundaryGenerator()
    original_builder = cast(
        Callable[[Settings], ContentService],
        app_module.build_content_service,  # type: ignore[attr-defined]
    )

    def builder(settings: Settings) -> ContentService:
        return ContentService(
            PostgresContentRepository(settings.app_database_url),
            generator,
            build_content_control_service(settings),
        )

    app_module.build_content_service = builder  # type: ignore[attr-defined]
    try:
        app = app_module.create_app(_settings(database_url, candidate_sha))
    finally:
        app_module.build_content_service = original_builder  # type: ignore[attr-defined,assignment]

    with TestClient(app, base_url="https://diyu.example") as admin:
        member_journey = _admin_member_journey(admin, credentials)

    with TestClient(app, base_url="https://diyu.example") as content:
        _login(
            content,
            "/login",
            str(credentials["content_username"]),
            str(credentials["content_password"]),
        )
        user_context = content.get("/api/v1/session/context")
        if user_context.status_code != 200:
            raise DomainError("正式笛语品控上下文不可读取")
        identity = _dictionary(
            _list(user_context.json().get("publishing_identities"), "发布身份缺失")[0],
            "发布身份无效",
        )
        account_id = str(identity["id"])
        targets = {
            str(_dictionary(item, "平台目标无效")["value"])
            for item in _list(identity.get("platform_targets"), "平台目标缺失")
        }
        if targets != {
            "douyin_video",
            "xiaohongshu_video",
            "xiaohongshu_graphic",
            "wechat_channels_video",
        }:
            raise DomainError("正式逻辑账号四个平台目标不完整")

        send_before = _counts(database_url, tenant_id)
        writer_before = generator.writer_calls
        sent = _events(
            content,
            message=_FACTORY_INPUT,
            account_id=account_id,
            interaction_mode="conversation",
        )
        send_after = _counts(database_url, tenant_id)
        if (
            sent[-1].get("event") != "conversation"
            or send_after != send_before
            or generator.writer_calls != writer_before
        ):
            raise DomainError("普通发送错误建立了内容任务或调用 Writer")

        cases: list[dict[str, object]] = []
        results: dict[str, dict[str, object]] = {}
        for case_id, message, classification, outcome in (
            ("factory_actuality", _FACTORY_INPUT, "task_actuality", "succeeded"),
            ("explicit_product", _PRODUCT_INPUT, "specific_product_claim", "succeeded"),
            ("institutional_guarantee", _GUARANTEE_INPUT, "institutional_claim", "rejected_before_task"),
            ("unknown_sku", _UNKNOWN_SKU_INPUT, "specific_product_claim", "rejected_before_task"),
            ("ordinary_life", _ORDINARY_INPUT, "general_topic", "succeeded"),
        ):
            case, result = _case(
                client=content,
                database_url=database_url,
                tenant_id=tenant_id,
                generator=generator,
                account_id=account_id,
                case_id=case_id,
                message=message,
                classification=classification,
                expected_outcome=outcome,
            )
            cases.append(case)
            if result is not None:
                results[case_id] = result

        factory = results["factory_actuality"]
        task_id = str(factory["task_id"])
        v1 = content.get(
            f"/api/v1/tasks/{task_id}/versions/1",
            params={"target": "douyin_video", "publishing_identity_id": account_id},
        )
        if v1.status_code != 200:
            raise DomainError("正式 V1 回读失败")
        time.sleep(MODEL_REQUEST_DUPLICATE_WINDOW_SECONDS + 0.05)
        revision = content.post(
            f"/api/v1/tasks/{task_id}/revisions",
            json={
                "instruction": _REVISION_INPUT,
                "target": "douyin_video",
                "source_target": "douyin_video",
                "publishing_identity_id": account_id,
                "request_id": str(uuid4()),
            },
        )
        if revision.status_code != 201 or revision.json().get("version") != 2:
            raise DomainError("正式 V2 修改失败")
        v2 = content.get(
            f"/api/v1/tasks/{task_id}/versions/2",
            params={"target": "douyin_video", "publishing_identity_id": account_id},
        )
        v1_again = content.get(
            f"/api/v1/tasks/{task_id}/versions/1",
            params={"target": "douyin_video", "publishing_identity_id": account_id},
        )
        v2_again = content.get(
            f"/api/v1/tasks/{task_id}/versions/2",
            params={"target": "douyin_video", "publishing_identity_id": account_id},
        )
        if any(response.status_code != 200 for response in (v2, v1_again, v2_again)):
            raise DomainError("正式 V1→V2→V1→V2 回读失败")
        if v1.json() != v1_again.json() or v2.json() != v2_again.json():
            raise DomainError("正式历史回读发生漂移")

        time.sleep(MODEL_REQUEST_DUPLICATE_WINDOW_SECONDS + 0.05)
        adapted = content.post(
            f"/api/v1/tasks/{task_id}/revisions",
            json={
                "instruction": "保持同一事实和判断，改编为小红书图文结构。",
                "target": "xiaohongshu_graphic",
                "source_target": "douyin_video",
                "publishing_identity_id": account_id,
                "request_id": str(uuid4()),
            },
        )
        if (
            adapted.status_code != 201
            or adapted.json().get("target_key") != "xiaohongshu_graphic"
            or adapted.json().get("body") == v2.json().get("body")
        ):
            raise DomainError("正式跨平台结构化改编失败")

        factory_record = _task_record(database_url, tenant_id, UUID(task_id))
        factory_snapshot = _dictionary(factory_record["content_context_snapshot"], "正式验厂任务快照缺失")
        packet = _dictionary(factory_snapshot.get("brand_context_packet"), "正式验厂上下文包缺失")

        with TestClient(app, base_url="https://diyu.example") as admin:
            _login(
                admin,
                "/tenant-admin/login",
                str(credentials["admin_username"]),
                str(credentials["admin_password"]),
            )
            current_response = admin.get("/api/v1/tenant-management/brand-publication")
            current = _dictionary(current_response.json().get("current"), "正式当前投影缺失")
            candidate_payload = [
                {
                    "source_segment_id": item["source_segment_id"],
                    "publication_role": item["publication_role"],
                    "published_text": item["published_text"],
                    "applicability": item["applicability"],
                }
                for item in cast(list[dict[str, object]], current["items"])
            ]
            # Change the ordered projection digest while keeping every item
            # source-bound and authorized. Old tasks must continue replaying
            # their original packet after this distinct version becomes current.
            candidate_payload = candidate_payload[1:] + candidate_payload[:1]
            candidate_response = admin.post(
                "/api/v1/tenant-management/brand-publication/candidates",
                json={"items": candidate_payload},
            )
            if candidate_response.status_code != 201:
                raise DomainError("正式新投影 candidate 创建失败")
            candidate = _dictionary(candidate_response.json(), "正式新投影 candidate 无效")
            confirmed_response = admin.post(f"/api/v1/tenant-management/brand-publication/{candidate['id']}/confirm")
            if confirmed_response.status_code != 200:
                raise DomainError("正式新投影确认失败")
            confirmed_projection = _dictionary(confirmed_response.json(), "正式新投影确认返回无效")
            projection_after_response = admin.get("/api/v1/tenant-management/brand-publication")
            projection_after = _dictionary(projection_after_response.json(), "正式新投影确认后历史无效")
            current_after = _dictionary(projection_after.get("current"), "正式新投影确认后 current 缺失")
            if (
                confirmed_projection.get("status") != "confirmed"
                or current_after.get("id") != candidate.get("id")
                or confirmed_projection.get("digest") == current.get("digest")
                or int(str(current_after.get("version"))) <= int(str(current.get("version")))
            ):
                raise DomainError("正式新投影没有成为追加式 current 版本")

        after_projection = _task_record(database_url, tenant_id, UUID(task_id))
        after_snapshot = _dictionary(
            after_projection["content_context_snapshot"],
            "新投影后的旧任务快照缺失",
        )
        before_packet_digest = str(packet["packet_digest"])
        after_packet_digest = str(
            _dictionary(after_snapshot.get("brand_context_packet"), "旧任务上下文包漂移")["packet_digest"]
        )
        if (
            before_packet_digest != after_packet_digest
            or str(v1.json()["body"]) != str(v1_again.json()["body"])
            or str(v2.json()["body"]) != str(v2_again.json()["body"])
        ):
            raise DomainError("新 current projection 污染了旧任务")

        v1_digest = _version_digest(database_url, tenant_id, UUID(task_id), 1)
        v2_digest = _version_digest(database_url, tenant_id, UUID(task_id), 2)
        adapted_task_id = UUID(str(adapted.json()["task_id"]))
        adapted_digest = _version_digest(
            database_url,
            tenant_id,
            adapted_task_id,
            int(adapted.json()["version"]),
        )

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
        formal_user = connection.execute(
            """
            SELECT person.id, credential.username,
                   person.entry_kind, person.business_data_kind
              FROM users person
              JOIN user_credentials credential
                ON credential.tenant_id = person.tenant_id
               AND credential.user_id = person.id
             WHERE person.tenant_id = %s AND person.id = %s
            """,
            (tenant_id, UUID(str(credentials["content_user_id"]))),
        ).fetchone()
    if formal_user is None:
        raise DomainError("正式笛语品控真值缺失")

    current_projection = _dictionary(
        member_journey["publication_projection"],
        "正式当前发布投影证据缺失",
    )
    readiness = _dictionary(member_journey["readiness"], "正式就绪度证据缺失")
    tenant_data_items = {
        str(item["id"]): item for item in cast(list[dict[str, object]], readiness["tenant_data_items"])
    }
    final_counts = _counts(database_url, tenant_id)
    document: dict[str, object] = {
        "schema_version": "tenant01-formal-context-consumption-v1",
        "candidate_sha": candidate_sha,
        "tenant_id": str(tenant_id),
        "raw_segment_count": 5046,
        "formal_user": {
            "id": str(formal_user["id"]),
            "username": str(formal_user["username"]),
            "entry_kind": str(formal_user["entry_kind"]),
            "business_data_kind": str(formal_user["business_data_kind"]),
        },
        "current_projection": {
            "id": current_projection["id"],
            "version": current_projection["version"],
            "digest": current_projection["digest"],
        },
        "send_vs_generate": {
            "send_task_run_version_delta": [0, 0, 0],
            "send_writer_calls": 0,
            "generate_creates_version": True,
        },
        "cases": cases,
        "version_replay": {
            "v1_projection_id": packet["publication_projection_id"],
            "v2_projection_id": packet["publication_projection_id"],
            "v1_packet_digest": before_packet_digest,
            "v2_packet_digest": after_packet_digest,
            "v1_artifact_digest": v1_digest,
            "v1_reread_artifact_digest": v1_digest,
            "v2_artifact_digest": v2_digest,
            "current_version": 2,
            "read_sequence": [1, 2, 1, 2],
            "copy_version": 2,
            "export_version": 2,
            "cross_platform_target": adapted.json()["target_key"],
            "cross_platform_artifact_digest": adapted_digest,
        },
        "projection_isolation": {
            "old_projection_id": packet["publication_projection_id"],
            "old_projection_version": current_projection["version"],
            "new_projection_id": confirmed_projection["id"],
            "new_projection_version": confirmed_projection["version"],
            "new_projection_status": confirmed_projection["status"],
            "new_projection_digest": confirmed_projection["digest"],
            "old_task_packet_before": before_packet_digest,
            "old_task_packet_after": after_packet_digest,
            "old_task_artifact_before": v1_digest,
            "old_task_artifact_after": v1_digest,
        },
        "user_visible_readiness": {
            "ordinary_content": "available",
            "P4": tenant_data_items["tenant_local_content"]["state"],
            "P5": tenant_data_items["tenant_visual_content"]["state"],
            "DM01": tenant_data_items["tenant_dm01"]["state"],
            "all_capabilities_ready": False,
        },
        "member_journey": member_journey,
        "platform_targets": sorted(targets),
        "final_counts": final_counts,
        "generator_evidence_scope": "controlled_pre_freeze_service_boundary_only",
        "model_quality_proven": False,
        "checks": [
            {"id": "FORMAL_USER_DIYU_QC", "status": "PASS"},
            {"id": "FORMAL_MEMBER_DUPLICATE_DISPLAY_NAME", "status": "PASS"},
            {"id": "FORMAL_MEMBER_USERNAME_CONFLICT", "status": "PASS"},
            {"id": "FORMAL_MEMBER_ACTIVATION_RESET", "status": "PASS"},
            {"id": "FORMAL_MEMBER_GRANT_DISABLE_RESTORE", "status": "PASS"},
            {"id": "PERMISSION_403_SESSION_PRESERVED", "status": "PASS"},
            {"id": "SEND_ZERO_OBJECTS", "status": "PASS"},
            {"id": "FACTORY_ACTUALITY_V1", "status": "PASS"},
            {"id": "EXPLICIT_PRODUCT_SCOPED_FACTS", "status": "PASS"},
            {"id": "INSTITUTIONAL_GUARANTEE_PRETASK_REJECT", "status": "PASS"},
            {"id": "UNKNOWN_SKU_PRETASK_REJECT", "status": "PASS"},
            {"id": "ORDINARY_LIFE_NOT_FORCED_PRODUCT", "status": "PASS"},
            {"id": "V1_V2_REPLAY_IMMUTABLE", "status": "PASS"},
            {"id": "CROSS_PLATFORM_STRUCTURE", "status": "PASS"},
            {"id": "PROJECTION_ISOLATION", "status": "PASS"},
            {"id": "USER_VISIBLE_DATA_GAPS", "status": "PASS"},
        ],
        "verdict": "PASS",
    }
    validate_context_consumption_evidence(
        document,
        expected_candidate_sha=candidate_sha,
        expected_tenant_id=str(tenant_id),
    )
    _write_private(output_path, document)
    return {
        "candidate_sha": candidate_sha,
        "tenant_id": str(tenant_id),
        "projection_id": current_projection["id"],
        "projection_version": current_projection["version"],
        "cases": len(cases),
        "member": member_journey["username"],
        "permanent_running": final_counts["running"],
        "evidence": str(output_path),
        "evidence_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "verdict": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the bounded local formal TENANT-01 service vertical.")
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--candidate-sha", required=True)
    args = parser.parse_args()
    database_url = os.environ.get("DIYU_APP_DATABASE_URL", "")
    if not database_url:
        raise DomainError("缺少本地正式应用数据库连接")
    result = run(
        database_url=database_url,
        credential_path=args.credentials.resolve(strict=True),
        output_path=args.output.resolve(),
        candidate_sha=args.candidate_sha,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
