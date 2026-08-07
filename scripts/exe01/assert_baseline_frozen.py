#!/usr/bin/env python3
"""Gate the EXE-01 baseline commit.

The frozen baselines are only worth something if they came from a real build of
the tree being committed. This re-runs both measurements and requires the
committed files to reproduce byte for byte, so a hand-edited or stale baseline
cannot enter the history and silently loosen the later budget check.

Usage:
    python3 scripts/exe01/assert_baseline_frozen.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bundle_report  # noqa: E402
import test_inventory  # noqa: E402

HERE = Path(__file__).resolve().parent
BUNDLE_BASELINE = HERE / "bundle_baseline.json"
TEST_BASELINE = HERE / "test_baseline.json"


def render(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def check(name: str, path: Path, live: dict[str, object]) -> list[str]:
    if not path.exists():
        return [f"{name}: missing frozen baseline at {path}"]
    frozen = path.read_text(encoding="utf-8")
    if frozen != render(live):
        return [
            f"{name}: frozen baseline does not reproduce from the current tree "
            f"({path}); re-run the generator instead of editing it by hand"
        ]
    return []


def main() -> int:
    failures: list[str] = []
    failures += check("bundle", BUNDLE_BASELINE, bundle_report.collect())
    failures += check("tests", TEST_BASELINE, test_inventory.collect())

    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1

    bundle = json.loads(BUNDLE_BASELINE.read_text(encoding="utf-8"))
    tests = json.loads(TEST_BASELINE.read_text(encoding="utf-8"))
    print("PASS baseline frozen and reproducible")
    print(
        "  entry js  raw={entry_js_raw} gzip={entry_js_gzip}".format(
            **bundle["totals"]
        )
    )
    print("  css       raw={css_raw} gzip={css_gzip}".format(**bundle["totals"]))
    print("  route chunks={chunk_count}".format(**bundle["totals"]))
    print(
        "  tests     files={file_count} assertions={assertions} "
        "browser_scripts={browser_script_count} skips={skip_markers}".format(
            **tests["totals"]
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
