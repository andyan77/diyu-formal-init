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
)
from src.tool.llm_gateway.deepseek import DeepSeekGenerator


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
                            "content": '{"body":"自然导读\\n保住分寸\\n完整台词/解说\\n活动受限时调整\\n画面与动作\\n走动确认\\n字幕\\n走动确认\\n声音与制作提示\\n一人手机","choice":"保住分寸","boundary":"活动受限时调整","next_action":"走动确认","natural_guide":"保住分寸","spoken_lines":"活动受限时调整","visual_actions":"走动确认","subtitles":"走动确认","sound_and_production":"一人手机"}'
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
    assert "B-TPO-001@v0.1" in request_payload
    assert "D-CRAFT-001@v0.1" in request_payload


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
                            "content": "```json\n{\"body\":\"自然导读\\n选择\\n边界\\n下一步\\n完整台词/解说\\n台词\\n画面与动作\\n动作\\n字幕\\n字幕\\n声音与制作提示\\n一人手机\",\"choice\":\"选择\",\"boundary\":\"边界\",\"next_action\":\"下一步\",\"natural_guide\":\"自然导读\",\"spoken_lines\":\"台词\",\"visual_actions\":\"动作\",\"subtitles\":\"字幕\",\"sound_and_production\":\"一人手机\"}\n```"
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

    assert artifact.semantic_contract.choice == "选择"


def test_deepseek_adapter_adds_missing_contract_values_to_visible_body() -> None:
    body = DeepSeekGenerator._body_with_contract(
        "自然导读\n完整台词/解说\n画面与动作\n字幕\n声音与制作提示",
        P1SemanticContract("会议后不换主线", "接孩子前会有活动量", "先走十步确认"),
    )

    assert "会议后不换主线" in body
    assert "接孩子前会有活动量" in body
    assert "先走十步确认" in body


def test_deepseek_adapter_adds_missing_production_parts_to_visible_body() -> None:
    body = DeepSeekGenerator._body_with_production(
        "自然导读：开场说明",
        P1ProductionBundle("开场说明", "完整台词", "画面动作", "字幕文案", "声音提示"),
    )

    assert "完整台词/解说：完整台词" in body
    assert "画面与动作：画面动作" in body
    assert "字幕：字幕文案" in body
    assert "声音与制作提示：声音提示" in body
