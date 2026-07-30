from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import src.infrastructure.postgres_repository as repository_module
from src.brain.content_expression import (
    direction_from_snapshot,
    snapshot_document,
)
from src.brain.p1_contract import assert_content_complete
from src.brain.platform_directions import direction_for
from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.seed_demo import (
    ACCOUNT_ID,
    BRAND_ID,
    TENANT_ID,
    USER_ID,
)
from src.shared.creative_kernel import (
    KERNEL_VERSION,
    CreativeKernelV1,
    build_kernel_skeleton,
    parse_writer_kernel,
    select_kernel_program,
)
from src.shared.creative_plan import (
    ACCOUNT_BASELINE_TONE_ID,
    build_creative_plan,
)
from src.shared.delivery_compiler import (
    CREATOR_EXPRESSION_RESOURCE_ID,
    DELIVERY_COMPILER_VERSION,
    ORIGINAL_COMPOSITION_RESOURCE_ID,
    DeliveryCompileInput,
    compile_delivery,
    compiler_owned_media_unit_texts,
)
from src.shared.errors import DomainError
from src.shared.narrative import new_frame, visible_digest
from src.shared.types import (
    AccountExpression,
    BrandContext,
    ContentControlContext,
    CreativeDirection,
    DirectionSelection,
    GeneratedArtifact,
    GenerationInput,
    GraphicProductionBundle,
    RequestedControls,
    SeriesContext,
    SeriesEntry,
    VideoProductionBundle,
)
from src.tool.llm_gateway.deepseek import BoundaryContext, DeepSeekGenerator
from src.tool.llm_gateway.stub import DeterministicContentGenerator
from tests.test_ui05_semantic_rework import (
    _app,
    _conversation_payload,
    _persistence_counts,
    _session_token,
    _stream_events,
)

_RUN_ID = UUID("83000000-0000-0000-0000-000000000001")
_TASK_ID = UUID("83000000-0000-0000-0000-000000000002")
_RESOURCES = frozenset(
    {
        ORIGINAL_COMPOSITION_RESOURCE_ID,
        CREATOR_EXPRESSION_RESOURCE_ID,
    }
)


def _brand(*, account_name: str = "门店生活观察账号") -> BrandContext:
    return BrandContext(
        brand_name="测试品牌",
        positioning="尊重真实处境，也给人可执行的选择",
        decision_order="先说清边界，再给出选择",
        tone="自然、克制、有一点冷幽默",
        account_name=account_name,
        operator_name="当前运营者",
        organization_name="当前门店",
        content_role_name="门店生活观察者",
        content_role_boundary="只表达一般观察，不冒充顾客或门店历史。",
        audience_description="希望在忙碌日常里得到一个清楚观察的人",
        strategy_version="brand-expression-v1",
        platform="小红书",
        media_format="图文",
        production_conditions="一人一部手机，普通室内环境。",
    )


def _direction() -> CreativeDirection:
    return CreativeDirection(
        catalog_version="content-expression-catalog-v1",
        selections=(
            DirectionSelection(
                "topic",
                "CAT-TOPIC-RELATION-01",
                "婆媳",
                "婆媳",
                False,
                "",
                "explicit",
            ),
            DirectionSelection(
                "style",
                "CAT-STYLE-HUMOUR-01",
                "克制的冷幽默",
                "克制的冷幽默",
                False,
                "",
                "saved_default",
            ),
        ),
        custom_text="不把任何一方写成反派",
        body_related_opt_in=True,
        translation_notice=None,
        cleared_axes=("form",),
    )


def _series_context() -> SeriesContext:
    return SeriesContext(
        series_id=UUID("83000000-0000-0000-0000-000000000010"),
        revision=2,
        title="把空间留给人的三篇观察",
        premise="每篇从一个不同停顿继续。",
        target_position=3,
        prior_entries=(
            SeriesEntry(
                UUID("83000000-0000-0000-0000-000000000011"),
                UUID("83000000-0000-0000-0000-000000000012"),
                1,
                1,
                "第一篇：先允许沉默",
                "第一篇完整正文：不是每次停顿都需要立刻解释。",
            ),
            SeriesEntry(
                UUID("83000000-0000-0000-0000-000000000013"),
                UUID("83000000-0000-0000-0000-000000000014"),
                1,
                2,
                "第二篇：把选择留在原处",
                "第二篇完整正文：不催促，也是一种清楚回应。",
            ),
        ),
    )


def _generation_input(
    *,
    media_format: str = "graphic",
    series_context: SeriesContext | None = None,
    creative_direction: CreativeDirection | None = None,
) -> GenerationInput:
    target = (
        "xiaohongshu_graphic"
        if media_format == "graphic"
        else "douyin_video"
    )
    frame = new_frame("general_observation", (), ())
    return GenerationInput(
        run_id=_RUN_ID,
        task_id=_TASK_ID,
        weak_seed="今天喝了一直喝的蓝山咖啡，居然是甜的，帮我发一条。",
        primary_product="brand_life_narrative",
        revision_instruction=None,
        brand=replace(
            _brand(),
            platform=("小红书" if media_format == "graphic" else "抖音"),
            media_format=("图文" if media_format == "graphic" else "视频"),
        ),
        target=cast(Any, target),
        media_format=cast(Any, media_format),
        platform_direction=direction_for(cast(Any, target)),
        creative_direction=creative_direction,
        account_expression=AccountExpression(
            UUID("83000000-0000-0000-0000-000000000020"),
            3,
            "门店生活观察者",
            "不冒充顾客、总部或真实经历。",
            "把空间留给想按自己节奏看的人。",
            "门店日常、穿衣选择和关系里的停顿。",
            "一人一部手机，普通室内环境。",
            False,
        ),
        series_context=series_context,
        narrative_frame=frame,
        creative_plan=build_creative_plan(
            topic_spans=("今天喝了一直喝的蓝山咖啡，居然是甜的",),
            primary_value="brand_life_narrative",
            tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
            mechanism_id=None,
            target_shape="小红书图文完整成品",
        ),
        delivery_compiler_version=DELIVERY_COMPILER_VERSION,
    )


def _filled_kernel(request: GenerationInput) -> object:
    assert request.narrative_frame is not None
    context = BoundaryContext.from_request(request, request.narrative_frame)
    skeleton = build_kernel_skeleton(
        frame=request.narrative_frame,
        fact_registry=context.fact_registry,
        constraint_refs=tuple(
            identifier for identifier, _ in context.constraint_registry
        ),
        program_id=select_kernel_program(frame=request.narrative_frame),
        allowed_resource_ids=tuple(sorted(_RESOURCES)),
        media_format=request.media_format,
        kernel_version=KERNEL_VERSION,
    )
    compiler_texts = compiler_owned_media_unit_texts(
        DeliveryCompileInput(
            primary_product=request.primary_product,
            media_format=request.media_format,
            products=(),
            production_conditions=request.brand.production_conditions,
            allowed_resource_ids=_RESOURCES,
        )
    )
    text_by_purpose = {
        "title": "甜味把熟悉的一天叫醒了",
        "natural_guide": "看一次熟悉感被意外打断后，人会怎样重新注意日常。",
        "media_opening": "首图只放咖啡杯边缘和一句“今天怎么是甜的？”",
        "media_sequence": "第一张给意外，第二张拆开熟悉感，第三张留下一次重新注意。",
        "subtitle_strategy": "只保留“熟悉”和“重新注意”两个转折，不复写整段台词。",
        "production_note": "用本次登记的手机和普通室内光线，保留杯子落桌的自然声音。",
        "body": "一直喝的味道突然变甜，最先被打断的不是判断，而是那种不用再看一眼的熟悉。偶尔被日常叫醒一下，也会重新发现自己究竟在意什么。",
        "release_caption": "熟悉的东西突然变了一点，你会先怀疑味道，还是先重新看它一眼？",
    }
    raw = {
        "units": [
            {
                "unit_id": unit.unit_id,
                "text": text_by_purpose[unit.purpose],
            }
            for unit in skeleton.writable_units
            if unit.unit_id not in compiler_texts
        ]
    }
    return parse_writer_kernel(
        raw,
        skeleton,
        compiler_owned_text_by_id=compiler_texts,
    )


def test_media_native_units_compile_one_scope_and_distinct_platform_parts() -> None:
    request = _generation_input(media_format="video")
    kernel = _filled_kernel(request)
    compiled = compile_delivery(
        DeliveryCompileInput(
            primary_product=request.primary_product,
            media_format=request.media_format,
            products=(),
            production_conditions=request.brand.production_conditions,
            allowed_resource_ids=_RESOURCES,
        ),
        cast(Any, kernel),
    )

    assert compiled.outline == "甜味把熟悉的一天叫醒了"
    assert compiled.body.count("表达范围：") == 1
    assert "从你提供的片段出发" not in compiled.body
    assert "沿着正文主线" not in compiled.body
    assert "你更愿意带走哪一种理解" not in compiled.body
    assert "完整台词/解说：" in compiled.body
    assert "字幕策略：" in compiled.body
    assert isinstance(compiled.production, VideoProductionBundle)
    assert compiled.production.spoken_lines != compiled.production.subtitles
    artifact = GeneratedArtifact(
        outline=compiled.outline,
        body=compiled.body,
        model="deterministic-test",
        latency_ms=0,
        retry_count=0,
        provider_usage=None,
        primary_product=request.primary_product,
        semantic_contract=compiled.semantic_contract,
        production=compiled.production,
        reviewed_digest=visible_digest(compiled.outline, compiled.body),
        completion_snapshot_patch={
            "delivery_compiler_version": DELIVERY_COMPILER_VERSION,
        },
    )
    assert_content_complete(artifact)


def test_actuality_creative_units_are_preallocated_as_disclosed_hypothesis() -> None:
    fact = "今天喝了一直喝的蓝山咖啡，居然是甜的。"
    frame = new_frame("actuality_reflection", (fact,), ())
    request = replace(
        _generation_input(),
        weak_seed=fact + "帮我发一条。",
        narrative_frame=frame,
        creative_plan=build_creative_plan(
            topic_spans=(fact,),
            primary_value="brand_life_narrative",
            tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
            mechanism_id=None,
            target_shape="小红书图文完整成品",
        ),
    )
    kernel = cast(CreativeKernelV1, _filled_kernel(request))

    assert kernel.unit("unit:body").mode == "hypothesis"
    compiled = compile_delivery(
        DeliveryCompileInput(
            primary_product=request.primary_product,
            media_format=request.media_format,
            products=(),
            production_conditions=request.brand.production_conditions,
            allowed_resource_ids=_RESOURCES,
            trusted_fact_texts=(
                (
                    frame.user_facts[0].source_id,
                    fact,
                ),
            ),
        ),
        kernel,
    )

    assert f"你提到：“{fact}”" in compiled.body
    assert compiled.body.count("表达范围：") == 1
    assert (
        "其余是创作性推演，不作为这段经历的事实补充"
        in compiled.body
    )


def test_direction_receipt_freezes_origins_clears_custom_and_body_opt_in() -> None:
    direction = _direction()
    control = ContentControlContext(
        catalog_version=direction.catalog_version,
        direction=direction,
        account_expression=None,
        materials=(),
        preference_mode="preference_applied",
        preference_version=7,
    )
    snapshot = snapshot_document(
        control,
        "门店生活观察者",
    )

    original = cast(dict[str, object], snapshot["original_direction"])
    selections = cast(list[dict[str, object]], original["selections"])
    assert [item["origin"] for item in selections] == [
        "explicit",
        "saved_default",
    ]
    assert original["custom_text"] == "不把任何一方写成反派"
    assert original["cleared_axes"] == ["form"]
    assert original["body_related_opt_in"] is True
    replayed = direction_from_snapshot(snapshot)
    assert replayed == direction


def test_writer_prompt_receives_direction_and_every_frozen_series_entry() -> None:
    request = _generation_input(
        creative_direction=_direction(),
        series_context=_series_context(),
    )
    kernel = _filled_kernel(request)
    prompt = DeepSeekGenerator(
        "https://example.invalid",
        "not-a-real-key",
        "deepseek-test",
    )._kernel_writer_prompt(
        request,
        cast(Any, kernel),
        {},
    )

    assert "婆媳" in prompt
    assert "克制的冷幽默" in prompt
    assert "不把任何一方写成反派" in prompt
    assert "第一篇：先允许沉默" in prompt
    assert "第一篇完整正文" in prompt
    assert "第二篇：把选择留在原处" in prompt
    assert "第二篇完整正文" in prompt
    assert '"position": 1' in prompt
    assert '"position": 2' in prompt
    assert '"unit_contract": "audience_guidance"' in prompt
    assert '"unit_contract": "abstract_observation"' in prompt
    assert '"subject_scope": "generic_only"' in prompt
    assert '"actual_event_or_result"' in prompt
    assert '"resource_id": "resource:original_composition"' in prompt
    assert "不包含现实人物、场地、家具、照片、商品或外部素材" in prompt
    assert '"resource_id": "resource:creator_expression"' in prompt
    assert "其他租户诱饵前情" not in prompt


def test_deepseek_adapter_accepts_only_the_complete_media_native_unit_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _generation_input(
        creative_direction=_direction(),
        series_context=_series_context(),
    )
    kernel = cast(CreativeKernelV1, _filled_kernel(request))
    writer_payload = {
        "units": [
            {
                "unit_id": unit.unit_id,
                "text": unit.text,
            }
            for unit in kernel.writable_units
        ]
    }
    prompts: list[str] = []

    def respond(
        system: str,
        prompt: str,
        max_tokens: int,
        *,
        thinking_disabled: bool = True,
        timeout_seconds: float | None = None,
    ) -> tuple[dict[str, Any], int]:
        del system, max_tokens, thinking_disabled, timeout_seconds
        prompts.append(prompt)
        return (
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                writer_payload,
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 200,
                    "total_tokens": 300,
                },
            },
            0,
        )

    generator = DeepSeekGenerator(
        "https://example.invalid",
        "not-a-real-key",
        "deepseek-test",
    )
    monkeypatch.setattr(generator, "_request", respond)
    artifact = generator.generate(request)

    assert artifact.outline == "甜味把熟悉的一天叫醒了"
    assert artifact.body.count("表达范围：") == 1
    assert artifact.completion_snapshot_patch is not None
    assert (
        artifact.completion_snapshot_patch["delivery_compiler_version"]
        == DELIVERY_COMPILER_VERSION
    )
    assert "第一篇：先允许沉默" in prompts[0]
    assert "不把任何一方写成反派" in prompts[0]


def test_stub_output_changes_with_direction_and_series_without_repeating_body() -> None:
    generator = DeterministicContentGenerator()
    plain = generator.generate(_generation_input())
    directed = generator.generate(
        _generation_input(
            creative_direction=_direction(),
            series_context=_series_context(),
        )
    )

    assert plain.body != directed.body
    assert "克制的冷幽默" in directed.body
    assert "承接上一篇《第二篇：把选择留在原处》" in directed.body
    assert directed.body.count("表达范围：") == 1
    assert isinstance(directed.production, GraphicProductionBundle)
    assert directed.production.full_body != directed.production.image_sequence


def test_three_episode_series_reaches_writer_in_order_and_revision_replays_it(
    app_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[GenerationInput] = []
    original_generate = DeterministicContentGenerator.generate

    def capture(
        self: DeterministicContentGenerator,
        request: GenerationInput,
    ) -> GeneratedArtifact:
        captured.append(request)
        return original_generate(self, request)

    monkeypatch.setattr(
        DeterministicContentGenerator,
        "generate",
        capture,
    )
    settings = Settings.model_validate(
        {
            "DIYU_RUNTIME_MODE": "test",
            "DIYU_APP_DATABASE_URL": app_database_url,
            "DIYU_SESSION_SECRET": "ux03-gate-c-series-session-secret",
            "DIYU_DEMO_TENANT_ID": str(TENANT_ID),
            "DIYU_DEMO_USER_ID": str(USER_ID),
            "DIYU_DEMO_BRAND_ID": str(BRAND_ID),
            "DIYU_DEMO_ACCOUNT_ID": str(ACCOUNT_ID),
            "DIYU_GENERATOR_MODE": "stub",
        }
    )
    with TestClient(create_app(settings)) as client:
        client.get("/ui/select/content")
        bait_series = client.post(
            "/api/v1/content/series",
            json={
                "title": f"其他系列诱饵 {uuid4()}",
                "premise": "其他租户诱饵前情不得进入主系列。",
            },
        ).json()
        bait = client.post(
            "/api/v1/content",
            json={
                "weak_seed": "写一条内容：其他租户诱饵前情。",
                "series_id": bait_series["id"],
                "series_position": 1,
            },
        )
        assert bait.status_code == 200

        series = client.post(
            "/api/v1/content/series",
            json={
                "title": f"Gate C 三篇系列 {uuid4()}",
                "premise": "每篇沿着同一个停顿继续，但不机械复述。",
            },
        ).json()
        first = client.post(
            "/api/v1/content",
            json={
                "weak_seed": "写一条内容：第一篇先允许沉默。",
                "series_id": series["id"],
                "series_position": 1,
            },
        )
        assert first.status_code == 200
        first_request = captured[-1]
        assert first_request.series_context is not None
        assert first_request.series_context.prior_entries == ()

        second = client.post(
            "/api/v1/content",
            json={
                "weak_seed": "接着这个系列，第二篇把选择留在原处。",
                "series_id": series["id"],
            },
        )
        assert second.status_code == 200
        second_request = captured[-1]
        assert second_request.series_context is not None
        assert [
            item.outline for item in second_request.series_context.prior_entries
        ] == [first.json()["outline"]]

        third = client.post(
            "/api/v1/content",
            json={
                "weak_seed": "接着这个系列，第三篇回应不被催促的时刻。",
                "series_id": series["id"],
            },
        )
        assert third.status_code == 200
        third_request = captured[-1]
        frozen = third_request.series_context
        assert frozen is not None
        assert frozen.target_position == 3
        assert [item.position for item in frozen.prior_entries] == [1, 2]
        assert [item.outline for item in frozen.prior_entries] == [
            first.json()["outline"],
            second.json()["outline"],
        ]
        assert all(
            "其他租户诱饵前情" not in item.body
            for item in frozen.prior_entries
        )

        revised = client.post(
            f"/api/v1/tasks/{third.json()['task_id']}/revisions",
            json={
                "instruction": "保留承接关系，改得更短一点。",
                "target": "douyin_video",
                "source_target": "douyin_video",
            },
        )
        assert revised.status_code == 201
        assert captured[-1].series_context == frozen


def test_commit_readback_failure_emits_no_completed_and_persists_no_version(
    app_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_readback(row: object) -> object:
        del row
        raise DomainError("受控提交回读失败")

    monkeypatch.setattr(
        repository_module,
        "validate_version_content",
        fail_readback,
    )
    token = _session_token(app_database_url, USER_ID, "tenant-user")
    request_id = uuid4()
    payload = _conversation_payload(
        "请生成一条完整的门店生活观察内容。",
        identity_id=ACCOUNT_ID,
    )
    payload.update(
        {
            "interaction_mode": "generate",
            "direct_generate": True,
            "request_id": str(request_id),
        }
    )
    before = _persistence_counts(app_database_url)
    with TestClient(
        _app(app_database_url, monkeypatch),
        base_url="https://diyuai.cc",
    ) as client:
        client.cookies.set("diyu_session", token)
        events = _stream_events(client, payload)

    assert [item["event"] for item in events] == [
        "received",
        "compiling_context",
        "generating",
        "validating",
        "finalizing",
        "failed",
    ]
    assert all(item["event"] != "completed" for item in events)
    after = _persistence_counts(app_database_url)
    assert after == {
        "tasks": before["tasks"] + 1,
        "runs": before["runs"] + 1,
        "running": before["running"],
        "failed": before["failed"] + 1,
        "versions": before["versions"],
    }


def test_controls_request_remains_optional_and_has_no_hidden_required_axis() -> None:
    empty = RequestedControls()
    assert empty.selections == ()
    assert empty.cleared_axes == ()
    assert empty.custom_text == ""
    assert empty.body_related_opt_in is False
