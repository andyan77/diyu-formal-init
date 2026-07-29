from __future__ import annotations

import json
from typing import cast

import httpx
import pytest

from src.shared.clause_license import (
    CLAUSE_LICENSE_REVIEW_VERSION,
    CLAUSE_LICENSE_TOOL_NAME,
    ClauseLicenseV1,
)
from src.shared.errors import GenerationFailed
from src.tool.llm_gateway.qwen_reviewer import QwenReviewerProvider


class _FakeResponse:
    def __init__(
        self,
        payload: dict[str, object],
        *,
        status_code: int = 200,
    ) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeClient:
    response = _FakeResponse({})
    requests: list[tuple[str, dict[str, object]]] = []

    def __init__(self, **_: object) -> None:
        pass

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def post(
        self,
        url: str,
        **kwargs: object,
    ) -> _FakeResponse:
        self.requests.append((url, kwargs))
        return self.response


@pytest.fixture(autouse=True)
def _fake_client(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeClient.requests = []
    _FakeClient.response = _FakeResponse({})
    monkeypatch.setattr(httpx, "Client", _FakeClient)


def _provider() -> QwenReviewerProvider:
    return QwenReviewerProvider(
        api_base_url=(
            "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
        api_key="test-only-key",
        model="qwen3.7-max-2026-05-20",
    )


def _licenses() -> tuple[ClauseLicenseV1, ...]:
    return (
        ClauseLicenseV1(
            license_version="clause-license-v1",
            license_id="license:unit:body:clause:1",
            clause_id="unit:body:clause:1",
            unit_id="unit:body",
            text_source="writer_unit",
            discourse_contract="actuality_reflection",
            subject_scope="generic_only",
            allowed_expression_types=(
                "generic_observation",
                "recommendation",
                "non_situated_metaphor",
            ),
            allowed_fact_refs=(),
            prohibited_bindings=(
                "current_person",
                "unfrozen_dialogue",
            ),
        ),
    )


def _document() -> dict[str, object]:
    license_ = _licenses()[0]
    return {
        "review_version": CLAUSE_LICENSE_REVIEW_VERSION,
        "reviews": [
            {
                "clause_id": license_.clause_id,
                "license_id": license_.license_id,
                "expression_type": "generic_observation",
                "binding_checks": [
                    {
                        "binding_id": binding,
                        "status": "absent",
                    }
                    for binding in license_.prohibited_bindings
                ],
                "unsupported_quote": "",
            }
        ],
    }


def _payload(
    *,
    document: object | None = None,
    status: str = "completed",
    name: str = CLAUSE_LICENSE_TOOL_NAME,
    call_count: int = 1,
    extra_output: dict[str, object] | None = None,
) -> dict[str, object]:
    function_call: dict[str, object] = {
        "type": "function_call",
        "name": name,
        "arguments": json.dumps(
            document if document is not None else _document(),
            ensure_ascii=False,
        ),
        "call_id": "call-review",
    }
    output: list[dict[str, object]] = [
        {"type": "reasoning", "id": "reasoning-review"},
        *[dict(function_call) for _ in range(call_count)],
    ]
    if extra_output is not None:
        output.append(extra_output)
    return {
        "id": "response-review",
        "status": status,
        "error": None,
        "output": output,
        "usage": {
            "input_tokens": 120,
            "output_tokens": 40,
            "total_tokens": 160,
        },
    }


def test_qwen_reviewer_uses_one_responses_function_with_fail_closed_auto_choice() -> None:
    _FakeClient.response = _FakeResponse(_payload())

    result = _provider().review(
        system_prompt="system",
        user_prompt="prompt",
        licenses=_licenses(),
        timeout_seconds=90.0,
    )

    assert result.reviews.review_version == CLAUSE_LICENSE_REVIEW_VERSION
    assert result.retry_count == 0
    assert len(_FakeClient.requests) == 1
    url, request = _FakeClient.requests[0]
    assert url.endswith("/compatible-mode/v1/responses")
    headers = request["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer test-only-key"
    body = request["json"]
    assert isinstance(body, dict)
    assert body["model"] == "qwen3.7-max-2026-05-20"
    assert body["instructions"] == "system"
    assert body["input"] == "prompt"
    assert body["reasoning"] == {"effort": "high"}
    assert body["tool_choice"] == "auto"
    assert body["store"] is False
    tools = cast(list[dict[str, object]], body["tools"])
    assert len(tools) == 1
    assert tools[0]["type"] == "function"
    assert tools[0]["name"] == CLAUSE_LICENSE_TOOL_NAME
    assert isinstance(tools[0]["parameters"], dict)
    assert "temperature" not in body
    assert "response_format" not in body
    assert "previous_response_id" not in body


@pytest.mark.parametrize(
    "payload",
    (
        _payload(status="incomplete"),
        _payload(call_count=0),
        _payload(call_count=2),
        _payload(name="wrong_function"),
        _payload(
            extra_output={
                "type": "message",
                "content": [{"type": "output_text", "text": "{}"}],
            }
        ),
    ),
)
def test_qwen_reviewer_rejects_noncanonical_transport(
    payload: dict[str, object],
) -> None:
    _FakeClient.response = _FakeResponse(payload)

    with pytest.raises(GenerationFailed, match="许可证据不完整"):
        _provider().review(
            system_prompt="system",
            user_prompt="prompt",
            licenses=_licenses(),
            timeout_seconds=90.0,
        )

    assert len(_FakeClient.requests) == 1


def test_qwen_reviewer_rejects_invalid_or_incomplete_arguments() -> None:
    invalid = _payload(document={"review_version": CLAUSE_LICENSE_REVIEW_VERSION})
    _FakeClient.response = _FakeResponse(invalid)

    with pytest.raises(GenerationFailed, match="许可证据不完整"):
        _provider().review(
            system_prompt="system",
            user_prompt="prompt",
            licenses=_licenses(),
            timeout_seconds=90.0,
        )


def test_qwen_reviewer_has_no_retry_or_provider_fallback() -> None:
    _FakeClient.response = _FakeResponse(
        {"error": {"code": "rate_limit"}},
        status_code=429,
    )

    with pytest.raises(GenerationFailed, match="服务拒绝"):
        _provider().review(
            system_prompt="system",
            user_prompt="prompt",
            licenses=_licenses(),
            timeout_seconds=90.0,
        )

    assert len(_FakeClient.requests) == 1
