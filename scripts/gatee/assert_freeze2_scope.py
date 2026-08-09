#!/usr/bin/env python3
"""Fail closed if E-1' changes anything outside its exam-administration write surface."""

from __future__ import annotations

import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_BASE = "bb9e63daa4558b9b202465d148b43d7c92a83266"
_BRANCH = "exe/brand-matrix-e-freeze2"
_ALLOWED_PREFIXES = (
    "docs/BRAND-MATRIX-01/GateE-记录/",
    "scripts/gatee/",
    "tests/",
)
_ALLOWED_EXACT = {"MILESTONE.md"}


def _git(*arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> int:
    if _git("branch", "--show-current") != _BRANCH:
        raise RuntimeError("E-1' must run only on the signed execution branch")
    if _git("merge-base", "HEAD", _BASE) != _BASE:
        raise RuntimeError("E-1' branch ancestry differs from the signed baseline")
    tracked = set(_git("diff", "--name-only", _BASE).splitlines())
    untracked = {line for line in _git("ls-files", "--others", "--exclude-standard").splitlines() if line != ".venv"}
    changed = tracked | untracked
    forbidden = sorted(
        path for path in changed if path not in _ALLOWED_EXACT and not path.startswith(_ALLOWED_PREFIXES)
    )
    if forbidden:
        raise RuntimeError(f"E-1' write-surface violation: {forbidden}")
    runtime_changed = _git(
        "diff",
        "--name-only",
        _BASE,
        "--",
        "src",
        "frontend",
        "alembic",
    ).splitlines()
    if runtime_changed:
        raise RuntimeError(f"accepted R1-R4 runtime changed during E-1': {runtime_changed}")
    if any(path == ".env" or path.endswith("/.env") for path in changed):
        raise RuntimeError("dotenv entered the E-1' write surface")
    print(f"freeze2 scope PASS: changed={len(changed)} runtime_changed=0 branch={_BRANCH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
