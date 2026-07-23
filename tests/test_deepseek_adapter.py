from __future__ import annotations

import time
from typing import Any
from uuid import UUID

import httpx
import pytest

from src.shared.errors import GenerationFailed
from src.shared.types import (
    ActiveAsset,
    BrandContext,
    GenerationInput,
    P1ProductionBundle,
    P1SemanticContract,
    P2SemanticContract,
    P5SemanticContract,
    ProductFact,
)
from src.tool.llm_gateway.deepseek import DeepSeekGenerator, FactBoundary


class FakeResponse:
    def __init__(
        self, status_code: int, payload: dict[str, Any], headers: dict[str, str] | None = None
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
        active_domain_assets=(
            ActiveAsset("B-TPO-001", "v0.1", "boundary", "场合", "先看场合。"),
            ActiveAsset("C-COMMUTE-001", "v0.1", "boundary", "通勤", "兼顾转场。"),
            ActiveAsset("D-DIRECT-001", "v0.1", "method", "直接", "明确选择。"),
            ActiveAsset("D-CRAFT-001", "v0.1", "method", "细节", "保留分寸。"),
        ),
    )


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
                            "content": '{"title":"从容选择","choice":"保住分寸","boundary":"活动受限时调整","next_action":"走动确认","natural_guide":"保住分寸","spoken_lines":"活动受限时调整","visual_actions":"走动确认","subtitles":"走动确认","sound_and_production":"一人手机"}'
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
    generator = DeepSeekGenerator(
        "https://compat.example/v1", "not-a-real-key", "verified-deepseek-model"
    )

    artifact = generator.generate(generation_input)

    assert artifact.model == "verified-deepseek-model"
    assert artifact.retry_count == 1
    assert artifact.provider_usage == {"total_tokens": 12}
    assert pauses == [0.0]
    request_json = FakeClient.requests[1]["json"]
    assert isinstance(request_json, dict)
    assert request_json["max_tokens"] == 3072
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


def test_deepseek_adapter_does_not_retry_nonrecoverable_status(
    monkeypatch: pytest.MonkeyPatch, generation_input: GenerationInput
) -> None:
    FakeClient.responses = [FakeResponse(400, {})]
    monkeypatch.setattr(httpx, "Client", FakeClient)
    generator = DeepSeekGenerator(
        "https://compat.example/v1", "not-a-real-key", "verified-deepseek-model"
    )

    with pytest.raises(GenerationFailed):
        generator.generate(generation_input)


def test_deepseek_adapter_accepts_provider_fenced_json(
    monkeypatch: pytest.MonkeyPatch, generation_input: GenerationInput
) -> None:
    FakeClient.responses = [
        FakeResponse(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": '```json\n{"title":"选择","choice":"选择","boundary":"边界","next_action":"下一步","natural_guide":"自然导读","spoken_lines":"台词","visual_actions":"动作","subtitles":"字幕","sound_and_production":"一人手机"}\n```'
                        }
                    }
                ]
            },
        )
    ]
    monkeypatch.setattr(httpx, "Client", FakeClient)
    generator = DeepSeekGenerator(
        "https://compat.example/v1", "not-a-real-key", "verified-deepseek-model"
    )

    artifact = generator.generate(generation_input)

    assert isinstance(artifact.semantic_contract, P1SemanticContract)
    assert artifact.semantic_contract.choice == "选择"


def test_deepseek_adapter_repairs_one_incomplete_structured_response(
    monkeypatch: pytest.MonkeyPatch, generation_input: GenerationInput
) -> None:
    complete = (
        '{"title":"选择",'
        '"choice":"选择","boundary":"边界","next_action":"下一步","natural_guide":"自然导读",'
        '"spoken_lines":"台词","visual_actions":"动作","subtitles":"字幕","sound_and_production":"一人手机"}'
    )
    FakeClient.responses = [
        FakeResponse(200, {"choices": [{"message": {"content": '{"outline":"缺字段"}'}}]}),
        FakeResponse(200, {"choices": [{"message": {"content": complete}}]}),
    ]
    FakeClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeClient)
    generator = DeepSeekGenerator(
        "https://compat.example/v1", "not-a-real-key", "verified-deepseek-model"
    )

    artifact = generator.generate(generation_input)

    assert artifact.retry_count == 1
    assert len(FakeClient.requests) == 2
    assert "字段缺失、为空或不是单个字符串" in str(FakeClient.requests[1]["json"])


def test_deepseek_adapter_repairs_non_string_visible_fields(
    monkeypatch: pytest.MonkeyPatch, generation_input: GenerationInput
) -> None:
    complete = (
        '{"title":"选择","choice":"选择","boundary":"边界","next_action":"下一步","natural_guide":"自然导读",'
        '"spoken_lines":"台词","visual_actions":"拍摄安排：动作","subtitles":"字幕","sound_and_production":"一人手机"}'
    )
    FakeClient.responses = [
        FakeResponse(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"title":"选择","choice":"选择","boundary":"边界","next_action":"下一步","natural_guide":"自然导读","spoken_lines":["台词"],"visual_actions":"动作","subtitles":"字幕","sound_and_production":"一人手机"}'
                        }
                    }
                ]
            },
        ),
        FakeResponse(200, {"choices": [{"message": {"content": complete}}]}),
    ]
    FakeClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeClient)
    generator = DeepSeekGenerator(
        "https://compat.example/v1", "not-a-real-key", "verified-deepseek-model"
    )

    artifact = generator.generate(generation_input)

    assert artifact.production.spoken_lines == "台词"
    assert artifact.retry_count == 1
    assert len(FakeClient.requests) == 2
    assert "不是单个字符串" in str(FakeClient.requests[1]["json"])


def test_deepseek_adapter_repairs_a_specific_unsupported_product_claim(
    monkeypatch: pytest.MonkeyPatch, generation_input: GenerationInput
) -> None:
    unsafe = (
        '{"title":"选择","choice":"选择","boundary":"边界","next_action":"下一步",'
        '"natural_guide":"自然导读","spoken_lines":"这件外套很保暖。","visual_actions":"拍摄安排：展示翻面",'
        '"subtitles":"这件外套很保暖。","sound_and_production":"一人手机"}'
    )
    repaired = '{"spoken_lines":"现有资料不能证明保暖表现。","subtitles":"现有资料不能证明保暖表现。"}'
    FakeClient.responses = [
        FakeResponse(200, {"choices": [{"message": {"content": unsafe}}]}),
        FakeResponse(200, {"choices": [{"message": {"content": repaired}}]}),
    ]
    FakeClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeClient)
    generator = DeepSeekGenerator(
        "https://compat.example/v1", "not-a-real-key", "verified-deepseek-model"
    )

    artifact = generator.generate(generation_input)

    assert "很保暖" not in artifact.body
    assert "现有资料不能证明保暖表现" in artifact.body
    assert {receipt.field for receipt in artifact.fact_repair_receipts} == {"spoken_lines", "subtitles"}
    assert len(FakeClient.requests) == 2
    repair_request = str(FakeClient.requests[1]["json"])
    assert "具体违规片段" in repair_request
    assert "spoken_lines" in repair_request
    assert "subtitles" in repair_request
    assert '"title"' not in repair_request


def test_deepseek_adapter_compiles_visible_body_only_from_controlled_fields() -> None:
    body = DeepSeekGenerator._visible_body(
        "自然标题",
        P1ProductionBundle("开场说明", "完整台词", "画面动作", "字幕文案", "声音提示"),
    )

    assert body.startswith("标题：自然标题")
    assert "完整台词/解说：完整台词" in body
    assert "画面与动作：画面动作" in body
    assert "字幕：字幕文案" in body
    assert "声音与制作提示：声音提示" in body


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
    assert "不能把全部差异归因于双面结构" in product
    assert "口袋情况未提供" not in product


def test_deepseek_adapter_accepts_a_p2_anti_misuse_boundary_without_accepting_the_claim() -> None:
    boundary = DeepSeekGenerator._natural_product(
        "ZX-C218", {"sample_weight_m_grams": 960, "comparison_single_layer_short_coat_m_grams": 650}
    )
    violations = DeepSeekGenerator._boundary_violations(
        FactBoundary(boundary, ""),
        "标题",
        P2SemanticContract("新增理解", "不能从重量差异推断厚度、手感或品质。", "当前样衣数据"),
        P1ProductionBundle("导读", "台词", "拍摄安排：称重", "字幕", "声音"),
    )

    assert violations == ()


def test_deepseek_adapter_rejects_an_unprovided_garment_component_in_p5() -> None:
    boundary = FactBoundary("商品 ZX-C218：两面均为完整外观。", "")
    violations = DeepSeekGenerator._boundary_violations(
        boundary,
        "标题",
        P5SemanticContract(
            "ZX-C218 双面短外套", "视觉重音来自翻面", "翻面动作不可移除"
        ),
        P1ProductionBundle("导读", "台词", "拍摄安排：翻开左襟露出格纹。", "字幕", "声音"),
    )

    assert violations[0].field == "visual_actions"
