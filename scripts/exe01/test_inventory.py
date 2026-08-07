#!/usr/bin/env python3
"""Inventory the frontend test assets EXE-01 must protect.

FE-04 forbids deleting tests, shrinking assertions, or letting coverage quietly
drain away. The suites are plain `node:assert/strict` scripts with no reporter,
so "test findings" are counted as assertion call sites per file, alongside the
browser-script roster and skip markers. A frozen copy of this inventory is the
reconciliation baseline; `assert_test_reconciliation.py` compares against it.

Usage:
    python3 scripts/exe01/test_inventory.py                # print JSON
    python3 scripts/exe01/test_inventory.py --out PATH     # also write it
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = PROJECT_ROOT / "frontend" / "test"
SCHEMA = "exe01.test_inventory.v1"

# The suites use three unrelated assertion mechanisms. Counting only the
# `node:assert` form would report every browser script as having zero coverage
# and let real deletions pass unnoticed, so each mechanism is detected on its
# own terms and the helper's own definition line is excluded from the tally.
ASSERTION = re.compile(r"\bassert\.(?P<method>[A-Za-z][A-Za-z0-9]*)\s*\(")
# `ensure(value, message)` throws on a falsy value; `record(name, detail)` files
# a named PASS check. Their own `const x = (...) => ...` definition sites match
# the same call shape, so definitions are counted separately and subtracted
# rather than excluded by signature — the signatures differ between scripts.
HELPER_NAMES = ("ensure", "record")
HELPER_CALLS = {
    name: re.compile(rf"(?<![.\w]){name}\s*\(") for name in HELPER_NAMES
}
HELPER_DEFINITIONS = {
    name: re.compile(rf"^\s*const\s+{name}\s*=", re.MULTILINE)
    for name in HELPER_NAMES
}
# Any of these appearing in a suite means a case stopped running; FE-04 treats a
# newly introduced one as a failure, so they are counted rather than described.
SKIP_MARKERS = (
    re.compile(r"\bit\.skip\b"),
    re.compile(r"\bdescribe\.skip\b"),
    re.compile(r"\btest\.skip\b"),
    re.compile(r"\bxit\b"),
    re.compile(r"\bxdescribe\b"),
    re.compile(r"\.todo\b"),
    re.compile(r"\bskip\s*:\s*true\b"),
)
SOURCE_SUFFIXES = {".mjs", ".js", ".ts", ".tsx"}


def count_skips(text: str) -> int:
    return sum(len(marker.findall(text)) for marker in SKIP_MARKERS)


def inspect(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    methods: dict[str, int] = {}
    for match in ASSERTION.finditer(text):
        method = match.group("method")
        methods[method] = methods.get(method, 0) + 1
    definitions = 0
    for name, pattern in HELPER_CALLS.items():
        declared = len(HELPER_DEFINITIONS[name].findall(text))
        definitions += declared
        hits = len(pattern.findall(text)) - declared
        if hits > 0:
            methods[name] = hits
    return {
        "path": path.relative_to(PROJECT_ROOT).as_posix(),
        "lines": len(text.splitlines()),
        "assertions": sum(methods.values()),
        "assertion_methods": dict(sorted(methods.items())),
        "helper_definitions": definitions,
        "skip_markers": count_skips(text),
        "is_browser_script": path.name.endswith("-browser.mjs"),
    }


def collect() -> dict[str, object]:
    if not TEST_DIR.exists():
        raise SystemExit("frontend/test is missing.")
    files = sorted(
        (p for p in TEST_DIR.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(PROJECT_ROOT).as_posix(),
    )
    records = [inspect(p) for p in files if p.suffix in SOURCE_SUFFIXES]
    all_paths = [p.relative_to(PROJECT_ROOT).as_posix() for p in files]
    browser_scripts = [r["path"] for r in records if r["is_browser_script"]]
    return {
        "schema": SCHEMA,
        "files": records,
        "all_files": all_paths,
        "totals": {
            "file_count": len(all_paths),
            "source_file_count": len(records),
            "browser_script_count": len(browser_scripts),
            "total_lines_all_files": sum(
                len(p.read_text(encoding="utf-8").splitlines())
                for p in files
            ),
            "assertions": sum(int(r["assertions"]) for r in records),
            "skip_markers": sum(int(r["skip_markers"]) for r in records),
        },
        "browser_scripts": browser_scripts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write the inventory to this path")
    args = parser.parse_args()

    inventory = collect()
    rendered = json.dumps(inventory, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
