#!/usr/bin/env python3
"""Replay legacy_routes.json against the real application.

FE-01 moved two addresses and added a router, so "the old URLs still work" has
to be checked, not asserted in prose. Every row marked runtime_verified is
issued against an app built by `create_app()` and compared on status, final
path, preserved query and bootstrap application. Rows that only exist under
production configuration are checked for registration instead, and say so.

Needs the same environment as scripts/test.sh (local Postgres and the demo
identifiers). Run it through that, or export them first.

Usage:
    python3 scripts/exe01/assert_route_compatibility.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

CONTRACT = Path(__file__).resolve().parent / "legacy_routes.json"
APP_SOURCE = PROJECT_ROOT / "src" / "gateway" / "api" / "app.py"


def single_valued(query: dict[str, list[str]]) -> dict[str, str]:
    return {key: values[0] for key, values in query.items()}


def check_runtime(client, row: dict) -> list[str]:
    url = str(row["legacy_url"])
    response = client.get(url)
    problems: list[str] = []

    if response.status_code != row["expected_status"]:
        problems.append(
            f"status {response.status_code}, expected {row['expected_status']}"
        )

    if response.status_code in (301, 302, 303, 307, 308):
        destination = urlparse(response.headers.get("location", ""))
        landed, landed_query = destination.path, single_valued(
            parse_qs(destination.query)
        )
    else:
        source = urlparse(url)
        landed, landed_query = source.path, single_valued(parse_qs(source.query))

    if landed != row["final_pathname"]:
        problems.append(
            f"final pathname {landed!r}, expected {row['final_pathname']!r}"
        )
    if landed_query != row["preserved_query"]:
        problems.append(
            f"query {landed_query!r}, expected {row['preserved_query']!r}"
        )

    expected_app = row["bootstrap_application"]
    if expected_app is not None:
        found = re.search(r"__DIYU_BOOTSTRAP__=(\{.*?\});", response.text, re.S)
        actual = None
        if found:
            try:
                actual = json.loads(found.group(1)).get("application")
            except json.JSONDecodeError:
                actual = "<unparsable>"
        if actual != expected_app:
            problems.append(
                f"bootstrap application {actual!r}, expected {expected_app!r}"
            )
    return problems


def check_static(row: dict, source: str) -> list[str]:
    evidence = str(row.get("registration_evidence", ""))
    if not evidence:
        return ["static_verified row has no registration_evidence"]
    if not row.get("blocked_reason"):
        return ["static_verified row has no blocked_reason"]
    # The evidence must name a path the source actually registers.
    path = str(row["legacy_url"])
    if f'"{path}"' not in source:
        return [f"app.py does not register {path}"]
    return []


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    source = APP_SOURCE.read_text(encoding="utf-8")

    try:
        from fastapi.testclient import TestClient

        from src.gateway.api.app import create_app

        client = TestClient(create_app(), follow_redirects=False)
    except Exception as exc:  # noqa: BLE001 - report, do not pass silently
        print(
            "FAIL cannot build the application; run under scripts/test.sh's "
            f"environment ({type(exc).__name__}: {exc})",
            file=sys.stderr,
        )
        return 1

    failures: list[str] = []
    runtime_rows = static_rows = 0
    for row in contract["routes"]:
        if row["verification"] == "runtime_verified":
            runtime_rows += 1
            problems = check_runtime(client, row)
        else:
            static_rows += 1
            problems = check_static(row, source)
        for problem in problems:
            failures.append(f"{row['legacy_url']}: {problem}")

    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1

    print("PASS legacy route compatibility")
    print(f"  rows replayed against the live app: {runtime_rows}")
    print(f"  rows verified by registration only: {static_rows}")
    for row in contract["routes"]:
        if row["verification"] != "runtime_verified":
            print(
                f"    static: {row['legacy_url']} — {row['blocked_reason']}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
