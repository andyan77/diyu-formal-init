from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import httpx
import pytest

from src.shared.clause_license import (
    CLAUSE_LICENSE_REVIEW_VERSION,
    CLAUSE_LICENSE_TOOL_NAME,
    ClauseLicenseV1,
    UnitClauseLicensePolicyV1,
    clause_license_review_json_schema,
    materialize_clause_licenses_v1,
)
from src.shared.closed_review import (
    CLOSED_REVIEW_DIMENSIONS,
    CLOSED_REVIEW_TOOL_NAME,
    CLOSED_REVIEW_VERSION,
    ClosedReviewQuestion,
    build_closed_review_questions,
    closed_review_json_schema,
)
from src.shared.errors import GenerationFailed
from src.shared.narrative import NarrativeIssue
from src.shared.review_evidence import (
    ClauseContextV2,
    validate_server_owned_contexts_v2,
    writer_clause_contexts_v2,
)
from src.tool.llm_gateway.deepseek import DeepSeekGenerator


class _FakeResponse:
    def __init__(
        self,
        payload: dict[str, Any],
        status_code: int = 200,
    ) -> None:
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


def _generator(
    base_url: str = "https://example.invalid",
) -> DeepSeekGenerator:
    return DeepSeekGenerator(
        base_url,
        "test-key",
        "deepseek-v4-flash",
        reviewer_model="deepseek-v4-pro",
        max_retries=9,
    )


def _writer_context(
    text: str = "换位思考不等于没有边界。",
) -> ClauseContextV2:
    return ClauseContextV2(
        "unit:body:clause:1",
        "unit:body",
        text,
        1001,
        "writer_unit",
        "abstract_observation",
        "institutional_account",
    )


def _questions(
    text: str = "换位思考不等于没有边界。",
) -> tuple[ClosedReviewQuestion, ...]:
    return build_closed_review_questions((_writer_context(text),))


def _licenses() -> tuple[ClauseLicenseV1, ...]:
    context = _writer_context()
    return materialize_clause_licenses_v1(
        contexts=(context,),
        policies=(
            UnitClauseLicensePolicyV1(
                unit_id=context.unit_id,
                discourse_contract=context.unit_contract,
                subject_scope="generic_only",
                allowed_fact_refs=(),
                prohibited_bindings=(
                    "current_person",
                    "current_institution",
                    "protected_exact_subject",
                ),
            ),
        ),
    )


def _license_review_document() -> dict[str, object]:
    license_ = _licenses()[0]
    return {
        "review_version": CLAUSE_LICENSE_REVIEW_VERSION,
        "reviews": [
            {
                "clause_id": license_.clause_id,
                "license_id": license_.license_id,
                "verdict": "supported",
                "reason_code": "supported_by_license",
                "unsupported_quote": "",
            }
        ],
    }


def _answer_document(
    questions: tuple[ClosedReviewQuestion, ...] | None = None,
) -> dict[str, object]:
    active = questions or _questions()
    return {
        "evidence_version": CLOSED_REVIEW_VERSION,
        "answers": [
            {
                "question_id": question.question_id,
                "uncertain": False,
                "operands": (["generic_observation"] if question.dimension == "statement_mode" else []),
            }
            for question in active
        ],
    }


def _strict_payload(
    document: object | None = None,
    *,
    finish_reason: str = "tool_calls",
    tool_name: str = CLOSED_REVIEW_TOOL_NAME,
    tool_count: int = 1,
    completion_tokens: int = 100,
) -> dict[str, Any]:
    arguments = json.dumps(
        document if document is not None else _answer_document(),
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


def _schema_property_names(node: object) -> set[str]:
    names: set[str] = set()
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            names.update(properties)
        for value in node.values():
            names.update(_schema_property_names(value))
    elif isinstance(node, list):
        for value in node:
            names.update(_schema_property_names(value))
    return names


def test_strict_schema_requires_closed_answer_fields() -> None:
    questions = _questions()
    schema = closed_review_json_schema(questions)

    _assert_strict_objects(schema)
    properties = schema["properties"]
    assert isinstance(properties, dict)
    assert properties["evidence_version"] == {
        "type": "string",
        "enum": [CLOSED_REVIEW_VERSION],
    }
    answers = properties["answers"]
    assert isinstance(answers, dict)
    answer = answers["items"]
    assert isinstance(answer, dict)
    answer_properties = answer["properties"]
    assert isinstance(answer_properties, dict)
    assert list(answer_properties) == [
        "question_id",
        "uncertain",
        "operands",
    ]
    assert {"start", "end", "occurrence"}.isdisjoint(_schema_property_names(schema))
    assert answer_properties["question_id"] == {
        "type": "string",
        "enum": [question.question_id for question in questions],
    }


def test_reviewer_uses_only_beta_strict_tool_without_json_fallback() -> None:
    questions = _questions()
    _FakeClient.response = _FakeResponse(_strict_payload())

    payload, retries = _generator("https://example.invalid/v1")._request_strict_review(
        "system",
        "prompt",
        question_count=len(questions),
        questions=questions,
    )

    assert payload == _FakeClient.response.json()
    assert retries == 0
    assert len(_FakeClient.requests) == 1
    url, request = _FakeClient.requests[0]
    assert url == "https://example.invalid/beta/chat/completions"
    body = request["json"]
    assert isinstance(body, dict)
    assert body["model"] == "deepseek-v4-pro"
    assert body["temperature"] == 0.0
    assert body["max_tokens"] == 2624
    assert body["thinking"] == {"type": "disabled"}
    assert "response_format" not in body
    assert body["tool_choice"] == {
        "type": "function",
        "function": {"name": CLOSED_REVIEW_TOOL_NAME},
    }
    tools = body["tools"]
    assert isinstance(tools, list)
    assert len(tools) == 1
    function = tools[0]["function"]
    assert function["name"] == CLOSED_REVIEW_TOOL_NAME
    assert function["strict"] is True
    _assert_strict_objects(function["parameters"])


def test_runtime_license_review_uses_only_beta_strict_tool() -> None:
    licenses = _licenses()
    _FakeClient.response = _FakeResponse(
        _strict_payload(
            _license_review_document(),
            tool_name=CLAUSE_LICENSE_TOOL_NAME,
        )
    )

    payload, retries = _generator("https://example.invalid/v1")._request_strict_license_review(
        "system",
        "prompt",
        license_count=len(licenses),
        licenses=licenses,
    )

    assert payload == _FakeClient.response.json()
    assert retries == 0
    assert len(_FakeClient.requests) == 1
    url, request = _FakeClient.requests[0]
    assert url == "https://example.invalid/beta/chat/completions"
    body = request["json"]
    assert isinstance(body, dict)
    assert body["model"] == "deepseek-v4-pro"
    assert body["temperature"] == 0.0
    assert body["thinking"] == {"type": "disabled"}
    assert "response_format" not in body
    assert body["tool_choice"] == {
        "type": "function",
        "function": {"name": CLAUSE_LICENSE_TOOL_NAME},
    }
    tools = body["tools"]
    assert isinstance(tools, list)
    function = tools[0]["function"]
    assert function["strict"] is True
    assert function["parameters"] == clause_license_review_json_schema(licenses)
    _assert_strict_objects(function["parameters"])


def test_runtime_license_review_rejects_old_closed_question_tool() -> None:
    licenses = _licenses()
    payload = _strict_payload(
        _license_review_document(),
        tool_name=CLOSED_REVIEW_TOOL_NAME,
    )

    with pytest.raises(TypeError, match="function name"):
        DeepSeekGenerator._strict_license_review_answers(
            payload,
            licenses=licenses,
        )


def test_runtime_license_review_never_repairs_invalid_json_arguments() -> None:
    licenses = _licenses()
    payload = _strict_payload(
        _license_review_document(),
        tool_name=CLAUSE_LICENSE_TOOL_NAME,
    )
    function = payload["choices"][0]["message"]["tool_calls"][0]["function"]
    function["arguments"] = (
        '{"review_version":"clause-license-review-v1",'
        '"reviews":[{"unsupported_quote":"他说"辛苦了""}]}'
    )

    with pytest.raises(json.JSONDecodeError):
        DeepSeekGenerator._strict_license_review_answers(
            payload,
            licenses=licenses,
        )


def test_writer_and_reviewer_model_routes_are_independent() -> None:
    questions = _questions()
    _FakeClient.response = _FakeResponse({"choices": []})
    generator = _generator()

    generator._request("system", "prompt", 100)

    _, writer_request = _FakeClient.requests[-1]
    writer_body = writer_request["json"]
    assert isinstance(writer_body, dict)
    assert writer_body["model"] == "deepseek-v4-flash"

    _FakeClient.response = _FakeResponse(_strict_payload())
    generator._request_strict_review(
        "system",
        "prompt",
        question_count=len(questions),
        questions=questions,
    )

    _, reviewer_request = _FakeClient.requests[-1]
    reviewer_body = reviewer_request["json"]
    assert isinstance(reviewer_body, dict)
    assert reviewer_body["model"] == "deepseek-v4-pro"
    assert generator.model_name == "deepseek-v4-flash"
    assert generator.reviewer_model_name == "deepseek-v4-pro"


def test_reviewer_token_budget_is_deterministic_and_hard_capped() -> None:
    generator = _generator()

    assert generator._review_max_tokens(1) == 1184
    assert generator._review_max_tokens(10) == 2624
    assert generator._review_max_tokens(80) == 13824
    assert generator._review_max_tokens(100) == 16384
    with pytest.raises(ValueError, match="positive"):
        generator._review_max_tokens(0)


def test_reviewer_prompt_uses_closed_questions_without_addresses() -> None:
    context = _writer_context("如果双方先停一下，就更容易听清彼此。")
    questions = build_closed_review_questions((context,))
    prompt = DeepSeekGenerator._kernel_reviewer_prompt(
        questions=questions,
        contexts=(context,),
        actuality_facts=(),
        protected_subjects=("笛语",),
    )

    assert "每个固定风险问题恰好" in prompt
    assert "不能通过省略整个问题表达" in prompt
    assert "uncertain 当 absent" in prompt
    assert "subject_binding" in prompt
    assert "relationship_claim" in prompt
    assert "motive_or_mental_state" in prompt
    assert "statement_mode" in prompt
    assert "只向受众征询观点、经验或选择" in prompt
    assert "用于其后的泛指反思" in prompt
    assert "这篇内容／这个角度" in prompt
    assert "题材相似不是现实主体绑定" in prompt
    assert "比喻、类比或拟人本身不构成 dramatization" in prompt
    assert "每题只返回 uncertain 和 operands" in prompt
    assert "某个\n  subject_binding 类别存在时必须把该类别放入 operands" in prompt
    assert "商品名称或编号作为主体只在 subject_binding 使用 named_product" in prompt
    assert "不得跨 question 借用" in prompt
    assert "不要返回 quote、start、end、occurrence" in prompt
    assert '"uncertain":false' in prompt
    assert "Unicode offset 与审计 quote 都由" in prompt


def test_closed_questions_batch_by_whole_clauses() -> None:
    contexts = tuple(
        replace(
            _writer_context(f"第{index}句。"),
            clause_id=f"unit:body:clause:{index}",
            visible_order=1000 + index,
        )
        for index in range(1, 18)
    )
    questions = build_closed_review_questions(contexts)

    batches = DeepSeekGenerator._closed_review_batches(questions)

    assert tuple(len(batch) for batch in batches) == (80, 80, 10)
    for batch in batches:
        counts: dict[str, int] = {}
        for question in batch:
            counts[question.clause_id] = counts.get(question.clause_id, 0) + 1
        assert set(counts.values()) == {len(CLOSED_REVIEW_DIMENSIONS)}


@pytest.mark.parametrize(
    ("payload", "reason"),
    (
        (
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(_answer_document()),
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
        DeepSeekGenerator._strict_review_answers(
            payload,
            questions=_questions(),
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
        DeepSeekGenerator._strict_review_answers(
            payload,
            questions=_questions(),
        )


def test_server_derives_present_status_from_closed_operands() -> None:
    questions = _questions()
    document = _answer_document(questions)
    answers = document["answers"]
    assert isinstance(answers, list)
    subject = answers[0]
    assert isinstance(subject, dict)
    subject["operands"] = ["generic"]

    parsed = DeepSeekGenerator._strict_review_answers(
        _strict_payload(document),
        questions=questions,
    )

    assert parsed.answers[0].status == "present"
    assert parsed.answers[0].evidence_scope == "entire_clause"
    assert parsed.answers[0].quote == questions[0].exact_text


@pytest.mark.parametrize(
    "mutation",
    ("missing_answer", "missing_field", "extra", "null", "wrong_order"),
)
def test_strict_arguments_are_never_defaulted_or_repaired(
    mutation: str,
) -> None:
    document = _answer_document()
    answers = document["answers"]
    assert isinstance(answers, list)
    if mutation == "missing_answer":
        answers.pop()
    elif mutation == "missing_field":
        answer = answers[0]
        assert isinstance(answer, dict)
        answer.pop("uncertain")
    elif mutation == "extra":
        answer = answers[0]
        assert isinstance(answer, dict)
        answer["observation_type"] = "abstract_principle"
    elif mutation == "null":
        answer = answers[0]
        assert isinstance(answer, dict)
        answer["uncertain"] = None
    else:
        answers[0], answers[1] = answers[1], answers[0]

    with pytest.raises(TypeError, match="closed review"):
        DeepSeekGenerator._strict_review_answers(
            _strict_payload(document),
            questions=_questions(),
        )


def test_old_open_evidence_arguments_are_not_silently_repaired() -> None:
    document = {
        "evidence_version": CLOSED_REVIEW_VERSION,
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

    with pytest.raises(TypeError, match="closed review root"):
        DeepSeekGenerator._strict_review_answers(
            _strict_payload(document),
            questions=_questions(),
        )


def test_server_owned_sources_are_validated_but_not_asked() -> None:
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

    assert (
        validate_server_owned_contexts_v2(
            contexts=contexts,
            fact_text_by_id={"source:user_actuality:1": "今天店里忙了一天。"},
        )
        == ()
    )
    assert tuple(context.clause_id for context in writer_clause_contexts_v2(contexts)) == ("unit:body:clause:2",)
    assert {question.clause_id for question in build_closed_review_questions(contexts)} == {"unit:body:clause:2"}

    bad_wrapper = replace(contexts[0], exact_text="假设有这一幕：\n")
    assert validate_server_owned_contexts_v2(
        contexts=(bad_wrapper, *contexts[1:]),
        fact_text_by_id={"source:user_actuality:1": "今天店里忙了一天。"},
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
        fact_text_by_id={"source:user_actuality:1": "今天店里忙了一天。"},
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
            question_count=10,
            questions=_questions(),
        )

    assert len(_FakeClient.requests) == 1
