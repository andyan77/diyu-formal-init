from __future__ import annotations

import json
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
    P2SemanticContract,
    P5SemanticContract,
    ProductFact,
    VideoProductionBundle,
)
from src.tool.llm_gateway.deepseek import DeepSeekGenerator, FactBoundary, FactViolation


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any], headers: dict[str, str] | None = None) -> None:
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
        weak_seed="先开完正式会议，再去接孩子。",
        primary_product="dressing_decision",
        revision_instruction=None,
        brand=BrandContext(
            "折线之间",
            "从容判断",
            "先场合再活动",
            "平等具体",
            "折线之间品牌母账号·抖音",
            "总部内容运营甲",
            "折线之间总部",
            "总部零售/服务专家",
            "不冒充具体门店店长或顾客。",
            "在多场景之间切换的城市女性。",
            "V1.0-first-phase-data-ready",
            "抖音",
            "视频",
            "一人一部手机完成。",
        ),
        target="douyin_video",
        media_format="video",
        platform_direction=direction_for("douyin_video"),
        active_domain_assets=(
            ActiveAsset("B-TPO-001", "v0.1", "boundary", "场合", "先看场合。"),
            ActiveAsset("C-COMMUTE-001", "v0.1", "boundary", "通勤", "兼顾转场。"),
            ActiveAsset("D-DIRECT-001", "v0.1", "method", "直接", "明确选择。"),
            ActiveAsset("D-CRAFT-001", "v0.1", "method", "细节", "保留分寸。"),
        ),
    )


def _video_payload(**overrides: object) -> str:
    payload: dict[str, object] = {
        "title": "选择",
        "choice": "选择",
        "boundary": "边界",
        "next_action": "下一步",
        "natural_guide": "自然导读",
        "cover_or_first_frame": "首帧",
        "viewing_flow": "完整观看链",
        "spoken_lines": "台词",
        "visual_actions": "拍摄安排：动作",
        "subtitles": "字幕",
        "sound_and_production": "一人手机",
        "natural_duration": "自然时长",
        "release_caption_and_interaction": "发布配文",
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def test_deepseek_adapter_retries_429_with_retry_after(
    monkeypatch: pytest.MonkeyPatch, generation_input: GenerationInput
) -> None:
    FakeClient.responses = [
        FakeResponse(429, {}, {"Retry-After": "0"}),
        FakeResponse(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": _video_payload(
                                title="从容选择",
                                choice="保住分寸",
                                boundary="活动受限时调整",
                                next_action="走动确认",
                                natural_guide="保住分寸",
                                spoken_lines="活动受限时调整",
                                visual_actions="走动确认",
                                subtitles="走动确认",
                            )
                        }
                    }
                ],
                "usage": {"total_tokens": 12},
            },
        ),
    ]
    FakeClient.requests = []
    pauses: list[float] = []
    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(time, "sleep", pauses.append)
    generator = DeepSeekGenerator("https://compat.example/v1", "not-a-real-key", "verified-deepseek-model")

    artifact = generator.generate(generation_input)

    assert artifact.model == "verified-deepseek-model"
    assert artifact.retry_count == 1
    assert artifact.provider_usage == {"total_tokens": 12}
    assert pauses == [0.0]
    request_json = FakeClient.requests[1]["json"]
    assert isinstance(request_json, dict)
    assert request_json["max_tokens"] == 4096
    assert request_json["temperature"] == 0.0
    assert request_json["thinking"] == {"type": "disabled"}
    assert request_json["response_format"] == {"type": "json_object"}
    request_payload = str(request_json)
    assert "总部零售/服务专家" in request_payload
    assert "在多场景之间切换的城市女性" in request_payload
    assert "V1.0-first-phase-data-ready" in request_payload
    assert "抖音／视频" in request_payload
    assert "先看场合。" in request_payload
    assert "保留分寸。" in request_payload
    assert "B-TPO-001" not in request_payload
    assert "v0.1" not in request_payload
    assert "用户种子中的人物、事件和对白可作为本次前提" in request_payload


def test_deepseek_adapter_does_not_turn_a_visual_plan_into_a_word_blacklist(
    monkeypatch: pytest.MonkeyPatch, generation_input: GenerationInput
) -> None:
    request = GenerationInput(
        **{
            **generation_input.__dict__,
            "primary_product": "visual_styling_story",
            "weak_seed": "同一身内搭，只改变外套朝外表面。",
        }
    )
    FakeClient.responses = [
        FakeResponse(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": _video_payload(
                                real_product_anchor="真实锚点",
                                visible_styling_proposition="可见命题",
                                visual_dependency="成立条件",
                            )
                        }
                    }
                ]
            },
        )
    ]
    FakeClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeClient)
    generator = DeepSeekGenerator("https://compat.example/v1", "not-a-real-key", "verified-deepseek-model")

    generator.generate(request)

    assert "绝不补充内搭颜色、款式或任何衣物部位" not in str(FakeClient.requests[0]["json"])


def test_deepseek_adapter_forbids_invented_product_claims_when_no_product_is_named(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    request = GenerationInput(**{**generation_input.__dict__, "products": ()})

    prompt = DeepSeekGenerator._generation_prompt(request)

    assert "当前没有已点名商品或可用商品事实" in prompt
    assert "不得把某件未提供的商品属性、功能、效果或现实经历" in prompt
    assert "不要自行把抽象选择指定为裙、裤、颜色、配饰、材质或性能" in prompt
    assert "自然的选择、情绪、节奏和未来拍摄构思" in prompt

    FakeClient.responses = [FakeResponse(200, {"choices": [{"message": {"content": _video_payload()}}]})]
    FakeClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeClient)
    generator = DeepSeekGenerator("https://compat.example/v1", "not-a-real-key", "verified-deepseek-model")

    generator.generate(request)

    system = str(FakeClient.requests[0]["json"])
    assert "不得把某件商品的具体属性、功能或效果写成已经确认" in system
    assert "不得虚构已经发生的人物、对话、顾客/同事/孩子或现场事件" in system


def test_deepseek_adapter_allows_non_factual_clothing_choice_when_no_product_fact_exists() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("（无当前商品事实）", "不要把任何一件衣服说成万能。"),
        "标题",
        P1SemanticContract("选一件有结构感的单品", "条件改变时调整", "出门前走两步"),
        VideoProductionBundle("导读", "台词", "动作", "字幕", "声音", "首帧", "观看链", "时长", "发布"),
    )

    assert violations == ()


def test_deepseek_adapter_rejects_invented_product_details_and_events_without_product_facts() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("（无当前商品事实）", "下午开完正式会议，再去接孩子。"),
        "会议后的切换",
        P1SemanticContract(
            "穿深色连衣裙或连体裤，剪裁利落、面料抗皱。",
            "同事问我：这身蹲下不皱，站起来不垮吗？",
            "下午开完正式会议，再去接孩子。",
        ),
        VideoProductionBundle(
            "导读",
            "一位女性站在写字楼门口，准备去接孩子。",
            "动作",
            "字幕",
            "声音",
            "首帧",
            "观看链",
            "时长",
            "发布",
        ),
    )

    assert {item.field for item in violations} == {
        "choice",
        "boundary",
        "spoken_lines",
    }


def test_deepseek_adapter_rejects_product_detail_before_a_generic_garment_name() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("（无当前商品事实）", "下午开完正式会议，再去接孩子。"),
        "标题",
        P1SemanticContract(
            "优先选一件剪裁利落、面料抗皱的连衣裙，搭配可拆卸丝巾。",
            "如果临时去户外，再换成高弹力、易活动的裤装。",
            "出门前走两步。",
        ),
        VideoProductionBundle(
            "导读",
            "台词",
            "动作",
            "字幕",
            "声音",
            "深蓝色连衣裙作为首帧。",
            "观看链",
            "时长",
            "发布",
        ),
    )

    assert {item.field for item in violations} == {
        "choice",
        "cover_or_first_frame",
    }


def test_deepseek_adapter_rejects_concrete_product_facts_that_conflict_with_current_input(
    generation_input: GenerationInput,
) -> None:
    boundary = FactBoundary.from_request(
        GenerationInput(
            **{
                **generation_input.__dict__,
                "products": (
                    ProductFact(
                        "ZX-C218",
                        {
                            "colors": ["炭灰纯色", "深绿细格纹"],
                            "sample_weight_m_grams": 960,
                            "comparison_single_layer_short_coat_m_grams": 650,
                        },
                    ),
                ),
            }
        )
    )

    violations = DeepSeekGenerator._boundary_violations(
        boundary,
        "ZX-C999",
        P2SemanticContract("这件 ZX-C218 是黑色，当前样衣重800克。", "边界", "条件"),
        VideoProductionBundle("导读", "台词", "拍摄安排：翻面", "字幕", "声音", "首帧", "观看链", "时长", "发布"),
    )

    assert {item.field for item in violations} == {"title", "product_insight"}


def test_deepseek_adapter_does_not_retry_nonrecoverable_status(
    monkeypatch: pytest.MonkeyPatch, generation_input: GenerationInput
) -> None:
    FakeClient.responses = [FakeResponse(400, {})]
    monkeypatch.setattr(httpx, "Client", FakeClient)
    generator = DeepSeekGenerator("https://compat.example/v1", "not-a-real-key", "verified-deepseek-model")

    with pytest.raises(GenerationFailed):
        generator.generate(generation_input)


def test_deepseek_adapter_accepts_provider_fenced_json(
    monkeypatch: pytest.MonkeyPatch, generation_input: GenerationInput
) -> None:
    FakeClient.responses = [
        FakeResponse(
            200,
            {"choices": [{"message": {"content": "```json\n" + _video_payload() + "\n```"}}]},
        )
    ]
    monkeypatch.setattr(httpx, "Client", FakeClient)
    generator = DeepSeekGenerator("https://compat.example/v1", "not-a-real-key", "verified-deepseek-model")

    artifact = generator.generate(generation_input)

    assert isinstance(artifact.semantic_contract, P1SemanticContract)
    assert artifact.semantic_contract.choice == "选择"


def test_deepseek_adapter_repairs_one_incomplete_structured_response(
    monkeypatch: pytest.MonkeyPatch, generation_input: GenerationInput
) -> None:
    complete = _video_payload()
    FakeClient.responses = [
        FakeResponse(200, {"choices": [{"message": {"content": '{"outline":"缺字段"}'}}]}),
        FakeResponse(200, {"choices": [{"message": {"content": complete}}]}),
    ]
    FakeClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeClient)
    generator = DeepSeekGenerator("https://compat.example/v1", "not-a-real-key", "verified-deepseek-model")

    artifact = generator.generate(generation_input)

    assert artifact.retry_count == 1
    assert len(FakeClient.requests) == 2
    assert "字段缺失、为空或不是单个字符串" in str(FakeClient.requests[1]["json"])


def test_deepseek_adapter_repairs_non_string_visible_fields(
    monkeypatch: pytest.MonkeyPatch, generation_input: GenerationInput
) -> None:
    complete = _video_payload()
    FakeClient.responses = [
        FakeResponse(
            200,
            {"choices": [{"message": {"content": _video_payload(spoken_lines=["台词"])}}]},
        ),
        FakeResponse(200, {"choices": [{"message": {"content": complete}}]}),
    ]
    FakeClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeClient)
    generator = DeepSeekGenerator("https://compat.example/v1", "not-a-real-key", "verified-deepseek-model")

    artifact = generator.generate(generation_input)

    assert isinstance(artifact.production, VideoProductionBundle)
    assert artifact.production.spoken_lines == "台词"
    assert artifact.retry_count == 1
    assert len(FakeClient.requests) == 2
    assert "不是单个字符串" in str(FakeClient.requests[1]["json"])


def test_deepseek_adapter_repairs_a_specific_unsupported_product_claim(
    monkeypatch: pytest.MonkeyPatch, generation_input: GenerationInput
) -> None:
    unsafe = _video_payload(
        spoken_lines="这件外套很保暖。",
        visual_actions="拍摄安排：展示翻面",
        subtitles="这件外套很保暖。",
    )
    repaired = '{"spoken_lines":"现有资料不能证明保暖表现。","subtitles":"现有资料不能证明保暖表现。"}'
    FakeClient.responses = [
        FakeResponse(200, {"choices": [{"message": {"content": unsafe}}]}),
        FakeResponse(200, {"choices": [{"message": {"content": repaired}}]}),
    ]
    FakeClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeClient)
    generator = DeepSeekGenerator("https://compat.example/v1", "not-a-real-key", "verified-deepseek-model")

    artifact = generator.generate(generation_input)

    assert "很保暖" not in artifact.body
    assert "现有资料不能证明保暖表现" in artifact.body
    assert {receipt.field for receipt in artifact.fact_repair_receipts} == {
        "spoken_lines",
        "subtitles",
    }
    assert len(FakeClient.requests) == 2
    repair_request = str(FakeClient.requests[1]["json"])
    assert "spoken_lines" in repair_request
    assert "subtitles" in repair_request
    assert '"title"' not in repair_request
    assert "不得保留或新增任何具体衣物、颜色、配饰、材质、性能、部位或示例" in repair_request
    assert "这件外套很保暖" not in repair_request


def test_deepseek_adapter_compiles_visible_body_only_from_controlled_fields() -> None:
    body = DeepSeekGenerator._visible_body(
        "自然标题",
        VideoProductionBundle(
            "开场说明",
            "完整台词",
            "画面动作",
            "字幕文案",
            "声音提示",
            "首帧",
            "观看链",
            "自然时长",
            "发布配文",
        ),
    )

    assert body.startswith("标题：自然标题")
    assert "完整台词/解说：完整台词" in body
    assert "画面与动作：画面动作" in body
    assert "字幕：字幕文案" in body
    assert "声音与制作提示：声音提示" in body


def test_deepseek_adapter_rejects_punctuation_only_visible_text() -> None:
    with pytest.raises(TypeError):
        DeepSeekGenerator._visible_text("'")


def test_deepseek_adapter_prunes_only_finally_rejected_sentences() -> None:
    projected = DeepSeekGenerator._prune_rejected_sentences(
        {"tradeoff_or_limit": ("现有资料只有两份样衣重量记录。不能简单认为双面结构直接导致重量增加。")},
        (
            FactViolation(
                "tradeoff_or_limit",
                "不能简单认为双面结构直接导致重量增加。",
            ),
        ),
    )

    assert projected == {"tradeoff_or_limit": "现有资料只有两份样衣重量记录。"}


def test_deepseek_adapter_fails_when_final_rejection_would_empty_a_field() -> None:
    with pytest.raises(GenerationFailed):
        DeepSeekGenerator._prune_rejected_sentences(
            {"tradeoff_or_limit": "不能简单归因于双面结构。"},
            (
                FactViolation(
                    "tradeoff_or_limit",
                    "不能简单归因于双面结构。",
                ),
            ),
        )


def test_deepseek_adapter_does_not_prune_a_rejected_production_field() -> None:
    with pytest.raises(GenerationFailed):
        DeepSeekGenerator._prune_rejected_sentences(
            {"cover_or_first_frame": "展示未提供的商品部位。"},
            (
                FactViolation(
                    "cover_or_first_frame",
                    "展示未提供的商品部位。",
                ),
            ),
        )


def test_deepseek_adapter_prunes_one_rejected_spoken_sentence_when_copy_remains() -> None:
    projected = DeepSeekGenerator._prune_rejected_sentences(
        {
            "spoken_lines": (
                "当前M码样衣约960克，对照同季同长度单层短外套M码样衣约650克。"
                "两面外观完整，两面口袋均可正常使用。"
                "不能确认重量差异是不是双面结构造成的。"
                "当前只有这两份样衣记录，没有结构测试，现有资料无法归因。"
            )
        },
        (
            FactViolation(
                "spoken_lines",
                "不能确认重量差异是不是双面结构造成的。",
            ),
        ),
    )

    spoken = str(projected["spoken_lines"])
    assert "是不是双面结构造成" not in spoken
    assert "当前M码样衣约960克" in spoken
    assert "现有资料无法归因" in spoken


def test_deepseek_adapter_prunes_one_rejected_subtitle_segment() -> None:
    projected = DeepSeekGenerator._prune_rejected_sentences(
        {"subtitles": ("M码960克 | 同季同长度单层样衣M码650克 | 不能确认差异全因双面 | 现有资料无法归因")},
        (
            FactViolation(
                "subtitles",
                "不能确认差异全因双面",
            ),
        ),
    )

    subtitles = str(projected["subtitles"])
    assert "全因双面" not in subtitles
    assert "M码960克" in subtitles
    assert "现有资料无法归因" in subtitles


def test_deepseek_adapter_exposes_p5_contract_as_readable_sections() -> None:
    body = DeepSeekGenerator._visible_body(
        "视觉标题",
        VideoProductionBundle("导读", "无口播", "动作", "字幕", "声音", "首帧", "观看链", "时长", "发布"),
        P5SemanticContract("真实锚点", "可见命题", "成立条件"),
    )

    assert "真实商品锚点：真实锚点" in body
    assert "可见造型命题：可见命题" in body
    assert "画面成立条件：成立条件" in body


def test_deepseek_adapter_marks_a_short_video_as_a_narrow_transform() -> None:
    body = DeepSeekGenerator._visible_body(
        "短版",
        VideoProductionBundle("导读", "台词", "动作", "字幕", "声音", "首帧", "观看链", "8秒", "发布"),
    )

    assert "变换边界：这是 8 秒窄主题版，不等同于原完整版本。" in body


def test_deepseek_adapter_removes_reserved_product_labels_from_visible_text() -> None:
    visible = DeepSeekGenerator._visible_text("P2：product_truth 解释商品")

    assert visible == "解释商品"


def test_deepseek_adapter_projects_zx_c218_facts_without_erasing_known_pockets() -> None:
    product = DeepSeekGenerator._natural_product(
        "ZX-C218",
        ProductFact(
            "ZX-C218",
            {
                "colors": ["炭灰纯色", "深绿细格纹"],
                "category": "double-faced short coat",
                "both_sides_complete": True,
                "pockets_functional_both_sides": True,
                "sample_weight_m_grams": 960,
                "comparison_single_layer_short_coat_m_grams": 650,
                "weight_boundary": "only the current sample weight difference is known; do not attribute all difference to the double-faced structure",
            },
        ).facts,
    )

    assert "两面均为完整外观" in product
    assert "双面短外套" in product
    assert "两面口袋均可正常使用" in product
    assert "960克" in product
    assert "650克" in product
    assert "没有结构测试，现有资料无法归因" in product
    assert "口袋情况未提供" not in product


def test_deepseek_adapter_accepts_a_p2_anti_misuse_boundary_without_accepting_the_claim() -> None:
    boundary = DeepSeekGenerator._natural_product(
        "ZX-C218", {"sample_weight_m_grams": 960, "comparison_single_layer_short_coat_m_grams": 650}
    )
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary(boundary, ""),
        "标题",
        P2SemanticContract("新增理解", "不能从重量差异推断厚度、手感或品质。", "当前样衣数据"),
        VideoProductionBundle("导读", "台词", "拍摄安排：称重", "字幕", "声音", "首帧", "观看链", "时长", "发布"),
    )

    assert violations == ()


def test_deepseek_adapter_allows_a_future_visual_plan_without_turning_it_into_product_fact() -> None:
    boundary = FactBoundary("商品 ZX-C218：两面均为完整外观。", "")
    violations = DeepSeekGenerator._boundary_violations(
        boundary,
        "标题",
        P5SemanticContract("ZX-C218 双面短外套", "视觉重音来自翻面", "翻面动作不可移除"),
        VideoProductionBundle(
            "导读",
            "台词",
            "拍摄安排：翻开左襟露出格纹。",
            "字幕",
            "声音",
            "首帧",
            "观看链",
            "时长",
            "发布",
        ),
    )

    assert violations == ()


def test_deepseek_adapter_rejects_an_unprovided_inner_layer_detail_in_p5() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：两面均为完整外观。", "同一身内搭。"),
        "标题",
        P5SemanticContract("锚点", "命题", "条件"),
        VideoProductionBundle("导读", "无口播", "动作", "字幕", "声音", "人物穿黑色高领内搭", "观看链", "时长", "发布"),
    )

    assert violations[0].field == "cover_or_first_frame"


def test_deepseek_adapter_rejects_unverified_weighing_or_comparison_capture() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：当前样衣约960克；对照数据约650克。", ""),
        "标题",
        P2SemanticContract("理解", "边界", "条件"),
        VideoProductionBundle(
            "我们实测了重量。",
            "台词",
            "拍摄安排：把当前样衣和对照单层外套分别放到称重台。",
            "字幕",
            "声音",
            "首帧",
            "观看链",
            "时长",
            "发布",
        ),
    )

    assert {violation.field for violation in violations} == {"natural_guide", "visual_actions"}


def test_deepseek_adapter_rejects_a_hand_raising_an_unprovided_comparison_sample() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：当前样衣约960克；对照数据约650克。", ""),
        "标题",
        P2SemanticContract("理解", "边界", "条件"),
        VideoProductionBundle(
            "导读",
            "台词",
            "另一只手拿起一件单层短外套，只作视觉对比。",
            "字幕",
            "声音",
            "首帧",
            "观看链",
            "时长",
            "发布",
        ),
    )

    assert {violation.field for violation in violations} == {"visual_actions"}


def test_deepseek_adapter_rejects_an_unprovided_comparison_sample_in_visual_planning() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：当前样衣约960克；对照数据约650克。", ""),
        "标题",
        P2SemanticContract("理解", "边界", "条件"),
        VideoProductionBundle(
            "导读",
            "台词",
            "旁边放一件同季同长度单层短外套。",
            "字幕可写单层短外套 M 码约650克。",
            "声音",
            "首帧",
            "观看链",
            "时长",
            "发布",
        ),
    )

    assert {violation.field for violation in violations} == {"visual_actions"}


def test_deepseek_adapter_rejects_two_physical_products_when_only_one_is_available() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary(
            "商品 ZX-C218：当前样衣约960克；对照数据约650克。",
            "",
            product_skus=("ZX-C218",),
        ),
        "标题",
        P2SemanticContract("理解", "边界", "条件"),
        VideoProductionBundle(
            "展示两件外套的差别。",
            "台词",
            "拍摄安排：只拍当前商品。",
            "字幕",
            "声音",
            "一只手分别拿起两件外套。",
            "两件商品并排后再讲重量。",
            "时长",
            "发布",
        ),
    )

    assert {violation.field for violation in violations} == {
        "natural_guide",
        "cover_or_first_frame",
        "viewing_flow",
    }


def test_deepseek_adapter_allows_a_visual_boundary_that_refuses_a_comparison_sample() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：当前样衣约960克；对照数据约650克。", ""),
        "标题",
        P2SemanticContract("理解", "边界", "条件"),
        VideoProductionBundle(
            "导读",
            "台词",
            "不展示、提及或对比任何单层短外套。",
            "字幕",
            "声音",
            "首帧",
            "观看链",
            "时长",
            "发布",
        ),
    )

    assert violations == ()


def test_deepseek_adapter_repairs_comparison_visuals_without_showing_a_second_sample() -> None:
    prompt = DeepSeekGenerator._boundary_repair_prompt(
        {"visual_actions": "旁边放单层短外套。"},
        FactBoundary("商品 ZX-C218：当前样衣约960克；对照数据约650克。", ""),
        (FactViolation("visual_actions", "旁边放单层短外套。"),),
    )

    assert "不得提及、展示、悬挂、拿起或并排任何单层外套、对照样衣或第二件商品" in prompt
    assert "旁边放单层短外套" not in prompt
    assert "不得声称双面造成、带来或增加了重量" in prompt


def test_deepseek_adapter_allows_comparison_weight_as_a_text_card() -> None:
    boundary = FactBoundary(
        "商品 ZX-C218：当前样衣约960克；对照数据约650克。",
        "",
        product_skus=("ZX-C218",),
    )

    assert not DeepSeekGenerator._depicts_unavailable_comparison(
        boundary,
        "viewing_flow",
        "外套挂在衣架上，画面出现文字卡片“同季同长度单层样衣 M 码 650 克”。",
    )


def test_deepseek_adapter_treats_comparison_weight_as_data_not_a_shootable_sample(
    generation_input: GenerationInput,
) -> None:
    request = GenerationInput(
        **{
            **generation_input.__dict__,
            "primary_product": "product_truth",
            "products": (
                ProductFact(
                    "ZX-C218",
                    {
                        "sample_weight_m_grams": 960,
                        "comparison_single_layer_short_coat_m_grams": 650,
                    },
                ),
            ),
        }
    )

    prompt = DeepSeekGenerator._generation_prompt(request)

    assert "当前只提供了对照重量记录，没有提供可拍摄的对照样衣" in prompt
    assert "画面只能使用当前点名商品" in prompt


def test_deepseek_adapter_semantically_repairs_an_unprovided_product_property(
    monkeypatch: pytest.MonkeyPatch, generation_input: GenerationInput
) -> None:
    request = GenerationInput(
        **{
            **generation_input.__dict__,
            "primary_product": "product_truth",
            "products": (
                ProductFact(
                    "ZX-C218",
                    {
                        "sample_weight_m_grams": 960,
                        "comparison_single_layer_short_coat_m_grams": 650,
                    },
                ),
            ),
        }
    )
    initial = json.loads(_video_payload())
    initial.update(
        {
            "product_insight": "当前只可确认两份样衣重量。",
            "tradeoff_or_limit": "不能归因。",
            "validity_condition": "限当前记录。",
            "spoken_lines": "它是一件更扎实的外套。",
        }
    )
    repaired = {"spoken_lines": "当前只可确认两份样衣重量存在差异，原因不能归因。"}
    FakeClient.responses = [
        FakeResponse(
            200,
            {
                "choices": [{"message": {"content": json.dumps(initial, ensure_ascii=False)}}],
                "usage": {"total_tokens": 10},
            },
        ),
        FakeResponse(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"violations":[{"field":"spoken_lines","fragment":"它是一件更扎实的外套。"}]}'
                        }
                    }
                ],
                "usage": {"total_tokens": 2},
            },
        ),
        FakeResponse(
            200,
            {
                "choices": [{"message": {"content": json.dumps(repaired, ensure_ascii=False)}}],
                "usage": {"total_tokens": 3},
            },
        ),
        FakeResponse(
            200,
            {
                "choices": [{"message": {"content": '{"violations":[]}'}}],
                "usage": {"total_tokens": 2},
            },
        ),
    ]
    FakeClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeClient)

    artifact = DeepSeekGenerator("https://compat.example/v1", "not-a-real-key", "verified-deepseek-model").generate(
        request
    )

    assert "更扎实" not in artifact.body
    assert artifact.provider_usage == {"total_tokens": 17}
    assert {receipt.field for receipt in artifact.fact_repair_receipts} == {"spoken_lines"}
    assert len(FakeClient.requests) == 4
    assert "不得据此肯定更扎实" in str(FakeClient.requests[1]["json"])


def test_deepseek_adapter_uses_a_system_repair_guard_for_comparison_visuals(
    monkeypatch: pytest.MonkeyPatch, generation_input: GenerationInput
) -> None:
    unsafe = _video_payload(visual_actions="旁边放一件单层短外套。")
    repaired = '{"visual_actions":"画面只展示当前商品，重量作为文字数据出现。"}'
    FakeClient.responses = [
        FakeResponse(200, {"choices": [{"message": {"content": unsafe}}]}),
        FakeResponse(200, {"choices": [{"message": {"content": repaired}}]}),
    ]
    FakeClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeClient)

    DeepSeekGenerator("https://compat.example/v1", "not-a-real-key", "verified-deepseek-model").generate(
        generation_input
    )

    assert "当前只有对照重量数据，没有对照样衣拍摄事实" in str(FakeClient.requests[1]["json"])


def test_deepseek_adapter_uses_a_system_repair_guard_for_weak_causal_negation(
    monkeypatch: pytest.MonkeyPatch, generation_input: GenerationInput
) -> None:
    unsafe = _video_payload(spoken_lines="不能确认这310克是否完全由双面结构造成。")
    repaired = '{"spoken_lines":"现有资料只有两份重量记录，没有结构测试，无法归因。"}'
    FakeClient.responses = [
        FakeResponse(200, {"choices": [{"message": {"content": unsafe}}]}),
        FakeResponse(200, {"choices": [{"message": {"content": repaired}}]}),
    ]
    FakeClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeClient)

    artifact = DeepSeekGenerator("https://compat.example/v1", "not-a-real-key", "verified-deepseek-model").generate(
        generation_input
    )

    assert "无法归因" in artifact.body
    assert "不得把双面结构与重量差异组成因果句" in str(FakeClient.requests[1]["json"])
    assert "不得再次出现“双面结构”四个字" in str(FakeClient.requests[1]["json"])


def test_deepseek_adapter_rejects_an_invented_explanation_for_weight_difference() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：两份样衣相差约310克，不能归因。", ""),
        "标题",
        P2SemanticContract("理解", "因为单层那件本身有650克，所以能解释310克差异。", "条件"),
        VideoProductionBundle("导读", "台词", "动作", "字幕", "声音", "首帧", "观看链", "时长", "发布"),
    )

    assert violations[0].field == "tradeoff_or_limit"


def test_deepseek_adapter_rejects_a_speculative_weight_cause() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：两份样衣相差约310克，不能归因。", ""),
        "标题",
        P2SemanticContract("理解", "未被测试的结构因素可能导致差异。", "当前样衣数据"),
        VideoProductionBundle("导读", "台词", "动作", "字幕", "声音", "首帧", "观看链", "时长", "发布"),
    )

    assert violations[0].field == "tradeoff_or_limit"


def test_deepseek_adapter_rejects_a_partial_weight_attribution_without_structure_test() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：两份样衣相差约310克，不能归因。", ""),
        "标题",
        P2SemanticContract("理解", "双面结构是重量差异的一部分原因。", "条件"),
        VideoProductionBundle("导读", "台词", "动作", "字幕", "声音", "首帧", "观看链", "时长", "发布"),
    )

    assert {violation.field for violation in violations} == {"tradeoff_or_limit"}


def test_deepseek_adapter_rejects_a_claim_that_double_facing_created_the_weight_difference() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：两份样衣相差约310克，不能归因。", ""),
        "标题",
        P2SemanticContract("双面结构确实带来了约310克重量差异。", "边界", "条件"),
        VideoProductionBundle("导读", "台词", "动作", "字幕", "声音", "首帧", "观看链", "时长", "发布"),
    )

    assert {violation.field for violation in violations} == {"product_insight"}


def test_deepseek_adapter_rejects_a_claim_that_double_facing_increased_weight() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：两份样衣相差约310克，不能归因。", ""),
        "标题",
        P2SemanticContract("双面结构确实增加了重量。", "边界", "条件"),
        VideoProductionBundle("导读", "台词", "动作", "字幕", "声音", "首帧", "观看链", "时长", "发布"),
    )

    assert {violation.field for violation in violations} == {"product_insight"}


def test_deepseek_adapter_rejects_more_sides_as_more_weight() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：两份样衣重量不同，不能归因。", ""),
        "标题",
        P2SemanticContract("理解", "边界", "条件"),
        VideoProductionBundle(
            "导读",
            "台词",
            "动作",
            "字幕",
            "声音",
            "首帧",
            "观看链",
            "时长",
            "双面外套，多一个面，也多一份重量。",
        ),
    )

    assert {violation.field for violation in violations} == {"release_caption_and_interaction"}


def test_deepseek_adapter_accepts_an_explicit_no_partial_attribution_boundary() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：两份样衣相差约310克，不能归因。", ""),
        "标题",
        P2SemanticContract(
            "两份样衣重量不同。",
            "没有结构测试，不能确认双面结构造成了其中任何一部分差异。",
            "当前两份样衣记录",
        ),
        VideoProductionBundle("导读", "台词", "动作", "字幕", "声音", "首帧", "观看链", "时长", "发布"),
    )

    assert violations == ()


@pytest.mark.parametrize(
    "claim",
    [
        "不能确认这310克差异是否完全由双面结构造成。",
        "不能确认双面结构是重量差异的唯一或主要原因。",
        "不能确认双面结构造成了多少重量差异。",
        "双面结构不一定带来全部重量差异。",
        "不能把重量差异全归因于双面结构。",
        "不知道双面结构具体贡献了多少重量差异。",
        "不能确认这份重量是不是全因为双面。",
        "不能简单把这份重量差异归因于双面结构。",
        "你猜双面结构贡献了多少？",
        "不能简单理解为双面结构直接导致重量增加。",
        "没法说这重量差就是双面结构带来的。",
        "无法判断双面设计对重量的具体影响。",
        "不能确认重量差异全因双面。",
    ],
)
def test_deepseek_adapter_rejects_causal_degree_language_that_implies_partial_weight(
    claim: str,
) -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：两份样衣相差约310克，不能归因。", ""),
        "标题",
        P2SemanticContract("两份样衣重量不同。", claim, "当前两份样衣记录"),
        VideoProductionBundle("导读", "台词", "动作", "字幕", "声音", "首帧", "观看链", "时长", "发布"),
    )

    assert {violation.field for violation in violations} == {"tradeoff_or_limit"}


def test_deepseek_adapter_rejects_an_unverified_claim_that_we_weighed_the_product() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：当前样衣约960克。", ""),
        "标题",
        P2SemanticContract("两份样衣重量不同。", "现有资料无法归因。", "当前样衣记录"),
        VideoProductionBundle(
            "导读",
            "台词",
            "动作",
            "字幕",
            "声音",
            "首帧",
            "观看链",
            "时长",
            "我们称了重量，结果很意外。",
        ),
    )

    assert {violation.field for violation in violations} == {"release_caption_and_interaction"}


def test_deepseek_adapter_rejects_unprovided_candidate_causes_even_when_negated() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：当前样衣960克；对照样衣650克。", ""),
        "标题",
        P2SemanticContract(
            "两份样衣重量不同。",
            "现有资料无法把重量差异归因于面料、里料或工艺。",
            "当前两份样衣记录",
        ),
        VideoProductionBundle("导读", "台词", "动作", "字幕", "声音", "首帧", "观看链", "时长", "发布"),
    )

    assert {violation.field for violation in violations} == {"tradeoff_or_limit"}


@pytest.mark.parametrize(
    "claim",
    [
        "双面设计提供了双倍口袋使用。",
        "这件外套的口袋数量翻倍。",
    ],
)
def test_deepseek_adapter_rejects_turning_two_sided_pocket_use_into_double_quantity(
    claim: str,
) -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：两面口袋均可正常使用。", ""),
        "标题",
        P2SemanticContract("两面口袋均可使用。", "现有资料无法归因。", "当前商品记录"),
        VideoProductionBundle("导读", "台词", "动作", "字幕", "声音", "首帧", "观看链", "时长", claim),
    )

    assert {violation.field for violation in violations} == {"release_caption_and_interaction"}


def test_deepseek_adapter_allows_ordinary_visual_garment_language() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：两面均为完整外观。", ""),
        "标题",
        P2SemanticContract("两面完整。", "现有资料无法归因。", "当前商品记录"),
        VideoProductionBundle(
            "导读",
            "台词",
            "手拎衣领翻面，镜头推近至面料纹理。",
            "字幕",
            "声音",
            "衣领与面料纹理的画面",
            "观看链",
            "时长",
            "发布",
        ),
    )

    assert violations == ()


def test_deepseek_adapter_rejects_an_unverified_first_person_measurement() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：当前样衣约960克。", ""),
        "标题",
        P2SemanticContract("两份样衣重量不同。", "现有资料无法归因。", "当前样衣记录"),
        VideoProductionBundle(
            "导读",
            "我们M码样衣称出来是960克。",
            "动作",
            "字幕",
            "声音",
            "首帧",
            "观看链",
            "时长",
            "发布",
        ),
    )

    assert {violation.field for violation in violations} == {"spoken_lines"}


def test_deepseek_adapter_rejects_no_voice_direction_when_spoken_copy_exists() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：当前样衣约960克。", ""),
        "标题",
        P2SemanticContract("两份样衣重量不同。", "现有资料无法归因。", "当前样衣记录"),
        VideoProductionBundle(
            "导读",
            "这是一段完整口播。",
            "无口播、无对白、无解说。画面展示当前商品。",
            "字幕",
            "声音",
            "首帧",
            "观看链",
            "时长",
            "发布",
        ),
    )

    assert {violation.field for violation in violations} == {"visual_actions"}


def test_deepseek_adapter_rejects_no_voice_subtitle_when_spoken_copy_exists() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：当前样衣约960克。", ""),
        "标题",
        P2SemanticContract("两份样衣重量不同。", "现有资料无法归因。", "当前样衣记录"),
        VideoProductionBundle(
            "导读",
            "这是一段完整口播。",
            "画面展示当前商品。",
            "无口播、无对白、无解说",
            "声音",
            "首帧",
            "观看链",
            "时长",
            "发布",
        ),
    )

    assert {violation.field for violation in violations} == {"subtitles"}


def test_deepseek_adapter_accepts_a_consistent_no_voice_video() -> None:
    no_voice = "无口播、无对白、无解说"
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：当前样衣约960克。", ""),
        "标题",
        P2SemanticContract("两份样衣重量不同。", "现有资料无法归因。", "当前样衣记录"),
        VideoProductionBundle(
            "导读",
            no_voice,
            no_voice,
            "字幕",
            "声音",
            "首帧",
            "观看链",
            "时长",
            "发布",
        ),
    )

    assert violations == ()


@pytest.mark.parametrize(
    "claim",
    [
        "这件双面外套确实比普通单层外套重。",
        "双面外套通常比单层外套更重。",
        "一般单层外套都比双面款轻。",
    ],
)
def test_deepseek_adapter_rejects_a_two_sample_weight_as_a_category_claim(
    claim: str,
) -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：当前样衣960克；对照样衣650克。", ""),
        "标题",
        P2SemanticContract(claim, "现有资料无法归因。", "当前两份样衣记录"),
        VideoProductionBundle("导读", "台词", "动作", "字幕", "声音", "首帧", "观看链", "时长", "发布"),
    )

    assert {violation.field for violation in violations} == {"product_insight"}


def test_deepseek_adapter_rejects_treating_a_known_weight_difference_as_unknown() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary(
            "商品 ZX-C218：当前样衣960克；对照样衣650克。",
            "",
            known_weight_grams=(960, 650, 310),
        ),
        "标题",
        P2SemanticContract("两份样衣相差310克。", "原因未知。", "当前两份样衣记录"),
        VideoProductionBundle(
            "导读",
            "它确实更重，但重多少、为什么重，现有资料没法确定。",
            "动作",
            "字幕",
            "声音",
            "首帧",
            "观看链",
            "时长",
            "发布",
        ),
    )

    assert {violation.field for violation in violations} == {"spoken_lines"}


def test_deepseek_adapter_rejects_internal_copy_direction() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：两面均为完整外观。", ""),
        "标题",
        P2SemanticContract("理解", "边界", "当前样衣数据"),
        VideoProductionBundle(
            "需向受众说明两面完整。",
            "台词",
            "动作",
            "字幕",
            "声音",
            "首帧",
            "观看链",
            "时长",
            "发布",
        ),
    )

    assert violations[0].field == "natural_guide"


def test_deepseek_adapter_repairs_personal_identifiers_field_by_field() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：两面均为完整外观。", ""),
        "标题",
        P1SemanticContract("今天先看炭灰面", "不需要联系 test@example.com", "下次再翻面"),
        VideoProductionBundle("导读", "台词", "动作", "字幕", "声音", "首帧", "观看链", "时长", "发布"),
    )

    assert [(item.field, item.fragment) for item in violations] == [("boundary", "不需要联系 test@example.com")]


def test_deepseek_adapter_rejects_unprovided_technical_test_details() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：当前样衣约960克；没有结构测试。", ""),
        "标题",
        P2SemanticContract("理解", "现有资料没有测试里料或工艺。", "当前样衣数据"),
        VideoProductionBundle("导读", "台词", "动作", "字幕", "声音", "首帧", "观看链", "时长", "发布"),
    )

    assert violations[0].field == "tradeoff_or_limit"


def test_deepseek_adapter_does_not_require_a_user_premise_to_use_fixed_words_or_one_sentence() -> None:
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary("商品 ZX-C218：两面均为完整外观。", "品牌已知差异仍坚持要求两面完整。"),
        "标题",
        P2SemanticContract("理解", "边界", "当前样衣数据"),
        VideoProductionBundle("导读", "台词", "动作", "字幕", "声音", "首帧", "观看链", "时长", "发布"),
    )

    assert violations == ()
