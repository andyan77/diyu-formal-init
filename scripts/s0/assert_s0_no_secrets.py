"""Scan the S0 document surface without re-scanning unrelated historical text."""

from __future__ import annotations

import logging
import re
from pathlib import Path

LOGGER = logging.getLogger(__name__)

FULL_DOCUMENTS = (
    "docs/BRAND-MATRIX-01/S0-证据/S0-终局核验摘要.md",
    "docs/BRAND-MATRIX-01/盲测托管/README.md",
)
MARKED_SECTIONS = (
    (
        "docs/EXE-V0/P0-裁决摘要.md",
        "<!-- BRAND-MATRIX-01-S0-P0-D1-START -->",
        "<!-- BRAND-MATRIX-01-S0-P0-D1-END -->",
    ),
    (
        "docs/COMM-01-执行包排产与工程对照指南.md",
        "<!-- BRAND-MATRIX-01-S0-CLOSEOUT-START -->",
        "<!-- BRAND-MATRIX-01-S0-CLOSEOUT-END -->",
    ),
)
MILESTONE_STATUS = "S0 IMPLEMENTED · AWAITING_SUPERVISOR_REVERIFICATION"

RULES = (
    ("ipv4", re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")),
    ("task-or-person UUID", re.compile(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", re.I)),
    ("private evidence absolute path", re.compile(r"(?:/home/[^\s`]+|~/[^\s`]+|/mnt/[^\s`]+)diyu-evidence", re.I)),
    ("private key path", re.compile(r"(?:/home/[^\s`]+/\.ssh/[^\s`]+|ECS_SSH_KEY_PATH\s*[=:]\s*\S+)", re.I)),
    ("credential assignment", re.compile(r"(?:api[_-]?key|token|secret|password)\s*[=:]\s*[^\s`]+", re.I)),
    ("credential token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})\b")),
    ("private key material", re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----")),
    ("login username", re.compile(r"(?:root@|用户名\s*[=:：]\s*\S+|username\s*[=:]\s*\S+)", re.I)),
)


def _marked_section(text: str, start: str, end: str, path: Path) -> str:
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"{path}: required S0 markers are missing or duplicated")
    before, remainder = text.split(start, 1)
    section, after = remainder.split(end, 1)
    if before is None or after is None:
        raise ValueError(f"{path}: invalid marker order")
    return section


def _surfaces(repo_root: Path) -> dict[str, str]:
    surfaces: dict[str, str] = {}
    milestone = repo_root / "MILESTONE.md"
    milestone_data = milestone.read_bytes() if milestone.exists() else b""
    if b"\x00" in milestone_data:
        raise ValueError("MILESTONE.md: NUL byte")
    milestone_text = milestone_data.decode("utf-8")
    finalized = MILESTONE_STATUS in milestone_text
    for relative in FULL_DOCUMENTS:
        path = repo_root / relative
        if path.exists():
            data = path.read_bytes()
            if b"\x00" in data:
                raise ValueError(f"{relative}: NUL byte")
            surfaces[relative] = data.decode("utf-8")
    for relative, start, end in MARKED_SECTIONS:
        path = repo_root / relative
        if path.exists():
            data = path.read_bytes()
            if b"\x00" in data:
                raise ValueError(f"{relative}: NUL byte")
            text = data.decode("utf-8")
            if start not in text and end not in text and not finalized:
                continue
            surfaces[relative] = _marked_section(text, start, end, path)
    status_lines = [line for line in milestone_text.splitlines() if MILESTONE_STATUS in line]
    if status_lines:
        surfaces["MILESTONE.md#S0-status"] = "\n".join(status_lines)
    return surfaces


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        surfaces = _surfaces(repo_root)
    except (OSError, UnicodeError, ValueError) as exc:
        LOGGER.error("FAIL S0 secrets/PII scan: %s", exc)
        return 1
    findings: list[str] = []
    for label, text in surfaces.items():
        for rule_name, pattern in RULES:
            if pattern.search(text):
                findings.append(f"{label}: {rule_name}")
    if findings:
        LOGGER.error("FAIL S0 secrets/PII scan")
        for finding in findings:
            LOGGER.error("  %s", finding)
        return 1
    LOGGER.info("PASS S0 secrets/PII scan (%d scoped surfaces)", len(surfaces))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
