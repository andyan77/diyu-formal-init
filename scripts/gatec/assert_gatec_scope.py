#!/usr/bin/env python3
"""Fail closed when Gate C changes escape its authorized write surface."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

EXPECTED_BASE_SHA = "5aa37d65168ab7fe2277ce4fbb8d27a9a41a353a"
EXPECTED_BRANCH = "exe/brand-matrix-c"

_EXACT_ALLOWED = frozenset(
    {
        "MILESTONE.md",
        "docs/COMM-01-执行包排产与工程对照指南.md",
    }
)
_PREFIX_ALLOWED = (
    "alembic/versions/",
    "src/",
    "tests/",
    "scripts/gatec/",
    "docs/BRAND-MATRIX-01/GateC-记录/",
)
_FROZEN_PREFIXES = (
    "frontend/",
    "docs/BRAND-MATRIX-01/GateA-素材合同/",
    "docs/BRAND-MATRIX-01/素材草案-v0/",
    "docs/品牌入驻候选/",
    "scripts/exev0/",
    "scripts/exev1/",
    "scripts/exe01/",
    "scripts/s0/",
    "scripts/gatea/",
    "scripts/gateb/",
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
_MIGRATION = "alembic/versions/20260818_45_brand_scope_authorization.py"
_DESTRUCTIVE_DDL = re.compile(r"\b(?:DROP\s+(?:TABLE|COLUMN)|DELETE\s+FROM)\b", re.IGNORECASE)


def _run(root: Path, *args: str) -> str:
    return subprocess.run(
        args,
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repo_root() -> Path:
    return Path(
        subprocess.run(
            ("git", "rev-parse", "--show-toplevel"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )


def _dependency_bridge(root: Path, path: str) -> bool:
    candidate = root / path
    return path == ".venv" and candidate.is_symlink() and candidate.resolve().name == ".venv"


def changed_paths(root: Path) -> set[str]:
    tracked = {
        path
        for path in _run(
            root,
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACMRTUXB",
            EXPECTED_BASE_SHA,
        ).splitlines()
        if path
    }
    untracked = {path for path in _run(root, "git", "ls-files", "--others", "--exclude-standard").splitlines() if path}
    return {path for path in tracked | untracked if not _dependency_bridge(root, path)}


def _allowed(path: str) -> bool:
    return path in _EXACT_ALLOWED or path.startswith(_PREFIX_ALLOWED)


def _assert_append_only(root: Path, path: str) -> None:
    numstat = _run(root, "git", "diff", "--numstat", EXPECTED_BASE_SHA, "--", path)
    if not numstat:
        raise SystemExit(f"Gate C scope FAIL: required append-only file unchanged: {path}")
    for line in numstat.splitlines():
        _, removed, _ = line.split("\t", maxsplit=2)
        if removed == "-" or int(removed) != 0:
            raise SystemExit(f"Gate C scope FAIL: shared record is not append-only: {path}")


def main() -> None:
    root = _repo_root()
    if _run(root, "git", "branch", "--show-current") != EXPECTED_BRANCH:
        raise SystemExit("Gate C scope FAIL: wrong branch")
    _run(root, "git", "cat-file", "-e", f"{EXPECTED_BASE_SHA}^{{commit}}")
    if subprocess.run(
        ("git", "merge-base", "--is-ancestor", EXPECTED_BASE_SHA, "HEAD"),
        cwd=root,
        check=False,
    ).returncode:
        raise SystemExit("Gate C scope FAIL: expected base is not an ancestor")

    changed = changed_paths(root)
    if not changed:
        raise SystemExit("Gate C scope FAIL: no candidate changes")
    disallowed = sorted(path for path in changed if not _allowed(path))
    frozen = sorted(path for path in changed if path in _FROZEN_EXACT or path.startswith(_FROZEN_PREFIXES))
    migrations = sorted(path for path in changed if path.startswith("alembic/versions/"))
    if migrations != [_MIGRATION]:
        raise SystemExit(f"Gate C scope FAIL: migration surface is not exact: {migrations}")
    migration_source = (root / _MIGRATION).read_text(encoding="utf-8")
    destructive = _DESTRUCTIVE_DDL.search(migration_source)
    if destructive is not None:
        raise SystemExit(f"Gate C scope FAIL: destructive DDL: {destructive.group(0)}")
    if disallowed or frozen:
        details = ", ".join(sorted(set(disallowed + frozen)))
        raise SystemExit(f"Gate C scope FAIL: unauthorized paths: {details}")
    _assert_append_only(root, "MILESTONE.md")
    _assert_append_only(root, "docs/COMM-01-执行包排产与工程对照指南.md")
    print(f"GATEC_SCOPE_OK changed_paths={len(changed)} migration=20260818_45 destructive_ddl=0")


if __name__ == "__main__":
    main()
