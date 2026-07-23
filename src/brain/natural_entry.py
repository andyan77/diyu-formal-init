from __future__ import annotations

import re

_DIRECT_P1_SIGNALS = ("怎么穿", "穿什么", "怎么搭", "搭配", "造型", "穿衣选择", "p1")
_SITUATION_SIGNALS = ("开会", "会议", "见客户", "上班", "接孩子", "骑车", "下雨", "出门", "约会")
_TRANSITION_SIGNALS = ("然后", "之后", "再", "转身", "还要", "同一天")
_CONTINUATION_SIGNALS = ("接着上一条", "延续之前", "继续上一条", "沿用上一条")


def is_p1_weak_seed(text: str) -> bool:
    """Route only a visible P1 request or a concrete multi-situation choice opportunity."""
    normalized = text.strip().casefold()
    if any(signal in normalized for signal in _CONTINUATION_SIGNALS):
        return True
    if any(signal in normalized for signal in _DIRECT_P1_SIGNALS):
        return True
    return any(signal in normalized for signal in _SITUATION_SIGNALS) and any(
        signal in normalized for signal in _TRANSITION_SIGNALS
    )


def natural_reply() -> str:
    return "你好。你可以随便聊；当你想把一个具体穿衣情境做成内容时，直接说出来就行。"


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
