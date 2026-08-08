#!/usr/bin/env python3
"""Fail closed when Gate B changes escape its authorized write surface."""

from __future__ import annotations

import subprocess
from pathlib import Path

EXPECTED_BASE_SHA = "64d040ebf2c8a10404f6ad8aae328a076babfc08"
EXPECTED_BRANCH = "exe/brand-matrix-b"

_EXACT_ALLOWED = frozenset(
    {
        "MILESTONE.md",
        "docs/COMM-01-执行包排产与工程对照指南.md",
        "src/tool/llm_gateway/deepseek.py",
        "src/tool/llm_gateway/stub.py",
    }
)
_PREFIX_ALLOWED = (
    "src/shared/",
    "src/brain/",
    "tests/",
    "scripts/gateb/",
    "docs/BRAND-MATRIX-01/GateB-记录/",
)
_FROZEN_PREFIXES = (
    "alembic/",
    "frontend/",
    "docs/BRAND-MATRIX-01/GateA-素材合同/",
    "docs/BRAND-MATRIX-01/素材草案-v0/",
    "docs/品牌入驻候选/",
    "scripts/exev0/",
    "scripts/exev1/",
    "scripts/exe01/",
    "scripts/s0/",
    "scripts/gatea/",
)
_FROZEN_EXACT = frozenset(
    {
        "docs/项目记忆.md",
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "uv.lock",
        "requirements.txt",
        "requirements-dev.txt",
    }
)


def _run(*args: str) -> str:
    return subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repo_root() -> Path:
    return Path(_run("git", "rev-parse", "--show-toplevel"))


def _changed_paths(root: Path) -> set[str]:
    tracked = {
        path
        for path in _run(
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACMRTUXB",
            f"{EXPECTED_BASE_SHA}..HEAD",
        ).splitlines()
        if path
    }
    worktree = {
        path
        for path in _run(
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACMRTUXB",
            "HEAD",
        ).splitlines()
        if path
    }
    status = subprocess.run(
        ("git", "status", "--porcelain=v1", "--untracked-files=all", "-z"),
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout.decode("utf-8")
    untracked: set[str] = set()
    for entry in status.split("\0"):
        if not entry or not entry.startswith("?? "):
            continue
        untracked.add(entry[3:])
    return tracked | worktree | untracked


def _allowed(path: str) -> bool:
    return path in _EXACT_ALLOWED or path.startswith(_PREFIX_ALLOWED)


def main() -> None:
    root = _repo_root()
    if _run("git", "branch", "--show-current") != EXPECTED_BRANCH:
        raise SystemExit("Gate B scope FAIL: wrong branch")
    _run("git", "cat-file", "-e", f"{EXPECTED_BASE_SHA}^{{commit}}")
    if subprocess.run(
        ("git", "merge-base", "--is-ancestor", EXPECTED_BASE_SHA, "HEAD"),
        cwd=root,
        check=False,
    ).returncode:
        raise SystemExit("Gate B scope FAIL: expected base is not an ancestor")

    changed = _changed_paths(root)
    disallowed = sorted(path for path in changed if not _allowed(path))
    frozen = sorted(path for path in changed if path in _FROZEN_EXACT or path.startswith(_FROZEN_PREFIXES))
    if disallowed or frozen:
        details = ", ".join(sorted(set(disallowed + frozen)))
        raise SystemExit(f"Gate B scope FAIL: unauthorized paths: {details}")
    if not changed:
        raise SystemExit("Gate B scope FAIL: no Gate B candidate changes")
    print(f"GATEB_SCOPE_OK changed_paths={len(changed)} base={EXPECTED_BASE_SHA}")


if __name__ == "__main__":
    main()
