"""Fail closed unless the pending S0 change set is one approved commit group."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

LOGGER = logging.getLogger(__name__)

EVIDENCE_COMMIT = frozenset(
    {
        "docs/BRAND-MATRIX-01/S0-证据/S0-终局核验摘要.md",
        "docs/EXE-V0/P0-裁决摘要.md",
        "scripts/s0/assert_s0_no_secrets.py",
        "scripts/s0/assert_s0_scope.py",
    }
)
GOVERNANCE_COMMIT = frozenset(
    {
        "MILESTONE.md",
        "docs/BRAND-MATRIX-01/盲测托管/README.md",
        "docs/COMM-01-执行包排产与工程对照指南.md",
    }
)


def _git_paths(repo_root: Path, *args: str) -> set[str]:
    completed = subprocess.run(
        ("git", *args),
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return {line for line in completed.stdout.splitlines() if line}


def _pending_paths(repo_root: Path) -> frozenset[str]:
    unstaged = _git_paths(repo_root, "diff", "--name-only", "--diff-filter=ACDMRTUXB")
    staged = _git_paths(repo_root, "diff", "--cached", "--name-only", "--diff-filter=ACDMRTUXB")
    untracked = _git_paths(repo_root, "ls-files", "--others", "--exclude-standard")
    return frozenset(unstaged | staged | untracked)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    pending = _pending_paths(repo_root)
    groups = {
        "evidence-and-verification": EVIDENCE_COMMIT,
        "blind-hosting-and-governance": GOVERNANCE_COMMIT,
    }
    for name, expected in groups.items():
        if pending == expected:
            LOGGER.info("PASS S0 scope: %s (%d files)", name, len(expected))
            return 0
    LOGGER.error("FAIL S0 scope: pending paths do not match an approved commit group")
    LOGGER.error("pending=%s", sorted(pending))
    return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())

