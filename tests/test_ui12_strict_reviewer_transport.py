from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import httpx
import pytest

from src.shared.errors import GenerationFailed
from src.shared.narrative import NarrativeIssue
from src.shared.review_evidence import (
    REVIEW_EVIDENCE_V2_TOOL_NAME,
    REVIEW_EVIDENCE_V2_VERSION,
    ClauseContextV2,
    ReviewClause,
    review_evidence_v2_json_schema,
    unique_review_quote_candidates,
    validate_server_owned_contexts_v2,
    writer_clause_contexts_v2,
)
from src.tool.llm_gateway.deepseek import DeepSeekGenerator


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
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


def _generator(base_url: str = "https://example.invalid") -> DeepSeekGenerator:
    return DeepSeekGenerator(
        base_url,
        "test-key",
        "deepseek-v4-flash",
        max_retries=9,
    )


def _evidence_document() -> dict[str, object]:
    return {
        "evidence_version": REVIEW_EVIDENCE_V2_VERSION,
        "clauses": [
            {
                "clause_id": "unit:body:clause:1",
                "exact_text": "换位思考不等于没有边界。",
                "evidence": [
                    {
                        "category": "predicate",
                        "text": "不等于",
                    }
                ],
                "implicit_subject": "none",
                "uncertain": False,
            }
        ],
    }


def _strict_payload(
    document: object | None = None,
    *,
    finish_reason: str = "tool_calls",
    tool_name: str = REVIEW_EVIDENCE_V2_TOOL_NAME,
    tool_count: int = 1,
    completion_tokens: int = 100,
) -> dict[str, Any]:
    arguments = json.dumps(
        document if document is not None else _evidence_document(),
        ensure_ascii=False,
    )
    tool_call = {
        "id": "call-review-v2",
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": arguments,
        },
    }
    return {
        "choices": [
            {
                "finish_reason": finish_reason,
                "message": {
                    "content": None,
                    "tool_calls": [dict(tool_call) for _ in range(tool_count)],
                },
            }
        ],
        "usage": {"completion_tokens": completion_tokens},
    }


def _assert_strict_objects(node: object) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object":
            properties = node.get("properties")
            required = node.get("required")
            assert isinstance(properties, dict)
            assert required == list(properties)
            assert node.get("additionalProperties") is False
        for value in node.values():
            _assert_strict_objects(value)
    elif isinstance(node, list):
        for value in node:
            _assert_strict_objects(value)


def test_strict_schema_requires_every_nested_object_field() -> None:
    schema = review_evidence_v2_json_schema()

    _assert_strict_objects(schema)
    properties = schema["properties"]
    assert isinstance(properties, dict)
    assert properties["evidence_version"] == {
        "type": "string",
        "enum": [REVIEW_EVIDENCE_V2_VERSION],
    }
    clauses = properties["clauses"]
    assert isinstance(clauses, dict)
    clause = clauses["items"]
    assert isinstance(clause, dict)
    clause_properties = clause["properties"]
    assert isinstance(clause_properties, dict)
    assert clause_properties["implicit_subject"] == {
        "type": "string",
        "enum": ["none", "current_speaker", "generic", "uncertain"],
    }
    assert clause_properties["uncertain"] == {"type": "boolean"}
    evidence = clause_properties["evidence"]
    assert isinstance(evidence, dict)
    evidence_item = evidence["items"]
    assert isinstance(evidence_item, dict)
    evidence_properties = evidence_item["properties"]
    assert isinstance(evidence_properties, dict)
    assert evidence_properties["category"] == {
        "type": "string",
        "enum": [
            "subject",
            "predicate",
            "action_or_event",
            "dialogue",
            "motive",
            "cause",
            "result",
            "time",
            "location",
            "modality",
            "aspect",
        ],
    }
    text_property = evidence_properties["text"]
    assert isinstance(text_property, dict)
    assert text_property["type"] == "string"
    assert "occurs once" in str(text_property["description"])
    assert evidence_item["required"] == ["category", "text"]


def test_reviewer_uses_only_beta_strict_tool_without_json_fallback() -> None:
    _FakeClient.response = _FakeResponse(_strict_payload())

    payload, retries = _generator("https://example.invalid/v1")._request_strict_review(
        "system",
        "prompt",
        clause_count=25,
        allowed_quotes=(
            "换位思考不等于没有边界",
            "婆婆要尊重儿媳",
        ),
    )

    assert payload == _FakeClient.response.json()
    assert retries == 0
    assert len(_FakeClient.requests) == 1
    url, request = _FakeClient.requests[0]
    assert url == "https://example.invalid/beta/chat/completions"
    body = request["json"]
    assert isinstance(body, dict)
    assert body["temperature"] == 0.0
    assert body["max_tokens"] == 13824
    assert body["thinking"] == {"type": "disabled"}
    assert "response_format" not in body
    assert body["tool_choice"] == {
        "type": "function",
        "function": {"name": REVIEW_EVIDENCE_V2_TOOL_NAME},
    }
    tools = body["tools"]
    assert isinstance(tools, list)
    assert len(tools) == 1
    function = tools[0]["function"]
    assert function["name"] == REVIEW_EVIDENCE_V2_TOOL_NAME
    assert function["strict"] is True
    _assert_strict_objects(function["parameters"])
    parameters = function["parameters"]
    assert isinstance(parameters, dict)
    root_properties = parameters["properties"]
    assert isinstance(root_properties, dict)
    clauses = root_properties["clauses"]
    assert isinstance(clauses, dict)
    clause = clauses["items"]
    assert isinstance(clause, dict)
    clause_properties = clause["properties"]
    assert isinstance(clause_properties, dict)
    evidence = clause_properties["evidence"]
    assert isinstance(evidence, dict)
    evidence_item = evidence["items"]
    assert isinstance(evidence_item, dict)
    evidence_properties = evidence_item["properties"]
    assert isinstance(evidence_properties, dict)
    assert evidence_properties["text"] == {
        "type": "string",
        "description": (
            "Server-provided exact evidence quote that occurs once in its "
            "source clause; never return an address or index."
        ),
        "enum": [
            "换位思考不等于没有边界",
            "婆婆要尊重儿媳",
        ],
    }


def test_reviewer_token_budget_is_deterministic_and_hard_capped() -> None:
    generator = _generator()

    assert generator._review_max_tokens(1) == 1536
    assert generator._review_max_tokens(25) == 13824
    assert generator._review_max_tokens(30) == 16384
    assert generator._review_max_tokens(100) == 16384
    with pytest.raises(ValueError, match="positive"):
        generator._review_max_tokens(0)


def test_reviewer_requires_unique_source_quotes_without_model_addresses() -> None:
    prompt = DeepSeekGenerator._kernel_reviewer_prompt(
        (
            ReviewClause(
                unit_id="unit:body",
                clause_id="unit:body:clause:1",
                exact_text="婆婆停了一下，又继续说话。",
                visible_order=1001,
            ),
        )
    )

    assert "每项只返回 category\n与 text" in prompt
    assert "text 必须从当前 clause 的 allowed_quotes" in prompt
    assert "并已在其来源 clause 内唯一" in prompt
    assert "不得自行缩短、拼接或创造 quote" in prompt
    assert '"allowed_quotes": ["婆婆停了一下，", "又继续说话。"]' in prompt
    assert "不要计算或返回\nstart/end/occurrence" in prompt
    assert "各 category 不是互斥分类" in prompt
    assert "无论它是已发生、假设、建议、否定、泛指或演绎" in prompt
    assert "还必须独立返回 action_or_event" in prompt
    assert "不判断现实性" in prompt
    assert "在一个可想象情境中实施的具体行为" in prompt
    assert "活动概念名称" in prompt
    assert "导航描述本身，不属于 action_or_event" in prompt
    assert "修辞性动作或因果比喻也不属于 action_or_event" in prompt


def test_server_quote_vocabulary_excludes_repeated_short_phrases() -> None:
    text = "婆婆先停一下，婆婆再回应。"
    candidates = unique_review_quote_candidates((text,))

    assert candidates == (
        "婆婆先停一下，",
        "婆婆再回应。",
    )
    assert "婆婆" not in candidates
    for candidate in candidates:
        assert text.count(candidate) == 1


def test_server_quote_vocabulary_expands_only_repeated_chunks() -> None:
    text = "先说，先说。"

    assert unique_review_quote_candidates((text,)) == (
        "先说，",
        "先说。",
    )


@pytest.mark.parametrize(
    ("payload", "reason"),
    (
        (
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(_evidence_document()),
                        },
                    }
                ]
            },
            "finish reason",
        ),
        (_strict_payload(finish_reason="length"), "finish reason"),
        (_strict_payload(tool_count=2), "tool call count"),
        (_strict_payload(tool_name="wrong_function"), "function name"),
        (
            _strict_payload(completion_tokens=16385),
            "exceeded hard limit",
        ),
    ),
)
def test_only_one_complete_named_tool_call_is_accepted(
    payload: dict[str, Any],
    reason: str,
) -> None:
    with pytest.raises(TypeError, match=reason):
        DeepSeekGenerator._strict_review_evidence(
            payload,
            clause_text_by_id={
                "unit:body:clause:1": "换位思考不等于没有边界。"
            },
        )


@pytest.mark.parametrize("arguments", (None, "{"))
def test_tool_arguments_must_be_an_unmodified_json_string(
    arguments: str | None,
) -> None:
    payload = _strict_payload()
    function = payload["choices"][0]["message"]["tool_calls"][0]["function"]
    if arguments is None:
        function.pop("arguments")
        expected_error: type[Exception] = TypeError
    else:
        function["arguments"] = arguments
        expected_error = json.JSONDecodeError

    with pytest.raises(expected_error):
        DeepSeekGenerator._strict_review_evidence(
            payload,
            clause_text_by_id={
                "unit:body:clause:1": "换位思考不等于没有边界。"
            },
        )


@pytest.mark.parametrize(
    "mutation",
    ("missing_subject", "missing_uncertain", "root_aspect", "extra", "null"),
)
def test_strict_arguments_are_never_defaulted_or_repaired(
    mutation: str,
) -> None:
    document = _evidence_document()
    clauses = document["clauses"]
    assert isinstance(clauses, list)
    clause = clauses[0]
    assert isinstance(clause, dict)
    if mutation == "missing_subject":
        clause.pop("implicit_subject")
    elif mutation == "missing_uncertain":
        clause.pop("uncertain")
    elif mutation == "root_aspect":
        clause["aspect"] = []
    elif mutation == "extra":
        clause["observation_type"] = "abstract_principle"
    else:
        clause["uncertain"] = None

    with pytest.raises(TypeError, match="review evidence v2"):
        DeepSeekGenerator._strict_review_evidence(
            _strict_payload(document),
            clause_text_by_id={
                "unit:body:clause:1": "换位思考不等于没有边界。"
            },
        )


@pytest.mark.parametrize(
    "legacy_span",
    (
        {"text": "不等于", "start": 4, "end": 7},
        {"text": "不等于", "occurrence": 1},
    ),
)
def test_old_address_arguments_are_not_silently_repaired(
    legacy_span: dict[str, object],
) -> None:
    document = _evidence_document()
    clauses = document["clauses"]
    assert isinstance(clauses, list)
    clause = clauses[0]
    assert isinstance(clause, dict)
    clause["evidence"] = [
        {
            "category": "predicate",
            **legacy_span,
        }
    ]

    with pytest.raises(TypeError, match="item"):
        DeepSeekGenerator._strict_review_evidence(
            _strict_payload(document),
            clause_text_by_id={
                "unit:body:clause:1": "换位思考不等于没有边界。"
            },
        )


def test_server_owned_sources_are_validated_but_not_sent_to_reviewer() -> None:
    contexts = (
        ClauseContextV2(
            "unit:body:clause:1",
            "unit:body",
            "假设有这样一幕：\n",
            1001,
            "server_wrapper",
            "hypothetical_example",
            "institutional_account",
        ),
        ClauseContextV2(
            "unit:body:clause:2",
            "unit:body",
            "婆婆先停了一下。",
            1002,
            "writer_unit",
            "hypothetical_example",
            "institutional_account",
        ),
        ClauseContextV2(
            "unit:frozen-fact:1:clause:1",
            "unit:frozen-fact:1",
            "今天店里忙了一天。",
            2001,
            "frozen_user_fact",
            "frozen_fact",
            "institutional_account",
            "source:user_actuality:1",
        ),
    )

    assert validate_server_owned_contexts_v2(
        contexts=contexts,
        fact_text_by_id={
            "source:user_actuality:1": "今天店里忙了一天。"
        },
    ) == ()
    assert tuple(
        context.clause_id
        for context in writer_clause_contexts_v2(contexts)
    ) == ("unit:body:clause:2",)

    bad_wrapper = replace(contexts[0], exact_text="假设有这一幕：\n")
    assert validate_server_owned_contexts_v2(
        contexts=(bad_wrapper, *contexts[1:]),
        fact_text_by_id={
            "source:user_actuality:1": "今天店里忙了一天。"
        },
    ) == (
        NarrativeIssue(
            "unit:body",
            "server_wrapper_drift",
            "假设有这一幕：\n",
        ),
    )
    bad_fact = replace(contexts[2], exact_text="今天店里特别忙。")
    assert validate_server_owned_contexts_v2(
        contexts=(*contexts[:2], bad_fact),
        fact_text_by_id={
            "source:user_actuality:1": "今天店里忙了一天。"
        },
    ) == (
        NarrativeIssue(
            "unit:frozen-fact:1",
            "frozen_fact_changed",
            "今天店里特别忙。",
        ),
    )


def test_strict_transport_service_rejection_never_retries() -> None:
    _FakeClient.response = _FakeResponse({}, status_code=400)

    with pytest.raises(GenerationFailed, match="拒绝"):
        _generator()._request_strict_review(
            "system",
            "prompt",
            clause_count=1,
        )

    assert len(_FakeClient.requests) == 1
