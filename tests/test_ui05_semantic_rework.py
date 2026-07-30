from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

import src.gateway.api.app as app_module
from src.brain.content_service import ContentService
from src.composition.bootstrap import build_content_control_service
from src.gateway.api.settings import Settings
from src.infrastructure.content_control_repository import PostgresContentControlRepository
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.production_auth import OpsSession, ProductionAuthRepository, TenantSession
from src.infrastructure.seed_demo import (
    ACCOUNT_ID,
    BRAND_ID,
    EXTERNAL_OPERATOR_ORG_ID,
    EXTERNAL_OPERATOR_USER_ID,
    HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID,
    ORG_ID,
    ROLE_ID,
    STORE_CONTENT_ACCOUNT_ID,
    STORE_CONTENT_USER_ID,
    STORE_ORG_ID,
    TENANT_ADMIN_USER_ID,
    TENANT_ID,
    USER_ID,
)
from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.shared.errors import DomainError, GenerationFailed
from src.shared.types import (
    ConversationDecision,
    ConversationInput,
    GeneratedArtifact,
    GenerationInput,
    TenantManagementScope,
    TrustedScope,
)
from src.tool.llm_gateway.stub import DeterministicContentGenerator
from tests.conftest import BAIT_BRAND_ID, BAIT_TENANT_ID, SIBLING_BRAND_ID

_SECOND_ROOT_ID = UUID("80500000-0000-0000-0000-000000000031")
_SECOND_ROOT_ROLE_ID = UUID("80500000-0000-0000-0000-000000000061")
_SECOND_ROOT_GRANT_ID = UUID("80500000-0000-0000-0000-000000000041")
_BAIT_ORG_ID = UUID("80500000-0000-0000-0000-000000000210")
_BAIT_USER_ID = UUID("80500000-0000-0000-0000-000000000211")
_BAIT_LIBRARY_ID = UUID("80500000-0000-0000-0000-000000000212")
_SIBLING_LIBRARY_ID = UUID("80500000-0000-0000-0000-000000000213")


class _UI05Generator(DeterministicContentGenerator):
    """A deterministic seam double; no test in this module may call DeepSeek."""

    def collaborate(self, request: ConversationInput) -> ConversationDecision:
        if request.message == "今天有点不知道从哪儿开始。":
            return ConversationDecision(
                "chat",
                "听起来像是还没找到一个舒服的起点。我们可以先随便聊两句。",
            )
        if "去年创业最困难的那个月" in request.message:
            return ConversationDecision(
                "question",
                "那个月具体发生了哪一件最让你觉得困难的事？",
            )
        return super().collaborate(request)

    def generate(self, request: GenerationInput) -> GeneratedArtifact:
        if "触发受控失败" in request.weak_seed:
            raise GenerationFailed("controlled generation failure")
        return super().generate(request)


class _RequestDisconnected(BaseException):
    """Controlled transport cancellation at a real lifecycle boundary."""


def _settings(database_url: str) -> Settings:
    return Settings.model_validate(
        {
            "DIYU_RUNTIME_MODE": "production",
            "DIYU_APP_DATABASE_URL": database_url,
            "DIYU_SESSION_SECRET": "ui05-semantic-rework-test-session-secret",
            "DIYU_PUBLIC_URL": "https://diyuai.cc",
            # Production settings remain production-shaped; the generator port is replaced
            # below with the deterministic test double.
            "DIYU_GENERATOR_MODE": "deepseek",
            "DEEPSEEK_API_BASE_URL": "https://example.invalid",
            "DEEPSEEK_API_KEY": "not-a-real-key",
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
            "QWEN_REVIEWER_API_BASE_URL": "https://qwen.example.invalid",
            "DASHSCOPE_API_KEY": "not-a-real-qwen-key",
            "QWEN_REVIEWER_MODEL": "qwen3.7-max-2026-05-20",
            "DIYU_S3_ENDPOINT_URL": "http://127.0.0.1:9000",
            "DIYU_S3_BUCKET": "diyu-test",
            "DIYU_S3_ACCESS_KEY_ID": "test-access-key",
            "DIYU_S3_SECRET_ACCESS_KEY": "test-secret-key",
            "DIYU_S3_REGION": "us-east-1",
            "DIYU_MODEL_GLOBAL_CONCURRENCY": "10",
            "DIYU_MODEL_TENANT_CONCURRENCY": "10",
            "DIYU_MODEL_TENANT_RATE_PER_MINUTE": "120",
        }
    )


def _stub_builder(settings: Settings) -> ContentService:
    return ContentService(
        PostgresContentRepository(settings.app_database_url),
        _UI05Generator(),
        build_content_control_service(settings),
    )


def _app(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    monkeypatch.setattr(
        app_module,
        "build_content_service",
        cast(Callable[[Settings], ContentService], _stub_builder),
    )
    return app_module.create_app(_settings(database_url))


def _session_token(database_url: str, user_id: UUID, audience: str) -> str:
    repository = ProductionAuthRepository(database_url)
    return repository.create_tenant_session(TenantSession(TENANT_ID, user_id, audience))


def _stream_events(client: TestClient, payload: dict[str, object]) -> list[dict[str, object]]:
    response = client.post("/api/v1/content/stream", json=payload)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def _conversation_payload(
    message: str,
    *,
    identity_id: UUID = ACCOUNT_ID,
    target: str = "xiaohongshu_graphic",
    conversation: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "message": message,
        "conversation": conversation or [],
        "publishing_identity_id": str(identity_id),
        "target": target,
        "material_ids": [],
    }


def _persistence_counts(database_url: str) -> dict[str, int]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            """
            SELECT
              (SELECT count(*) FROM business_tasks
                WHERE tenant_id = %s) AS tasks,
              (SELECT count(*) FROM generation_runs
                WHERE tenant_id = %s) AS runs,
              (SELECT count(*) FROM generation_runs
                WHERE tenant_id = %s AND status = 'running') AS running,
              (SELECT count(*) FROM generation_runs
                WHERE tenant_id = %s AND status = 'failed') AS failed,
              (SELECT count(*) FROM content_versions
                WHERE tenant_id = %s) AS versions
            """,
            (TENANT_ID, TENANT_ID, TENANT_ID, TENANT_ID, TENANT_ID),
        )
        row = cursor.fetchone()
    assert row is not None
    return {key: int(row[key]) for key in ("tasks", "runs", "running", "failed", "versions")}


def test_ui05_a_conversation_only_persists_ready_and_failure_is_terminal(
    app_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _session_token(app_database_url, USER_ID, "tenant-user")
    with TestClient(_app(app_database_url, monkeypatch), base_url="https://diyuai.cc") as client:
        client.cookies.set("diyu_session", token)

        before_chat = _persistence_counts(app_database_url)
        chat = _stream_events(
            client,
            _conversation_payload("今天有点不知道从哪儿开始。"),
        )
        assert chat[-1]["event"] == "conversation"
        assert chat[-1]["kind"] == "chat"
        assert _persistence_counts(app_database_url) == before_chat
        time.sleep(2.05)

        question_text = "把我去年创业最困难的那个月写出来。"
        before_question = _persistence_counts(app_database_url)
        question = _stream_events(client, _conversation_payload(question_text))
        assert question[-1]["event"] == "conversation"
        assert question[-1]["kind"] == "question"
        assert _persistence_counts(app_database_url) == before_question
        time.sleep(2.05)

        ready_text = "帮我写条婆媳主题的小红书，别狗血，也不要把任何一方写成反派。"
        before_ready = _persistence_counts(app_database_url)
        ready = _stream_events(
            client,
            _conversation_payload(
                ready_text,
                conversation=[
                    {"role": "user", "content": question_text},
                    {
                        "role": "assistant",
                        "content": "那个月具体发生了哪一件最让你觉得困难的事？",
                    },
                ],
            ),
        )
        event_names = [str(item["event"]) for item in ready]
        assert event_names == [
            "received",
            "compiling_context",
            "generating",
            "validating",
            "finalizing",
            "completed",
        ]
        completed = cast(dict[str, object], ready[-1]["result"])
        assert completed["kind"] == "content"
        assert completed["version"] == 1
        assert _persistence_counts(app_database_url) == {
            "tasks": before_ready["tasks"] + 1,
            "runs": before_ready["runs"] + 1,
            "running": before_ready["running"],
            "failed": before_ready["failed"],
            "versions": before_ready["versions"] + 1,
        }
        time.sleep(2.05)

        before_failure = _persistence_counts(app_database_url)
        failed = _stream_events(
            client,
            _conversation_payload("请直接写一条完整内容，并触发受控失败。"),
        )
        assert failed[-1] == {
            "event": "failed",
            "message": (
                "这次还没能整理成一份可靠的成品。你的想法仍然保留，可以直接再试一次，也可以告诉我最想保留哪部分。"
            ),
        }
        assert _persistence_counts(app_database_url) == {
            "tasks": before_failure["tasks"] + 1,
            "runs": before_failure["runs"] + 1,
            "running": before_failure["running"],
            "failed": before_failure["failed"] + 1,
            "versions": before_failure["versions"],
        }

        before_disconnect = _persistence_counts(app_database_url)

        def disconnect_at_finalizing(stage: str) -> None:
            if stage == "finalizing":
                raise _RequestDisconnected

        with pytest.raises(_RequestDisconnected):
            _stub_builder(_settings(app_database_url)).respond_to_conversation(
                TrustedScope(
                    TENANT_ID,
                    USER_ID,
                    BRAND_ID,
                    HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID,
                ),
                "请直接写一条完整内容，并验证保存阶段断连。",
                (),
                "xiaohongshu_graphic",
                progress=disconnect_at_finalizing,
            )
        assert _persistence_counts(app_database_url) == {
            "tasks": before_disconnect["tasks"] + 1,
            "runs": before_disconnect["runs"] + 1,
            "running": before_disconnect["running"],
            "failed": before_disconnect["failed"] + 1,
            "versions": before_disconnect["versions"],
        }

        def disconnect_at_generating(stage: str) -> None:
            if stage == "generating":
                raise _RequestDisconnected

        before_early_disconnect = _persistence_counts(app_database_url)
        with pytest.raises(_RequestDisconnected):
            _stub_builder(_settings(app_database_url)).respond_to_conversation(
                TrustedScope(
                    TENANT_ID,
                    USER_ID,
                    BRAND_ID,
                    HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID,
                ),
                "请直接写一条完整内容，并验证生成阶段断连。",
                (),
                "xiaohongshu_graphic",
                progress=disconnect_at_generating,
            )
        after_early_disconnect = _persistence_counts(app_database_url)
        assert after_early_disconnect == {
            "tasks": before_early_disconnect["tasks"] + 1,
            "runs": before_early_disconnect["runs"] + 1,
            "running": before_early_disconnect["running"],
            "failed": before_early_disconnect["failed"] + 1,
            "versions": before_early_disconnect["versions"],
        }


def test_ui05_b_entry_qualifications_are_mutually_exclusive_and_api_errors_stay_json(
    app_database_url: str,
    migrator_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = ProductionAuthRepository(app_database_url)
    operator_id = uuid4()
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO platform_operators (id, username, password_hash, totp_secret)
            VALUES (%s, %s, %s, %s)
            """,
            (
                operator_id,
                f"ui05-ops-{uuid4().hex}",
                repository._password_hash("ui05-ops-password-is-long"),
                repository._totp_secret(),
            ),
        )
    admin_token = repository.create_tenant_session(TenantSession(TENANT_ID, TENANT_ADMIN_USER_ID, "tenant-admin"))
    user_token = repository.create_tenant_session(TenantSession(TENANT_ID, USER_ID, "tenant-user"))
    ops_token = repository.create_operator_session(OpsSession(operator_id))

    with TestClient(_app(app_database_url, monkeypatch), base_url="https://diyuai.cc") as client:
        for path, destination in (
            ("/content", "/login"),
            ("/tenant-admin", "/tenant-admin/login"),
            ("/ops", "/ops/login"),
        ):
            anonymous = client.get(path, follow_redirects=False)
            assert anonymous.status_code == 303
            assert anonymous.headers["location"].startswith(destination)

        client.cookies.set("diyu_session", admin_token)
        forbidden_content = client.get("/content")
        assert forbidden_content.status_code == 403
        assert forbidden_content.headers["content-type"].startswith("text/html")
        assert "当前账号不能使用这个入口" in forbidden_content.text
        assert "返回租户管理入口" in forbidden_content.text
        assert "当前正式会话" not in forbidden_content.text
        content_api = client.get("/api/v1/content/publishing-identities")
        assert content_api.status_code == 403
        assert content_api.headers["content-type"].startswith("application/json")
        assert set(content_api.json()) == {"detail"}

        client.cookies.set("diyu_session", user_token)
        forbidden_admin = client.get("/tenant-admin")
        assert forbidden_admin.status_code == 403
        assert forbidden_admin.headers["content-type"].startswith("text/html")
        assert "当前账号没有租户管理资格" in forbidden_admin.text
        assert "返回内容入口" in forbidden_admin.text
        assert "当前正式会话" not in forbidden_admin.text
        admin_api = client.get("/api/v1/admin/readiness")
        assert admin_api.status_code == 403
        assert admin_api.headers["content-type"].startswith("application/json")
        assert set(admin_api.json()) == {"detail"}

        client.cookies.delete("diyu_session")
        client.cookies.set("diyu_ops_session", ops_token)
        assert client.get("/ops").status_code == 200
        assert client.get("/content", follow_redirects=False).status_code == 303
        client.cookies.delete("diyu_ops_session")
        client.cookies.set("diyu_session", user_token)
        assert client.get("/ops", follow_redirects=False).status_code == 303


def test_ui05_c_logical_identity_owns_targets_and_explicit_selection_is_frozen(
    app_database_url: str,
    migrator_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            """
            INSERT INTO content_accounts
              (id, tenant_id, brand_id, name, channel, control_organization_id,
               control_organization_source)
            VALUES (%s, %s, %s, 'UI-05 第二逻辑发布账号', '抖音', %s, 'declared')
            ON CONFLICT (id) DO NOTHING
            """,
            (_SECOND_ROOT_ID, TENANT_ID, BRAND_ID, ORG_ID),
        )
        cursor.execute(
            """
            INSERT INTO account_content_roles (id, tenant_id, account_id, content_role_id)
            VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
            """,
            (_SECOND_ROOT_ROLE_ID, TENANT_ID, _SECOND_ROOT_ID, ROLE_ID),
        )
        cursor.execute(
            """
            INSERT INTO auth_grants (id, tenant_id, user_id, account_id, role_name)
            VALUES (%s, %s, %s, %s, 'UI-05 多逻辑账号反证')
            ON CONFLICT (id) DO UPDATE SET enabled = true
            """,
            (_SECOND_ROOT_GRANT_ID, TENANT_ID, USER_ID, _SECOND_ROOT_ID),
        )

    token = _session_token(app_database_url, USER_ID, "tenant-user")
    with TestClient(_app(app_database_url, monkeypatch), base_url="https://diyuai.cc") as client:
        client.cookies.set("diyu_session", token)
        identities_response = client.get("/api/v1/content/publishing-identities")
        assert identities_response.status_code == 200
        identities = identities_response.json()
        assert {UUID(item["id"]) for item in identities} >= {ACCOUNT_ID, _SECOND_ROOT_ID}
        headquarters = next(item for item in identities if UUID(item["id"]) == ACCOUNT_ID)
        assert {item["value"] for item in headquarters["platform_targets"]} == {
            "douyin_video",
            "xiaohongshu_graphic",
            "xiaohongshu_video",
            "wechat_channels_video",
        }
        second = next(item for item in identities if UUID(item["id"]) == _SECOND_ROOT_ID)
        assert {item["value"] for item in second["platform_targets"]} == {"douyin_video"}

        selection_page = client.get("/content")
        assert selection_page.status_code == 200
        assert '"current_publishing_identity_id": null' in selection_page.text

        marker = f"ui05-frozen-{uuid4().hex}"
        events = _stream_events(
            client,
            _conversation_payload(
                f"请写一条完整的门店观察内容。{marker}",
                identity_id=ACCOUNT_ID,
                target="xiaohongshu_graphic",
            ),
        )
        result = cast(dict[str, object], events[-1]["result"])
        task_id = UUID(str(result["task_id"]))
        with (
            psycopg.connect(
                migrator_database_url,
                row_factory=dict_row,
            ) as evidence_connection,
            evidence_connection.cursor() as evidence_cursor,
        ):
            evidence_cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
            evidence_cursor.execute(
                """
                SELECT account_id, logical_account_id, media_format, content_context_snapshot
                FROM business_tasks WHERE tenant_id = %s AND id = %s
                """,
                (TENANT_ID, task_id),
            )
            frozen = evidence_cursor.fetchone()
        assert frozen is not None
        assert UUID(str(frozen["account_id"])) == HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID
        assert UUID(str(frozen["logical_account_id"])) == ACCOUNT_ID
        assert frozen["media_format"] == "graphic"
        assert cast(dict[str, object], frozen["content_context_snapshot"])["target"] == "xiaohongshu_graphic"

        history = client.get(
            f"/api/v1/tasks/{task_id}/versions/1",
            params={
                "target": "xiaohongshu_graphic",
                "publishing_identity_id": str(ACCOUNT_ID),
            },
        )
        assert history.status_code == 200
        assert history.json()["version_id"] == result["version_id"]
        assert history.json()["target_key"] == "xiaohongshu_graphic"

        wrong_root = client.get(
            f"/api/v1/tasks/{task_id}/versions/1",
            params={
                "target": "douyin_video",
                "publishing_identity_id": str(_SECOND_ROOT_ID),
            },
        )
        assert wrong_root.status_code == 422

        created_series = client.post(
            "/api/v1/content/series",
            params={
                "target": "xiaohongshu_graphic",
                "publishing_identity_id": str(ACCOUNT_ID),
            },
            json={
                "title": f"UI-05 跨平台系列-{uuid4().hex}",
                "premise": "同一逻辑发布账号在不同平台继续。",
            },
        )
        assert created_series.status_code == 201, created_series.text
        series_id = UUID(str(created_series.json()["id"]))
        with (
            psycopg.connect(
                migrator_database_url,
                row_factory=dict_row,
            ) as series_connection,
            series_connection.cursor() as series_cursor,
        ):
            series_cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                (str(TENANT_ID),),
            )
            series_cursor.execute(
                """
                SELECT account_id, logical_account_id
                  FROM content_series
                 WHERE tenant_id = %s AND id = %s
                """,
                (TENANT_ID, series_id),
            )
            frozen_series = series_cursor.fetchone()
        assert frozen_series is not None
        assert UUID(str(frozen_series["account_id"])) == HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID
        assert UUID(str(frozen_series["logical_account_id"])) == ACCOUNT_ID
        listed_from_douyin = client.get(
            "/api/v1/content/series",
            params={
                "target": "douyin_video",
                "publishing_identity_id": str(ACCOUNT_ID),
            },
        )
        assert listed_from_douyin.status_code == 200
        assert series_id in {UUID(str(item["id"])) for item in listed_from_douyin.json()}

        legacy_series_id = uuid4()
        with psycopg.connect(app_database_url) as legacy_connection, legacy_connection.cursor() as legacy_cursor:
            legacy_cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                (str(TENANT_ID),),
            )
            # Exact previous-image write shape: no logical_account_id column.
            legacy_cursor.execute(
                """
                INSERT INTO content_series
                    (id, tenant_id, brand_id, account_id, created_by, title, premise)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING account_id, logical_account_id
                """,
                (
                    legacy_series_id,
                    TENANT_ID,
                    BRAND_ID,
                    HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID,
                    USER_ID,
                    f"UI-05 旧镜像兼容系列-{legacy_series_id.hex}",
                    "旧镜像写入仍保留物理账号，同时由数据库补足逻辑账号。",
                ),
            )
            legacy_series = legacy_cursor.fetchone()
        assert legacy_series is not None
        assert UUID(str(legacy_series[0])) == HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID
        assert UUID(str(legacy_series[1])) == ACCOUNT_ID


def test_ui05_c_carrier_grant_never_promotes_to_logical_identity_or_other_targets(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    repository = ProductionAuthRepository(app_database_url)
    existing_identity = TenantSession(TENANT_ID, USER_ID, "tenant-user")
    existing_roots = repository.list_publishing_identities(existing_identity)
    assert ACCOUNT_ID in {UUID(str(item["id"])) for item in existing_roots}
    assert (
        repository.content_scope(
            existing_identity,
            "douyin_video",
            ACCOUNT_ID,
        ).account_id
        == ACCOUNT_ID
    )

    carrier_only_user_id = uuid4()
    carrier_grant_id = uuid4()
    root_grant_id = uuid4()
    carrier_only_identity = TenantSession(
        TENANT_ID,
        carrier_only_user_id,
        "tenant-user",
    )
    try:
        with (
            psycopg.connect(migrator_database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                (str(TENANT_ID),),
            )
            cursor.execute(
                """
                INSERT INTO users
                    (id, tenant_id, organization_id, display_name, entry_kind)
                VALUES (%s, %s, %s, %s, 'tenant_user')
                """,
                (
                    carrier_only_user_id,
                    TENANT_ID,
                    ORG_ID,
                    f"UI05 仅平台载体历史授权-{carrier_only_user_id.hex[:8]}",
                ),
            )
            cursor.execute(
                """
                INSERT INTO auth_grants
                    (id, tenant_id, user_id, account_id, role_name)
                VALUES (%s, %s, %s, %s, 'UI05 历史平台载体授权')
                """,
                (
                    carrier_grant_id,
                    TENANT_ID,
                    carrier_only_user_id,
                    HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID,
                ),
            )

        assert repository.list_publishing_identities(carrier_only_identity) == []
        assert repository.allowed_content_targets(carrier_only_identity) == ()
        with pytest.raises(DomainError, match="还没有可使用的发布账号"):
            repository.content_scope(carrier_only_identity)
        with pytest.raises(DomainError, match="没有获准操作这个发布账号"):
            repository.content_scope(
                carrier_only_identity,
                "xiaohongshu_graphic",
                ACCOUNT_ID,
            )

        with (
            psycopg.connect(migrator_database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                (str(TENANT_ID),),
            )
            cursor.execute(
                """
                INSERT INTO auth_grants
                    (id, tenant_id, user_id, account_id, role_name)
                VALUES (%s, %s, %s, %s, 'UI05 明确逻辑发布账号授权')
                """,
                (
                    root_grant_id,
                    TENANT_ID,
                    carrier_only_user_id,
                    ACCOUNT_ID,
                ),
            )

        roots = repository.list_publishing_identities(carrier_only_identity)
        assert [UUID(str(item["id"])) for item in roots] == [ACCOUNT_ID]
        assert {str(target["value"]) for target in cast(list[dict[str, object]], roots[0]["platform_targets"])} == {
            "douyin_video",
            "xiaohongshu_graphic",
            "xiaohongshu_video",
            "wechat_channels_video",
        }
        assert (
            repository.content_scope(
                carrier_only_identity,
                "xiaohongshu_graphic",
                ACCOUNT_ID,
            ).account_id
            == HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID
        )
    finally:
        with (
            psycopg.connect(migrator_database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                (str(TENANT_ID),),
            )
            cursor.execute(
                "DELETE FROM auth_grants WHERE tenant_id = %s AND user_id = %s",
                (TENANT_ID, carrier_only_user_id),
            )
            cursor.execute(
                "DELETE FROM users WHERE tenant_id = %s AND id = %s",
                (TENANT_ID, carrier_only_user_id),
            )


def test_ui05_c_account_creation_stores_one_profile_without_a_second_boundary(
    app_database_url: str,
    migrator_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid4().hex
    account_name = f"UI-05 账号画像原子创建-{suffix}"
    role_name = f"总部内容短标签-{suffix}"
    segments = {
        "identity_position": "总部品牌内容运营，以品牌长期表达身份出现。",
        "authority_boundary": "只代表当前品牌已确认立场，不冒充门店经历或顾客。",
        "audience_relationship": "把受众当作有判断力的成年人。",
        "content_territories": "长期讲选择方法、商品取舍和服务关系。",
        "default_production_conditions": "一人、一部手机和普通室内。",
    }
    token = _session_token(
        app_database_url,
        TENANT_ADMIN_USER_ID,
        "tenant-admin",
    )
    account_id: UUID | None = None
    role_id: UUID | None = None
    profile_id: UUID | None = None
    try:
        with TestClient(
            _app(app_database_url, monkeypatch),
            base_url="https://diyuai.cc",
        ) as client:
            client.cookies.set("diyu_session", token)
            payload = {
                "name": account_name,
                "channel": "抖音",
                "content_role_name": role_name,
                "operator_id": str(USER_ID),
                "control_organization_id": str(ORG_ID),
                "initial_profile": segments,
            }
            created = client.post(
                "/api/v1/tenant-management/publishing-accounts",
                json=payload,
            )
            retried = client.post(
                "/api/v1/tenant-management/publishing-accounts",
                json=payload,
            )
            assert created.status_code == 201, created.text
            assert retried.status_code == 201, retried.text
            assert created.json()["id"] == retried.json()["id"]
            account_id = UUID(created.json()["id"])

            refused = client.post(
                "/api/v1/tenant-management/publishing-accounts",
                json={
                    **payload,
                    "name": f"{account_name}-门店越权",
                    "content_role_name": f"{role_name}-门店越权",
                    "control_organization_id": str(STORE_ORG_ID),
                },
            )
            assert refused.status_code == 422
            assert "公司级负责团队" in refused.json()["detail"]

        with (
            psycopg.connect(
                migrator_database_url,
                row_factory=dict_row,
            ) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                (str(TENANT_ID),),
            )
            cursor.execute(
                """
                SELECT role.id AS role_id, role.voice_boundary,
                       profile.id AS profile_id, profile.version,
                       profile.identity_position, profile.authority_boundary,
                       profile.audience_relationship, profile.content_territories,
                       profile.default_production_conditions,
                       (
                         SELECT count(*)
                           FROM account_expression_profile_versions history
                          WHERE history.tenant_id = account.tenant_id
                            AND history.account_id = account.id
                       ) AS profile_count
                  FROM content_accounts account
                  JOIN account_content_roles account_role
                    ON account_role.tenant_id = account.tenant_id
                   AND account_role.account_id = account.id
                  JOIN content_roles role
                    ON role.tenant_id = account_role.tenant_id
                   AND role.id = account_role.content_role_id
                  JOIN account_expression_profile_versions profile
                    ON profile.tenant_id = account.tenant_id
                   AND profile.id = account.current_expression_profile_id
                 WHERE account.tenant_id = %s
                   AND account.id = %s
                """,
                (TENANT_ID, account_id),
            )
            stored = cursor.fetchone()
            assert stored is not None
            role_id = UUID(str(stored["role_id"]))
            profile_id = UUID(str(stored["profile_id"]))
            assert stored["version"] == 1
            assert stored["profile_count"] == 1
            assert stored["voice_boundary"] == segments["authority_boundary"]
            for key, value in segments.items():
                assert stored[key] == value
    finally:
        if account_id is not None:
            with (
                psycopg.connect(migrator_database_url) as cleanup_connection,
                cleanup_connection.cursor() as cleanup_cursor,
            ):
                cleanup_cursor.execute(
                    "SELECT set_config('app.tenant_id', %s, true)",
                    (str(TENANT_ID),),
                )
                cleanup_cursor.execute(
                    "DELETE FROM activity_events WHERE tenant_id = %s AND entity_id = ANY(%s)",
                    (
                        TENANT_ID,
                        [value for value in (account_id, profile_id) if value is not None],
                    ),
                )
                cleanup_cursor.execute(
                    "DELETE FROM auth_grants WHERE tenant_id = %s AND account_id = %s",
                    (TENANT_ID, account_id),
                )
                cleanup_cursor.execute(
                    "UPDATE content_accounts SET current_expression_profile_id = NULL WHERE tenant_id = %s AND id = %s",
                    (TENANT_ID, account_id),
                )
                cleanup_cursor.execute(
                    "DELETE FROM account_expression_profile_versions WHERE tenant_id = %s AND account_id = %s",
                    (TENANT_ID, account_id),
                )
                cleanup_cursor.execute(
                    "DELETE FROM account_content_roles WHERE tenant_id = %s AND account_id = %s",
                    (TENANT_ID, account_id),
                )
                cleanup_cursor.execute(
                    "DELETE FROM content_accounts WHERE tenant_id = %s AND id = %s",
                    (TENANT_ID, account_id),
                )
                if role_id is not None:
                    cleanup_cursor.execute(
                        "DELETE FROM content_roles WHERE tenant_id = %s AND id = %s",
                        (TENANT_ID, role_id),
                    )


def test_ui05_d_brand_library_scopes_filter_before_context_and_private_materials_stay_private(
    app_database_url: str,
    migrator_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_token = _session_token(app_database_url, TENANT_ADMIN_USER_ID, "tenant-admin")
    suffix = uuid4().hex
    entries: tuple[tuple[str, list[str], str], ...] = (
        ("brand_all", [], f"UI05-BRAND-{suffix}"),
        ("headquarters", [str(ORG_ID)], f"UI05-HQ-{suffix}"),
        ("organizations", [str(STORE_ORG_ID)], f"UI05-STORE-{suffix}"),
        ("organizations", [str(EXTERNAL_OPERATOR_ORG_ID)], f"UI05-OTHER-{suffix}"),
    )
    with TestClient(_app(app_database_url, monkeypatch), base_url="https://diyuai.cc") as client:
        client.cookies.set("diyu_session", admin_token)
        for visibility_scope, organization_ids, title in entries:
            saved = client.post(
                "/api/v1/tenant-management/brand-library",
                json={
                    "category": "reference",
                    "title": title,
                    "source_note": "UI-05 scoped integration fixture",
                    "content": f"{title}-CONTENT",
                    "version": "1",
                    "status": "active",
                    "visibility_scope": visibility_scope,
                    "organization_ids": organization_ids,
                },
            )
            assert saved.status_code == 201, saved.text

    headquarters = PostgresContentRepository(app_database_url).load_brand_context(
        TrustedScope(TENANT_ID, USER_ID, BRAND_ID, ACCOUNT_ID),
        "graphic",
        "一人一部手机",
    )
    store = PostgresContentRepository(app_database_url).load_brand_context(
        TrustedScope(TENANT_ID, STORE_CONTENT_USER_ID, BRAND_ID, STORE_CONTENT_ACCOUNT_ID),
        "video",
        "一人一部手机",
    )
    headquarters_refs = "\n".join(headquarters.brand_reference_context)
    store_refs = "\n".join(store.brand_reference_context)
    assert f"UI05-BRAND-{suffix}" in headquarters_refs
    assert f"UI05-HQ-{suffix}" in headquarters_refs
    assert f"UI05-STORE-{suffix}" not in headquarters_refs
    assert f"UI05-OTHER-{suffix}" not in headquarters_refs
    assert f"UI05-BRAND-{suffix}" in store_refs
    assert f"UI05-STORE-{suffix}" in store_refs
    assert f"UI05-HQ-{suffix}" not in store_refs
    assert f"UI05-OTHER-{suffix}" not in store_refs

    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (BAIT_TENANT_ID,))
        cursor.execute(
            """
            INSERT INTO organizations (id, tenant_id, name, organization_level)
            VALUES (%s, %s, 'UI05 隔离组织', 'company') ON CONFLICT (id) DO NOTHING
            """,
            (_BAIT_ORG_ID, BAIT_TENANT_ID),
        )
        cursor.execute(
            """
            INSERT INTO users (id, tenant_id, organization_id, display_name, entry_kind)
            VALUES (%s, %s, %s, 'UI05-CROSS-TENANT-SENTINEL', 'tenant_user')
            ON CONFLICT (id) DO NOTHING
            """,
            (_BAIT_USER_ID, BAIT_TENANT_ID, _BAIT_ORG_ID),
        )
        cursor.execute(
            """
            INSERT INTO brand_library_entries
              (id, tenant_id, brand_id, category, title, source_note, content,
               version, status, visibility_scope, updated_by)
            VALUES (%s, %s, %s, 'reference', 'UI05-BAIT-LIBRARY',
                    'cross tenant sentinel', 'must never cross tenant',
                    '1', 'active', 'brand_all', %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (_BAIT_LIBRARY_ID, BAIT_TENANT_ID, BAIT_BRAND_ID, _BAIT_USER_ID),
        )
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            """
            INSERT INTO brand_library_entries
              (id, tenant_id, brand_id, category, title, source_note, content,
               version, status, visibility_scope, updated_by)
            VALUES (%s, %s, %s, 'reference', 'UI05-SIBLING-BRAND',
                    'same tenant different brand', 'must never cross brand',
                    '1', 'active', 'brand_all', %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (_SIBLING_LIBRARY_ID, TENANT_ID, SIBLING_BRAND_ID, USER_ID),
        )

    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            "SELECT count(*) FROM brand_library_entries WHERE tenant_id = %s",
            (BAIT_TENANT_ID,),
        )
        assert cursor.fetchone() == (0,)
    refreshed = PostgresContentRepository(app_database_url).load_brand_context(
        TrustedScope(TENANT_ID, USER_ID, BRAND_ID, ACCOUNT_ID),
        "graphic",
        "一人一部手机",
    )
    assert "UI05-SIBLING-BRAND" not in "\n".join(refreshed.brand_reference_context)

    workbench = PostgresWorkbenchRepository(app_database_url)
    headquarters_material_id = uuid4()
    external_material_id = uuid4()
    management_scope = TenantManagementScope(
        TENANT_ID,
        TENANT_ADMIN_USER_ID,
        BRAND_ID,
    )
    workbench.create_management_organization_material(
        management_scope,
        ORG_ID,
        headquarters_material_id,
        f"UI05-HQ-MATERIAL-{suffix}",
        "image",
        f"ui05/headquarters/{suffix}.png",
        8,
        "headquarters.png",
        f"headquarters-{suffix}",
        "headquarters material note",
        "headquarters",
        (ORG_ID,),
    )
    workbench.create_management_organization_material(
        management_scope,
        EXTERNAL_OPERATOR_ORG_ID,
        external_material_id,
        f"UI05-EXTERNAL-MATERIAL-{suffix}",
        "image",
        f"ui05/external/{suffix}.png",
        8,
        "external.png",
        f"external-{suffix}",
        "external material note",
        "organizations",
        (EXTERNAL_OPERATOR_ORG_ID,),
    )
    external_headquarters_scope = TrustedScope(
        TENANT_ID,
        EXTERNAL_OPERATOR_USER_ID,
        BRAND_ID,
        HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID,
    )
    visible_material_ids = {UUID(str(item["id"])) for item in workbench.list_materials(external_headquarters_scope)}
    assert headquarters_material_id in visible_material_ids
    assert external_material_id not in visible_material_ids

    control_repository = PostgresContentControlRepository(app_database_url)
    selected = control_repository.selected_materials(
        external_headquarters_scope,
        (headquarters_material_id,),
    )
    assert {UUID(str(item["asset_id"])) for item in selected} == {headquarters_material_id}
    with pytest.raises(DomainError, match="当前身份不能使用"):
        control_repository.selected_materials(
            external_headquarters_scope,
            (external_material_id,),
        )

    material_title = f"UI05-PRIVATE-{suffix}"
    workbench.create_material(
        TrustedScope(TENANT_ID, STORE_CONTENT_USER_ID, BRAND_ID, STORE_CONTENT_ACCOUNT_ID),
        uuid4(),
        material_title,
        "image",
        "personal",
        f"ui05/private/{suffix}.png",
        8,
        "fixture.png",
        suffix,
        "private sentinel note",
    )
    assert material_title in {
        item["title"]
        for item in workbench.list_materials(
            TrustedScope(TENANT_ID, STORE_CONTENT_USER_ID, BRAND_ID, STORE_CONTENT_ACCOUNT_ID)
        )
    }
    assert material_title not in {
        item["title"] for item in workbench.list_materials(TrustedScope(TENANT_ID, USER_ID, BRAND_ID, ACCOUNT_ID))
    }


def test_ui05_e_team_usage_is_tenant_aggregate_without_content_or_private_payloads(
    app_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _session_token(app_database_url, TENANT_ADMIN_USER_ID, "tenant-admin")
    with TestClient(_app(app_database_url, monkeypatch), base_url="https://diyuai.cc") as client:
        client.cookies.set("diyu_session", token)
        seven = client.get("/api/v1/tenant-management/team-usage", params={"window_days": 7})
        thirty = client.get("/api/v1/tenant-management/team-usage", params={"window_days": 30})
    assert seven.status_code == 200, seven.text
    assert thirty.status_code == 200, thirty.text
    assert seven.json()["window_days"] == 7
    assert thirty.json()["window_days"] == 30
    assert seven.json()["members"]["registered"] <= thirty.json()["members"]["registered"]
    visible_names = {item["display_name"] for item in thirty.json()["members"]["items"]}
    assert "UI05-CROSS-TENANT-SENTINEL" not in visible_names

    serialized = json.dumps(thirty.json(), ensure_ascii=False)
    assert "must never cross tenant" not in serialized
    assert "private sentinel note" not in serialized
    assert "最近店里总有人只想自己看看" not in serialized
    assert thirty.json()["provider_usage"]["label"] == "已记录模型用量"
    assert thirty.json()["provider_usage"]["is_complete_billing_total"] is False
    forbidden_keys = {"body", "weak_seed", "prompt", "private_materials", "private_preferences"}

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | set().union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value))
        return set()

    assert not (keys(thirty.json()) & forbidden_keys)
    assert client.get("/api/v1/tenant-management/team-usage", params={"window_days": 14}).status_code == 422


def test_ui05_f_readiness_has_rich_evidence_and_a_product_gap_is_localized(
    app_database_url: str,
    migrator_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _session_token(app_database_url, TENANT_ADMIN_USER_ID, "tenant-admin")
    sku = f"UI05-READY-{uuid4().hex[:10].upper()}"
    with psycopg.connect(migrator_database_url, row_factory=dict_row) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            "SELECT positioning, tone, strategy_version FROM brands WHERE tenant_id = %s AND id = %s",
            (TENANT_ID, BRAND_ID),
        )
        original_brand = cast(dict[str, object], cursor.fetchone())
        cursor.execute(
            "SELECT version, draft, status, confirmed_by, confirmed_at, updated_at "
            "FROM brand_expression_baselines WHERE tenant_id = %s AND brand_id = %s",
            (TENANT_ID, BRAND_ID),
        )
        original_baseline = cast(dict[str, object], cursor.fetchone())
        cursor.execute(
            "SELECT current_expression_profile_id FROM content_accounts WHERE tenant_id = %s AND id = %s",
            (TENANT_ID, ACCOUNT_ID),
        )
        original_profile_id = cast(dict[str, object], cursor.fetchone())["current_expression_profile_id"]
    profile_payload = {
        "identity_position": "总部品牌内容运营，以品牌长期表达身份出现。",
        "authority_boundary": "只代表当前品牌已确认立场，不冒充门店经历或顾客。",
        "audience_relationship": "把受众当作有判断力的成年人，提供可带走的观察方法。",
        "content_territories": "长期讲商品取舍、服务关系和日常穿着判断。",
        "default_production_conditions": "一人、一部手机、普通室内和现有商品。",
    }
    with TestClient(_app(app_database_url, monkeypatch), base_url="https://diyuai.cc") as client:
        client.cookies.set("diyu_session", token)
        confirmed = client.post(
            "/api/v1/admin/brand-expression/confirm",
            json={"draft": "成熟、平等、具体地讲清真实选择，不补造人物、经历或商品事实。"},
        )
        assert confirmed.status_code == 200, confirmed.text
        profile = client.post(
            f"/api/v1/tenant-management/publishing-accounts/{ACCOUNT_ID}/expression-profile/versions",
            json=profile_payload,
        )
        assert profile.status_code == 201, profile.text
        created_profile_id = UUID(str(profile.json()["profile_id"]))
        product = client.put(
            "/api/v1/tenant-management/brand-products",
            json={
                "sku": sku,
                "display_name": "UI-05 就绪诊断夹具",
                "category": "短外套",
                "colors": ["炭灰"],
                "material_or_structure": "可见双层结构",
                "silhouette": "直身短轮廓",
                "observable_features": "正面可见纽扣",
                "source_note": "UI-05 后端集成夹具责任来源",
                "applicability": "仅用于 UI-05 测试数据库",
                "confirm_as_current_brand_fact": True,
                "as_synthetic_business_fixture": True,
            },
        )
        assert product.status_code == 200, product.text

        with psycopg.connect(migrator_database_url, row_factory=dict_row) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
            cursor.execute(
                "SELECT id, source_note FROM brand_products WHERE tenant_id = %s AND brand_id = %s AND sku <> %s",
                (TENANT_ID, BRAND_ID, sku),
            )
            original_notes = [(UUID(str(row["id"])), str(row["source_note"])) for row in cursor.fetchall()]
            cursor.execute(
                "UPDATE brand_products SET source_note = '' WHERE tenant_id = %s AND brand_id = %s AND sku <> %s",
                (TENANT_ID, BRAND_ID, sku),
            )

        try:
            before_response = client.get("/api/v1/admin/readiness")
            assert before_response.status_code == 200
            before_items = {item["id"]: item for item in before_response.json()["items"]}
            assert set(before_items) == {
                "brand_expression",
                "non_product_content",
                "product_facts",
                "continuous_series",
                "platform_recompile",
                "dm01_display",
            }
            required = {
                "status",
                "evidence",
                "gaps",
                "impact",
                "action",
                "source",
                "version",
                "evaluated_at",
            }
            assert all(required <= set(item) for item in before_items.values())
            assert before_items["product_facts"]["status"] == "available"
            assert before_items["product_facts"]["gaps"] == []

            with psycopg.connect(migrator_database_url) as gap_connection, gap_connection.cursor() as gap_cursor:
                gap_cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
                gap_cursor.execute(
                    "UPDATE brand_products SET source_note = '' WHERE tenant_id = %s AND brand_id = %s AND sku = %s",
                    (TENANT_ID, BRAND_ID, sku),
                )

            after_response = client.get("/api/v1/admin/readiness")
            assert after_response.status_code == 200
            after_items = {item["id"]: item for item in after_response.json()["items"]}
            assert after_items["product_facts"]["status"] != "available"
            assert after_items["product_facts"]["gaps"]
            assert "商品" in after_items["product_facts"]["impact"]
            assert after_items["product_facts"]["action"]["section"] == "brand-library"
            for stable_id in set(before_items) - {"product_facts"}:
                assert after_items[stable_id]["status"] == before_items[stable_id]["status"]
                assert after_items[stable_id]["evidence"] == before_items[stable_id]["evidence"]
                assert after_items[stable_id]["gaps"] == before_items[stable_id]["gaps"]
        finally:
            with (
                psycopg.connect(migrator_database_url) as restore_connection,
                restore_connection.cursor() as restore_cursor,
            ):
                restore_cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
                for product_id, source_note in original_notes:
                    restore_cursor.execute(
                        "UPDATE brand_products SET source_note = %s WHERE tenant_id = %s AND id = %s",
                        (source_note, TENANT_ID, product_id),
                    )
                restore_cursor.execute(
                    "UPDATE brand_products SET source_note = %s WHERE tenant_id = %s AND brand_id = %s AND sku = %s",
                    ("UI-05 后端集成夹具责任来源", TENANT_ID, BRAND_ID, sku),
                )
                restore_cursor.execute(
                    "DELETE FROM brand_products WHERE tenant_id = %s AND brand_id = %s AND sku = %s",
                    (TENANT_ID, BRAND_ID, sku),
                )
                restore_cursor.execute(
                    "UPDATE content_accounts SET current_expression_profile_id = %s WHERE tenant_id = %s AND id = %s",
                    (original_profile_id, TENANT_ID, ACCOUNT_ID),
                )
                restore_cursor.execute(
                    "DELETE FROM account_expression_profile_versions WHERE tenant_id = %s AND id = %s",
                    (TENANT_ID, created_profile_id),
                )
                restore_cursor.execute(
                    "UPDATE brands SET positioning = %s, tone = %s, strategy_version = %s "
                    "WHERE tenant_id = %s AND id = %s",
                    (
                        original_brand["positioning"],
                        original_brand["tone"],
                        original_brand["strategy_version"],
                        TENANT_ID,
                        BRAND_ID,
                    ),
                )
                restore_cursor.execute(
                    "UPDATE brand_expression_baselines "
                    "SET version = %s, draft = %s, status = %s, confirmed_by = %s, "
                    "confirmed_at = %s, updated_at = %s "
                    "WHERE tenant_id = %s AND brand_id = %s",
                    (
                        original_baseline["version"],
                        original_baseline["draft"],
                        original_baseline["status"],
                        original_baseline["confirmed_by"],
                        original_baseline["confirmed_at"],
                        original_baseline["updated_at"],
                        TENANT_ID,
                        BRAND_ID,
                    ),
                )
