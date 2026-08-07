#!/usr/bin/env python3
"""Assert route splitting actually happened and the entry bundle did not grow.

"We added lazy()" is not evidence. This reads Vite's build manifest, follows
static imports transitively, and requires that each business application is
reachable from the entry only through a dynamic import — a single stray static
import anywhere in the graph would silently put the tenant admin console back
into the public home page's first load.

Usage:
    python3 scripts/exe01/assert_bundle_budget.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bundle_report  # noqa: E402

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "bundle_baseline.json"

ENTRY = "index.html"
CREATOR = "src/app/CreatorApp.tsx"
TENANT_ADMIN = "src/app/TenantAdminApp.tsx"
OPS = "src/app/OpsApp.tsx"
USER_HOME = "src/app/ProductShells.tsx"
DIAGNOSTICS = "src/components/CapabilityGuide.tsx"
PUBLIC_HOME = "src/app/PublicHome.tsx"

# Every business application must be behind its own dynamic import.
MUST_BE_LAZY = [
    CREATOR,
    TENANT_ADMIN,
    OPS,
    USER_HOME,
    PUBLIC_HOME,
    "src/app/DisplayApp.tsx",
    "src/app/LoginPage.tsx",
    "src/app/OrganizationMaterialsApp.tsx",
    "src/app/StatusPage.tsx",
]

# (route module, modules its first load must not reach)
ROUTE_ISOLATION = [
    (PUBLIC_HOME, [CREATOR, TENANT_ADMIN, OPS], "/ first load"),
    (CREATOR, [TENANT_ADMIN, OPS], "/content first load"),
    (USER_HOME, [DIAGNOSTICS, TENANT_ADMIN, OPS], "/user first load"),
]


def static_closure(graph: dict[str, dict], start: str) -> set[str]:
    """Modules pulled in by loading `start`, following static imports only."""
    seen: set[str] = set()
    queue = [start]
    while queue:
        node = queue.pop()
        if node in seen or node not in graph:
            continue
        seen.add(node)
        queue.extend(graph[node].get("imports") or [])
    return seen


def main() -> int:
    report = bundle_report.collect()
    graph: dict[str, dict] = report["graph"]  # type: ignore[assignment]
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    failures: list[str] = []

    if ENTRY not in graph:
        print(f"FAIL build manifest has no {ENTRY} entry", file=sys.stderr)
        return 1

    entry_gzip = int(report["totals"]["entry_js_gzip"])  # type: ignore[index]
    baseline_gzip = int(baseline["totals"]["entry_js_gzip"])
    if entry_gzip > baseline_gzip:
        failures.append(
            f"entry JS gzip grew: {baseline_gzip} -> {entry_gzip}"
        )

    if int(report["totals"]["chunk_count"]) == 0:  # type: ignore[index]
        failures.append("no route chunks were emitted; nothing was split")

    entry_static = static_closure(graph, ENTRY)
    entry_dynamic = set(graph[ENTRY].get("dynamicImports") or [])
    for module in MUST_BE_LAZY:
        if module not in graph:
            failures.append(f"{module} is absent from the build manifest")
            continue
        if module in entry_static:
            failures.append(
                f"{module} is statically reachable from the entry; it must be "
                "behind a dynamic import"
            )
        elif module not in entry_dynamic:
            failures.append(f"{module} is not a dynamic import of the entry")

    for route, forbidden, label in ROUTE_ISOLATION:
        if route not in graph:
            continue
        reachable = static_closure(graph, route)
        for module in forbidden:
            if module in reachable:
                failures.append(f"{label} statically pulls in {module}")

    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1

    totals = report["totals"]
    print("PASS bundle budget")
    print(
        f"  entry js gzip {baseline_gzip} -> {entry_gzip} "
        f"({entry_gzip - baseline_gzip:+d})"
    )
    print(
        "  entry js raw  {} -> {}".format(
            baseline["totals"]["entry_js_raw"], totals["entry_js_raw"]
        )
    )
    print(
        "  css gzip      {} -> {}".format(
            baseline["totals"]["css_gzip"], totals["css_gzip"]
        )
    )
    print(f"  route chunks  {totals['chunk_count']}")
    print(f"  lazy business modules verified: {len(MUST_BE_LAZY)}")
    for _, forbidden, label in ROUTE_ISOLATION:
        print(f"  {label} excludes {len(forbidden)} module(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
