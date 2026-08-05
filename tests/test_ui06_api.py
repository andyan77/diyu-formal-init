from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import replace
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
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.production_auth import ProductionAuthRepository, TenantSession
from src.infrastructure.seed_demo import (
    ACCOUNT_ID,
    BRAND_ID,
    TENANT_ID,
    USER_ID,
)
from src.shared.creative_plan import (
    ACCOUNT_BASELINE_TONE_ID,
    build_creative_plan,
)
from src.shared.errors import DomainError, GenerationFailed
from src.shared.narrative import NarrativeFrame, frame_document, visible_digest
from src.shared.publication_contract import IntakeSpanRole
from src.shared.types import (
    ConversationDecision,
    ConversationInput,
    GeneratedArtifact,
    GenerationInput,
    TrustedScope,
)
from src.tool.llm_gateway.stub import DeterministicContentGenerator

_G1 = "今天有点不知道从哪儿开始。"
_G2 = "ZX-C218，帮我生成一篇小红书文案。"
_G3 = "帮我写条婆媳主题的小红书，别狗血，也不要把任何一方写成反派。"
_G4 = "今天店里忙了一天，回家还因为谁洗碗拌了两句。帮我发条小红书。"
_G4_FACT = "今天店里忙了一天，回家还因为谁洗碗拌了两句。"
_G4_FACT_SPANS = ("今天店里忙了一天，", "回家还因为谁洗碗拌了两句。")
_G5 = "今天不知道发什么，帮我做条小红书。"
_G6 = "把我去年创业最困难的那个月写出来。"
_G7 = "别讲道理，荒诞一点。"
_BAD_PLAN = "帮我生成一篇关系文案。"
_MALICIOUS_FACT_SLICE = "我没有和婆婆吵架。帮我发条小红书。"
_FACTORY_ACTUALITY = "今天去工厂验厂，今年量装大货的车缝品质有了大幅度的提升"
_FACTORY_FACT_SPANS = (
    "今天去工厂验厂，",
    "今年量装大货的车缝品质有了大幅度的提升",
)
_UNSUPPORTED_BRAND_GUARANTEE = "笛语已经正式保证今年所有产品车缝品质大幅提升"
_UNREGISTERED_SKU_CLAIM = "请写 ZX-NOT-REGISTERED 的车缝品质已经大幅提升"
_RETRYABLE_REVISION = "保留原判断，把结尾改得更克制。"
_UNCHANGED_REVISION = "受控测试：原样返回不得创建新版本。"

_CAPTURED_FRAMES: list[NarrativeFrame] = []
_CAPTURED_PLANS: list[object] = []
_CALLS = {"intake": 0, "writer": 0, "reviewer": 0}
_FAILED_ONCE: set[str] = set()
_FIRST_ARTIFACTS: dict[UUID, GeneratedArtifact] = {}


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
                "ready",
                "模型错误地认为可以直接泛化这段个人经历。",
                user_premises=(request.message,),
                narrative_mode="general_observation",
                creative_plan=cast(Any, _plan(request, "brand_life_narrative")),
                primary_product="brand_life_narrative",
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
        if request.message == _MALICIOUS_FACT_SLICE:
            return ConversationDecision(
                "ready",
                "模型试图截断否定语义。",
                user_premises=(request.message,),
                user_fact_spans=("和婆婆吵架。",),
                user_fact_source_ids=(request.user_fact_candidates[0].source_id,),
                narrative_mode="actuality_reflection",
                creative_plan=cast(Any, _plan(request, "brand_life_narrative")),
                primary_product="brand_life_narrative",
            )
        selected_facts = tuple(
            candidate
            for candidate in request.user_fact_candidates
            if (request.message == _G4 and candidate.exact_text in _G4_FACT_SPANS)
            or (request.message == _FACTORY_ACTUALITY and candidate.exact_text in _FACTORY_FACT_SPANS)
            or request.message == _UNSUPPORTED_BRAND_GUARANTEE
        )
        fact_spans = tuple(candidate.exact_text for candidate in selected_facts)
        span_roles: tuple[tuple[str, IntakeSpanRole], ...] = tuple(
            (
                candidate.source_id,
                "observable_actuality" if candidate in selected_facts else "creation_instruction",
            )
            for candidate in request.user_fact_candidates
        )
        product = (
            "product_truth"
            if request.message in {_G2, _FACTORY_ACTUALITY, _UNREGISTERED_SKU_CLAIM}
            else "brand_life_narrative"
        )
        claim_scope = (
            "task_actuality"
            if request.message == _FACTORY_ACTUALITY
            else "institutional_claim"
            if request.message == _UNSUPPORTED_BRAND_GUARANTEE
            else "specific_product_claim"
            if request.message == _UNREGISTERED_SKU_CLAIM
            else None
        )
        return ConversationDecision(
            "ready",
            "可以，我直接完成。",
            user_premises=(request.message,),
            user_fact_spans=fact_spans,
            user_fact_source_ids=tuple(candidate.source_id for candidate in selected_facts),
            user_span_roles=span_roles,
            claim_scope=cast(Any, claim_scope),
            narrative_mode=(
                "actuality_reflection" if fact_spans else request.explicit_narrative_mode or "general_observation"
            ),
            creative_plan=cast(
                Any,
                _plan(
                    request,
                    product,
                ),
            ),
            primary_product=cast(Any, product),
        )

    def generate(self, request: GenerationInput) -> GeneratedArtifact:
        _CALLS["writer"] += 1
        if request.revision_instruction == _UNCHANGED_REVISION:
            return _FIRST_ARTIFACTS[request.task_id]
        if "验证一次失败原子性" in request.weak_seed:
            raise GenerationFailed("受控失败")
        if "验证同一请求失败后安全重试" in request.weak_seed and request.weak_seed not in _FAILED_ONCE:
            _FAILED_ONCE.add(request.weak_seed)
            raise GenerationFailed(
                "受控可重试失败",
                error_code="PROVIDER_UNAVAILABLE",
                failure_stage="provider",
                retryable=True,
            )
        if request.revision_instruction == _RETRYABLE_REVISION and _RETRYABLE_REVISION not in _FAILED_ONCE:
            _FAILED_ONCE.add(_RETRYABLE_REVISION)
            raise GenerationFailed(
                "受控修改可重试失败",
                error_code="PROVIDER_UNAVAILABLE",
                failure_stage="provider",
                retryable=True,
            )
        assert request.narrative_frame is not None
        _CAPTURED_FRAMES.append(request.narrative_frame)
        _CAPTURED_PLANS.append(request.creative_plan)
        # The deterministic stub otherwise emits one generic revision suffix
        # for every instruction. Keep this idempotency fixture visibly distinct
        # from its parent without changing production revision semantics.
        generated_request = (
            replace(request, revision_instruction=None)
            if request.revision_instruction == _RETRYABLE_REVISION
            else request
        )
        artifact = super().generate(generated_request)
        if request.revision_instruction is None:
            _FIRST_ARTIFACTS[request.task_id] = artifact
        return artifact


def _settings(database_url: str) -> Settings:
    return Settings.model_validate(
        {
            "DIYU_RUNTIME_MODE": "production",
            "DIYU_APP_DATABASE_URL": database_url,
            "DIYU_SESSION_SECRET": "ui06-api-test-session-secret",
            "DIYU_PUBLIC_URL": "https://diyuai.cc",
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
    interaction_mode: str = "auto",
    request_id: UUID | None = None,
    conversation: list[dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    response = client.post(
        "/api/v1/content/stream",
        json={
            "message": message,
            "conversation": conversation or [],
            "publishing_identity_id": str(ACCOUNT_ID),
            "target": "xiaohongshu_graphic",
            "material_ids": [],
            "interaction_mode": interaction_mode,
            "request_id": str(request_id) if request_id is not None else None,
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


def _version_audits(database_url: str, task_id: UUID) -> list[dict[str, object]]:
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
            SELECT id, version_number, outline, body, artifact_digest, version_audit_snapshot
              FROM content_versions
             WHERE tenant_id = %s AND task_id = %s
             ORDER BY version_number
            """,
            (TENANT_ID, task_id),
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def _force_version_body_for_integrity_test(
    database_url: str,
    version_id: object,
    body: str,
) -> None:
    """Mutate one test row while guaranteeing the append-only trigger is restored."""

    with (
        psycopg.connect(database_url) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true)",
            (str(TENANT_ID),),
        )
        trigger_disabled = False
        try:
            cursor.execute("ALTER TABLE content_versions DISABLE TRIGGER content_versions_append_only")
            trigger_disabled = True
            with connection.transaction():
                cursor.execute(
                    "UPDATE content_versions SET body = %s WHERE tenant_id = %s AND id = %s",
                    (body, TENANT_ID, version_id),
                )
        finally:
            if trigger_disabled:
                cursor.execute("ALTER TABLE content_versions ENABLE TRIGGER content_versions_append_only")
        cursor.execute(
            """
            SELECT trigger_record.tgenabled
              FROM pg_trigger trigger_record
             WHERE trigger_record.tgrelid = 'content_versions'::regclass
               AND trigger_record.tgname = 'content_versions_append_only'
            """
        )
        assert cursor.fetchone() == ("O",)


def test_factory_actuality_routes_without_product_fact_and_claim_scopes_fail_closed(
    app_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _CAPTURED_FRAMES.clear()
    _CAPTURED_PLANS.clear()
    _FAILED_ONCE.clear()
    _FIRST_ARTIFACTS.clear()
    _CALLS.update(intake=0, writer=0, reviewer=0)
    auth = ProductionAuthRepository(app_database_url)
    token = auth.create_tenant_session(TenantSession(TENANT_ID, USER_ID, "tenant-user"))
    with TestClient(
        _app(app_database_url, monkeypatch),
        base_url="https://diyuai.cc",
    ) as client:
        client.cookies.set("diyu_session", token)
        before = _counts(app_database_url)
        factory = _events(client, _FACTORY_ACTUALITY, "generate")
        assert factory[-1]["event"] == "completed", factory
        result = cast(dict[str, object], factory[-1]["result"])
        after = _counts(app_database_url)
        assert after["tasks"] == before["tasks"] + 1
        assert after["runs"] == before["runs"] + 1
        assert after["versions"] == before["versions"] + 1
        assert after["running"] == 0
        snapshot = _snapshot(app_database_url, UUID(str(result["task_id"])))
        plan = cast(dict[str, object], snapshot["creative_plan_v2"])
        assert plan["primary_value"] == "brand_life_narrative"
        frame = cast(dict[str, object], snapshot["narrative_frame"])
        assert [item["exact_text"] for item in cast(list[dict[str, object]], frame["user_facts"])] == list(
            _FACTORY_FACT_SPANS
        )
        assert frame["allowed_product_fact_ids"] == []
        publication = cast(dict[str, object], snapshot["publication_contract"])
        permission = cast(dict[str, object], publication["account_editorial_permission"])
        assert "已冻结的上位事实允许 Writer 用常识性、非量化、非认证的常见观察维度帮助理解" in str(
            permission["refusals"]
        )
        assert "具体数值或规格、检验结果、认证" in str(permission["refusals"])
        assert "只在本题事实、来源与资源边界内影响怎样表达" in str(permission["response_posture"])

        time.sleep(2.05)
        guarantee_before = _counts(app_database_url)
        guarantee = _events(client, _UNSUPPORTED_BRAND_GUARANTEE, "generate")
        assert guarantee[-1]["event"] == "conversation"
        assert guarantee[-1]["kind"] == "question"
        assert "已确认机构来源" in str(guarantee[-1]["message"])
        assert _counts(app_database_url) == guarantee_before

        time.sleep(2.05)
        sku_before = _counts(app_database_url)
        sku = _events(client, _UNREGISTERED_SKU_CLAIM, "generate")
        assert sku[-1]["event"] == "conversation"
        assert sku[-1]["kind"] == "question"
        assert "ProductFact" in str(sku[-1]["message"])
        assert _counts(app_database_url) == sku_before


def test_send_then_generate_same_actuality_freezes_each_statement_once(
    app_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _CAPTURED_FRAMES.clear()
    _CAPTURED_PLANS.clear()
    _FAILED_ONCE.clear()
    _CALLS.update(intake=0, writer=0, reviewer=0)
    auth = ProductionAuthRepository(app_database_url)
    token = auth.create_tenant_session(TenantSession(TENANT_ID, USER_ID, "tenant-user"))
    with TestClient(
        _app(app_database_url, monkeypatch),
        base_url="https://diyuai.cc",
    ) as client:
        client.cookies.set("diyu_session", token)
        before = _counts(app_database_url)
        sent = _events(client, _FACTORY_ACTUALITY, "conversation")
        assert sent[-1]["event"] == "conversation"
        assert _counts(app_database_url) == before
        assistant_message = str(sent[-1]["message"])
        time.sleep(2.05)
        generated = _events(
            client,
            _FACTORY_ACTUALITY,
            "generate",
            conversation=[
                {"role": "user", "content": _FACTORY_ACTUALITY},
                {"role": "assistant", "content": assistant_message},
            ],
        )
        assert generated[-1]["event"] == "completed"
        result = cast(dict[str, object], generated[-1]["result"])
        snapshot = _snapshot(app_database_url, UUID(str(result["task_id"])))
        frame = cast(dict[str, object], snapshot["narrative_frame"])
        assert [item["exact_text"] for item in cast(list[dict[str, object]], frame["user_facts"])] == list(
            _FACTORY_FACT_SPANS
        )


def test_formal_api_g1_to_g7_snapshot_history_and_atomic_failure(
    app_database_url: str,
    migrator_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _CAPTURED_FRAMES.clear()
    _CAPTURED_PLANS.clear()
    _FAILED_ONCE.clear()
    _FIRST_ARTIFACTS.clear()
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
        assert _CALLS == {"intake": 0, "writer": 0, "reviewer": 0}
        time.sleep(2.05)

        conversation_before = _counts(app_database_url)
        conversation = _events(client, _G3, "conversation")
        assert [event["event"] for event in conversation] == ["conversation"]
        assert _counts(app_database_url) == conversation_before
        assert _CALLS["writer"] == 0
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

        malicious_fact_before = _counts(app_database_url)
        malicious_fact_calls = dict(_CALLS)
        malicious_fact = _events(client, _MALICIOUS_FACT_SLICE)
        assert malicious_fact[-1]["event"] == "failed"
        assert _counts(app_database_url) == malicious_fact_before
        assert _CALLS["intake"] == malicious_fact_calls["intake"] + 1
        assert _CALLS["writer"] == malicious_fact_calls["writer"]
        assert _CALLS["reviewer"] == malicious_fact_calls["reviewer"]
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
        assert all(fact_span in g4_body for fact_span in _G4_FACT_SPANS)
        g3_snapshot = _snapshot(app_database_url, task_ids["G3"])
        g3_kernel = g3_snapshot["creative_kernel_v5"]
        assert isinstance(g3_kernel, dict)
        assert g3_kernel["media_program_id"] == "graphic_observation_progression_v1"

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
        assert isinstance(frame["user_facts"], list)
        assert len(frame["user_facts"]) == 2
        assert [fact["exact_text"] for fact in frame["user_facts"]] == list(_G4_FACT_SPANS)
        assert str(frame["user_facts"][0]["source_id"]).startswith("source:user_actuality:turn-1:clause-1:")
        assert str(frame["user_facts"][1]["source_id"]).startswith("source:user_actuality:turn-1:clause-2:")
        publication_contract = snapshot["publication_contract"]
        assert isinstance(publication_contract, dict)
        assert [span["role"] for span in publication_contract["input_roles"]] == [
            "observable_actuality",
            "observable_actuality",
            "creation_instruction",
        ]
        assert [
            span["exact_text"] for span in publication_contract["input_roles"] if span["role"] == "observable_actuality"
        ] == list(_G4_FACT_SPANS)
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
        assert plan["plan_version"] == "creative-plan-v3"
        assert plan["topic_origin"] == "explicit_user"
        assert "system_creative_plan" not in snapshot
        kernel_v1 = snapshot["creative_kernel_v5"]
        assert isinstance(kernel_v1, dict)
        assert kernel_v1["kernel_version"] == "creative-kernel-v5"
        assert kernel_v1["media_program_id"] == "graphic_fact_guided_v1"
        assert snapshot["delivery_compiler_version"] == "delivery-compiler-v5"
        assert snapshot["version_authorization"] == "deterministic-publication-v3"
        assert "review_evidence_version" not in snapshot
        assert isinstance(snapshot["deterministic_checked_kernel_digest"], str)
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

        unchanged_before = _counts(app_database_url)
        unchanged = client.post(
            f"/api/v1/tasks/{g4_task_id}/revisions",
            json={
                "instruction": _UNCHANGED_REVISION,
                "publishing_identity_id": str(ACCOUNT_ID),
                "target": "xiaohongshu_graphic",
                "source_target": "xiaohongshu_graphic",
                "request_id": str(uuid4()),
            },
        )
        assert unchanged.status_code == 422, unchanged.text
        assert unchanged.json()["error_code"] == "REVISION_UNCHANGED"
        assert unchanged.json()["failure_stage"] == "validation"
        assert unchanged.json()["retryable"] is False
        unchanged_after = _counts(app_database_url)
        assert unchanged_after == {
            "tasks": unchanged_before["tasks"],
            "runs": unchanged_before["runs"] + 1,
            "running": unchanged_before["running"],
            "failed": unchanged_before["failed"] + 1,
            "versions": unchanged_before["versions"],
        }
        assert _snapshot(app_database_url, g4_task_id) == snapshot
        time.sleep(2.05)

        revision_request_id = uuid4()
        revision = client.post(
            f"/api/v1/tasks/{g4_task_id}/revisions",
            json={
                "instruction": _G7,
                "publishing_identity_id": str(ACCOUNT_ID),
                "target": "xiaohongshu_graphic",
                "source_target": "xiaohongshu_graphic",
                "request_id": str(revision_request_id),
            },
        )
        assert revision.status_code == 201, revision.text
        v2 = revision.json()
        assert v2["version"] == 2
        assert all(fact_span in v2["body"] for fact_span in _G4_FACT_SPANS)
        assert v2["body"] != g4_body
        revision_counts = _counts(app_database_url)
        revision_calls = dict(_CALLS)
        replayed_revision = client.post(
            f"/api/v1/tasks/{g4_task_id}/revisions",
            json={
                "instruction": _G7,
                "publishing_identity_id": str(ACCOUNT_ID),
                "target": "xiaohongshu_graphic",
                "source_target": "xiaohongshu_graphic",
                "request_id": str(revision_request_id),
            },
        )
        assert replayed_revision.status_code == 201
        assert replayed_revision.json()["version_id"] == v2["version_id"]
        assert _counts(app_database_url) == revision_counts
        assert revision_calls == _CALLS

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
        revised_kernel = revised_snapshot["creative_kernel_v5"]
        assert isinstance(revised_kernel, dict)
        assert revised_kernel != kernel_v1
        assert revised_kernel["media_program_id"] == kernel_v1["media_program_id"]
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
        assert "情景演绎" not in v1.json()["body"]
        current = client.get(
            f"/api/v1/tasks/{g4_task_id}/versions/2",
            params={
                "target": "xiaohongshu_graphic",
                "publishing_identity_id": str(ACCOUNT_ID),
            },
        )
        assert current.status_code == 200
        assert current.json()["version"] == 2
        history = client.get(
            f"/api/v1/content/tasks/{g4_task_id}/versions",
            params={
                "target": "xiaohongshu_graphic",
                "publishing_identity_id": str(ACCOUNT_ID),
            },
        )
        assert history.status_code == 200
        history_versions = history.json()
        assert [item["version"] for item in history_versions] == [2, 1]
        assert history_versions[0]["body"] == current.json()["body"]
        assert history_versions[1]["body"] == v1.json()["body"]
        audits = _version_audits(app_database_url, g4_task_id)
        assert [audit["version_number"] for audit in audits] == [1, 2]
        for audit in audits:
            version_audit = audit["version_audit_snapshot"]
            assert isinstance(version_audit, dict)
            assert version_audit["audit_version"] == "content-version-audit-v3"
            assert version_audit["visible_projection"] == "delivery-compiler-v3-final-visible-v1"
            assert version_audit["artifact_digest"] == audit["artifact_digest"]
            assert audit["artifact_digest"] == visible_digest(
                str(audit["outline"]),
                str(audit["body"]),
            )
            assert version_audit["narrative_frame"] == snapshot["narrative_frame"]
            assert version_audit["creative_plan_v2"] == snapshot["creative_plan_v2"]
            assert version_audit["delivery_compiler_version"] == snapshot["delivery_compiler_version"]
        v1_audit = cast(dict[str, object], audits[0]["version_audit_snapshot"])
        v2_audit = cast(dict[str, object], audits[1]["version_audit_snapshot"])
        assert v1_audit["creative_kernel_v5"] == kernel_v1
        assert v2_audit["creative_kernel_v5"] == revised_kernel
        assert v1_audit["narrative_frame"] == v2_audit["narrative_frame"]
        with (
            psycopg.connect(app_database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                (str(TENANT_ID),),
            )
            for column, value in (
                ("body", "被篡改的正文"),
                ("outline", "被篡改的标题"),
                ("product_contract", "{}"),
                ("artifact_digest", "0" * 64),
                ("version_audit_snapshot", "{}"),
            ):
                connection.rollback()
                cursor.execute(
                    "SELECT set_config('app.tenant_id', %s, true)",
                    (str(TENANT_ID),),
                )
                with pytest.raises(psycopg.Error):
                    cursor.execute(
                        f"UPDATE content_versions SET {column} = %s WHERE tenant_id = %s AND id = %s",
                        (value, TENANT_ID, audits[0]["id"]),
                    )

        with (
            psycopg.connect(migrator_database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                (str(TENANT_ID),),
            )
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="content versions are append-only",
            ):
                cursor.execute(
                    "UPDATE content_versions SET body = %s WHERE tenant_id = %s AND id = %s",
                    ("数据库管理员也不能改写版本正文", TENANT_ID, audits[0]["id"]),
                )

        original_body = str(audits[0]["body"])
        task_account_id: UUID
        with (
            psycopg.connect(migrator_database_url) as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                (str(TENANT_ID),),
            )
            cursor.execute(
                "SELECT account_id FROM business_tasks WHERE tenant_id = %s AND id = %s",
                (TENANT_ID, g4_task_id),
            )
            task_row = cursor.fetchone()
            assert task_row is not None
            task_account_id = UUID(str(task_row["account_id"]))
        _force_version_body_for_integrity_test(
            migrator_database_url,
            audits[0]["id"],
            "人为构造的摘要不一致正文",
        )
        try:
            repository = PostgresContentRepository(app_database_url)
            with pytest.raises(DomainError, match="完整性校验失败"):
                repository.fetch_version(
                    TrustedScope(TENANT_ID, USER_ID, BRAND_ID, task_account_id),
                    g4_task_id,
                    1,
                )
        finally:
            _force_version_body_for_integrity_test(
                migrator_database_url,
                audits[0]["id"],
                original_body,
            )

        time.sleep(2.05)
        failed_revision_request_id = uuid4()
        failed_revision_before = _counts(app_database_url)
        failed_revision = client.post(
            f"/api/v1/tasks/{g4_task_id}/revisions",
            json={
                "instruction": _RETRYABLE_REVISION,
                "publishing_identity_id": str(ACCOUNT_ID),
                "target": "xiaohongshu_graphic",
                "source_target": "xiaohongshu_graphic",
                "request_id": str(failed_revision_request_id),
            },
        )
        assert failed_revision.status_code == 503
        assert failed_revision.json()["error_code"] == "PROVIDER_UNAVAILABLE"
        after_failed_revision = _counts(app_database_url)
        assert after_failed_revision == {
            "tasks": failed_revision_before["tasks"],
            "runs": failed_revision_before["runs"] + 1,
            "running": failed_revision_before["running"],
            "failed": failed_revision_before["failed"] + 1,
            "versions": failed_revision_before["versions"],
        }
        time.sleep(2.05)
        changed_retry = client.post(
            f"/api/v1/tasks/{g4_task_id}/revisions",
            json={
                "instruction": "偷换后的修改要求不得复用旧请求。",
                "publishing_identity_id": str(ACCOUNT_ID),
                "target": "xiaohongshu_graphic",
                "source_target": "xiaohongshu_graphic",
                "request_id": str(failed_revision_request_id),
            },
        )
        assert changed_retry.status_code == 422
        assert changed_retry.json()["error_code"] == "IDEMPOTENCY_CONTEXT_CHANGED"
        assert _counts(app_database_url) == after_failed_revision
        time.sleep(2.05)
        retried_revision = client.post(
            f"/api/v1/tasks/{g4_task_id}/revisions",
            json={
                "instruction": _RETRYABLE_REVISION,
                "publishing_identity_id": str(ACCOUNT_ID),
                "target": "xiaohongshu_graphic",
                "source_target": "xiaohongshu_graphic",
                "request_id": str(failed_revision_request_id),
            },
        )
        assert retried_revision.status_code == 201, retried_revision.text
        retried_revision_payload = retried_revision.json()
        assert retried_revision_payload["version"] == 3
        after_retried_revision = _counts(app_database_url)
        assert after_retried_revision == {
            "tasks": failed_revision_before["tasks"],
            "runs": failed_revision_before["runs"] + 2,
            "running": failed_revision_before["running"],
            "failed": failed_revision_before["failed"] + 1,
            "versions": failed_revision_before["versions"] + 1,
        }
        time.sleep(2.05)
        replayed_retried_revision = client.post(
            f"/api/v1/tasks/{g4_task_id}/revisions",
            json={
                "instruction": _RETRYABLE_REVISION,
                "publishing_identity_id": str(ACCOUNT_ID),
                "target": "xiaohongshu_graphic",
                "source_target": "xiaohongshu_graphic",
                "request_id": str(failed_revision_request_id),
            },
        )
        assert replayed_retried_revision.status_code == 201
        assert replayed_retried_revision.json()["version_id"] == retried_revision_payload["version_id"]
        assert _counts(app_database_url) == after_retried_revision

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

        time.sleep(2.05)
        retry_seed = "请生成一篇内容，验证同一请求失败后安全重试。"
        retry_request_id = uuid4()
        retry_before = _counts(app_database_url)
        first_attempt = _events(client, retry_seed, "generate", retry_request_id)
        assert first_attempt[-1]["event"] == "failed"
        assert first_attempt[-1]["error_code"] == "PROVIDER_UNAVAILABLE"
        after_failed_attempt = _counts(app_database_url)
        assert after_failed_attempt == {
            "tasks": retry_before["tasks"] + 1,
            "runs": retry_before["runs"] + 1,
            "running": retry_before["running"],
            "failed": retry_before["failed"] + 1,
            "versions": retry_before["versions"],
        }
        time.sleep(2.05)
        retried = _events(client, retry_seed, "generate", retry_request_id)
        assert retried[-1]["event"] == "completed"
        after_retry = _counts(app_database_url)
        assert after_retry == {
            "tasks": retry_before["tasks"] + 1,
            "runs": retry_before["runs"] + 2,
            "running": retry_before["running"],
            "failed": retry_before["failed"] + 1,
            "versions": retry_before["versions"] + 1,
        }
        replayed_retry = _events(client, retry_seed, "generate", retry_request_id)
        assert replayed_retry[-1]["event"] == "completed"
        assert _counts(app_database_url) == after_retry

        time.sleep(2.05)
        idempotency_key = uuid4()
        first_idempotent = _events(client, _G3, "generate", idempotency_key)
        assert first_idempotent[-1]["event"] == "completed"
        first_result = cast(dict[str, object], first_idempotent[-1]["result"])
        idempotent_counts = _counts(app_database_url)
        idempotent_calls = dict(_CALLS)
        replayed = _events(client, _G3, "generate", idempotency_key)
        replayed_result = cast(dict[str, object], replayed[-1]["result"])
        assert replayed_result["version_id"] == first_result["version_id"]
        assert replayed_result["outline"] == first_result["outline"]
        assert replayed_result["body"] == first_result["body"]
        assert _counts(app_database_url) == idempotent_counts
        assert idempotent_calls == _CALLS
