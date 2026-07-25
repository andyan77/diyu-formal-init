from __future__ import annotations

import json
import time
from typing import Any, cast
from uuid import UUID

import httpx
import pytest

from src.brain.platform_directions import direction_for
from src.shared.errors import GenerationFailed
from src.shared.types import (
    ActiveAsset,
    BrandContext,
    GenerationInput,
    GraphicProductionBundle,
    ProductFact,
    VideoProductionBundle,
)
from src.tool.llm_gateway.deepseek import (
    BoundaryContext,
    DeepSeekGenerator,
)


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


@pytest.fixture()
def generation_input() -> GenerationInput:
    return GenerationInput(
        run_id=UUID("00000000-0000-0000-0000-000000000101"),
        task_id=UUID("00000000-0000-0000-0000-000000000102"),
        weak_seed="一家人一定要穿成同款，才算有家庭感吗？",
        primary_product="dressing_decision",
        revision_instruction=None,
        brand=BrandContext(
            "笛语服饰",
            "家庭成员各自成立，也可以自然呼应",
            "先尊重差异，再讨论呼应",
            "真实、克制、有依据",
            "笛语服饰品牌官方账号",
            "当前运营者",
            "笛语服饰",
            "品牌官方 / 品牌定义者",
            "表达品牌判断，不冒充自然人、门店岗位或顾客。",
            "重视真实感受与家庭差异的人。",
            "brand-expression-v1",
            "抖音",
            "视频",
            "一名创作者、一部手机、普通室内环境。",
        ),
        target="douyin_video",
        media_format="video",
        platform_direction=direction_for("douyin_video"),
        active_domain_assets=(
            ActiveAsset(
                "B-001",
                "v1",
                "brand",
                "品牌基线",
                "内容先建立理解和关系，不把生活强行变成卖货。",
            ),
        ),
    )


def _with(request: GenerationInput, **changes: object) -> GenerationInput:
    return GenerationInput(**{**request.__dict__, **changes})


def _claim(
    claim_id: str,
    slot: str,
    text: str,
    basis: str = "brand_viewpoint",
    actuality: str = "non_event",
    source_refs: tuple[str, ...] = ("source:brand_baseline",),
) -> dict[str, object]:
    return {
        "claim_id": claim_id,
        "slot": slot,
        "text": text,
        "basis": basis,
        "actuality": actuality,
        "source_refs": list(source_refs),
    }


def _step(
    step_id: str,
    purpose: str,
    action_text: str,
    claim_refs: tuple[str, ...],
    actor_refs: tuple[str, ...] = (),
    resource_refs: tuple[str, ...] = (),
    sound_text: str = "",
    production_note: str = "",
) -> dict[str, object]:
    return {
        "step_id": step_id,
        "purpose": purpose,
        "actor_refs": list(actor_refs),
        "resource_refs": list(resource_refs),
        "action_text": action_text,
        "sound_text": sound_text,
        "production_note": production_note,
        "claim_refs": list(claim_refs),
    }


def _video_core(
    claims: list[dict[str, object]] | None = None,
    spoken_order: list[str] | None = None,
    steps: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "speaker_ref": "speaker:brand_account",
        "claims": claims
        if claims is not None
        else [
            _claim("c1", "title", "不必穿成同款"),
            _claim(
                "c2", "natural_guide", "从同款是否等于家庭感进入", "user_premise", "non_event", ("source:user_request",)
            ),
            _claim("c3", "viewing_flow", "固定机位完成口播", "conditional_guidance", "non_event"),
            _claim("c4", "release_caption", "你更在意整齐，还是每个人都自在？"),
            _claim("c5", "choice", "先保留每个人舒服的选择", "conditional_guidance", "hypothetical"),
            _claim("c6", "boundary", "如果需要正式合照，再找一个自然呼应点", "conditional_guidance", "hypothetical"),
            _claim("c7", "next_action", "先看每个人愿不愿意这样穿", "conditional_guidance", "hypothetical"),
            _claim("c8", "spoken", "一家人的家庭感，不一定来自穿成同款。"),
            _claim(
                "c9",
                "spoken",
                "我们更愿意先尊重每个人舒服的选择，再找一个自然的呼应点。",
            ),
        ],
        "spoken_order": spoken_order if spoken_order is not None else ["c8", "c9"],
        "scene_steps": steps
        if steps is not None
        else [
            _step(
                "s1",
                "cover",
                "手写标题卡：不必穿成同款。",
                ("c1",),
                resource_refs=("resource:onsite_text",),
            ),
            _step(
                "s2",
                "scene",
                "当前创作者正对手机自然口播。",
                ("c8", "c9"),
                actor_refs=("actor:creator",),
                resource_refs=("resource:phone",),
                sound_text="手机直接收录当前创作者的人声。",
            ),
        ],
    }


def _completion(content: str, tokens: int = 0) -> FakeResponse:
    payload: dict[str, Any] = {"choices": [{"message": {"content": content}}]}
    if tokens:
        payload["usage"] = {"total_tokens": tokens}
    return FakeResponse(200, payload)


def _core_response(core: dict[str, object], tokens: int = 0) -> FakeResponse:
    return _completion(json.dumps(core, ensure_ascii=False), tokens)


def _unit_ids(core: dict[str, object]) -> list[str]:
    claims = core["claims"]
    steps = core["scene_steps"]
    assert isinstance(claims, list) and isinstance(steps, list)
    return [str(entry["claim_id"]) for entry in claims] + [str(entry["step_id"]) for entry in steps]


def _verdicts(
    core: dict[str, object],
    failures: dict[str, tuple[str, ...]] | None = None,
) -> FakeResponse:
    failures = failures or {}
    verdicts = []
    for unit_id in _unit_ids(core):
        entry: dict[str, object] = {"id": unit_id}
        for flag in ("identity_ok", "actuality_ok", "resource_ok", "fact_ok"):
            entry[flag] = flag not in failures.get(unit_id, ())
        verdicts.append(entry)
    return _completion(json.dumps({"verdicts": verdicts}, ensure_ascii=False))


def _repairs(*units: dict[str, object]) -> FakeResponse:
    return _completion(json.dumps({"repairs": list(units)}, ensure_ascii=False))


def _install_fake(monkeypatch: pytest.MonkeyPatch, responses: list[FakeResponse]) -> None:
    FakeClient.responses = responses
    FakeClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeClient)


def _generator() -> DeepSeekGenerator:
    return DeepSeekGenerator(
        "https://compat.example/v1",
        "not-a-real-key",
        "verified-deepseek-model",
    )


def test_generation_prompt_separates_six_input_semantics(
    generation_input: GenerationInput,
) -> None:
    context = BoundaryContext.from_request(generation_input)
    prompt = DeepSeekGenerator._generation_prompt(generation_input, context)

    assert "task_topic_or_request" in prompt
    assert generation_input.weak_seed in prompt
    assert "不是用户亲历" in prompt
    assert "user_presented_actuality" in prompt
    assert "（本次没有。没有列出即为不存在，不得虚构。）" in prompt
    assert "brand_viewpoint" in prompt
    assert generation_input.brand.positioning in prompt
    assert "不证明品牌观察过、经历过或已经执行任何具体事件" in prompt
    assert "confirmed_actuality" in prompt
    assert "无已确认门店事实、无已执行服务、无顾客案例、无家庭事件、无既有照片或素材" in prompt
    assert "method_guidance" in prompt
    assert "不证明任何现实人物、物品、场地或素材存在" in prompt
    assert "allowed_speaker_and_resources" in prompt
    assert "不证明场地内存在家庭成员、顾客、商品、合照、家具或已执行服务" in prompt
    assert "speaker:brand_account" in prompt
    assert "actor:creator" in prompt
    assert "resource:phone" in prompt
    assert "source:user_request" in prompt
    assert "标题、观点、比喻、幽默、节奏、完整口播和互动由你自然创作" in prompt
    assert "B-001" not in prompt
    assert "schema_version" not in prompt


def test_weak_seed_stays_topic_unless_product_requires_near_field_signal(
    generation_input: GenerationInput,
) -> None:
    topic_context = BoundaryContext.from_request(generation_input)
    near_field_context = BoundaryContext.from_request(_with(generation_input, primary_product="local_response"))

    assert topic_context.user_presented_actuality == ""
    assert topic_context.user_actuality_source is None
    assert "source:user_actuality" not in topic_context.source_ids
    assert near_field_context.user_actuality_source == "source:user_actuality"
    assert generation_input.weak_seed in near_field_context.user_presented_actuality


def test_full_pass_compiles_visible_product_from_passed_units(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    core = _video_core()
    _install_fake(monkeypatch, [_core_response(core, tokens=10), _verdicts(core)])

    artifact = _generator().generate(generation_input)

    assert isinstance(artifact.production, VideoProductionBundle)
    spoken = "一家人的家庭感，不一定来自穿成同款。我们更愿意先尊重每个人舒服的选择，再找一个自然的呼应点。"
    assert artifact.production.spoken_lines == spoken
    assert artifact.production.subtitles == spoken
    assert artifact.production.cover_or_first_frame == "手写标题卡：不必穿成同款。"
    assert artifact.production.visual_actions == "当前创作者正对手机自然口播。"
    assert artifact.production.sound_and_production == "手机直接收录当前创作者的人声。"
    assert artifact.production.viewing_flow == "固定机位完成口播"
    assert artifact.production.natural_duration == f"约 {DeepSeekGenerator._natural_spoken_seconds(spoken)} 秒"
    assert artifact.outline == "不必穿成同款"
    assert "标题：不必穿成同款" in artifact.body
    assert "当前选择：先保留每个人舒服的选择" in artifact.body
    assert artifact.fact_repair_receipts == ()
    assert artifact.retry_count == 0
    assert len(FakeClient.requests) == 2


def test_judgement_uses_bounded_config_independent_of_writer(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    core = _video_core()
    _install_fake(monkeypatch, [_core_response(core), _verdicts(core)])

    _generator().generate(generation_input)

    writer_json = FakeClient.requests[0]["json"]
    judge_json = FakeClient.requests[1]["json"]
    assert isinstance(writer_json, dict) and isinstance(judge_json, dict)
    assert writer_json["thinking"] == {"type": "disabled"}
    assert "thinking" not in judge_json
    assert judge_json["temperature"] == 0.0
    assert judge_json["response_format"] == {"type": "json_object"}
    assert judge_json["max_tokens"] == 8192
    judge_prompt = str(judge_json["messages"])
    assert "对下面列出的每一个 id 各返回一条完整判定" in judge_prompt
    assert "identity_ok" in judge_prompt and "actuality_ok" in judge_prompt
    assert "resource_ok" in judge_prompt and "fact_ok" in judge_prompt
    assert "恰好覆盖上面列出的每个 id" in judge_prompt


@pytest.mark.parametrize(
    "mutate",
    [
        lambda verdicts: verdicts[:-1],
        lambda verdicts: [*verdicts, {**verdicts[0], "id": "unknown"}],
        lambda verdicts: [*verdicts, verdicts[0]],
        lambda verdicts: [{**verdicts[0], "identity_ok": "yes"}, *verdicts[1:]],
    ],
)
def test_incomplete_or_drifting_verdict_sets_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
    mutate: Any,
) -> None:
    core = _video_core()
    complete = json.loads(_verdicts(core).json()["choices"][0]["message"]["content"])
    broken = json.dumps({"verdicts": mutate(complete["verdicts"])}, ensure_ascii=False)
    _install_fake(monkeypatch, [_core_response(core), _completion(broken)])

    with pytest.raises(GenerationFailed, match="边界判定返回格式不完整"):
        _generator().generate(generation_input)


def test_legacy_sparse_violations_shape_is_no_longer_accepted(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    core = _video_core()
    _install_fake(
        monkeypatch,
        [_core_response(core), _completion(json.dumps({"violations": []}))],
    )

    with pytest.raises(GenerationFailed, match="边界判定返回格式不完整"):
        _generator().generate(generation_input)


def test_verdict_failure_triggers_one_unit_repair_then_full_rereview(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    unsafe = "让一家三口穿着三套衣服在门店里走动。"
    steps = [
        _step("s1", "cover", "手写标题卡：不必穿成同款。", ("c1",), resource_refs=("resource:onsite_text",)),
        _step(
            "s2",
            "scene",
            unsafe,
            ("c8", "c9"),
            actor_refs=("actor:creator",),
            resource_refs=("resource:phone",),
            sound_text="手机直接收录当前创作者的人声。",
        ),
    ]
    core = _video_core(steps=steps)
    repaired_action = "当前创作者正对手机，用手写关键词辅助口播。"
    _install_fake(
        monkeypatch,
        [
            _core_response(core),
            _verdicts(core, {"s2": ("resource_ok",)}),
            _repairs(
                {
                    "step_id": "s2",
                    "action_text": repaired_action,
                    "sound_text": "手机直接收录当前创作者的人声。",
                    "production_note": "",
                    "actor_refs": ["actor:creator"],
                    "resource_refs": ["resource:phone", "resource:onsite_text"],
                    "claim_refs": ["c8", "c9"],
                }
            ),
            _verdicts(core),
        ],
    )

    artifact = _generator().generate(generation_input)

    assert isinstance(artifact.production, VideoProductionBundle)
    assert artifact.production.visual_actions == repaired_action
    assert unsafe not in artifact.body
    assert {receipt.field for receipt in artifact.fact_repair_receipts} == {"visual_actions"}
    assert len(FakeClient.requests) == 4
    repair_json = FakeClient.requests[2]["json"]
    assert isinstance(repair_json, dict)
    repair_prompt = str(repair_json["messages"])
    assert "unsupported_resource" in repair_prompt
    assert "只修复下列单元" in repair_prompt
    assert "固定安全文案" in repair_prompt


def test_repair_fails_closed_when_the_same_unit_still_fails(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    core = _video_core()
    unsafe: dict[str, object] = {
        "claim_id": "c8",
        "text": "作为孩子的妈妈，我每天都这样选择。",
        "basis": "brand_viewpoint",
        "actuality": "non_event",
        "source_refs": ["source:brand_baseline"],
    }
    _install_fake(
        monkeypatch,
        [
            _core_response(core),
            _verdicts(core, {"c8": ("identity_ok",)}),
            _repairs(unsafe),
            _verdicts(core, {"c8": ("identity_ok",)}),
        ],
    )

    with pytest.raises(GenerationFailed, match="一次单元修复"):
        _generator().generate(generation_input)

    assert len(FakeClient.requests) == 4


def test_repair_must_cover_exactly_the_violating_units(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    core = _video_core()
    _install_fake(
        monkeypatch,
        [
            _core_response(core),
            _verdicts(core, {"c8": ("actuality_ok",)}),
            _repairs(
                {
                    "claim_id": "c9",
                    "text": "换了一个没被要求修复的单元。",
                    "basis": "brand_viewpoint",
                    "actuality": "non_event",
                    "source_refs": ["source:brand_baseline"],
                }
            ),
        ],
    )

    with pytest.raises(GenerationFailed, match="修复返回格式不完整"):
        _generator().generate(generation_input)


def test_closed_world_rejects_unregistered_source_before_any_model_verdict(
    generation_input: GenerationInput,
) -> None:
    context = BoundaryContext.from_request(generation_input)
    core = _generator()._parse_core(
        generation_input,
        context,
        _video_core(
            claims=[
                _claim("c1", "title", "不必穿成同款"),
                _claim("c2", "natural_guide", "从同款进入", "user_premise", "non_event", ("source:user_request",)),
                _claim("c3", "viewing_flow", "固定机位完成口播", "conditional_guidance", "non_event"),
                _claim("c4", "release_caption", "你更在意整齐，还是自在？"),
                _claim("c5", "choice", "先保留舒服的选择", "conditional_guidance", "hypothetical"),
                _claim("c6", "boundary", "需要合照时再找呼应点", "conditional_guidance", "hypothetical"),
                _claim("c7", "next_action", "先问每个人的意愿", "conditional_guidance", "hypothetical"),
                _claim(
                    "c8",
                    "spoken",
                    "上周有位顾客带孩子来店里试穿。",
                    "user_premise",
                    "user_presented_actual",
                    ("source:store_visit",),
                ),
                _claim("c9", "spoken", "我们更愿意先尊重每个人舒服的选择。"),
            ]
        ),
    )

    issues = DeepSeekGenerator._closed_world_issues(context, core)

    reasons = {(issue.unit_id, issue.reason_code) for issue in issues}
    assert ("c8", "factual_conflict") in reasons
    assert ("c8", "invented_actuality") in reasons


def test_closed_world_blocks_viewpoint_or_guidance_marked_as_happened(
    generation_input: GenerationInput,
) -> None:
    context = BoundaryContext.from_request(generation_input)
    claims = [
        _claim("c1", "title", "沉默也值得被尊重"),
        _claim("c2", "natural_guide", "从安静浏览进入", "user_premise", "non_event", ("source:user_request",)),
        _claim("c3", "viewing_flow", "固定机位完成口播", "conditional_guidance", "non_event"),
        _claim("c4", "release_caption", "你也喜欢自己安静看看吗？"),
        _claim("c5", "choice", "先给自己留判断空间", "conditional_guidance", "hypothetical"),
        _claim("c6", "boundary", "需要帮助时再开口", "conditional_guidance", "hypothetical"),
        _claim("c7", "next_action", "下次先自己看看", "conditional_guidance", "hypothetical"),
        _claim(
            "c8",
            "spoken",
            "我们的门店已经要求店员不主动打扰顾客。",
            "brand_viewpoint",
            "user_presented_actual",
        ),
        _claim("c9", "spoken", "我们主张给每个人留出安静判断的空间。"),
    ]
    core = _generator()._parse_core(generation_input, context, _video_core(claims=claims))

    issues = DeepSeekGenerator._closed_world_issues(context, core)

    assert ("c8", "invented_actuality") in {(issue.unit_id, issue.reason_code) for issue in issues}
    assert not any(issue.unit_id == "c9" for issue in issues)


def test_closed_world_blocks_confirmed_fact_that_is_not_a_recorded_state(
    generation_input: GenerationInput,
) -> None:
    context = BoundaryContext.from_request(generation_input)
    claims = [
        _claim("c1", "title", "不必穿成同款"),
        _claim("c2", "natural_guide", "从同款进入", "user_premise", "non_event", ("source:user_request",)),
        _claim("c3", "viewing_flow", "固定机位完成口播", "conditional_guidance", "non_event"),
        _claim("c4", "release_caption", "你更在意整齐，还是自在？"),
        _claim("c5", "choice", "先保留舒服的选择", "conditional_guidance", "hypothetical"),
        _claim("c6", "boundary", "需要合照时再找呼应点", "conditional_guidance", "hypothetical"),
        _claim("c7", "next_action", "先问每个人的意愿", "conditional_guidance", "hypothetical"),
        _claim(
            "c8", "spoken", "我们见过很多家庭这样搭配。", "confirmed_fact", "hypothetical", ("source:organization",)
        ),
        _claim("c9", "spoken", "我们主张先尊重每个人的感受。"),
    ]
    core = _generator()._parse_core(generation_input, context, _video_core(claims=claims))

    issues = DeepSeekGenerator._closed_world_issues(context, core)

    assert ("c8", "invented_actuality") in {(issue.unit_id, issue.reason_code) for issue in issues}


def test_closed_world_accepts_mixed_registered_refs_with_one_carrying_source(
    generation_input: GenerationInput,
) -> None:
    """A viewpoint naming the brand cites the organization record too; that is legal."""
    context = BoundaryContext.from_request(generation_input)
    claims = [
        _claim(
            "c1",
            "title",
            "沉默也值得被尊重",
            "brand_viewpoint",
            "non_event",
            ("source:user_request", "source:brand_baseline"),
        ),
        _claim("c2", "natural_guide", "从安静浏览进入", "user_premise", "non_event", ("source:user_request",)),
        _claim("c3", "viewing_flow", "固定机位完成口播", "conditional_guidance", "non_event"),
        _claim("c4", "release_caption", "你也喜欢自己安静看看吗？"),
        _claim("c5", "choice", "先给自己留判断空间", "conditional_guidance", "hypothetical"),
        _claim("c6", "boundary", "需要帮助时再开口", "conditional_guidance", "hypothetical"),
        _claim("c7", "next_action", "下次先自己看看", "conditional_guidance", "hypothetical"),
        _claim(
            "c8",
            "spoken",
            "笛语服饰认为，家庭成员各自成立，也可以自然呼应。",
            "brand_viewpoint",
            "non_event",
            ("source:brand_baseline", "source:organization"),
        ),
        _claim(
            "c9",
            "spoken",
            "笛语服饰品牌官方账号真实存在。",
            "confirmed_fact",
            "non_event",
            ("source:organization", "source:brand_baseline"),
        ),
    ]
    core = _generator()._parse_core(generation_input, context, _video_core(claims=claims))

    assert DeepSeekGenerator._closed_world_issues(context, core) == ()


def test_closed_world_requires_one_carrying_source_for_the_basis(
    generation_input: GenerationInput,
) -> None:
    context = BoundaryContext.from_request(generation_input)
    claims = [
        *cast("list[dict[str, object]]", _video_core()["claims"])[:7],
        _claim(
            "c8",
            "spoken",
            "这是被当成已确认事实的品牌观点。",
            "confirmed_fact",
            "non_event",
            ("source:brand_baseline",),
        ),
        _claim("c9", "spoken", "我们主张先尊重每个人的感受。"),
    ]
    core = _generator()._parse_core(generation_input, context, _video_core(claims=claims))

    issues = DeepSeekGenerator._closed_world_issues(context, core)

    assert ("c8", "factual_conflict") in {(issue.unit_id, issue.reason_code) for issue in issues}


def test_deterministic_check_catches_unit_id_leak_in_visible_text(
    generation_input: GenerationInput,
) -> None:
    context = BoundaryContext.from_request(generation_input)
    steps = [
        _step("s1", "cover", "手写标题卡。", ("c1",), resource_refs=("resource:onsite_text",)),
        _step(
            "s2",
            "scene",
            "当前创作者正对手机自然口播。",
            ("c8", "c9"),
            actor_refs=("actor:creator",),
            resource_refs=("resource:phone",),
            sound_text="创作者口播（对应c8）。",
        ),
    ]
    core = _generator()._parse_core(generation_input, context, _video_core(steps=steps))

    issues = DeepSeekGenerator._deterministic_unit_issues(context, core)

    assert ("s2", "factual_conflict") in {(issue.unit_id, issue.reason_code) for issue in issues}
    assert "c8" in {issue.fragment for issue in issues}


@pytest.mark.parametrize(
    "shorthand",
    [
        "创作者口播：c8、c9内容",
        "口播内容：c8、c9",
        "口播：c8、c9 的内容",
    ],
)
def test_pure_claim_reference_sound_text_resolves_to_spoken_lines(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
    shorthand: str,
) -> None:
    steps = [
        _step("s1", "cover", "手写标题卡：不必穿成同款。", ("c1",), resource_refs=("resource:onsite_text",)),
        _step(
            "s2",
            "scene",
            "当前创作者正对手机自然口播。",
            ("c8", "c9"),
            actor_refs=("actor:creator",),
            resource_refs=("resource:phone",),
            sound_text=shorthand,
        ),
    ]
    core = _video_core(steps=steps)
    _install_fake(monkeypatch, [_core_response(core), _verdicts(core)])

    artifact = _generator().generate(generation_input)

    spoken = "一家人的家庭感，不一定来自穿成同款。我们更愿意先尊重每个人舒服的选择，再找一个自然的呼应点。"
    assert isinstance(artifact.production, VideoProductionBundle)
    assert artifact.production.sound_and_production == f"创作者口播：{spoken}"
    assert "c8" not in artifact.body and "c9" not in artifact.body
    assert artifact.fact_repair_receipts == ()
    assert len(FakeClient.requests) == 2


def test_sound_reference_outside_step_claim_refs_still_fails_closed(
    generation_input: GenerationInput,
) -> None:
    context = BoundaryContext.from_request(generation_input)
    steps = [
        _step("s1", "cover", "手写标题卡。", ("c1",), resource_refs=("resource:onsite_text",)),
        _step(
            "s2",
            "scene",
            "当前创作者正对手机自然口播。",
            ("c8",),
            actor_refs=("actor:creator",),
            resource_refs=("resource:phone",),
            sound_text="创作者口播：c8、c9内容",
        ),
    ]
    core = _generator()._parse_core(generation_input, context, _video_core(steps=steps))

    issues = DeepSeekGenerator._deterministic_unit_issues(context, core)

    assert ("s2", "factual_conflict") in {(issue.unit_id, issue.reason_code) for issue in issues}


def test_repaired_step_with_claim_reference_shorthand_is_also_resolved(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    bad_steps = [
        _step("s1", "cover", "手写标题卡：不必穿成同款。", ("c1",), resource_refs=("resource:onsite_text",)),
        _step(
            "s2",
            "scene",
            "当前创作者正对手机自然口播。",
            ("c8", "c9"),
            actor_refs=("actor:creator",),
            resource_refs=("resource:phone",),
            sound_text="创作者口播（对应c8）。",
        ),
    ]
    core = _video_core(steps=bad_steps)
    repaired_step = _step(
        "s2",
        "scene",
        "当前创作者正对手机自然口播。",
        ("c8", "c9"),
        actor_refs=("actor:creator",),
        resource_refs=("resource:phone",),
        sound_text="口播：c8、c9 的内容",
    )
    _install_fake(
        monkeypatch,
        [
            _core_response(core),
            _verdicts(core),
            _repairs(repaired_step),
            _verdicts(core),
        ],
    )

    artifact = _generator().generate(generation_input)

    spoken = "一家人的家庭感，不一定来自穿成同款。我们更愿意先尊重每个人舒服的选择，再找一个自然的呼应点。"
    assert isinstance(artifact.production, VideoProductionBundle)
    assert artifact.production.sound_and_production == f"创作者口播：{spoken}"
    assert "c8" not in artifact.body
    assert len(FakeClient.requests) == 4


def test_scene_steps_only_reference_registered_actors_and_resources(
    generation_input: GenerationInput,
) -> None:
    context = BoundaryContext.from_request(generation_input)
    steps = [
        _step("s1", "cover", "手写标题卡。", ("c1",), resource_refs=("resource:onsite_text",)),
        _step(
            "s2",
            "scene",
            "妈妈牵着孩子在门店里走动。",
            ("c8",),
            actor_refs=("actor:topic_mother",),
            resource_refs=("resource:store_scene",),
            sound_text="脚步声。",
        ),
        _step(
            "s3",
            "scene",
            "当前创作者正对手机自然口播。",
            ("c9",),
            actor_refs=("actor:creator",),
            resource_refs=("resource:phone",),
            sound_text="人声。",
        ),
    ]
    core = _generator()._parse_core(generation_input, context, _video_core(steps=steps))

    issues = DeepSeekGenerator._closed_world_issues(context, core)

    assert {(issue.unit_id, issue.reason_code) for issue in issues} == {("s2", "unsupported_resource")}


def test_structural_core_failures_get_exactly_one_regeneration(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    broken = dict(_video_core())
    del broken["scene_steps"]
    core = _video_core()
    _install_fake(
        monkeypatch,
        [
            _core_response(broken),
            _core_response(core),
            _verdicts(core),
        ],
    )

    artifact = _generator().generate(generation_input)

    assert artifact.retry_count == 1
    assert len(FakeClient.requests) == 3


@pytest.mark.parametrize(
    "mutate",
    [
        lambda core: core.update(speaker_ref="speaker:store_manager"),
        lambda core: core.update(spoken_order=["c8"]),
        lambda core: core.update(spoken_order=["c8", "c9", "c9"]),
        lambda core: core["claims"].append(_claim("c1", "spoken", "重复 id")),
        lambda core: core["claims"].pop(0),
        lambda core: core["scene_steps"].pop(0),
        lambda core: core["claims"].append(_claim("c10", "surprise_slot", "未知职责")),
    ],
)
def test_parse_core_rejects_structural_drift(
    generation_input: GenerationInput,
    mutate: Any,
) -> None:
    context = BoundaryContext.from_request(generation_input)
    core = _video_core()
    mutate(core)

    with pytest.raises((TypeError, ValueError)):
        _generator()._parse_core(generation_input, context, core)


def test_deterministic_unit_checks_keep_identifiers_and_values_exact(
    generation_input: GenerationInput,
) -> None:
    product = ProductFact(
        "ZX-C218",
        {
            "category": "double-faced short coat",
            "colors": ["炭灰面", "深绿面"],
            "sample_weight_m_grams": 960,
        },
    )
    request = _with(generation_input, products=(product,))
    context = BoundaryContext.from_request(request)
    good_claims = [
        _claim("c1", "title", "炭灰面"),
        _claim("c2", "natural_guide", "从当前样衣进入", "user_premise", "non_event", ("source:user_request",)),
        _claim("c3", "viewing_flow", "固定机位完成口播", "conditional_guidance", "non_event"),
        _claim("c4", "release_caption", "想看哪一面？"),
        _claim("c5", "choice", "先看两面的完整外观", "conditional_guidance", "hypothetical"),
        _claim("c6", "boundary", "如果要正式场合再定", "conditional_guidance", "hypothetical"),
        _claim("c7", "next_action", "翻面看看", "conditional_guidance", "hypothetical"),
        _claim(
            "c8",
            "spoken",
            "当前商品 ZX-C218 的样衣记录为960克。",
            "confirmed_fact",
            "non_event",
            ("source:product:ZX-C218",),
        ),
        _claim("c9", "spoken", "我们主张先看真实感受。"),
    ]
    bad_claims = [
        *good_claims[:7],
        _claim(
            "c8",
            "spoken",
            "当前商品 ZX-B999 的样衣记录为999克，颜色是红色；联系 test@example.com，见 source:brand_baseline。",
            "confirmed_fact",
            "non_event",
            ("source:product:ZX-C218",),
        ),
        good_claims[8],
    ]
    good_core = _generator()._parse_core(request, context, _video_core(claims=good_claims))
    bad_core = _generator()._parse_core(request, context, _video_core(claims=bad_claims))

    assert DeepSeekGenerator._deterministic_unit_issues(context, good_core) == ()
    fragments = {issue.fragment for issue in DeepSeekGenerator._deterministic_unit_issues(context, bad_core)}
    assert {"ZX-B999", "999克", "红色", "test@example.com"} <= fragments
    assert any(fragment.startswith("source:") for fragment in fragments)


def test_fixed_duration_repairs_the_copy_instead_of_only_the_label(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    fixed_brand = BrandContext(
        **{
            **generation_input.brand.__dict__,
            "production_conditions": "一人一部手机，固定 8 秒。",
        }
    )
    request = _with(generation_input, brand=fixed_brand)
    long_core = _video_core(
        claims=[
            *_video_core()["claims"][:7],  # type: ignore[index]
            _claim("c8", "spoken", "这是必须真实缩短的完整口播。" * 6),
            _claim("c9", "spoken", "这一段也要跟着一起收短。" * 6),
        ]
    )
    short_c8 = "先尊重差异。"
    short_c9 = "再找呼应。"
    _install_fake(
        monkeypatch,
        [
            _core_response(long_core),
            _verdicts(long_core),
            _repairs(
                {
                    "claim_id": "c8",
                    "text": short_c8,
                    "basis": "brand_viewpoint",
                    "actuality": "non_event",
                    "source_refs": ["source:brand_baseline"],
                },
                {
                    "claim_id": "c9",
                    "text": short_c9,
                    "basis": "brand_viewpoint",
                    "actuality": "non_event",
                    "source_refs": ["source:brand_baseline"],
                },
            ),
            _verdicts(long_core),
        ],
    )

    artifact = _generator().generate(request)

    assert isinstance(artifact.production, VideoProductionBundle)
    assert artifact.production.spoken_lines == short_c8 + short_c9
    assert artifact.production.natural_duration == "8 秒"
    assert artifact.production.subtitles == short_c8 + short_c9
    assert {receipt.field for receipt in artifact.fact_repair_receipts} == {"spoken_lines"}
    repair_json = FakeClient.requests[2]["json"]
    assert isinstance(repair_json, dict)
    assert "media_contract" in str(repair_json["messages"])


def test_natural_duration_uses_at_most_four_readable_characters_per_second(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    core = _video_core()
    _install_fake(monkeypatch, [_core_response(core), _verdicts(core)])

    artifact = _generator().generate(generation_input)

    assert isinstance(artifact.production, VideoProductionBundle)
    spoken = artifact.production.spoken_lines
    seconds = int(artifact.production.natural_duration.removeprefix("约 ").removesuffix(" 秒"))
    readable = len(
        [char for char in spoken if "一" <= char <= "鿿"],
    )
    assert seconds >= (readable + 3) // 4
    assert seconds == DeepSeekGenerator._natural_spoken_seconds(spoken)


def test_graphic_core_compiles_reading_chain(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    request = _with(
        generation_input,
        target="xiaohongshu_graphic",
        media_format="graphic",
        platform_direction=direction_for("xiaohongshu_graphic"),
    )
    claims = [
        _claim("c1", "title", "不必穿成同款"),
        _claim("c2", "natural_guide", "从同款进入", "user_premise", "non_event", ("source:user_request",)),
        _claim("c3", "release_caption", "你更在意整齐，还是自在？"),
        _claim("c4", "choice", "先保留舒服的选择", "conditional_guidance", "hypothetical"),
        _claim("c5", "boundary", "需要合照时再找呼应点", "conditional_guidance", "hypothetical"),
        _claim("c6", "next_action", "先问每个人的意愿", "conditional_guidance", "hypothetical"),
        _claim("c7", "spoken", "家庭感不一定来自同款。"),
        _claim("c8", "spoken", "先尊重差异，再找自然呼应。"),
    ]
    steps = [
        _step(
            "s1",
            "cover",
            "手写标题卡特写。",
            ("c1",),
            resource_refs=("resource:onsite_text",),
            production_note="自然光拍摄字卡。",
        ),
        _step(
            "s2",
            "scene",
            "创作者手持字卡示意两种选择。",
            ("c7",),
            actor_refs=("actor:creator",),
            resource_refs=("resource:onsite_text",),
            production_note="同一机位连拍。",
        ),
        _step(
            "s3",
            "scene",
            "屏幕文字总结下一步。",
            ("c8",),
            resource_refs=("resource:onsite_text",),
        ),
    ]
    core: dict[str, object] = {
        "speaker_ref": "speaker:brand_account",
        "claims": claims,
        "spoken_order": ["c7", "c8"],
        "scene_steps": steps,
    }
    _install_fake(monkeypatch, [_core_response(core), _verdicts(core)])

    artifact = _generator().generate(request)

    assert isinstance(artifact.production, GraphicProductionBundle)
    assert artifact.production.hero_image == "手写标题卡特写。"
    assert artifact.production.image_sequence == ("第1张：创作者手持字卡示意两种选择。第2张：屏幕文字总结下一步。")
    assert artifact.production.full_body == "家庭感不一定来自同款。先尊重差异，再找自然呼应。"
    assert artifact.production.layout_and_production == "自然光拍摄字卡。同一机位连拍。"
    assert "首图方案" in artifact.body


def test_visual_only_story_derives_duration_from_scene_steps(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    product = ProductFact("ZX-C218", {"category": "double-faced short coat", "colors": ["炭灰面", "深绿面"]})
    request = _with(generation_input, primary_product="visual_styling_story", products=(product,))
    claims = [
        _claim("c1", "title", "两面各有重音"),
        _claim("c2", "natural_guide", "从翻面进入", "user_premise", "non_event", ("source:user_request",)),
        _claim("c3", "viewing_flow", "跟随翻面动作看完", "conditional_guidance", "non_event"),
        _claim("c4", "release_caption", "你先看哪一面？"),
        _claim(
            "c5",
            "real_product_anchor",
            "当前商品 ZX-C218 两面外观完整。",
            "confirmed_fact",
            "non_event",
            ("source:product:ZX-C218",),
        ),
        _claim("c6", "visible_styling_proposition", "同一件外套翻面换重音", "conditional_guidance", "hypothetical"),
        _claim("c7", "visual_dependency", "翻面动作在画面中完成", "conditional_guidance", "hypothetical"),
        _claim("c8", "spoken", "无口播、无对白、无解说"),
    ]
    steps = [
        _step("s1", "cover", "外套炭灰面平铺特写。", ("c1",), resource_refs=("resource:product:ZX-C218",)),
        _step(
            "s2",
            "scene",
            "创作者把外套翻面，展示深绿面。",
            ("c6",),
            actor_refs=("actor:creator",),
            resource_refs=("resource:product:ZX-C218", "resource:phone"),
            sound_text="环境底噪。",
        ),
        _step(
            "s3",
            "scene",
            "两面在画面中交替出现。",
            ("c7",),
            resource_refs=("resource:product:ZX-C218",),
        ),
    ]
    core: dict[str, object] = {
        "speaker_ref": "speaker:brand_account",
        "claims": claims,
        "spoken_order": ["c8"],
        "scene_steps": steps,
    }
    _install_fake(monkeypatch, [_core_response(core), _verdicts(core)])

    artifact = _generator().generate(request)

    assert isinstance(artifact.production, VideoProductionBundle)
    assert artifact.production.spoken_lines == "无口播、无对白、无解说"
    assert artifact.production.natural_duration == "约 6 秒"
    assert "真实商品锚点" in artifact.body


def test_adapter_retries_provider_429_without_adding_a_boundary_retry_layer(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    core = _video_core()
    _install_fake(
        monkeypatch,
        [
            FakeResponse(429, {}, {"Retry-After": "0"}),
            _core_response(core, tokens=10),
            _verdicts(core),
        ],
    )
    pauses: list[float] = []
    monkeypatch.setattr(time, "sleep", pauses.append)

    artifact = _generator().generate(generation_input)

    assert artifact.model == "verified-deepseek-model"
    assert artifact.retry_count == 1
    assert artifact.provider_usage == {"total_tokens": 10}
    assert pauses == [0.0]
    assert len(FakeClient.requests) == 3
    writer_json = FakeClient.requests[1]["json"]
    assert isinstance(writer_json, dict)
    assert writer_json["temperature"] == 0.0
    assert writer_json["thinking"] == {"type": "disabled"}
    assert writer_json["response_format"] == {"type": "json_object"}


def test_nonrecoverable_provider_status_fails_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake(monkeypatch, [FakeResponse(401, {})])

    with pytest.raises(GenerationFailed, match="拒绝当前请求"):
        _generator()._request("system", "prompt", 100)

    assert len(FakeClient.requests) == 1
