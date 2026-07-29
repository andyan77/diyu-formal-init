from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any, cast
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

import src.gateway.api.app as app_module
from src.brain.content_service import ContentService
from src.composition.bootstrap import build_content_control_service
from src.gateway.api.settings import Settings
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.production_auth import ProductionAuthRepository, TenantSession
from src.infrastructure.seed_demo import (
    ACCOUNT_ID,
    TENANT_ID,
    USER_ID,
)
from src.shared.creative_plan import (
    ACCOUNT_BASELINE_TONE_ID,
    build_creative_plan,
)
from src.shared.errors import GenerationFailed
from src.shared.narrative import NarrativeFrame, frame_document
from src.shared.types import (
    ConversationDecision,
    ConversationInput,
    GeneratedArtifact,
    GenerationInput,
)
from src.tool.llm_gateway.stub import DeterministicContentGenerator

_G1 = "今天有点不知道从哪儿开始。"
_G2 = "ZX-C218，帮我生成一篇小红书文案。"
_G3 = "帮我写条婆媳主题的小红书，别狗血，也不要把任何一方写成反派。"
_G4 = "今天店里忙了一天，回家还因为谁洗碗拌了两句。帮我发条小红书。"
_G4_FACT = "今天店里忙了一天，回家还因为谁洗碗拌了两句。"
_G5 = "今天不知道发什么，帮我做条小红书。"
_G6 = "把我去年创业最困难的那个月写出来。"
_G7 = "别讲道理，荒诞一点。"
_BAD_PLAN = "帮我生成一篇关系文案。"

_CAPTURED_FRAMES: list[NarrativeFrame] = []
_CAPTURED_PLANS: list[object] = []
_CALLS = {"intake": 0, "writer": 0, "reviewer": 0}


def _plan(
    request: ConversationInput,
    product: str,
) -> object:
    return build_creative_plan(
        topic_spans=(request.message,),
        primary_value=cast(Any, product),
        tone_ids=(request.allowed_tone_ids or (ACCOUNT_BASELINE_TONE_ID,)),
        mechanism_id=(request.allowed_mechanism_ids[0] if request.allowed_mechanism_ids else None),
        target_shape=request.platform_shape,
    )


class _UI06LifecycleGenerator(DeterministicContentGenerator):
    """Malicious intake/lifecycle seam; never evidence of model semantic quality."""

    def collaborate(self, request: ConversationInput) -> ConversationDecision:
        _CALLS["intake"] += 1
        if request.message == _G1:
            return ConversationDecision(
                "ready",
                "模型错误地认为可以直接创作。",
                user_premises=(request.message,),
                narrative_mode="general_observation",
                creative_plan=cast(Any, _plan(request, "brand_life_narrative")),
                primary_product="brand_life_narrative",
                creation_proposal=True,
                proposed_intent_span="帮我生成一篇小红书文案",
            )
        if request.message == _G6:
            return ConversationDecision(
                "question",
                "那个月具体发生了哪一件最让你觉得困难的事？",
            )
        if request.message == _BAD_PLAN:
            return ConversationDecision(
                "ready",
                "模型夹带了并不存在的情节。",
                user_premises=(request.message,),
                narrative_mode="general_observation",
                creative_plan=replace(
                    cast(Any, _plan(request, "brand_life_narrative")),
                    topic_spans=("饭桌上一句话让两个人都沉默。",),
                ),
                primary_product="brand_life_narrative",
            )
        fact_spans = (_G4_FACT,) if request.message == _G4 else ()
        return ConversationDecision(
            "ready",
            "可以，我直接完成。",
            user_premises=(request.message,),
            user_fact_spans=fact_spans,
            narrative_mode=(
                "actuality_reflection" if fact_spans else request.explicit_narrative_mode or "general_observation"
            ),
            creative_plan=cast(
                Any,
                _plan(
                    request,
                    ("product_truth" if request.message == _G2 else "brand_life_narrative"),
                ),
            ),
            primary_product=("product_truth" if request.message == _G2 else "brand_life_narrative"),
        )

    def generate(self, request: GenerationInput) -> GeneratedArtifact:
        _CALLS["writer"] += 1
        if "验证一次失败原子性" in request.weak_seed:
            raise GenerationFailed("受控失败")
        assert request.narrative_frame is not None
        _CAPTURED_FRAMES.append(request.narrative_frame)
        _CAPTURED_PLANS.append(request.creative_plan)
        return super().generate(request)


def _settings(database_url: str) -> Settings:
    return Settings.model_validate(
        {
            "DIYU_RUNTIME_MODE": "production",
            "DIYU_APP_DATABASE_URL": database_url,
            "DIYU_SESSION_SECRET": "ui06-api-test-session-secret",
            "DIYU_GENERATOR_MODE": "deepseek",
            "DEEPSEEK_API_BASE_URL": "https://example.invalid",
            "DEEPSEEK_API_KEY": "not-a-real-key",
            "DEEPSEEK_MODEL": "deepseek-test",
            "QWEN_REVIEWER_API_BASE_URL": "https://qwen.example.invalid",
            "DASHSCOPE_API_KEY": "not-a-real-qwen-key",
            "QWEN_REVIEWER_MODEL": "qwen-reviewer-test",
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


def _app(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    def builder(settings: Settings) -> ContentService:
        return ContentService(
            PostgresContentRepository(settings.app_database_url),
            _UI06LifecycleGenerator(),
            build_content_control_service(settings),
        )

    monkeypatch.setattr(
        app_module,
        "build_content_service",
        cast(Callable[[Settings], ContentService], builder),
    )
    return app_module.create_app(_settings(database_url))


def _events(
    client: TestClient,
    message: str,
) -> list[dict[str, object]]:
    response = client.post(
        "/api/v1/content/stream",
        json={
            "message": message,
            "conversation": [],
            "publishing_identity_id": str(ACCOUNT_ID),
            "target": "xiaohongshu_graphic",
            "material_ids": [],
        },
    )
    assert response.status_code == 200, response.text
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def _counts(database_url: str) -> dict[str, int]:
    with (
        psycopg.connect(database_url, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true)",
            (str(TENANT_ID),),
        )
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


def _snapshot(database_url: str, task_id: UUID) -> dict[str, object]:
    with (
        psycopg.connect(database_url, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true)",
            (str(TENANT_ID),),
        )
        cursor.execute(
            """
            SELECT content_context_snapshot
              FROM business_tasks
             WHERE tenant_id = %s AND id = %s
            """,
            (TENANT_ID, task_id),
        )
        row = cursor.fetchone()
    assert row is not None
    snapshot = row["content_context_snapshot"]
    assert isinstance(snapshot, dict)
    return cast(dict[str, object], snapshot)


def test_formal_api_g1_to_g7_snapshot_history_and_atomic_failure(
    app_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _CAPTURED_FRAMES.clear()
    _CAPTURED_PLANS.clear()
    _CALLS.update(intake=0, writer=0, reviewer=0)
    auth = ProductionAuthRepository(app_database_url)
    token = auth.create_tenant_session(TenantSession(TENANT_ID, USER_ID, "tenant-user"))
    with TestClient(
        _app(app_database_url, monkeypatch),
        base_url="https://diyuai.cc",
    ) as client:
        client.cookies.set("diyu_session", token)

        before_g1 = _counts(app_database_url)
        g1 = _events(client, _G1)
        assert [event["event"] for event in g1] == ["conversation"]
        assert g1[-1]["kind"] == "chat"
        assert _counts(app_database_url) == before_g1
        assert _CALLS == {"intake": 1, "writer": 0, "reviewer": 0}
        time.sleep(2.05)

        bad_plan_before = _counts(app_database_url)
        bad_plan_calls = dict(_CALLS)
        bad_plan = _events(client, _BAD_PLAN)
        assert bad_plan[-1]["event"] == "failed"
        assert _counts(app_database_url) == bad_plan_before
        assert _CALLS["intake"] == bad_plan_calls["intake"] + 1
        assert _CALLS["writer"] == bad_plan_calls["writer"]
        assert _CALLS["reviewer"] == bad_plan_calls["reviewer"]
        time.sleep(2.05)

        task_ids: dict[str, UUID] = {}
        g4_body = ""
        for card, message in (
            ("G2", _G2),
            ("G3", _G3),
            ("G4", _G4),
            ("G5", _G5),
        ):
            events = _events(client, message)
            assert events[-1]["event"] == "completed", (card, events)
            result = cast(dict[str, object], events[-1]["result"])
            assert result["version"] == 1
            task_ids[card] = UUID(str(result["task_id"]))
            if card == "G4":
                g4_body = str(result["body"])
            time.sleep(2.05)
        assert _G4_FACT in g4_body
        g3_snapshot = _snapshot(app_database_url, task_ids["G3"])
        g3_kernel = g3_snapshot["creative_kernel_v2"]
        assert isinstance(g3_kernel, dict)
        assert g3_kernel["program_id"] == "observation_with_hypothetical_example_v2"

        g6_before = _counts(app_database_url)
        g6 = _events(client, _G6)
        assert g6[-1]["kind"] == "question"
        assert _counts(app_database_url) == g6_before
        time.sleep(2.05)

        g4_task_id = task_ids["G4"]
        snapshot = _snapshot(app_database_url, g4_task_id)
        frame = snapshot["narrative_frame"]
        assert isinstance(frame, dict)
        assert frame["frame_version"] == "narrative-frame-v1"
        assert frame["narrative_mode"] == "actuality_reflection"
        assert frame["user_facts"] == [
            {
                "source_id": "source:user_actuality:1",
                "exact_text": _G4_FACT,
            }
        ]
        assert frame["allowed_brand_fact_ids"] == []
        assert snapshot["creation_commitment"] == {
            "gate_version": "creation-intent-gate-v1",
            "disposition": "committed",
            "source": "explicit_text",
            "creation_kind": "new_content",
            "source_turn": 0,
            "intent_span": "帮我发条小红书",
        }
        assert snapshot["speaker_kind"] == "institutional_account"
        plan = snapshot["creative_plan_v2"]
        assert isinstance(plan, dict)
        assert plan["plan_version"] == "creative-plan-v2"
        assert "system_creative_plan" not in snapshot
        kernel_v1 = snapshot["creative_kernel_v2"]
        assert isinstance(kernel_v1, dict)
        assert kernel_v1["kernel_version"] == "creative-kernel-v2"
        assert kernel_v1["program_id"] == "observation_only_v1"
        assert snapshot["delivery_compiler_version"] == "delivery-compiler-v2"
        assert snapshot["version_authorization"] == "deterministic-dual-track-v1"
        assert "review_evidence_version" not in snapshot
        assert isinstance(snapshot["reviewed_kernel_digest"], str)
        assert isinstance(snapshot["visible_provenance"], dict)

        forbidden_frame_change = client.post(
            f"/api/v1/tasks/{g4_task_id}/revisions",
            json={
                "instruction": _G7,
                "publishing_identity_id": str(ACCOUNT_ID),
                "target": "xiaohongshu_graphic",
                "source_target": "xiaohongshu_graphic",
                "narrative_frame": {
                    "narrative_mode": "dramatization",
                },
            },
        )
        assert forbidden_frame_change.status_code == 422

        revision = client.post(
            f"/api/v1/tasks/{g4_task_id}/revisions",
            json={
                "instruction": _G7,
                "publishing_identity_id": str(ACCOUNT_ID),
                "target": "xiaohongshu_graphic",
                "source_target": "xiaohongshu_graphic",
            },
        )
        assert revision.status_code == 201, revision.text
        v2 = revision.json()
        assert v2["version"] == 2
        assert _G4_FACT in v2["body"]
        assert "按你的修改要求改变了允许调整的表达" in v2["body"]
        assert len(_CAPTURED_FRAMES) >= 2
        assert frame_document(_CAPTURED_FRAMES[-1]) == frame
        assert len(_CAPTURED_PLANS) >= 5
        assert _CAPTURED_PLANS[-1] == _CAPTURED_PLANS[2]
        revised_snapshot = _snapshot(app_database_url, g4_task_id)
        assert revised_snapshot["narrative_frame"] == snapshot["narrative_frame"]
        assert revised_snapshot["creative_plan_v2"] == snapshot["creative_plan_v2"]
        assert revised_snapshot["creation_commitment"] == snapshot["creation_commitment"]
        assert revised_snapshot["delivery_compiler_version"] == snapshot["delivery_compiler_version"]
        assert revised_snapshot["version_authorization"] == snapshot["version_authorization"]
        assert revised_snapshot["speaker_kind"] == snapshot["speaker_kind"]
        revised_kernel = revised_snapshot["creative_kernel_v2"]
        assert isinstance(revised_kernel, dict)
        assert revised_kernel != kernel_v1
        assert revised_kernel["program_id"] == "actuality_with_disclosed_dramatization_v1"
        original_units = kernel_v1["units"]
        revised_units = revised_kernel["units"]
        assert isinstance(original_units, list)
        assert isinstance(revised_units, list)
        original_fact_units = [
            unit for unit in original_units if isinstance(unit, dict) and unit.get("purpose") == "frozen_fact"
        ]
        revised_fact_units = [
            unit for unit in revised_units if isinstance(unit, dict) and unit.get("purpose") == "frozen_fact"
        ]
        assert original_fact_units == revised_fact_units

        v1 = client.get(
            f"/api/v1/tasks/{g4_task_id}/versions/1",
            params={
                "target": "xiaohongshu_graphic",
                "publishing_identity_id": str(ACCOUNT_ID),
            },
        )
        assert v1.status_code == 200
        assert v1.json()["version"] == 1
        assert "按你的修改要求改变了允许调整的表达" not in v1.json()["body"]
        current = client.get(
            f"/api/v1/tasks/{g4_task_id}/versions/2",
            params={
                "target": "xiaohongshu_graphic",
                "publishing_identity_id": str(ACCOUNT_ID),
            },
        )
        assert current.status_code == 200
        assert current.json()["version"] == 2

        time.sleep(2.05)
        failure_before = _counts(app_database_url)
        failure = _events(client, "请生成一篇内容，验证一次失败原子性。")
        assert failure[-1]["event"] == "failed"
        failure_after = _counts(app_database_url)
        assert failure_after == {
            "tasks": failure_before["tasks"] + 1,
            "runs": failure_before["runs"] + 1,
            "running": failure_before["running"],
            "failed": failure_before["failed"] + 1,
            "versions": failure_before["versions"],
        }
        assert _CALLS["reviewer"] == 0
