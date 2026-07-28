from __future__ import annotations

import json
from dataclasses import replace
from typing import Any
from uuid import UUID

import httpx
import pytest

from src.brain.platform_directions import direction_for
from src.shared.errors import GenerationFailed
from src.shared.narrative import NarrativeFrame, new_frame, visible_digest
from src.shared.types import (
    ActiveAsset,
    BrandContext,
    ConversationInput,
    ConversationTurn,
    GenerationInput,
    GraphicProductionBundle,
    ProductFact,
    RoutingInput,
)
from src.tool.llm_gateway.deepseek import BoundaryContext, DeepSeekGenerator


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeClient:
    responses: list[FakeResponse] = []
    requests: list[dict[str, object]] = []

    def __init__(self, **_: object) -> None:
        pass

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def post(self, *_: object, **kwargs: object) -> FakeResponse:
        self.requests.append(kwargs)
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def _fake_client(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeClient.responses = []
    FakeClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeClient)


def _generator(*, max_retries: int = 0) -> DeepSeekGenerator:
    return DeepSeekGenerator(
        "https://example.invalid",
        "test-key",
        "deepseek-test",
        max_retries=max_retries,
    )


def _brand() -> BrandContext:
    return BrandContext(
        brand_name="笛语服饰",
        positioning="尊重每个人独立成立，也看见关系里的自然呼应",
        decision_order="先尊重差异，再讨论关系",
        tone="真实、克制、有依据",
        account_name="笛语服饰品牌官方账号",
        operator_name="当前运营者",
        organization_name="笛语服饰",
        content_role_name="品牌官方 / 品牌定义者",
        content_role_boundary="表达品牌判断，不冒充自然人、门店岗位或顾客。",
        audience_description="重视真实感受与关系边界的人。",
        strategy_version="brand-expression-v1",
        platform="小红书",
        media_format="图文",
        production_conditions="原创抽象构成和创作者表达。",
    )


def _request(
    frame: NarrativeFrame | None = None,
    *,
    revision_instruction: str | None = None,
    prior_saved_body: str | None = None,
    products: tuple[ProductFact, ...] = (),
) -> GenerationInput:
    selected_frame = frame or new_frame("general_observation", (), ())
    return GenerationInput(
        run_id=UUID("00000000-0000-0000-0000-000000000101"),
        task_id=UUID("00000000-0000-0000-0000-000000000102"),
        weak_seed="帮我写条婆媳主题的小红书，别狗血，也不要把任何一方写成反派。",
        primary_product="brand_life_narrative",
        revision_instruction=revision_instruction,
        brand=_brand(),
        target="xiaohongshu_graphic",
        media_format="graphic",
        platform_direction=direction_for("xiaohongshu_graphic"),
        active_domain_assets=(
            ActiveAsset(
                "B-001",
                "v1",
                "brand",
                "品牌基线",
                "方法应当尊重关系中的不同位置。",
            ),
        ),
        products=products,
        prior_saved_body=prior_saved_body,
        narrative_frame=selected_frame,
        system_creative_plan="用留白和轻微幽默讨论关系中的边界，不创造生活事件。",
    )


def _completion(document: object, tokens: int = 0) -> FakeResponse:
    payload: dict[str, Any] = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(document, ensure_ascii=False),
                }
            }
        ]
    }
    if tokens:
        payload["usage"] = {"total_tokens": tokens}
    return FakeResponse(200, payload)


def _mode_text(mode: str, value: str) -> str:
    if mode == "hypothesis":
        return f"如果先停十秒，{value}也许会换一种走向。"
    if mode == "dramatization":
        return f"情境演绎：{value}"
    return value


def _core(frame: NarrativeFrame) -> dict[str, object]:
    generated_type = (
        "general_observation"
        if frame.narrative_mode == "actuality_reflection"
        else frame.narrative_mode
    )
    values = {
        "title": "关系不是评判赛",
        "natural_guide": "把不同位置放在同一张纸上看，而不是忙着判输赢。",
        "release_caption": "你更愿意给关系留出哪一种空白？",
        "persona_observation": "边界像标点，停顿不等于敌意。",
        "audience_return": "先辨认分歧，再决定是否回应。",
        "brand_account_link": "这个账号愿意把复杂关系讲得不急不躁。",
        "spoken": "两种在意可以同时存在，不必把任何一方写成反派。",
    }
    scene_for_slot = {
        "title": "s-cover",
        "natural_guide": "s-body",
        "persona_observation": "s-body",
        "spoken": "s-body",
        "release_caption": "s-tail",
        "audience_return": "s-tail",
        "brand_account_link": "s-tail",
    }
    blocks: list[dict[str, object]] = []
    for slot, value in values.items():
        block_id = f"b-{slot}"
        scene_ids = [scene_for_slot[slot]]
        if slot == "spoken" and frame.user_facts:
            scene_ids.append("s-fact")
        blocks.append(
            {
                "block_id": block_id,
                "block_type": generated_type,
                "slot": slot,
                "text": _mode_text(frame.narrative_mode, value),
                "source_refs": ["source:brand_baseline"],
                "linked_scene_ids": scene_ids,
            }
        )
    actual_ids = [
        f"actuality:{index}"
        for index, _ in enumerate(frame.user_facts, start=1)
    ]
    scenes: list[dict[str, object]] = [
        {
            "step_id": "s-cover",
            "purpose": "cover",
            "actor_refs": [],
            "resource_refs": ["resource:original_composition"],
            "action_text": "两组色块保留距离，标题落在中间留白。",
            "sound_text": "",
            "production_note": "使用原创排版和留白。",
            "block_refs": ["b-title"],
        },
        {
            "step_id": "s-body",
            "purpose": "scene",
            "actor_refs": [],
            "resource_refs": ["resource:original_composition"],
            "action_text": "抽象标点沿阅读顺序展开，不模拟现实家庭现场。",
            "sound_text": "仅使用不指向现实场景的原创节奏。",
            "production_note": "使用原创图形和文字层级。",
            "block_refs": [
                "b-natural_guide",
                "b-persona_observation",
                "b-spoken",
            ],
        },
        {
            "step_id": "s-tail",
            "purpose": "scene",
            "actor_refs": [],
            "resource_refs": ["resource:original_composition"],
            "action_text": "末段缩小色块并留下开放结尾。",
            "sound_text": "",
            "production_note": "使用原创排版收束阅读节奏。",
            "block_refs": [
                "b-release_caption",
                "b-audience_return",
                "b-brand_account_link",
            ],
        },
    ]
    if actual_ids:
        scenes.append(
            {
                "step_id": "s-fact",
                "purpose": "scene",
                "actor_refs": [],
                "resource_refs": ["resource:original_composition"],
                "action_text": "原句以纯文字进入阅读顺序，不重演现实现场。",
                "sound_text": "",
                "production_note": "只用原创排版承载用户原句。",
                "block_refs": ["b-spoken", *actual_ids],
            }
        )
    return {
        "speaker_ref": "speaker:brand_account",
        "blocks": blocks,
        "spoken_order": ["b-spoken", *actual_ids],
        "scene_steps": scenes,
    }


def _targets(
    core: dict[str, object],
    frame: NarrativeFrame,
) -> list[tuple[str, str, str]]:
    blocks = core["blocks"]
    scenes = core["scene_steps"]
    assert isinstance(blocks, list)
    assert isinstance(scenes, list)
    targets = [
        (str(block["block_id"]), "block", str(block["text"]))
        for block in blocks
        if isinstance(block, dict)
    ]
    targets.extend(
        (
            f"actuality:{index}",
            "block",
            fact.exact_text,
        )
        for index, fact in enumerate(frame.user_facts, start=1)
    )
    for scene in scenes:
        assert isinstance(scene, dict)
        text = "\n".join(
            str(scene[key])
            for key in ("action_text", "sound_text", "production_note")
            if scene.get(key)
        )
        targets.append((str(scene["step_id"]), "scene", text))
    return targets


def _observations(
    core: dict[str, object],
    frame: NarrativeFrame,
    *,
    changes: dict[str, dict[str, object]] | None = None,
    omitted: frozenset[str] = frozenset(),
) -> dict[str, object]:
    changes = changes or {}
    observations: list[dict[str, object]] = []
    for target_id, target_kind, text in _targets(core, frame):
        if target_id in omitted:
            continue
        if target_id.startswith("actuality:"):
            binding = "user_actuality"
        elif (
            target_kind == "scene"
            or frame.narrative_mode == "actuality_reflection"
        ):
            binding = "general_observation"
        else:
            binding = frame.narrative_mode
        observation: dict[str, object] = {
            "id": target_id,
            "target_kind": target_kind,
            "text_spans": [text],
            "people": [],
            "relationships": [],
            "actions_or_events": [],
            "dialogue": [],
            "motives": [],
            "causes": [],
            "results": [],
            "times": [],
            "locations": [],
            "possessions": [],
            "reality_binding": binding,
            "resource_refs": (
                ["resource:original_composition"]
                if target_kind == "scene"
                else []
            ),
            "dramatization_disclosure_spans": (
                ["情境演绎"]
                if binding == "dramatization"
                else []
            ),
            "instruction_conflicts": [],
            "uncertain": False,
        }
        observation.update(changes.get(target_id, {}))
        claims: list[dict[str, str]] = []
        for category in (
            "people",
            "relationships",
            "actions_or_events",
            "dialogue",
            "motives",
            "causes",
            "results",
            "times",
            "locations",
            "possessions",
        ):
            values = observation.pop(category)
            assert isinstance(values, list)
            claims.extend(
                {"category": category, "span": str(value)}
                for value in values
            )
        observation["claims"] = claims
        observations.append(observation)
    return {"observations": observations}


def _payload_prompts() -> list[str]:
    prompts: list[str] = []
    for request in FakeClient.requests:
        payload = request["json"]
        assert isinstance(payload, dict)
        messages = payload["messages"]
        assert isinstance(messages, list)
        user_message = messages[1]
        assert isinstance(user_message, dict)
        prompts.append(str(user_message["content"]))
    return prompts


def test_conversation_intake_preserves_exact_spans_and_mode() -> None:
    message = "今天店里忙了一天，回家还因为谁洗碗拌了两句。帮我发条小红书。"
    FakeClient.responses = [
        _completion(
            {
                "kind": "ready",
                "message": "好，我保留这段原话，其他由我来完成。",
                "user_premises": [message],
                "user_fact_spans": [
                    "今天店里忙了一天，回家还因为谁洗碗拌了两句。"
                ],
                "narrative_mode": "actuality_reflection",
                "system_creative_plan": "从忙乱后的微小摩擦切入，形成不归因于任何人的一般观察。",
                "primary_value": "建立人格",
            }
        )
    ]
    decision = _generator().collaborate(
        ConversationInput(
            message=message,
            history=(),
            brand=_brand(),
            products=(),
            target="xiaohongshu_graphic",
        )
    )
    assert decision.disposition == "ready"
    assert decision.user_premises == (message,)
    assert decision.user_fact_spans == (
        "今天店里忙了一天，回家还因为谁洗碗拌了两句。",
    )
    assert decision.narrative_mode == "actuality_reflection"


@pytest.mark.parametrize(
    ("message", "mode", "facts"),
    (
        (
            "帮我写条婆媳主题的小红书。",
            "general_observation",
            [],
        ),
        (
            "如果两个人都先停十秒再回应，把这个想法写成小红书。",
            "hypothesis",
            [],
        ),
        (
            "把婆媳关系写成一段明确的情境演绎，不绑定真实人物。",
            "dramatization",
            [],
        ),
    ),
)
def test_conversation_intake_accepts_the_three_nonactual_modes(
    message: str,
    mode: str,
    facts: list[str],
) -> None:
    FakeClient.responses = [
        _completion(
            {
                "kind": "ready",
                "message": "可以，直接开始。",
                "user_premises": [message],
                "user_fact_spans": facts,
                "narrative_mode": mode,
                "system_creative_plan": "自主选择一个安全切口和完整结构。",
                "primary_value": "建立人格",
            }
        )
    ]
    decision = _generator().collaborate(
        ConversationInput(
            message,
            (),
            _brand(),
            (),
            "xiaohongshu_graphic",
            explicit_narrative_mode=(
                "dramatization" if mode == "dramatization" else None
            ),
        )
    )
    assert decision.narrative_mode == mode
    assert decision.user_fact_spans == ()


def test_conversation_question_must_bind_one_user_fact_gap() -> None:
    message = "把我去年创业最困难的那个月写出来。"
    FakeClient.responses = [
        _completion(
            {
                "kind": "question",
                "message": "那个月具体发生了哪一件最让你觉得困难的事？",
                "missing_fact_span": "去年创业最困难的那个月",
            }
        )
    ]
    decision = _generator().collaborate(
        ConversationInput(
            message,
            (ConversationTurn("assistant", "你可以只说最关键的一件事。"),),
            _brand(),
            (),
            "xiaohongshu_graphic",
        )
    )
    assert decision.disposition == "question"
    assert "具体发生" in decision.message


def test_conversation_rejects_synthetic_or_mode_drifted_spans() -> None:
    message = "帮我写条婆媳主题的小红书。"
    FakeClient.responses = [
        _completion(
            {
                "kind": "ready",
                "message": "开始。",
                "user_premises": [message],
                "user_fact_spans": ["婆婆曾经带过孩子"],
                "narrative_mode": "actuality_reflection",
                "system_creative_plan": "写关系。",
                "primary_value": "建立人格",
            }
        )
    ]
    with pytest.raises(GenerationFailed, match="事实跨度不存在"):
        _generator().collaborate(
            ConversationInput(
                message,
                (),
                _brand(),
                (),
                "xiaohongshu_graphic",
            )
        )


def test_writer_cannot_author_or_modify_service_actuality() -> None:
    frame = new_frame(
        "actuality_reflection",
        ("今天店里忙了一天，回家还因为谁洗碗拌了两句。",),
        (),
    )
    request = _request(frame)
    core = _core(frame)
    blocks = core["blocks"]
    assert isinstance(blocks, list)
    blocks.append(
        {
            "block_id": "writer-actuality",
            "block_type": "actuality_source",
            "slot": "spoken",
            "text": "丈夫最后去洗了碗。",
            "source_refs": ["source:user_actuality:1"],
            "linked_scene_ids": ["s-body"],
        }
    )
    FakeClient.responses = [_completion(core)]
    with pytest.raises(GenerationFailed, match="类型化成品不完整"):
        _generator().generate(request)


@pytest.mark.parametrize(
    "mode",
    (
        "general_observation",
        "actuality_reflection",
        "hypothesis",
        "dramatization",
    ),
)
def test_full_candidate_is_independently_reviewed_and_digest_locked(
    mode: str,
) -> None:
    frame = new_frame(
        mode,  # type: ignore[arg-type]
        (
            ("今天店里忙了一天，回家还因为谁洗碗拌了两句。",)
            if mode == "actuality_reflection"
            else ()
        ),
        (),
    )
    request = _request(frame)
    core = _core(frame)
    FakeClient.responses = [
        _completion(core, 100),
        _completion(_observations(core, frame), 50),
    ]
    artifact = _generator().generate(request)
    assert isinstance(artifact.production, GraphicProductionBundle)
    assert artifact.reviewed_digest == visible_digest(
        artifact.outline, artifact.body
    )
    for fact in frame.user_facts:
        assert fact.exact_text in artifact.body
    assert artifact.provider_usage == {"total_tokens": 150}
    prompts = _payload_prompts()
    assert len(prompts) == 2
    assert "最终完整可见成品" in prompts[1]
    assert '"block_type"' not in prompts[1]
    assert '"source_refs"' not in prompts[1]
    assert core["blocks"] != prompts[1]


def test_reviewer_must_cover_every_target_with_an_existing_span() -> None:
    frame = new_frame("general_observation", (), ())
    core = _core(frame)
    bad = _observations(
        core,
        frame,
        changes={"b-spoken": {"text_spans": ["并不存在的句子"]}},
        omitted=frozenset({"s-cover"}),
    )
    FakeClient.responses = [
        _completion(core),
        _completion(bad),
    ]
    with pytest.raises(GenerationFailed, match="Reviewer 观察不完整"):
        _generator().generate(_request(frame))
    assert len(FakeClient.requests) == 2


def test_reviewer_cannot_claim_coverage_with_only_a_partial_target_span() -> None:
    frame = new_frame("general_observation", (), ())
    core = _core(frame)
    partial = _observations(
        core,
        frame,
        changes={"b-spoken": {"text_spans": ["两种在意"]}},
    )
    FakeClient.responses = [
        _completion(core),
        _completion(partial),
    ]
    with pytest.raises(GenerationFailed, match="Reviewer 观察不完整"):
        _generator().generate(_request(frame))
    assert len(FakeClient.requests) == 2


def test_one_repair_replaces_whole_block_and_all_linked_scenes_then_rereviews() -> None:
    frame = new_frame("general_observation", (), ())
    core = _core(frame)
    bad = _observations(
        core,
        frame,
        changes={
            "b-spoken": {
                "people": ["任何一方"],
                "relationships": ["两种在意"],
                "actions_or_events": ["写成反派"],
            }
        },
    )
    blocks = core["blocks"]
    scenes = core["scene_steps"]
    assert isinstance(blocks, list)
    assert isinstance(scenes, list)
    repaired_block = dict(
        next(
            block
            for block in blocks
            if isinstance(block, dict) and block["block_id"] == "b-spoken"
        )
    )
    repaired_block["text"] = "边界不是结论，它只是让两种在意都有位置。"
    repaired_scene = dict(
        next(
            scene
            for scene in scenes
            if isinstance(scene, dict) and scene["step_id"] == "s-body"
        )
    )
    repaired_scene["action_text"] = "两条抽象线各自展开，最后保持一段留白。"
    repaired_core = {
        **core,
        "blocks": [
            repaired_block if block["block_id"] == "b-spoken" else block
            for block in blocks
            if isinstance(block, dict)
        ],
        "scene_steps": [
            repaired_scene if scene["step_id"] == "s-body" else scene
            for scene in scenes
            if isinstance(scene, dict)
        ],
    }
    FakeClient.responses = [
        _completion(core),
        _completion(bad),
        _completion(
            {
                "blocks": [repaired_block],
                "scene_steps": [repaired_scene],
            }
        ),
        _completion(_observations(repaired_core, frame)),
    ]
    artifact = _generator().generate(_request(frame))
    assert repaired_block["text"] in artifact.body
    assert len(artifact.fact_repair_receipts) == 1
    prompts = _payload_prompts()
    assert len(prompts) == 4
    assert "必须完整替换的 blocks" in prompts[2]
    assert '"block_id": "b-spoken"' in prompts[2]
    assert '"step_id": "s-body"' in prompts[2]
    assert "最终完整可见成品" in prompts[3]


def test_second_semantic_failure_closes_without_another_repair() -> None:
    frame = new_frame("general_observation", (), ())
    core = _core(frame)
    bad = _observations(
        core,
        frame,
        changes={
            "b-spoken": {
                "people": ["任何一方"],
                "relationships": ["两种在意"],
                "actions_or_events": ["写成反派"],
            }
        },
    )
    blocks = core["blocks"]
    scenes = core["scene_steps"]
    assert isinstance(blocks, list)
    assert isinstance(scenes, list)
    block = next(
        item
        for item in blocks
        if isinstance(item, dict) and item["block_id"] == "b-spoken"
    )
    scene = next(
        item
        for item in scenes
        if isinstance(item, dict) and item["step_id"] == "s-body"
    )
    FakeClient.responses = [
        _completion(core),
        _completion(bad),
        _completion({"blocks": [block], "scene_steps": [scene]}),
        _completion(bad),
    ]
    with pytest.raises(
        GenerationFailed,
        match="无法在一次叙事块修复内满足",
    ):
        _generator().generate(_request(frame))
    assert len(FakeClient.requests) == 4


def test_product_claims_are_exact_and_never_nearest_match() -> None:
    product = ProductFact(
        sku="ZX-C218",
        display_name="双面短外套",
        facts={
            "material": "棉混纺",
            "colors": ["雾蓝", "米白"],
            "sample_weight_m_grams": 620,
        },
    )
    claims = DeepSeekGenerator._registered_product_claims(product)
    assert "商品编号是 ZX-C218。" in claims
    assert "双面短外套已登记的材质是棉混纺。" in claims
    assert "双面短外套已登记的颜色是雾蓝、米白。" in claims
    assert "双面短外套已登记的M 码当前样衣重量是 620 克。" in claims
    context = BoundaryContext.from_request(
        _request(
            new_frame(
                "general_observation",
                (),
                ("source:product:ZX-C218",),
            ),
            products=(product,),
        ),
        new_frame(
            "general_observation",
            (),
            ("source:product:ZX-C218",),
        ),
    )
    assert not hasattr(DeepSeekGenerator, "_normalize_registered_product_claims")
    assert not hasattr(DeepSeekGenerator, "_bind_rejected_product_claims")
    assert context.exact_product_facts["source:product:ZX-C218"] == frozenset(
        claims
    )


def test_route_and_transport_only_retry_429_or_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeClient.responses = [
        FakeResponse(429, {}, {"Retry-After": "0"}),
        _completion({"primary_value": "建立人格"}),
    ]
    monkeypatch.setattr("src.tool.llm_gateway.deepseek.time.sleep", lambda _: None)
    result = _generator(max_retries=1).route(
        RoutingInput(
            "今天不知道发什么，帮我做条小红书。",
            _brand(),
            (),
        )
    )
    assert result == "brand_life_narrative"
    assert len(FakeClient.requests) == 2


def test_revision_must_change_allowed_expression_not_actuality() -> None:
    frame = new_frame(
        "actuality_reflection",
        ("今天店里忙了一天，回家还因为谁洗碗拌了两句。",),
        (),
    )
    core = _core(frame)
    first_request = _request(frame)
    FakeClient.responses = [
        _completion(core),
        _completion(_observations(core, frame)),
    ]
    first = _generator().generate(first_request)
    FakeClient.responses = [
        _completion(core),
        _completion(_observations(core, frame)),
    ]
    with pytest.raises(GenerationFailed, match="没有实质改变"):
        _generator().generate(
            replace(
                first_request,
                revision_instruction="别讲道理，荒诞一点。",
                prior_saved_body=first.body,
            )
        )


def test_writer_prompt_keeps_private_steering_out_of_fact_sources() -> None:
    frame = new_frame("general_observation", (), ())
    request = replace(
        _request(frame),
        collaboration_note="我平时更喜欢先说结论，再给一个具体例子。",
    )
    context = BoundaryContext.from_request(request, frame)
    prompt = _generator()._writer_prompt(request, frame, context)
    assert request.collaboration_note in prompt
    assert "成品中不得出现它的原文、转述或对它的解释" in prompt
    assert all(
        request.collaboration_note not in description
        for _, description in context.source_registry
    )
