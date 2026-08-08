#!/usr/bin/env python3
"""Assert that Gate B additions contain no credentials or private evidence paths."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from assert_gateb_scope import EXPECTED_BASE_SHA, _changed_paths

_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:sk|sk-proj)-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?i)\b(?:password|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*['\"][^'\"]{8,}"),
)
_PRIVATE_PATH_PATTERNS = (
    re.compile(r"/(?:home|Users)/[^/\s]+/"),
    re.compile(r"/mnt/[a-z]/Users/[^/\s]+/", re.IGNORECASE),
    re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+\\"),
)
_ENV_READ_PATTERN = re.compile(r"(?:open|read_text|Path)\([^\n]{0,200}\.env")
_FROZEN_PATHS = (
    "docs/BRAND-MATRIX-01/GateA-素材合同",
    "docs/BRAND-MATRIX-01/素材草案-v0",
    "docs/品牌入驻候选",
    "alembic",
    "frontend",
    "scripts/exev0",
    "scripts/exev1",
    "scripts/exe01",
    "scripts/s0",
    "scripts/gatea",
    "docs/项目记忆.md",
)
_SELF_PATH = "scripts/gateb/assert_gateb_no_secrets.py"


def _run(root: Path, *args: str) -> str:
    return subprocess.run(
        args,
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _added_content(diff: str) -> str:
    current_path = ""
    additions: list[str] = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_path = line[6:]
        elif line.startswith("+") and not line.startswith("+++") and current_path != _SELF_PATH:
            additions.append(line[1:])
    return "\n".join(additions)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    diff = _run(root, "git", "diff", "--unified=0", "--no-ext-diff", EXPECTED_BASE_SHA)
    added_lines = _added_content(diff)
    untracked = {
        entry[3:]
        for entry in _run(
            root,
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ).splitlines()
        if entry.startswith("?? ")
    }
    untracked_text = "\n".join(
        (root / path).read_text(encoding="utf-8")
        for path in sorted(untracked & _changed_paths(root))
        if path != _SELF_PATH and (root / path).is_file()
    )
    scanner_source = "\n".join(
        line for line in (root / _SELF_PATH).read_text(encoding="utf-8").splitlines() if "re.compile(" not in line
    )
    candidate = f"{added_lines}\n{untracked_text}\n{scanner_source}"
    hits: list[str] = []
    for pattern in (*_SECRET_PATTERNS, *_PRIVATE_PATH_PATTERNS):
        match = pattern.search(candidate)
        if match is not None:
            hits.append(match.group(0)[:80])
    if _ENV_READ_PATTERN.search(candidate):
        hits.append(".env read")
    if hits:
        raise SystemExit(f"Gate B privacy FAIL: {hits}")

    frozen_diff = _run(
        root,
        "git",
        "diff",
        "--name-only",
        EXPECTED_BASE_SHA,
        "--",
        *_FROZEN_PATHS,
    ).strip()
    if frozen_diff:
        raise SystemExit(f"Gate B privacy FAIL: frozen paths changed: {frozen_diff}")
    print("GATEB_NO_SECRETS_OK secret_hits=0 private_path_hits=0 frozen_path_diffs=0")


if __name__ == "__main__":
    main()
