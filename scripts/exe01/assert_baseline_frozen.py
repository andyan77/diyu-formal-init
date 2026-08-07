#!/usr/bin/env python3
"""Assert the EXE-01 baselines have not been edited since they were frozen.

The bundle and test baselines are a record of the tree *before* EXE-01 touched
it, so they must never be regenerated: re-freezing them after a regression would
silently move the budget and the coverage floor to wherever the code happens to
be. Their reproducibility was verified at the freeze commit; from then on the
only invariant worth checking is that the bytes are unchanged.

Usage:
    python3 scripts/exe01/assert_baseline_frozen.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# The commit that froze both baselines, verified there against a live build and
# a live inventory run.
FREEZE_COMMIT = "fa75ea2"
BASELINES = (
    "scripts/exe01/bundle_baseline.json",
    "scripts/exe01/test_baseline.json",
)


def frozen_bytes(relative: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{FREEZE_COMMIT}:{relative}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def main() -> int:
    failures: list[str] = []
    for relative in BASELINES:
        path = PROJECT_ROOT / relative
        if not path.exists():
            failures.append(f"{relative}: deleted")
            continue
        original = frozen_bytes(relative)
        if original is None:
            failures.append(
                f"{relative}: cannot read it at freeze commit {FREEZE_COMMIT}"
            )
        elif original != path.read_bytes():
            failures.append(
                f"{relative}: edited since {FREEZE_COMMIT}; a baseline records "
                "the pre-change tree and must not be re-frozen"
            )

    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    print(f"PASS baselines unchanged since {FREEZE_COMMIT}")
    for relative in BASELINES:
        print(f"  {relative}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
