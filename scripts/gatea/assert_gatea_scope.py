"""Fail-closed audit for the Gate A branch, base, and allowed write surface."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
EXPECTED_BASE_SHA = "ae4290e4eb7fab7a34f5393b850f759fc0a698ce"
EXPECTED_BRANCH = "exe/brand-matrix-a"
ALLOWED_EXACT = {
    "MILESTONE.md",
    "docs/COMM-01-执行包排产与工程对照指南.md",
}
ALLOWED_PREFIXES = (
    "docs/BRAND-MATRIX-01/GateA-素材合同/",
    "scripts/gatea/",
)
FROZEN_PREFIXES = (
    "docs/BRAND-MATRIX-01/素材草案-v0/",
    "docs/品牌入驻候选/笛语服饰/",
    "src/",
    "alembic/",
    "frontend/",
    "scripts/exev0/",
    "scripts/exev1/",
    "scripts/exe01/",
    "scripts/s0/",
)


def run_git(*args: str, check: bool = True) -> str:
    """Run Git in the Gate A worktree and return stdout."""
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def changed_paths() -> set[str]:
    """Return tracked and untracked candidate paths relative to the expected base."""
    tracked = set(run_git("diff", "--name-only", EXPECTED_BASE_SHA, "--").splitlines())
    untracked = set(run_git("ls-files", "--others", "--exclude-standard").splitlines())
    return {path for path in tracked | untracked if path}


def assert_append_only(path: str) -> None:
    """Require the two shared status documents to contain additions only."""
    output = run_git("diff", "--numstat", EXPECTED_BASE_SHA, "--", path).strip()
    if not output:
        raise AssertionError(f"required append-only document was not changed: {path}")
    for line in output.splitlines():
        added, removed, _ = line.split("\t", maxsplit=2)
        if added == "-" or removed == "-" or int(removed) != 0:
            raise AssertionError(f"document must be append-only: {path}")


def main() -> None:
    """Assert base ancestry, branch identity, allowlist, and frozen paths."""
    branch = run_git("branch", "--show-current").strip()
    if branch != EXPECTED_BRANCH:
        raise AssertionError(f"wrong branch: {branch!r}")
    run_git("merge-base", "--is-ancestor", EXPECTED_BASE_SHA, "HEAD")

    paths = changed_paths()
    if not paths:
        raise AssertionError("Gate A candidate has no changes")
    disallowed = sorted(path for path in paths if path not in ALLOWED_EXACT and not path.startswith(ALLOWED_PREFIXES))
    if disallowed:
        raise AssertionError(f"paths outside Gate A write surface: {disallowed}")
    frozen = sorted(path for path in paths if path.startswith(FROZEN_PREFIXES))
    if frozen:
        raise AssertionError(f"frozen paths changed: {frozen}")
    if "docs/项目记忆.md" in paths:
        raise AssertionError("docs/项目记忆.md must remain untouched")

    assert_append_only("MILESTONE.md")
    assert_append_only("docs/COMM-01-执行包排产与工程对照指南.md")
    LOGGER.info("Gate A scope PASS: %d changed paths are allowlisted", len(paths))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
