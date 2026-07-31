from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from urllib.request import urlopen
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

import src.infrastructure.postgres_repository as repository_module
from src.brain.content_expression import (
    direction_from_snapshot,
    snapshot_document,
)
from src.brain.p1_contract import assert_content_complete
from src.brain.platform_directions import direction_for
from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.production_auth import ProductionAuthRepository
from src.infrastructure.seed_demo import (
    ACCOUNT_ID,
    BRAND_ID,
    HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID,
    TENANT_ID,
    USER_ID,
)
from src.shared.content_snapshot import frozen_media_contract
from src.shared.creative_kernel import (
    DUAL_TRACK_KERNEL_VERSION,
    KERNEL_VERSION,
    LEGACY_KERNEL_VERSION,
    MEDIA_NATIVE_KERNEL_VERSION,
    CreativeKernelV1,
    build_kernel_skeleton,
    normalize_writer_unit_text,
    parse_writer_kernel,
    repair_kernel_units,
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
from src.shared.errors import DomainError, GenerationFailed
from src.shared.factual_basis import (
    build_product_fact_packet,
    immutable_product_fact_blocks,
    select_product_fact_block_ids,
)
from src.shared.media_program import (
    MediaResourceV1,
    assert_media_program_allowed,
    build_media_capability_envelope,
    select_media_program,
)
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
    P3SemanticContract,
    ProductFact,
    ReferenceMaterial,
    RequestedControls,
    SeriesContext,
    SeriesEntry,
    VideoProductionBundle,
)
from src.tool.gate_c_evidence import (
    GATE_C_REVIEW_CRITERIA,
    ArtifactEvidenceInput,
    EvidenceBindingError,
    HumanReviewInput,
    NormalizationEvidenceInput,
    artifact_visible_digest,
    sha256_file,
    verify_gate_c_evidence,
    write_gate_c_evidence,
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


def _run_gate_c_browser(
    app_database_url: str,
    token: str,
    material_root: Path,
) -> subprocess.CompletedProcess[str]:
    """Run the formal Creator React/API/PostgreSQL journey in real Chrome."""

    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = int(port_socket.getsockname()[1])
    base_url = f"http://127.0.0.1:{port}"
    environment = {
        **os.environ,
        "DIYU_RUNTIME_MODE": "test",
        "DIYU_APP_DATABASE_URL": app_database_url,
        "DIYU_SESSION_SECRET": "ux03-gate-c-browser-session-secret",
        "DIYU_DEMO_TENANT_ID": str(TENANT_ID),
        "DIYU_DEMO_USER_ID": str(USER_ID),
        "DIYU_DEMO_BRAND_ID": str(BRAND_ID),
        "DIYU_DEMO_ACCOUNT_ID": str(ACCOUNT_ID),
        "DIYU_GENERATOR_MODE": "stub",
        "DIYU_MATERIAL_STORAGE_ROOT": str(material_root),
    }
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "src.gateway.api.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            if server.poll() is not None:
                raise AssertionError("Gate C browser API server exited early")
            try:
                with urlopen(f"{base_url}/status", timeout=0.2) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            raise AssertionError("Gate C browser API server did not become ready")
        return subprocess.run(
            ["node", "frontend/test/ux03-gate-c-browser.mjs"],
            cwd=Path(__file__).resolve().parents[1],
            env={
                **os.environ,
                "UX03_GATE_C_BASE_URL": base_url,
                "UX03_GATE_C_SESSION_TOKEN": token,
                "UX03_GATE_C_ACCOUNT_ID": str(ACCOUNT_ID),
            },
            capture_output=True,
            text=True,
            timeout=180,
        )
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


def _delete_gate_c_browser_artifacts(
    database_url: str,
    *,
    task_ids: tuple[UUID, ...],
    session_token: str,
) -> None:
    """Remove only this local Chrome journey's exact task chain and session."""

    with (
        psycopg.connect(database_url, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        for task_id in task_ids:
            cursor.execute(
                "SELECT id FROM content_versions WHERE tenant_id = %s AND task_id = %s ORDER BY id",
                (TENANT_ID, task_id),
            )
            for row in cursor.fetchall():
                version_id = UUID(str(row["id"]))
                cursor.execute(
                    "SELECT set_config('app.tenant_id', %s, true)",
                    (str(TENANT_ID),),
                )
                cursor.execute(
                    "SELECT set_config('diyu.content_version_maintenance', 'delete_synthetic_fixture', true)"
                )
                cursor.execute(
                    "SELECT set_config("
                    "'diyu.content_version_maintenance_transaction_id', "
                    "pg_current_xact_id()::text, true)"
                )
                cursor.execute(
                    "SELECT set_config('diyu.content_version_maintenance_tenant_id', %s, true)",
                    (str(TENANT_ID),),
                )
                cursor.execute(
                    "SELECT set_config('diyu.content_version_maintenance_version_id', %s, true)",
                    (str(version_id),),
                )
                cursor.execute(
                    "DELETE FROM content_versions WHERE tenant_id = %s AND id = %s",
                    (TENANT_ID, version_id),
                )
            cursor.execute(
                "DELETE FROM activity_events WHERE tenant_id = %s AND entity_id = %s",
                (TENANT_ID, task_id),
            )
            cursor.execute(
                "DELETE FROM generation_runs WHERE tenant_id = %s AND task_id = %s",
                (TENANT_ID, task_id),
            )
            cursor.execute(
                "DELETE FROM content_items WHERE tenant_id = %s AND task_id = %s",
                (TENANT_ID, task_id),
            )
            cursor.execute(
                "DELETE FROM business_tasks WHERE tenant_id = %s AND id = %s",
                (TENANT_ID, task_id),
            )
        cursor.execute(
            "DELETE FROM tenant_sessions WHERE tenant_id = %s AND token_digest = %s",
            (
                TENANT_ID,
                ProductionAuthRepository._digest(session_token),
            ),
        )

        if task_ids:
            cursor.execute(
                """
                SELECT
                  (SELECT count(*) FROM business_tasks
                    WHERE tenant_id = %s AND id = ANY(%s)) AS tasks,
                  (SELECT count(*) FROM generation_runs
                    WHERE tenant_id = %s AND task_id = ANY(%s)) AS runs,
                  (SELECT count(*) FROM content_versions
                    WHERE tenant_id = %s AND task_id = ANY(%s)) AS versions
                """,
                (
                    TENANT_ID,
                    list(task_ids),
                    TENANT_ID,
                    list(task_ids),
                    TENANT_ID,
                    list(task_ids),
                ),
            )
            assert cursor.fetchone() == {
                "tasks": 0,
                "runs": 0,
                "versions": 0,
            }


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
    target = "xiaohongshu_graphic" if media_format == "graphic" else "douyin_video"
    frame = new_frame("general_observation", (), ())
    plan = build_creative_plan(
        topic_spans=("今天喝了一直喝的蓝山咖啡，居然是甜的",),
        primary_value="brand_life_narrative",
        tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
        mechanism_id=None,
        target_shape="小红书图文完整成品",
    )
    envelope = build_media_capability_envelope(
        platform_shape=(
            "小红书图文完整成品"
            if media_format == "graphic"
            else "抖音短视频完整成品"
        ),
        media_format=cast(Any, media_format),
    )
    media_program = select_media_program(
        primary_product="brand_life_narrative",
        envelope=envelope,
        mechanism_id=plan.mechanism_id,
        series_position=(
            series_context.target_position
            if series_context is not None
            else None
        ),
        fact_count=0,
    )
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
        creative_plan=plan,
        delivery_compiler_version=DELIVERY_COMPILER_VERSION,
        media_capability_envelope=envelope,
        media_program=media_program,
    )


def _compile_input(request: GenerationInput) -> DeliveryCompileInput:
    assert request.media_capability_envelope is not None
    assert request.media_program is not None
    return DeliveryCompileInput(
        primary_product=request.primary_product,
        media_format=request.media_format,
        products=request.products,
        production_conditions=request.brand.production_conditions,
        allowed_resource_ids=request.media_capability_envelope.resource_ids,
        media_capability_envelope=request.media_capability_envelope,
        media_program=request.media_program,
    )


def _filled_kernel(request: GenerationInput) -> object:
    assert request.narrative_frame is not None
    context = BoundaryContext.from_request(request, request.narrative_frame)
    skeleton = build_kernel_skeleton(
        frame=request.narrative_frame,
        fact_registry=context.fact_registry,
        constraint_refs=tuple(identifier for identifier, _ in context.constraint_registry),
        program_id=select_kernel_program(frame=request.narrative_frame),
        allowed_resource_ids=tuple(sorted(_RESOURCES)),
        media_format=request.media_format,
        kernel_version=KERNEL_VERSION,
        primary_product=request.primary_product,
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
        ]
    }
    return parse_writer_kernel(
        raw,
        skeleton,
    )


def test_media_native_units_compile_one_scope_and_distinct_platform_parts() -> None:
    request = _generation_input(media_format="video")
    kernel = _filled_kernel(request)
    compiled = compile_delivery(
        _compile_input(request),
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


def test_v3_media_units_are_writer_owned_and_reject_compiler_fallback() -> None:
    request = _generation_input(media_format="video")
    assert request.narrative_frame is not None
    skeleton = build_kernel_skeleton(
        frame=request.narrative_frame,
        fact_registry=(),
        constraint_refs=(),
        allowed_resource_ids=tuple(sorted(_RESOURCES)),
        media_format="video",
        kernel_version=MEDIA_NATIVE_KERNEL_VERSION,
        primary_product=request.primary_product,
    )
    text_by_id = {
        "unit:title": "标题",
        "unit:natural-guide": "导读",
        "unit:media-opening": "本篇独有的开头",
        "unit:media-sequence": "本篇独有的画面推进",
        "unit:subtitle-strategy": "本篇独有的字幕取舍",
        "unit:production-note": "本篇独有的制作提示",
        "unit:body": "完整正文",
        "unit:release-caption": "发布配文",
    }
    raw = {
        "units": [
            {"unit_id": unit.unit_id, "text": text_by_id[unit.unit_id]}
            for unit in skeleton.writable_units
        ]
    }

    parsed = parse_writer_kernel(raw, skeleton)
    for purpose in (
        "media_opening",
        "media_sequence",
        "subtitle_strategy",
        "production_note",
    ):
        unit = next(item for item in parsed.units if item.purpose == purpose)
        assert unit.text_source == "writer"
        assert unit.text == text_by_id[unit.unit_id]

    fallback = compiler_owned_media_unit_texts(
        DeliveryCompileInput(
            primary_product=request.primary_product,
            media_format=request.media_format,
            products=(),
            production_conditions=request.brand.production_conditions,
            allowed_resource_ids=_RESOURCES,
        )
    )
    with pytest.raises(ValueError, match="compiler-owned unit contract"):
        parse_writer_kernel(
            {
                "units": [
                    {"unit_id": unit.unit_id, "text": text_by_id[unit.unit_id]}
                    for unit in skeleton.writable_units
                    if unit.unit_id not in fallback
                ]
            },
            skeleton,
            compiler_owned_text_by_id=fallback,
        )


def test_v4_writer_has_no_media_units_and_rejects_one_if_returned() -> None:
    request = _generation_input()
    assert request.narrative_frame is not None
    skeleton = build_kernel_skeleton(
        frame=request.narrative_frame,
        fact_registry=(),
        constraint_refs=(),
        media_format=request.media_format,
        kernel_version=KERNEL_VERSION,
        primary_product=request.primary_product,
    )

    assert tuple(unit.purpose for unit in skeleton.writable_units) == (
        "title",
        "natural_guide",
        "body",
        "release_caption",
    )
    payload = {
        "units": [
            {"unit_id": unit.unit_id, "text": f"{unit.purpose} 的自然内容"}
            for unit in skeleton.writable_units
        ]
        + [
            {
                "unit_id": "unit:media-opening",
                "text": "拍摄一个未登记现实物件。",
            }
        ]
    }
    with pytest.raises(ValueError, match="coverage"):
        parse_writer_kernel(payload, skeleton)


def test_product_fact_and_production_condition_do_not_grant_media_capability() -> None:
    request = replace(
        _generation_input(media_format="video"),
        products=(
            ProductFact(
                sku="P-ONLY-FACT",
                display_name="只登记事实的商品",
                facts={"category": "测试类别"},
                source_kind="synthetic_confirmed_product_record",
            ),
        ),
        brand=replace(
            _generation_input(media_format="video").brand,
            production_conditions="一人一部手机，普通室内环境。",
        ),
    )
    assert request.media_capability_envelope is not None

    assert request.media_capability_envelope.capability_ids == (
        "abstract_composition",
    )
    assert request.media_capability_envelope.resource_ids == frozenset(
        {ORIGINAL_COMPOSITION_RESOURCE_ID}
    )
    assert "video_creator_expression_v1" not in (
        request.media_capability_envelope.allowed_program_ids
    )
    assert "video_registered_product_display_v1" not in (
        request.media_capability_envelope.allowed_program_ids
    )


def test_only_explicitly_selected_media_enters_the_envelope() -> None:
    chosen = ReferenceMaterial(
        UUID("83000000-0000-0000-0000-000000000031"),
        "本次明确选择的素材",
        "image",
        2,
        reference_note="不透明图片素材",
    )
    unchosen = ReferenceMaterial(
        UUID("83000000-0000-0000-0000-000000000032"),
        "资料库中未选择的素材",
        "image",
        7,
        reference_note="不应进入本次任务",
    )
    envelope = build_media_capability_envelope(
        platform_shape="小红书图文完整成品",
        media_format="graphic",
        selected_materials=(chosen,),
    )

    assert str(chosen.asset_id) in " ".join(envelope.resource_ids)
    assert str(unchosen.asset_id) not in " ".join(envelope.resource_ids)
    selected = envelope.resources_for("selected_media_asset")
    assert len(selected) == 1
    assert selected[0].resource_version == "2"
    assert selected[0].source_ref.endswith(":v2")


def test_media_program_rejects_unlisted_program_and_outside_resource() -> None:
    envelope = build_media_capability_envelope(
        platform_shape="小红书图文完整成品",
        media_format="graphic",
    )
    program = select_media_program(
        primary_product="brand_life_narrative",
        envelope=envelope,
        mechanism_id=None,
        series_position=None,
        fact_count=0,
    )

    with pytest.raises(GenerationFailed, match="不属于冻结媒体能力包"):
        assert_media_program_allowed(
            envelope,
            replace(
                program,
                program_id=cast(
                    Any,
                    "video_registered_product_display_v1",
                ),
            ),
        )
    with pytest.raises(GenerationFailed, match="媒体能力包之外"):
        assert_media_program_allowed(
            envelope,
            replace(
                program,
                required_resource_ids=(
                    *program.required_resource_ids,
                    "resource:outside-envelope",
                ),
            ),
        )


def test_optional_capture_is_visible_but_never_a_required_resource() -> None:
    base = _generation_input()
    assert base.media_capability_envelope is not None
    program = select_media_program(
        primary_product="brand_life_narrative",
        envelope=base.media_capability_envelope,
        mechanism_id=None,
        series_position=None,
        fact_count=1,
    )
    request = replace(base, media_program=program)
    compiled = compile_delivery(
        _compile_input(request),
        cast(Any, _filled_kernel(request)),
    )

    assert compiled.resource_refs == (ORIGINAL_COMPOSITION_RESOURCE_ID,)
    assert "可选补拍建议：" in compiled.body
    assert "如果刚才提到的事物仍在手边" in compiled.body
    assert "没有也不影响" in compiled.body
    assert isinstance(compiled.production, GraphicProductionBundle)
    assert compiled.production.optional_capture_suggestion is not None
    assert all(
        "optional" not in resource_id
        for resource_id in compiled.resource_refs
    )
    assert any(
        source.startswith("compiler:optional-capture-suggestion:")
        for source in compiled.visible_provenance["optional_capture_suggestion"]
    )


def test_p5_requires_two_frozen_registered_product_resources() -> None:
    empty_envelope = build_media_capability_envelope(
        platform_shape="抖音短视频完整成品",
        media_format="video",
    )
    with pytest.raises(GenerationFailed, match="至少两件"):
        select_media_program(
            primary_product="visual_styling_story",
            envelope=empty_envelope,
            mechanism_id=None,
            series_position=None,
            fact_count=2,
        )

    registered = tuple(
        MediaResourceV1(
            resource_id=f"resource:registered-product:{index}:v1",
            resource_version="1",
            media_type="image",
            source_ref=f"product-media:{index}:v1",
            capability_id="registered_product_display",
        )
        for index in (1, 2)
    )
    envelope = build_media_capability_envelope(
        platform_shape="抖音短视频完整成品",
        media_format="video",
        registered_resources=registered,
    )
    program = select_media_program(
        primary_product="visual_styling_story",
        envelope=envelope,
        mechanism_id=None,
        series_position=None,
        fact_count=2,
    )
    assert program.program_id == "video_registered_product_display_v1"
    assert set(program.required_resource_ids) == envelope.resource_ids


def test_series_positions_receive_distinct_closed_media_programs() -> None:
    envelope = build_media_capability_envelope(
        platform_shape="小红书图文完整成品",
        media_format="graphic",
    )
    series2 = select_media_program(
        primary_product="brand_life_narrative",
        envelope=envelope,
        mechanism_id=None,
        series_position=2,
        fact_count=0,
    )
    series3 = select_media_program(
        primary_product="brand_life_narrative",
        envelope=envelope,
        mechanism_id=None,
        series_position=3,
        fact_count=0,
    )

    assert series2.program_id == "graphic_series_response_v1"
    assert series3.program_id == "graphic_series_choice_v1"
    request2 = replace(
        _generation_input(series_context=replace(_series_context(), target_position=2)),
        media_capability_envelope=envelope,
        media_program=series2,
    )
    request3 = replace(
        _generation_input(series_context=_series_context()),
        media_capability_envelope=envelope,
        media_program=series3,
    )
    compiled2 = compile_delivery(
        _compile_input(request2),
        cast(Any, _filled_kernel(request2)),
    )
    compiled3 = compile_delivery(
        _compile_input(request3),
        cast(Any, _filled_kernel(request3)),
    )
    assert isinstance(compiled2.production, GraphicProductionBundle)
    assert isinstance(compiled3.production, GraphicProductionBundle)
    assert compiled2.production.hero_image != compiled3.production.hero_image
    assert (
        compiled2.production.image_sequence
        != compiled3.production.image_sequence
    )


def test_media_envelope_and_program_are_frozen_and_digest_bound() -> None:
    request = _generation_input(series_context=_series_context())
    assert request.media_capability_envelope is not None
    assert request.media_program is not None
    control = ContentControlContext(
        catalog_version="content-expression-catalog-v1",
        direction=None,
        account_expression=request.account_expression,
        materials=(),
        preference_mode="preference_disabled",
        preference_version=None,
    )
    snapshot = snapshot_document(
        control,
        "门店生活观察者",
        media_capability_envelope=request.media_capability_envelope,
        media_program=request.media_program,
    )

    assert frozen_media_contract(snapshot) == (
        request.media_capability_envelope,
        request.media_program,
    )
    tampered = dict(snapshot)
    tampered["media_program_digest"] = "0" * 64
    with pytest.raises(DomainError, match="摘要不一致"):
        frozen_media_contract(tampered)


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    (
        ("首图：从颜色的两面开始看选择。", "从颜色的两面开始看选择。"),
        ("首图：\n从颜色的两面开始看选择。", "\n从颜色的两面开始看选择。"),
        (
            "首图：第一行保留，标点不改；\n第二行保留 emoji 👨‍👩‍👧。",
            "第一行保留，标点不改；\n第二行保留 emoji 👨‍👩‍👧。",
        ),
    ),
)
def test_graphic_media_opening_removes_one_exact_compiler_wrapper(
    raw_text: str,
    expected: str,
) -> None:
    request = _generation_input()
    assert request.narrative_frame is not None
    skeleton = build_kernel_skeleton(
        frame=request.narrative_frame,
        fact_registry=(),
        constraint_refs=(),
        allowed_resource_ids=tuple(sorted(_RESOURCES)),
        media_format="graphic",
        kernel_version=MEDIA_NATIVE_KERNEL_VERSION,
        primary_product=request.primary_product,
    )
    opening = skeleton.unit("unit:media-opening")

    normalized, receipt = normalize_writer_unit_text(
        raw_text,
        unit=opening,
        kernel_version=MEDIA_NATIVE_KERNEL_VERSION,
        media_format="graphic",
    )

    assert normalized == expected
    assert receipt is not None
    assert receipt.unit_id == opening.unit_id
    assert receipt.purpose == opening.purpose
    assert receipt.removed_prefix == "首图："
    assert receipt.raw_text_sha256 == hashlib.sha256(raw_text.encode()).hexdigest()
    assert receipt.normalized_text_sha256 == hashlib.sha256(expected.encode()).hexdigest()
    assert receipt.contract_version == "writer-wrapper-normalization-v1"


@pytest.mark.parametrize(
    "raw_text",
    (
        "普通开头。\n首图：第二行伪装。",
        "首图：首图：重复包装。",
        "首图：标题：嵌套标题。",
        "首图：\n发布配文：嵌套标题。",
        "首图:半角冒号。",
        "首图﹕兼容冒号。",
        "首\u200b图：零宽拆分。",
        "**首图：** Markdown 包装。",
        "- 首图：项目符号包装。",
        "【首图】：额外标点包装。",
        "你提到：服务端范围说明。",
        "首图：",
        "首图：\u202e双向控制。",
    ),
)
def test_graphic_media_opening_rejects_noncanonical_or_nested_wrappers(
    raw_text: str,
) -> None:
    request = _generation_input()
    assert request.narrative_frame is not None
    opening = build_kernel_skeleton(
        frame=request.narrative_frame,
        fact_registry=(),
        constraint_refs=(),
        allowed_resource_ids=tuple(sorted(_RESOURCES)),
        media_format="graphic",
        kernel_version=MEDIA_NATIVE_KERNEL_VERSION,
        primary_product=request.primary_product,
    ).unit("unit:media-opening")

    with pytest.raises(ValueError):
        normalize_writer_unit_text(
            raw_text,
            unit=opening,
            kernel_version=MEDIA_NATIVE_KERNEL_VERSION,
            media_format="graphic",
        )


def test_wrapper_normalization_never_applies_to_wrong_purpose_legacy_fact_or_compiler_text() -> None:
    request = _generation_input()
    assert request.narrative_frame is not None
    skeleton = build_kernel_skeleton(
        frame=request.narrative_frame,
        fact_registry=(),
        constraint_refs=(),
        allowed_resource_ids=tuple(sorted(_RESOURCES)),
        media_format="graphic",
        kernel_version=MEDIA_NATIVE_KERNEL_VERSION,
        primary_product=request.primary_product,
    )
    opening = skeleton.unit("unit:media-opening")
    excluded_units = (
        skeleton.unit("unit:title"),
        replace(
            opening,
            purpose="frozen_fact",
            text_source="server_fact",
        ),
        replace(opening, text_source="server_compiler"),
    )
    for unit in excluded_units:
        with pytest.raises(ValueError):
            normalize_writer_unit_text(
                "首图：不能进入规范化路径。",
                unit=unit,
                kernel_version=MEDIA_NATIVE_KERNEL_VERSION,
                media_format="graphic",
            )
    for legacy_version in (
        LEGACY_KERNEL_VERSION,
        DUAL_TRACK_KERNEL_VERSION,
    ):
        with pytest.raises(ValueError):
            normalize_writer_unit_text(
                "首图：legacy 不能进入规范化路径。",
                unit=opening,
                kernel_version=legacy_version,
                media_format="graphic",
            )


def test_initial_and_repair_paths_share_exact_wrapper_normalization() -> None:
    request = _generation_input()
    assert request.narrative_frame is not None
    skeleton = build_kernel_skeleton(
        frame=request.narrative_frame,
        fact_registry=(),
        constraint_refs=(),
        allowed_resource_ids=tuple(sorted(_RESOURCES)),
        media_format="graphic",
        kernel_version=MEDIA_NATIVE_KERNEL_VERSION,
        primary_product=request.primary_product,
    )
    initial = parse_writer_kernel(
        {
            "units": [
                {
                    "unit_id": unit.unit_id,
                    "text": (
                        "首图：第一次的可见开头。"
                        if unit.unit_id == "unit:media-opening"
                        else f"{unit.purpose} 的自然内容"
                    ),
                }
                for unit in skeleton.writable_units
            ]
        },
        skeleton,
        media_format="graphic",
    )
    assert initial.unit("unit:media-opening").text == "第一次的可见开头。"

    repaired = repair_kernel_units(
        kernel=initial,
        affected_unit_ids=frozenset({"unit:media-opening"}),
        raw={
            "units": [
                {
                    "unit_id": "unit:media-opening",
                    "text": "首图：修复后的可见开头。",
                }
            ]
        },
        media_format="graphic",
    )
    assert repaired.unit("unit:media-opening").text == "修复后的可见开头。"


def test_actuality_life_units_are_preallocated_as_disclosed_hypothesis() -> None:
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
        replace(
            _compile_input(request),
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
    assert "其余是创作性推演，不作为这段经历的事实补充" in compiled.body


def test_p2_server_selects_only_the_three_frozen_product_facts() -> None:
    product = ProductFact(
        sku="ZX-C218",
        display_name="双面短外套",
        facts={
            "entity_kind": "apparel_product",
            "category": "双面短外套",
            "colors": ["炭灰纯色", "深绿细格纹"],
            "both_sides_complete": True,
        },
        source_kind="synthetic_confirmed_product_record",
    )
    packet = build_product_fact_packet((product,))
    blocks = immutable_product_fact_blocks(packet)
    selected_ids = select_product_fact_block_ids(packet, limit=3)
    selected = tuple(
        block.canonical_text
        for block_id in selected_ids
        for block in blocks
        if block.fact_block_id == block_id
    )

    assert selected == (
        "ZX-C218 是一件双面短外套。",
        "双面短外套有炭灰纯色、深绿细格纹这些已确认颜色。",
        "双面短外套两面都以完整外观呈现。",
    )


@pytest.mark.parametrize(
    ("primary_product", "frame_mode", "expected_mode"),
    (
        ("dressing_decision", "general_observation", "recommendation"),
        ("product_truth", "general_observation", "recommendation"),
        ("local_response", "actuality_reflection", "recommendation"),
        ("visual_styling_story", "general_observation", "recommendation"),
        ("brand_life_narrative", "actuality_reflection", "hypothesis"),
    ),
)
def test_v3_body_license_is_preallocated_from_the_content_value(
    primary_product: str,
    frame_mode: str,
    expected_mode: str,
) -> None:
    skeleton = build_kernel_skeleton(
        frame=new_frame(
            cast(Any, frame_mode),
            ("冻结现实片段",) if frame_mode == "actuality_reflection" else (),
            (),
        ),
        fact_registry=(),
        constraint_refs=(),
        kernel_version=KERNEL_VERSION,
        primary_product=cast(Any, primary_product),
    )

    assert skeleton.unit("unit:body").mode == expected_mode


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
    assert '"allowed_resources": []' in prompt
    assert "媒体程序 graphic_series_choice_v1 确定性生成" in prompt
    assert "不得返回任何媒体单元、资源引用" in prompt
    assert "resource:original_composition" not in prompt
    assert "resource:creator_expression" not in prompt
    assert "其他租户诱饵前情" not in prompt


def test_product_facts_are_hidden_and_do_not_grant_media_resources() -> None:
    product = ProductFact(
        sku="ZX-C218",
        display_name="双面短外套",
        facts={
            "entity_kind": "apparel_product",
            "category": "双面短外套",
            "colors": ["炭灰纯色", "深绿细格纹"],
        },
        source_kind="synthetic_confirmed_product_record",
    )
    base_request = _generation_input()
    assert base_request.media_capability_envelope is not None
    media_program = select_media_program(
        primary_product="product_truth",
        envelope=base_request.media_capability_envelope,
        mechanism_id=None,
        series_position=None,
        fact_count=3,
    )
    request = replace(
        base_request,
        weak_seed="帮我解释这个已选商品。",
        primary_product="product_truth",
        products=(product,),
        narrative_frame=new_frame(
            "general_observation",
            (),
            tuple(item.fact_id for item in build_product_fact_packet((product,)).facts),
        ),
        creative_plan=build_creative_plan(
            topic_spans=("ZX-C218，帮我解释这个商品",),
            primary_value="product_truth",
            tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
            mechanism_id=None,
            target_shape="小红书图文完整成品",
        ),
        media_program=media_program,
    )
    assert request.narrative_frame is not None
    context = BoundaryContext.from_request(request, request.narrative_frame)
    skeleton = build_kernel_skeleton(
        frame=request.narrative_frame,
        fact_registry=context.fact_registry,
        constraint_refs=tuple(context.constraint_ids),
        program_id=select_kernel_program(
            frame=request.narrative_frame,
        ),
        allowed_resource_ids=tuple(sorted(context.resource_ids)),
        media_format="graphic",
        kernel_version=KERNEL_VERSION,
    )
    skeleton = replace(
        skeleton,
        selected_fact_block_ids=select_product_fact_block_ids(
            context.product_fact_packet,
            limit=3,
        ),
    )

    prompt = DeepSeekGenerator(
        "https://example.invalid",
        "not-a-real-key",
        "deepseek-test",
    )._kernel_writer_prompt(
        request,
        skeleton,
        {},
    )

    assert "ZX-C218" not in prompt
    assert "双面短外套" not in prompt
    assert "炭灰纯色" not in prompt
    assert "深绿细格纹" not in prompt
    assert "resource:product:" not in prompt
    assert "resource:registered-product-1" not in prompt
    assert "resource:selected-media:" not in prompt
    assert "本次已选商品" in prompt
    assert "全部 Writer unit" in prompt
    assert "不能成为 Writer 文字的主语、宾语或指代对象" in prompt
    assert "媒体程序 graphic_fact_guided_v1 确定性生成" in prompt
    assert "不得返回任何媒体单元、资源引用" in prompt


def test_p3_writer_receives_one_explicit_account_editorial_link() -> None:
    request = replace(
        _generation_input(),
        brand=replace(
            _generation_input().brand,
            account_name="折线衣间·总部穿衣编辑",
            content_role_name="总部穿衣编辑",
        ),
        account_expression=AccountExpression(
            UUID("83000000-0000-0000-0000-000000000020"),
            3,
            "从穿衣编辑的位置重新看熟悉事物",
            "不把表达位置写成真实职业履历或机构事实。",
            "陪正在重新选择日常节奏的人看清取舍。",
            "穿衣选择、熟悉事物被重新看见的时刻。",
            "一人一部手机，普通室内环境。",
            False,
        ),
    )
    kernel = cast(CreativeKernelV1, _filled_kernel(request))
    prompt = DeepSeekGenerator(
        "https://example.invalid",
        "not-a-real-key",
        "deepseek-test",
    )._kernel_writer_prompt(request, kernel, {})

    assert "本篇账号关联路径" in prompt
    assert "从穿衣编辑的位置重新看熟悉事物" in prompt
    assert "陪正在重新选择日常节奏的人看清取舍" in prompt
    assert "为什么会说这段话" in prompt
    assert "折线衣间" not in prompt
    assert "每个 text 只填写该单元的自然内容" in prompt
    assert "正式标题、正文、字幕、制作提示和发布配文的结构只由" in prompt
    assert '"shape": "content_only"' in prompt
    assert '"wrapper_owner": "delivery_compiler"' in prompt
    assert '"text": ""' in prompt
    assert "填写 media_opening 的完整可见文字" not in prompt
    assert "purpose 只说明下游消费用途" in prompt

    compiled = compile_delivery(
        _compile_input(request),
        kernel,
    )
    assert isinstance(compiled.semantic_contract, P3SemanticContract)
    assert compiled.semantic_contract.brand_account_link == (
        "看一次熟悉感被意外打断后，人会怎样重新注意日常。"
    )
    assert compiled.semantic_contract.brand_account_link in compiled.body


def test_visual_styling_writer_never_receives_registered_product_resources() -> None:
    products = (
        ProductFact(
            sku="ZX-C218",
            display_name="双面短外套",
            facts={"entity_kind": "apparel_product", "category": "双面短外套"},
            source_kind="synthetic_confirmed_product_record",
        ),
        ProductFact(
            sku="ZX-S104",
            display_name="深灰直筒半裙",
            facts={"entity_kind": "apparel_product", "category": "直筒半裙"},
            source_kind="synthetic_confirmed_product_record",
        ),
    )
    fact_ids = tuple(fact.fact_id for product in products for fact in build_product_fact_packet((product,)).facts)
    registered_resources = (
        MediaResourceV1(
            "resource:registered-product:one:v1",
            "1",
            "image",
            "product-media:one:v1",
            "registered_product_display",
        ),
        MediaResourceV1(
            "resource:registered-product:two:v1",
            "1",
            "image",
            "product-media:two:v1",
            "registered_product_display",
        ),
    )
    envelope = build_media_capability_envelope(
        platform_shape="抖音短视频完整成品",
        media_format="video",
        registered_resources=registered_resources,
    )
    media_program = select_media_program(
        primary_product="visual_styling_story",
        envelope=envelope,
        mechanism_id=None,
        series_position=None,
        fact_count=4,
    )
    request = replace(
        _generation_input(media_format="video"),
        weak_seed="用 ZX-C218 和 ZX-S104 做一条能照着拍的视觉造型短视频。",
        primary_product="visual_styling_story",
        products=products,
        narrative_frame=new_frame("general_observation", (), fact_ids),
        creative_plan=build_creative_plan(
            topic_spans=("用 ZX-C218 和 ZX-S104 做一条能照着拍的视觉造型短视频",),
            primary_value="visual_styling_story",
            tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
            mechanism_id=None,
            target_shape="抖音短视频完整成品",
        ),
        media_capability_envelope=envelope,
        media_program=media_program,
    )
    assert request.narrative_frame is not None
    context = BoundaryContext.from_request(request, request.narrative_frame)
    skeleton = build_kernel_skeleton(
        frame=request.narrative_frame,
        fact_registry=context.fact_registry,
        constraint_refs=tuple(context.constraint_ids),
        program_id=select_kernel_program(frame=request.narrative_frame),
        allowed_resource_ids=tuple(sorted(context.resource_ids)),
        media_format="video",
        kernel_version=KERNEL_VERSION,
        primary_product="visual_styling_story",
    )
    skeleton = replace(
        skeleton,
        selected_fact_block_ids=select_product_fact_block_ids(
            context.product_fact_packet,
            limit=3,
        ),
    )
    prompt = DeepSeekGenerator(
        "https://example.invalid",
        "not-a-real-key",
        "deepseek-test",
    )._kernel_writer_prompt(request, skeleton, {})

    assert "ZX-C218" not in prompt
    assert "ZX-S104" not in prompt
    assert "双面短外套" not in prompt
    assert "深灰直筒半裙" not in prompt
    assert "resource:registered-product:" not in prompt
    assert '"allowed_resources": []' in prompt
    assert "媒体关系由服务端确定性编排" in prompt
    assert "video_registered_product_display_v1" in prompt


def test_restricted_media_fallback_stays_available_outside_the_v3_main_path() -> None:
    request = DeliveryCompileInput(
        primary_product="visual_styling_story",
        media_format="video",
        products=(),
        production_conditions="一人一部手机。",
        allowed_resource_ids=frozenset(
            {
                ORIGINAL_COMPOSITION_RESOURCE_ID,
                CREATOR_EXPRESSION_RESOURCE_ID,
                "resource:product:one",
                "resource:product:two",
            }
        ),
    )
    compiler_texts = compiler_owned_media_unit_texts(request)

    assert set(compiler_texts) == {
        "unit:media-opening",
        "unit:media-sequence",
        "unit:subtitle-strategy",
        "unit:production-note",
    }
    assert "已登记商品样衣" in compiler_texts["unit:media-opening"]
    assert "同一机位和背景" in compiler_texts["unit:media-sequence"]
    assert "resource:product:" not in json.dumps(
        compiler_texts,
        ensure_ascii=False,
    )


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
    assert artifact.completion_snapshot_patch["delivery_compiler_version"] == DELIVERY_COMPILER_VERSION
    assert "第一篇：先允许沉默" in prompts[0]
    assert "不把任何一方写成反派" in prompts[0]


def _write_gate_c_evidence_fixture(
    tmp_path: Path,
    *,
    fact_boundary: str = "PASS",
    include_normalization: bool = False,
) -> Path:
    root = tmp_path / "gate-c-evidence"
    root.mkdir(mode=0o700, exist_ok=True)
    artifacts: list[ArtifactEvidenceInput] = []
    reviews: list[HumanReviewInput] = []
    for card_id in ("P1", "P2", "P3", "P4", "P5", "series2", "series3"):
        artifact = root / f"{card_id}-artifact.json"
        artifact.write_text(
            json.dumps(
                {
                    "outline": f"{card_id} 的自然标题",
                    "body": (
                        f"标题：{card_id} 的自然标题\n\n"
                        "完整正文：服务端事实原句与一般判断各自保留边界。"
                    ),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        artifact.chmod(0o600)
        raw = root / f"{card_id}-raw-response.json"
        raw_document: object = {"provider_response": "redacted-test-fixture"}
        if card_id == "P2" and include_normalization:
            raw_document = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "units": [
                                        {
                                            "unit_id": "unit:media-opening",
                                            "text": "首图：从两面完整外观开始看选择。",
                                        }
                                    ]
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }
        raw.write_text(
            json.dumps(raw_document, ensure_ascii=False),
            encoding="utf-8",
        )
        raw.chmod(0o600)
        criteria = {
            criterion: "PASS"
            for criterion in GATE_C_REVIEW_CRITERIA
        }
        if card_id == "P2":
            criteria["fact_and_resource_boundary"] = fact_boundary
        artifacts.append(
            ArtifactEvidenceInput(
                card_id,
                artifact.name,
                raw.name,
            )
        )
        reviews.append(
            HumanReviewInput(
                card_id,
                artifact.name,
                "PASS",
                criteria,
                "测试夹具只验证摘要绑定。",
            )
        )
    write_gate_c_evidence(
        root,
        implementation_sha="1" * 40,
        model="deepseek-v4-flash",
        temperature=0,
        max_retries=0,
        artifacts=tuple(artifacts),
        reviews=tuple(reviews),
        normalizations=(
            (
                NormalizationEvidenceInput(
                    card_id="P2",
                    unit_id="unit:media-opening",
                    purpose="media_opening",
                    media_format="graphic",
                ),
            )
            if include_normalization
            else ()
        ),
    )
    return root


def test_gate_c_evidence_records_exact_writer_wrapper_normalization(
    tmp_path: Path,
) -> None:
    root = _write_gate_c_evidence_fixture(
        tmp_path,
        include_normalization=True,
    )

    verify_gate_c_evidence(root)
    manifest = json.loads(
        (root / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["writer_wrapper_normalizations"] == [
        {
            "card_id": "P2",
            "media_format": "graphic",
            "normalization_contract_version": (
                "writer-wrapper-normalization-v1"
            ),
            "normalized_text_sha256": hashlib.sha256(
                "从两面完整外观开始看选择。".encode()
            ).hexdigest(),
            "purpose": "media_opening",
            "raw_text_sha256": hashlib.sha256(
                "首图：从两面完整外观开始看选择。".encode()
            ).hexdigest(),
            "removed_prefix": "首图：",
            "unit_id": "unit:media-opening",
        }
    ]


def test_gate_c_evidence_binds_file_sha_visible_digest_and_human_review(
    tmp_path: Path,
) -> None:
    root = _write_gate_c_evidence_fixture(tmp_path)

    verify_gate_c_evidence(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    record = manifest["artifacts"][0]
    artifact_path = root / record["artifact_file"]
    assert record["artifact_sha256"] == sha256_file(artifact_path)
    assert record["visible_digest"] == artifact_visible_digest(artifact_path)
    assert (root / "SHA256SUMS").is_file()
    assert (root.stat().st_mode & 0o777) == 0o700
    assert all(
        (path.stat().st_mode & 0o777) == 0o600
        for path in root.iterdir()
        if path.is_file()
    )


def test_gate_c_evidence_rejects_artifact_or_review_binding_tamper(
    tmp_path: Path,
) -> None:
    root = _write_gate_c_evidence_fixture(tmp_path)
    artifact = root / "P2-artifact.json"
    artifact.write_text(
        json.dumps(
            {
                "outline": "被篡改的标题",
                "body": "被篡改的正文",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(EvidenceBindingError, match="artifact file SHA"):
        verify_gate_c_evidence(root)


def test_gate_c_evidence_rejects_human_review_digest_tamper(
    tmp_path: Path,
) -> None:
    root = _write_gate_c_evidence_fixture(tmp_path)
    review_path = root / "human-review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["reviews"][0]["visible_digest"] = "0" * 64
    review_path.write_text(
        json.dumps(review, ensure_ascii=False),
        encoding="utf-8",
    )
    sums_path = root / "SHA256SUMS"
    sums_path.write_text(
        "".join(
            (
                f"{sha256_file(review_path)}  human-review.json\n"
                if line.endswith("  human-review.json")
                else f"{line}\n"
            )
            for line in sums_path.read_text(encoding="utf-8").splitlines()
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        EvidenceBindingError,
        match="human review is bound to another artifact",
    ):
        verify_gate_c_evidence(root)


def test_gate_c_evidence_rejects_p2_with_unsupported_product_semantics(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        EvidenceBindingError,
        match="human review criteria are incomplete",
    ):
        _write_gate_c_evidence_fixture(
            tmp_path,
            fact_boundary="FAIL",
        )


def test_gate_c_evidence_never_overwrites_an_existing_final_manifest(
    tmp_path: Path,
) -> None:
    root = _write_gate_c_evidence_fixture(tmp_path)

    with pytest.raises(
        EvidenceBindingError,
        match="evidence outputs already exist",
    ):
        _write_gate_c_evidence_fixture(tmp_path)

    verify_gate_c_evidence(root)


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
        assert [item.outline for item in second_request.series_context.prior_entries] == [first.json()["outline"]]

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
        assert all("其他租户诱饵前情" not in item.body for item in frozen.prior_entries)

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


def test_formal_creator_gate_c_browser_journey(
    app_database_url: str,
    migrator_database_url: str,
    tmp_path: Path,
) -> None:
    if os.environ.get("DIYU_RUN_UX03_GATE_C_BROWSER") != "1":
        pytest.skip("set DIYU_RUN_UX03_GATE_C_BROWSER=1 for the formal Chrome journey")
    frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    assert (frontend_dist / "index.html").is_file()
    token = hmac.new(
        b"ux03-gate-c-browser-session-secret",
        b"content-production",
        hashlib.sha256,
    ).hexdigest()
    original_business_data_kind = ""
    with (
        psycopg.connect(migrator_database_url, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "SELECT business_data_kind FROM content_accounts WHERE tenant_id = %s AND id = %s",
            (TENANT_ID, HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID),
        )
        account_row = cursor.fetchone()
        assert account_row is not None
        original_business_data_kind = str(account_row["business_data_kind"])
        cursor.execute(
            "UPDATE content_accounts "
            "SET business_data_kind = 'synthetic_business_fixture' "
            "WHERE tenant_id = %s AND id = %s",
            (TENANT_ID, HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID),
        )
        cursor.execute(
            "SELECT id FROM business_tasks WHERE tenant_id = %s AND created_by = %s",
            (TENANT_ID, USER_ID),
        )
        before_task_ids = {UUID(str(row["id"])) for row in cursor.fetchall()}
    created_task_ids: tuple[UUID, ...] = ()
    try:
        browser = _run_gate_c_browser(
            app_database_url,
            token,
            tmp_path / "materials",
        )
        assert browser.returncode == 0, f"formal Gate C Chrome journey failed:\n{browser.stdout}\n{browser.stderr}"
        result = json.loads(browser.stdout)
        assert result["failures"] == []
        assert result["lifecycle_events"] == [
            "received",
            "compiling_context",
            "generating",
            "validating",
            "finalizing",
            "completed",
        ]
        created_task_ids = tuple(UUID(item) for item in result["created_task_ids"])
        assert len(created_task_ids) == 1
    finally:
        with (
            psycopg.connect(
                migrator_database_url,
                row_factory=dict_row,
            ) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "SELECT id FROM business_tasks WHERE tenant_id = %s AND created_by = %s",
                (TENANT_ID, USER_ID),
            )
            observed = {UUID(str(row["id"])) for row in cursor.fetchall()}
        cleanup_ids = tuple(sorted(observed - before_task_ids, key=str))
        try:
            _delete_gate_c_browser_artifacts(
                migrator_database_url,
                task_ids=cleanup_ids,
                session_token=token,
            )
        finally:
            with (
                psycopg.connect(migrator_database_url) as restore_connection,
                restore_connection.cursor() as cursor,
            ):
                cursor.execute(
                    "UPDATE content_accounts SET business_data_kind = %s WHERE tenant_id = %s AND id = %s",
                    (
                        original_business_data_kind,
                        TENANT_ID,
                        HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID,
                    ),
                )
