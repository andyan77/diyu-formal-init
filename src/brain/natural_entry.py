from __future__ import annotations

import re

_CONTINUATION_SIGNALS = ("接着上一条", "延续之前", "继续上一条", "沿用上一条")
_EXACT_SMALL_TALK = frozenset(("hello", "hi", "你好", "您好", "谢谢", "有点困", "挺安静"))
_EXPLICIT_CHAT_ENDING = re.compile(
    r"(?:陪我聊(?:两句|聊)?|只想聊聊|随便聊聊|聊两句)[。.!！]?$"
)
_CREATION_ACTION_SIGNALS = (
    "写",
    "生成",
    "做条",
    "做一条",
    "做篇",
    "做一篇",
    "发条",
    "发一条",
    "发篇",
    "发一篇",
    "整理成",
    "改成",
    "拍成",
)
_CREATION_RESULT_SIGNALS = (
    "内容",
    "文案",
    "小红书",
    "视频",
    "口播",
    "脚本",
    "图文",
    "帖子",
    "一条",
    "一篇",
    "条",
    "篇",
)


def is_natural_chat(text: str) -> bool:
    """Keep a tiny high-confidence ordinary-conversation fast path out of content tasks."""
    normalized = text.strip().casefold()
    return (
        bool(normalized)
        and (
            normalized.rstrip("。.!！") in _EXACT_SMALL_TALK
            or _EXPLICIT_CHAT_ENDING.search(normalized) is not None
        )
        and not requests_content_creation(normalized)
    )


def natural_reply() -> str:
    return "当然。今天先不用急着产出，想说什么就说什么。"


def requests_content_creation(text: str) -> bool:
    """Recognize an explicit request for a publishable result, not a topic alone."""
    normalized = text.strip().casefold()
    return (
        any(action in normalized for action in _CREATION_ACTION_SIGNALS)
        and any(result in normalized for result in _CREATION_RESULT_SIGNALS)
    )


def requests_continuation(text: str) -> bool:
    return any(signal in text.strip().casefold() for signal in _CONTINUATION_SIGNALS)


def sanitize_seed(text: str) -> str:
    """Keep task meaning while withholding obvious customer identifiers."""
    sanitized = re.sub(r"1[3-9]\d{9}", "一位顾客", text)
    sanitized = re.sub(r"[\w.+-]+@[\w.-]+", "一位顾客", sanitized)
    sanitized = re.sub(r"(?:订单号?|账号)\s*[:：]?\s*[A-Za-z0-9-]+", "一位顾客的来访", sanitized)
    return re.sub(
        r"(?:顾客|客户)\s*[\u4e00-\u9fff]{2,3}(?=(?:电话|订单|账号|来|问))",
        "一位顾客",
        sanitized,
    )
