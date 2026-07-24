from __future__ import annotations

import json
import re
import time
from typing import Any
from uuid import UUID

import httpx
import pytest

from src.brain.platform_directions import direction_for
from src.shared.errors import GenerationFailed
from src.shared.types import (
    ActiveAsset,
    BrandContext,
    GenerationInput,
    P1SemanticContract,
    P5SemanticContract,
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


def _with(
    request: GenerationInput,
    **changes: object,
) -> GenerationInput:
    return GenerationInput(**{**request.__dict__, **changes})


def _video_payload(**overrides: object) -> str:
    payload: dict[str, object] = {
        "title": "不必穿成同款",
        "choice": "先保留每个人舒服的选择",
        "boundary": "如果需要正式合照，再找一个自然呼应点",
        "next_action": "先看每个人愿不愿意这样穿",
        "natural_guide": "从同款是否等于家庭感进入",
        "cover_or_first_frame": "手写标题：不必穿成同款",
        "viewing_flow": "固定机位完成口播",
        "spoken_lines": (
            "一家人的家庭感，不一定来自穿成同款。我们更愿意先尊重每个人舒服的选择，再找一个自然的呼应点。"
        ),
        "visual_actions": "当前创作者正对手机自然口播。",
        "subtitles": "家庭感不一定来自同款，先尊重每个人舒服的选择。",
        "sound_and_production": "手机直接收录当前创作者的人声。",
        "natural_duration": "12 秒",
        "release_caption_and_interaction": "你更在意整齐，还是每个人都自在？",
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def _completion(content: str, tokens: int = 0) -> FakeResponse:
    payload: dict[str, Any] = {
        "choices": [{"message": {"content": content}}],
    }
    if tokens:
        payload["usage"] = {"total_tokens": tokens}
    return FakeResponse(200, payload)


def _judgement(
    *violations: tuple[str, str, str],
) -> str:
    return json.dumps(
        {
            "violations": [
                {
                    "field": field,
                    "fragment": fragment,
                    "reason_code": reason,
                }
                for field, fragment, reason in violations
            ]
        },
        ensure_ascii=False,
    )


def _install_fake(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[FakeResponse],
) -> None:
    FakeClient.responses = responses
    FakeClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeClient)


def test_generation_compiles_one_ephemeral_boundary_context(
    generation_input: GenerationInput,
) -> None:
    context = BoundaryContext.from_request(generation_input)
    prompt = DeepSeekGenerator._generation_prompt(generation_input, context)

    assert "可信表达身份" in prompt
    assert generation_input.brand.account_name in prompt
    assert generation_input.brand.content_role_name in prompt
    assert generation_input.brand.content_role_boundary in prompt
    assert "已确认事实" in prompt
    assert generation_input.brand.positioning in prompt
    assert "用户本次前提" in prompt
    assert generation_input.weak_seed in prompt
    assert "品牌观点与条件性判断" in prompt
    assert "当前可用制作资源" in prompt
    assert "话题中出现对象不表示" in prompt
    assert "当前创作者也不能扮演该对象" in prompt
    assert "场地可用也不自动证明场地内的任何实物可用" in prompt
    assert "第一人称只能表达当前品牌观点或当前拍摄动作" in prompt
    assert "不能写成门店已经执行的服务或普遍政策" in prompt
    assert "没有明确提供的人物、商品、衣物、图片" in prompt
    assert "B-001" not in prompt
    assert "schema_version" not in prompt


def test_semantic_judge_scans_every_field_under_closed_world_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    _install_fake(monkeypatch, [_completion(_judgement())])

    DeepSeekGenerator(
        "https://compat.example/v1",
        "not-a-real-key",
        "verified-deepseek-model",
    )._semantic_boundary_violations(
        BoundaryContext.from_request(generation_input),
        json.loads(_video_payload()),
    )

    request_json = FakeClient.requests[0]["json"]
    assert isinstance(request_json, dict)
    prompt = str(request_json["messages"])
    assert "边界未明确提供的事实或资源一律视为不存在" in prompt
    assert "对每个候选字段分别核对" in prompt
    assert "用户只是在话题中提到某类人，不构成账号具备该身份" in prompt
    assert "让该对象出镜、行动、发声" in prompt


def test_adapter_retries_provider_429_without_adding_a_boundary_retry_layer(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    _install_fake(
        monkeypatch,
        [
            FakeResponse(429, {}, {"Retry-After": "0"}),
            _completion(_video_payload(), tokens=10),
            _completion(_judgement(), tokens=2),
        ],
    )
    pauses: list[float] = []
    monkeypatch.setattr(time, "sleep", pauses.append)

    artifact = DeepSeekGenerator(
        "https://compat.example/v1",
        "not-a-real-key",
        "verified-deepseek-model",
    ).generate(generation_input)

    assert artifact.model == "verified-deepseek-model"
    assert artifact.retry_count == 1
    assert artifact.provider_usage == {"total_tokens": 12}
    assert pauses == [0.0]
    assert len(FakeClient.requests) == 3
    request_json = FakeClient.requests[1]["json"]
    assert isinstance(request_json, dict)
    assert request_json["temperature"] == 0.0
    assert request_json["thinking"] == {"type": "disabled"}
    assert request_json["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize(
    ("field", "unsafe", "reason", "repaired"),
    [
        (
            "spoken_lines",
            "作为孩子的妈妈，我每天都这样选择。",
            "untrusted_role",
            "品牌更愿意先听见每个人的感受，再表达自己的判断。",
        ),
        (
            "brand_account_link",
            "我们所有门店都已经要求店员不主动打扰顾客。",
            "invented_actuality",
            "品牌主张给每个人留出安静判断的空间。",
        ),
        (
            "visual_actions",
            "让一家三口穿着三套商品在门店里走动。",
            "unsupported_resource",
            "当前创作者正对手机，用手写关键词辅助口播。",
        ),
    ],
)
def test_semantic_boundary_repairs_properties_not_frozen_copy(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
    field: str,
    unsafe: str,
    reason: str,
    repaired: str,
) -> None:
    initial = json.loads(_video_payload())
    if field == "brand_account_link":
        initial["brand_account_link"] = unsafe
        initial["persona_observation"] = "品牌先理解真实感受"
        initial["audience_return"] = "受众保留自己的判断"
        request = _with(
            generation_input,
            primary_product="brand_life_narrative",
        )
    else:
        initial[field] = unsafe
        request = generation_input
    _install_fake(
        monkeypatch,
        [
            _completion(json.dumps(initial, ensure_ascii=False)),
            _completion(_judgement((field, unsafe, reason))),
            _completion(json.dumps({field: repaired}, ensure_ascii=False)),
            _completion(_judgement()),
        ],
    )

    artifact = DeepSeekGenerator(
        "https://compat.example/v1",
        "not-a-real-key",
        "verified-deepseek-model",
    ).generate(request)

    assert unsafe not in artifact.body
    assert repaired in artifact.body
    assert {receipt.field for receipt in artifact.fact_repair_receipts} == {field}
    repair_json = FakeClient.requests[2]["json"]
    assert isinstance(repair_json, dict)
    repair_text = str(repair_json["messages"])
    assert reason in repair_text
    assert "只修复下列字段" in repair_text
    assert "固定安全文案" in repair_text
    assert len(FakeClient.requests) == 4


def test_repair_fails_closed_when_the_same_boundary_still_fails(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    unsafe = "我是这家门店的店长。"
    _install_fake(
        monkeypatch,
        [
            _completion(_video_payload(spoken_lines=unsafe)),
            _completion(_judgement(("spoken_lines", unsafe, "untrusted_role"))),
            _completion(json.dumps({"spoken_lines": unsafe}, ensure_ascii=False)),
            _completion(_judgement(("spoken_lines", unsafe, "untrusted_role"))),
        ],
    )

    with pytest.raises(GenerationFailed, match="一次字段修复"):
        DeepSeekGenerator(
            "https://compat.example/v1",
            "not-a-real-key",
            "verified-deepseek-model",
        ).generate(generation_input)

    assert len(FakeClient.requests) == 4


def test_semantic_judgement_requires_exact_field_fragment_and_reason_code(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    context = BoundaryContext.from_request(generation_input)
    candidate = json.loads(_video_payload())
    _install_fake(
        monkeypatch,
        [
            _completion(
                json.dumps(
                    {
                        "violations": [
                            {
                                "field": "spoken_lines",
                                "fragment": "候选中不存在",
                                "reason_code": "other",
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            )
        ],
    )

    with pytest.raises(GenerationFailed, match="边界判定返回格式"):
        DeepSeekGenerator(
            "https://compat.example/v1",
            "not-a-real-key",
            "verified-deepseek-model",
        )._semantic_boundary_violations(context, candidate)


def test_deterministic_checks_keep_identifiers_and_product_values_exact(
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
    context = BoundaryContext.from_request(_with(generation_input, products=(product,)))

    accepted = DeepSeekGenerator._deterministic_boundary_violations(
        context,
        {
            "title": "炭灰面",
            "spoken_lines": "当前商品 ZX-C218 的样衣记录为960克。",
        },
    )
    rejected = DeepSeekGenerator._deterministic_boundary_violations(
        context,
        {
            "title": "asset_id=hidden",
            "spoken_lines": ("当前商品 ZX-B999 的样衣记录为999克，颜色是红色；联系 test@example.com。"),
        },
    )

    assert accepted == ()
    assert {issue.fragment for issue in rejected} >= {
        "asset_id",
        "ZX-B999",
        "999克",
        "红色",
        "test@example.com",
    }
    assert {issue.reason_code for issue in rejected} == {"factual_conflict"}


def test_subtitles_are_an_ordered_compression_of_final_spoken_copy(
    generation_input: GenerationInput,
) -> None:
    spoken = "我们认为，先尊重每个人的舒服，再找自然的呼应。"
    legal = json.loads(
        _video_payload(
            spoken_lines=spoken,
            subtitles="尊重每个人舒服，再找自然呼应",
        )
    )
    invented = json.loads(
        _video_payload(
            spoken_lines=spoken,
            subtitles="全国门店已经执行这项服务",
        )
    )

    legal_projection = DeepSeekGenerator._project_video_contract(
        generation_input,
        legal,
    )
    invented_projection = DeepSeekGenerator._project_video_contract(
        generation_input,
        invented,
    )

    assert legal_projection["subtitles"] == "尊重每个人舒服，再找自然呼应"
    assert invented_projection["subtitles"] == spoken


def test_natural_duration_uses_at_most_four_readable_characters_per_second(
    generation_input: GenerationInput,
) -> None:
    spoken = "家庭感不必来自同款。先听见每个人的舒服，再找自然的呼应。"
    structured = json.loads(
        _video_payload(
            spoken_lines=spoken,
            natural_duration="8 秒",
        )
    )

    projected = DeepSeekGenerator._project_video_contract(
        generation_input,
        structured,
    )
    seconds = int(str(projected["natural_duration"]).split()[1])
    readable = len(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", spoken))

    assert seconds >= (readable + 3) // 4
    assert seconds == DeepSeekGenerator._natural_spoken_seconds(spoken)


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
    long_spoken = "这是必须真实缩短的完整口播。" * 8
    short_spoken = "先尊重差异，再找呼应。"
    _install_fake(
        monkeypatch,
        [
            _completion(_video_payload(spoken_lines=long_spoken)),
            _completion(_judgement()),
            _completion(json.dumps({"spoken_lines": short_spoken}, ensure_ascii=False)),
            _completion(_judgement()),
        ],
    )

    artifact = DeepSeekGenerator(
        "https://compat.example/v1",
        "not-a-real-key",
        "verified-deepseek-model",
    ).generate(request)

    assert isinstance(artifact.production, VideoProductionBundle)
    assert artifact.production.spoken_lines == short_spoken
    assert artifact.production.natural_duration == "8 秒"
    assert artifact.production.subtitles == short_spoken
    assert {receipt.field for receipt in artifact.fact_repair_receipts} == {"spoken_lines"}


def test_legal_viewpoint_title_and_available_resource_are_not_hard_blocked(
    generation_input: GenerationInput,
) -> None:
    context = BoundaryContext.from_request(generation_input)
    candidate: dict[str, object] = {
        "title": "沉默也值得被尊重",
        "brand_account_link": "笛语服饰主张给每个人留出自己的判断空间。",
        "visual_actions": "当前创作者在普通室内正对自己的手机口播。",
        "spoken_lines": "我们认为，理解不必立刻变成推销。",
    }

    assert (
        DeepSeekGenerator._deterministic_boundary_violations(
            context,
            candidate,
        )
        == ()
    )


def test_visible_body_keeps_contract_and_media_fields_readable() -> None:
    body = DeepSeekGenerator._visible_body(
        "标题",
        VideoProductionBundle(
            "导读",
            "完整口播",
            "动作",
            "同源字幕",
            "声音",
            "首帧",
            "观看链",
            "约 12 秒",
            "发布",
        ),
        P1SemanticContract("选择", "边界", "下一步"),
    )

    assert "标题：标题" in body
    assert "当前选择：选择" in body
    assert "完整台词/解说：完整口播" in body
    assert "字幕：同源字幕" in body


def test_visual_only_product_story_can_remain_no_voice() -> None:
    body = DeepSeekGenerator._visible_body(
        "标题",
        VideoProductionBundle(
            "导读",
            "无口播、无对白、无解说",
            "当前商品在画面中翻面",
            "画面字幕",
            "环境声",
            "首帧",
            "观看链",
            "约 8 秒",
            "发布",
        ),
        P5SemanticContract("真实商品", "视觉命题", "画面成立条件"),
    )

    assert "无口播、无对白、无解说" in body


def test_nonrecoverable_provider_status_fails_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake(monkeypatch, [FakeResponse(401, {})])

    with pytest.raises(GenerationFailed, match="拒绝当前请求"):
        DeepSeekGenerator(
            "https://compat.example/v1",
            "not-a-real-key",
            "verified-deepseek-model",
        )._request("system", "prompt", 100)

    assert len(FakeClient.requests) == 1
