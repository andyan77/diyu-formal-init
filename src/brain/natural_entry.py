from __future__ import annotations

import re

_GREETINGS = {"hello", "hi", "你好", "您好", "嗨", "在吗"}


def is_greeting(text: str) -> bool:
    return text.strip().casefold().strip("!！。.") in _GREETINGS


def greeting_reply() -> str:
    return "你好。把今天遇到的穿衣情境说给我，我会帮你整理成一份完整的选择建议。"


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
