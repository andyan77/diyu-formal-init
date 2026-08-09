#!/usr/bin/env python3
"""Assert Gate D candidate changes contain no secret values or tracked binaries."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from assert_gated_scope import EXPECTED_MERGE_BASE, changed_paths

_SELF = "scripts/gated/assert_gated_no_secrets.py"
_PROMPT = "docs/BRAND-MATRIX-01/GateD-记录/Prompt-5-rev3.md"
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:sk|sk-proj)-[A-Za-z0-9_-]{20,}"),
    re.compile(
        r"(?i)\b(?:secret|api[_-]?key|access[_-]?token)\s*[:=]\s*['\"][^'\"]{8,}"
    ),
)
_PRIVATE_PATH_PATTERNS = (
    re.compile(r"/(?:home|Users)/[^/\s]+/"),
    re.compile(r"/mnt/[a-z]/Users/[^/\s]+/", re.IGNORECASE),
    re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+\\"),
)
_BINARY_SUFFIXES = frozenset(
    {".mov", ".mp4", ".avi", ".mkv", ".webm", ".dump", ".sqlite", ".db", ".zip"}
)


def _run(root: Path, *args: str) -> str:
    return subprocess.run(
        args,
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _added_content(root: Path, path: str, candidate: Path) -> str:
    diff = _run(
        root,
        "git",
        "diff",
        "--unified=0",
        "--no-ext-diff",
        EXPECTED_MERGE_BASE,
        "--",
        path,
    )
    additions = [
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    if additions:
        return "\n".join(additions)
    return candidate.read_text(encoding="utf-8")


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    hits: list[str] = []
    private_path_hits: list[str] = []
    for path in sorted(changed_paths(root)):
        candidate = root / path
        if path == _SELF or not candidate.is_file() or candidate.is_symlink():
            continue
        try:
            text = _added_content(root, path, candidate)
        except UnicodeDecodeError:
            hits.append(f"binary:{path}")
            continue
        for pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                hits.append(path)
                break
        if path != _PROMPT:
            for pattern in _PRIVATE_PATH_PATTERNS:
                if pattern.search(text):
                    private_path_hits.append(path)
                    break
    if hits or private_path_hits:
        raise SystemExit(
            f"Gate D privacy FAIL: secret_or_binary={hits} private_paths={private_path_hits}"
        )

    range_paths = _run(root, "git", "diff", "--name-only", EXPECTED_MERGE_BASE).splitlines()
    binary_paths = [path for path in range_paths if Path(path).suffix.lower() in _BINARY_SUFFIXES]
    if binary_paths:
        raise SystemExit(f"Gate D privacy FAIL: binary paths entered candidate range: {binary_paths}")
    gated_runtime = [
        path
        for path in _run(root, "git", "ls-files").splitlines()
        if path == "var/gated-prestate.dump" or path.startswith("var/gated-media-masters/")
    ]
    if gated_runtime:
        raise SystemExit("Gate D privacy FAIL: Gate D runtime artifacts are tracked")

    prompt_text = (root / _PROMPT).read_text(encoding="utf-8")
    if "DEEPSEEK_API_KEY" not in prompt_text or "不得 source 整个 .env" not in prompt_text:
        raise SystemExit("Gate D privacy FAIL: frozen credential discipline is missing")
    print(
        "GATED_NO_SECRETS_OK secret_hits=0 private_path_hits=0 binary_git_paths=0 "
        "provider_secret_values_persisted=0"
    )


if __name__ == "__main__":
    main()
