#!/usr/bin/env python3
"""Fail closed when Gate D changes escape its explicitly authorized surface."""

from __future__ import annotations

import subprocess
from pathlib import Path

EXPECTED_BRANCH = "exe/brand-matrix-d"
EXPECTED_MERGE_BASE = "bd5a6bfac1c196f059242e5f42fe6c5efbec5b06"
GOVERNANCE_BASE = "c913a1d38a522ecfed790b75ee822cb82f96fad8"
REMOTE_MAIN = "origin/claude/brand-knowledge-pilot-review-8a3105"

_EXACT_ALLOWED = frozenset(
    {
        "MILESTONE.md",
        "openapi.json",
        "docs/COMM-01-执行包排产与工程对照指南.md",
        "frontend/src/app/TenantAdminApp.tsx",
        "frontend/src/shared/contracts/gen/openapi.d.ts",
        "frontend/src/shared/contracts/manifest.json",
        "frontend/test/admin-run.mjs",
        "frontend/test/admin_interaction.test.tsx",
        "frontend/test/gated-d0-browser-entry.tsx",
        "frontend/test/gated-d0-browser.mjs",
    }
)
_PREFIX_ALLOWED = (
    "src/",
    "tests/",
    "scripts/gated/",
    "docs/BRAND-MATRIX-01/GateD-记录/",
)
_FROZEN_PREFIXES = (
    "alembic/",
    "docs/BRAND-MATRIX-01/GateA-素材合同/",
    "docs/BRAND-MATRIX-01/素材草案-v0/",
    "docs/品牌入驻候选/",
    "scripts/exev0/",
    "scripts/exev1/",
    "scripts/exe01/",
    "scripts/s0/",
    "scripts/gatea/",
    "scripts/gateb/",
    "scripts/gatec/",
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
_RUNTIME_UNTRACKED_PREFIXES = ("var/gated-media-masters/",)
_RUNTIME_UNTRACKED_EXACT = frozenset({"var/gated-prestate.dump", ".venv"})


def _run(root: Path, *args: str) -> str:
    return subprocess.run(
        args,
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repo_root() -> Path:
    return Path(_run(Path.cwd(), "git", "rev-parse", "--show-toplevel"))


def _runtime_untracked(path: str) -> bool:
    return path in _RUNTIME_UNTRACKED_EXACT or path.startswith(_RUNTIME_UNTRACKED_PREFIXES)


def changed_paths(root: Path) -> set[str]:
    tracked = {
        path
        for path in _run(
            root,
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACMRTUXB",
            EXPECTED_MERGE_BASE,
        ).splitlines()
        if path
    }
    untracked = {
        path
        for path in _run(root, "git", "ls-files", "--others", "--exclude-standard").splitlines()
        if path and not _runtime_untracked(path)
    }
    return tracked | untracked


def _allowed(path: str) -> bool:
    return path in _EXACT_ALLOWED or path.startswith(_PREFIX_ALLOWED)


def _assert_append_only_if_changed(root: Path, path: str) -> None:
    numstat = _run(root, "git", "diff", "--numstat", EXPECTED_MERGE_BASE, "--", path)
    if not numstat:
        return
    for line in numstat.splitlines():
        _, removed, _ = line.split("\t", maxsplit=2)
        if removed == "-" or int(removed) != 0:
            raise SystemExit(f"Gate D scope FAIL: shared record is not append-only: {path}")


def main() -> None:
    root = _repo_root()
    if _run(root, "git", "branch", "--show-current") != EXPECTED_BRANCH:
        raise SystemExit("Gate D scope FAIL: wrong branch")
    for revision in (EXPECTED_MERGE_BASE, GOVERNANCE_BASE, REMOTE_MAIN):
        _run(root, "git", "cat-file", "-e", f"{revision}^{{commit}}")
    merge_base = _run(root, "git", "merge-base", "HEAD", REMOTE_MAIN)
    if merge_base != EXPECTED_MERGE_BASE:
        raise SystemExit(f"Gate D scope FAIL: merge-base drifted: {merge_base}")
    if subprocess.run(
        ("git", "merge-base", "--is-ancestor", GOVERNANCE_BASE, REMOTE_MAIN),
        cwd=root,
        check=False,
    ).returncode:
        raise SystemExit("Gate D scope FAIL: required governance commit is not on remote main")

    changed = changed_paths(root)
    if not changed:
        raise SystemExit("Gate D scope FAIL: no candidate changes")
    disallowed = sorted(path for path in changed if not _allowed(path))
    frozen = sorted(path for path in changed if path in _FROZEN_EXACT or path.startswith(_FROZEN_PREFIXES))
    if disallowed or frozen:
        details = ", ".join(sorted(set(disallowed + frozen)))
        raise SystemExit(f"Gate D scope FAIL: unauthorized paths: {details}")

    tracked_runtime = [
        path
        for path in _run(root, "git", "ls-files").splitlines()
        if _runtime_untracked(path)
    ]
    staged_runtime = [
        path
        for path in _run(root, "git", "diff", "--cached", "--name-only").splitlines()
        if _runtime_untracked(path)
    ]
    if tracked_runtime or staged_runtime:
        raise SystemExit("Gate D scope FAIL: runtime media or database snapshot entered Git")

    _assert_append_only_if_changed(root, "MILESTONE.md")
    _assert_append_only_if_changed(root, "docs/COMM-01-执行包排产与工程对照指南.md")
    print(
        f"GATED_SCOPE_OK changed_paths={len(changed)} alembic_changes=0 "
        "dependency_changes=0 runtime_binaries_tracked=0"
    )


if __name__ == "__main__":
    main()
