from __future__ import annotations

import re

_CONTINUATION_SIGNALS = ("接着上一条", "延续之前", "继续上一条", "沿用上一条")
_SMALL_TALK_SIGNALS = ("hello", "hi", "你好", "您好", "有点困", "挺安静", "聊聊", "谢谢")
_CONTENT_INTENT_SIGNALS = (
    "内容",
    "口播",
    "脚本",
    "拍",
    "穿",
    "外套",
    "商品",
    "双面",
    "顾客",
    "品牌",
    "账号",
    "门店",
    "家庭",
    "孩子",
    "妈妈",
)


def is_natural_chat(text: str) -> bool:
    """Keep a tiny high-confidence ordinary-conversation fast path out of content tasks."""
    normalized = text.strip().casefold()
    return (
        bool(normalized)
        and any(signal in normalized for signal in _SMALL_TALK_SIGNALS)
        and not any(signal in normalized for signal in _CONTENT_INTENT_SIGNALS)
    )


def natural_reply() -> str:
    return "你好。你可以随便聊；想把一个具体观察、商品或穿衣情境做成内容时，直接告诉我。"


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
