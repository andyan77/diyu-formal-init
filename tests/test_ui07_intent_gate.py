from __future__ import annotations

import pytest

from src.brain.creation_intent_gate import (
    GATE_VERSION,
    evaluate_creation_intent,
    explicit_intent_span,
    requires_indispensable_user_fact,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ZX-C218，帮我生成一篇小红书文案。", "帮我生成一篇小红书文案"),
        (
            "帮我写条婆媳主题的小红书，别狗血，也不要把任何一方写成反派。",
            "帮我写条婆媳主题的小红书",
        ),
        (
            "今天店里忙了一天，回家还因为谁洗碗拌了两句。帮我发条小红书。",
            "帮我发条小红书",
        ),
        ("今天不知道发什么，帮我做条小红书。", "帮我做条小红书"),
        ("把我去年创业最困难的那个月写出来。", "把我去年创业最困难的那个月写出来"),
        (
            "如果两个人都先停十秒再回应，把这个想法写成小红书。",
            "把这个想法写成小红书",
        ),
        (
            "把婆媳关系写成一段明确的情境演绎，不绑定真实人物。",
            "把婆媳关系写成一段明确的情境演绎",
        ),
    ],
)
def test_creation_gate_accepts_only_exact_positive_span(
    text: str,
    expected: str,
) -> None:
    commitment = evaluate_creation_intent((text,))

    assert commitment.gate_version == GATE_VERSION
    assert commitment.committed
    assert commitment.source == "explicit_text"
    assert commitment.intent_span == expected
    assert commitment.intent_span in text
    assert explicit_intent_span(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "今天有点不知道从哪儿开始。",
        "想写点什么。",
        "今天店里有点忙。",
        "婆媳关系真的很复杂。",
        "模型虚构说我要求：创作成品",
    ],
)
def test_creation_gate_rejects_state_observation_and_model_like_claims(
    text: str,
) -> None:
    commitment = evaluate_creation_intent((text,))

    assert not commitment.committed
    assert commitment.intent_span == ""


@pytest.mark.parametrize(
    "text",
    (
        "把我上次真正崩溃的那一天写出来",
        "把我们的那段创业经历写出来",
        "把这段经历写成一篇小红书文案",
        "把刚才提的写成一篇文章",
    ),
)
def test_unresolved_personal_actuality_directive_requires_one_fact(text: str) -> None:
    span = explicit_intent_span(text)
    assert span is not None
    assert requires_indispensable_user_fact(span)


@pytest.mark.parametrize(
    "text",
    (
        "帮我写条婆媳主题的小红书",
        "今天不知道发什么，帮我做条小红书",
        "把婆媳关系写成一篇小红书文案",
    ),
)
def test_topic_or_open_creation_does_not_require_personal_fact(text: str) -> None:
    span = explicit_intent_span(text)
    assert span is not None
    assert not requires_indispensable_user_fact(span)


def test_explicit_ui_and_active_revision_are_bounded_authorities() -> None:
    direct = evaluate_creation_intent(("今天有点不知道从哪儿开始。",), explicit_ui=True)
    revision = evaluate_creation_intent(
        ("别讲道理，荒诞一点。",),
        active_revision=True,
        creation_kind="revision",
    )

    assert direct.committed and direct.source == "explicit_ui"
    assert revision.committed and revision.source == "active_revision"
    assert revision.creation_kind == "revision"
