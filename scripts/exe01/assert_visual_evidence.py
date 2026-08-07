#!/usr/bin/env python3
"""Assert the FE-00 visual evidence matrix is complete and accessible.

AGENTS.md §14.7 makes screenshots part of the definition of done, and names the
matrix: 1440×900, 390×844, 200% zoom, prefers-reduced-motion, covering loading,
empty, error and long text. It also rules out "looks about right" as a standard,
so the same pass requires an axe-core scan with nothing serious or critical
left standing.

Regenerate with:
    node frontend/tools/fe00-evidence.mjs --out docs/前端UI架构/FE-00/evidence

Usage:
    python3 scripts/exe01/assert_visual_evidence.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = PROJECT_ROOT / "docs/前端UI架构/FE-00/evidence"
MANIFEST = EVIDENCE / "evidence-manifest.json"

REQUIRED_CONDITIONS = {"1440x900", "390x844", "200pct-zoom", "reduced-motion"}
# The four content states §14.7 names by hand, as they appear in frame ids.
REQUIRED_STATES = {"loading", "empty", "failure", "longtext"}
BLOCKING_IMPACTS = {"serious", "critical"}


def main() -> int:
    if not MANIFEST.exists():
        print(f"FAIL missing {MANIFEST}", file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    captures = manifest["captures"]
    failures: list[str] = []

    conditions = {str(c["name"]) for c in captures}
    missing_conditions = REQUIRED_CONDITIONS - conditions
    if missing_conditions:
        failures.append(f"missing viewport conditions: {sorted(missing_conditions)}")

    frames = {str(c["frame"]).replace("fe00-", "") for c in captures}
    missing_states = REQUIRED_STATES - frames
    if missing_states:
        failures.append(f"missing content states: {sorted(missing_states)}")

    for capture in captures:
        image = EVIDENCE / str(capture["file"])
        if not image.exists():
            failures.append(f"manifest lists {capture['file']}, which is not on disk")
        elif image.stat().st_size == 0:
            failures.append(f"{capture['file']} is empty")

    violations = [v for scope in manifest["axe"].values() for v in scope]
    blocking = [v for v in violations if v.get("impact") in BLOCKING_IMPACTS]
    for violation in blocking:
        failures.append(
            f"axe {violation['impact']} {violation['id']}: "
            f"{violation['help']} ({violation['count']} nodes)"
        )

    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1

    print("PASS FE-00 visual evidence matrix")
    print(f"  captures: {len(captures)}")
    for condition in sorted(conditions):
        count = sum(1 for c in captures if c["name"] == condition)
        print(f"    {condition:16s} {count}")
    print(f"  content states covered: {sorted(REQUIRED_STATES & frames)}")
    print(
        f"  axe-core: {len(violations)} violations, "
        f"{len(blocking)} serious/critical"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
