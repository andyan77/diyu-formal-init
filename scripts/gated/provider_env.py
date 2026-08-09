"""Strictly read only the three authorized DeepSeek keys from one dotenv file."""

from __future__ import annotations

import re
from pathlib import Path

AUTHORIZED_KEYS = (
    "DEEPSEEK_API_BASE_URL",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_MODEL",
)
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def _value(raw: str) -> str:
    candidate = raw.strip()
    if not candidate:
        return ""
    if candidate[0] in {'"', "'"}:
        quote = candidate[0]
        if len(candidate) < 2 or candidate[-1] != quote:
            raise ValueError("authorized dotenv value has unmatched quotes")
        candidate = candidate[1:-1]
    elif " #" in candidate:
        candidate = candidate.split(" #", maxsplit=1)[0].rstrip()
    if "\n" in candidate or "\r" in candidate or "\\n" in candidate or "\\r" in candidate:
        raise ValueError("authorized dotenv value must be one physical line")
    return candidate


def parse_authorized_deepseek_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError("authorized dotenv file is unavailable")
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, raw_value = line.partition("=")
        key = key.strip()
        if not separator or _KEY.fullmatch(key) is None:
            raise ValueError("dotenv contains a malformed physical line")
        if key not in AUTHORIZED_KEYS:
            continue
        if key in result:
            raise ValueError(f"dotenv repeats authorized key {key}")
        result[key] = _value(raw_value)
    if set(result) != set(AUTHORIZED_KEYS) or any(not result[key] for key in AUTHORIZED_KEYS):
        raise ValueError("the three authorized DeepSeek keys must be present and non-empty")
    return result
