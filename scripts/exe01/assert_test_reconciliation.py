#!/usr/bin/env python3
"""Assert the frontend test asset survived EXE-01 intact.

FE-04 makes the 9,311-line suite a hard constraint: no deleting tests, no
shrinking assertions, no new skips. A refactor that breaks a journey is
supposed to migrate it, so this compares the live inventory against the frozen
baseline and requires every shortfall to be accounted for, assertion by
assertion, in the migration ledger.

Usage:
    python3 scripts/exe01/assert_test_reconciliation.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_inventory  # noqa: E402

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "test_baseline.json"
LEDGER = HERE / "test_migrations.json"


def main() -> int:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    live = test_inventory.collect()

    before = {str(r["path"]): r for r in baseline["files"]}
    after = {str(r["path"]): r for r in live["files"]}
    retired = {entry["path"]: entry for entry in ledger["removed_files"]}
    credited: dict[str, int] = {}
    for entry in ledger["migrations"]:
        gained = int(entry["new_assertions"]) - int(entry["old_assertions"])
        credited[entry["file"]] = credited.get(entry["file"], 0) + gained

    failures: list[str] = []

    for path, record in sorted(before.items()):
        if path not in after:
            if path not in retired:
                failures.append(f"{path}: deleted without a ledger entry")
            elif not retired[path].get("replaced_by"):
                failures.append(f"{path}: retired without naming a replacement")
            continue
        was = int(record["assertions"])
        now = int(after[path]["assertions"])
        if now < was:
            failures.append(
                f"{path}: assertions dropped {was} -> {now}; a migration must "
                "not lose coverage, and any change needs a ledger entry"
            )

    # A ledger entry is a claim; it must match what is actually in the file.
    for file, gained in sorted(credited.items()):
        if file not in after:
            failures.append(f"ledger names {file}, which no longer exists")
            continue
        was = int(before.get(file, {}).get("assertions", 0))
        now = int(after[file]["assertions"])
        if now < was + gained:
            failures.append(
                f"{file}: ledger claims a net +{gained} assertions "
                f"({was} -> at least {was + gained}) but the file has {now}"
            )

    live_totals = live["totals"]
    base_totals = baseline["totals"]
    if int(live_totals["skip_markers"]) > int(base_totals["skip_markers"]):
        failures.append(
            "new skip markers appeared: "
            f"{base_totals['skip_markers']} -> {live_totals['skip_markers']}"
        )
    if int(live_totals["browser_script_count"]) < int(
        base_totals["browser_script_count"]
    ):
        failures.append(
            "browser scripts lost: "
            f"{base_totals['browser_script_count']} -> "
            f"{live_totals['browser_script_count']}"
        )
    if int(live_totals["assertions"]) < int(base_totals["assertions"]):
        failures.append(
            "total assertions fell: "
            f"{base_totals['assertions']} -> {live_totals['assertions']}"
        )

    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1

    print("PASS test asset reconciled against the frozen baseline")
    print(
        "  assertions      {} -> {} ({:+d})".format(
            base_totals["assertions"],
            live_totals["assertions"],
            int(live_totals["assertions"]) - int(base_totals["assertions"]),
        )
    )
    print(
        "  source files    {} -> {}".format(
            base_totals["source_file_count"], live_totals["source_file_count"]
        )
    )
    print(
        "  browser scripts {} -> {}".format(
            base_totals["browser_script_count"],
            live_totals["browser_script_count"],
        )
    )
    print(
        "  skip markers    {} -> {}".format(
            base_totals["skip_markers"], live_totals["skip_markers"]
        )
    )
    print(f"  migrations reconciled: {len(ledger['migrations'])}")
    for entry in ledger["migrations"]:
        print(
            f"    {entry['file']}: {entry['old_assertions']} -> "
            f"{entry['new_assertions']} — {entry['why']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
