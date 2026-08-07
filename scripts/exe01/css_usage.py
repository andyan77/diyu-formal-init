#!/usr/bin/env python3
"""Map every CSS class in the frontend stylesheets to who references it.

Deleting a rule because `grep` over TSX found nothing is how server-rendered
markup loses its styling: `src/gateway/api/html.py` emits `entry-page`,
`entry-choice` and friends as plain strings that no component ever mentions.
So the search runs over four domains, and a class counts as referenced if its
bare name appears as a word in any of them — deliberately the widest reading,
because over-counting keeps a live rule and under-counting breaks a page.

Usage:
    python3 scripts/exe01/css_usage.py                 # print JSON
    python3 scripts/exe01/css_usage.py --unreferenced  # just the dead names
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "exe01.css_usage.v1"

STYLESHEETS = (
    "frontend/src/styles.css",
    "frontend/src/styles/product.css",
    "frontend/src/styles/ops.css",
    "frontend/src/styles/tenant-admin.css",
    "frontend/src/styles/user-extensions.css",
)

# The four domains a class name can legitimately come from.
SEARCH_DOMAINS = {
    "frontend_src": ("frontend/src", (".ts", ".tsx", ".js", ".mjs", ".html")),
    "frontend_test": ("frontend/test", (".ts", ".tsx", ".js", ".mjs", ".html", ".json")),
    "gateway_api": ("src/gateway/api", (".py",)),
    "fe00_design": ("docs/前端UI架构/FE-00", (".html", ".md", ".css", ".json")),
}

CLASS_SELECTOR = re.compile(r"\.(-?[_a-zA-Z][_a-zA-Z0-9-]*)")
COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
VAR_DEFINITION = re.compile(r"(--[_a-zA-Z][_a-zA-Z0-9-]*)\s*:")
VAR_USAGE = re.compile(r"var\(\s*(--[_a-zA-Z][_a-zA-Z0-9-]*)")


def selector_text(css: str) -> str:
    """Everything outside declaration blocks — where selectors live."""
    without_comments = COMMENT.sub(" ", css)
    chunks: list[str] = []
    depth = 0
    current: list[str] = []
    for char in without_comments:
        if char == "{":
            if depth == 0:
                chunks.append("".join(current))
                current = []
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        elif depth == 0:
            current.append(char)
    chunks.append("".join(current))
    return "\n".join(chunks)


def classes_in(css: str) -> set[str]:
    return set(CLASS_SELECTOR.findall(selector_text(css)))


def split_top_level(text: str, sep: str) -> list[str]:
    parts, depth, current = [], 0, []
    for char in text:
        if char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        if char == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def blocks(css: str) -> list[tuple[str, str]]:
    """Split into (prelude, body) pairs, with comments removed first."""
    text = COMMENT.sub(" ", css)
    out: list[tuple[str, str]] = []
    i, n, prelude = 0, len(text), []
    while i < n:
        if text[i] == "{":
            depth, j = 1, i + 1
            while j < n and depth:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                j += 1
            out.append(("".join(prelude), text[i + 1 : j - 1]))
            prelude, i = [], j
        else:
            prelude.append(text[i])
            i += 1
    return out


def selector_parts(css: str) -> list[str]:
    """Every comma-separated selector part, at any nesting level, normalized.

    Selector-level rather than class-level, because a rule can be legitimately
    deleted for naming a dead class alongside a live one: `.readiness-card.ready`
    goes when `.readiness-card` does, even though `.ready` lives on elsewhere.
    At-rule preludes are prefixed so a media query cannot collide with a rule.
    """
    parts: list[str] = []
    for prelude, body in blocks(css):
        head = " ".join(prelude.split())
        if head.startswith("@"):
            if "{" in body:
                parts.extend(f"{head} {{ {p} }}" for p in selector_parts(body))
            continue
        parts.extend(
            " ".join(p.split()) for p in split_top_level(head, ",") if p.strip()
        )
    return parts


def read_domain(root: str, suffixes: tuple[str, ...]) -> str:
    base = PROJECT_ROOT / root
    if not base.exists():
        return ""
    parts: list[str] = []
    for path in sorted(base.rglob("*")):
        if path.is_file() and path.suffix in suffixes:
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def collect() -> dict[str, object]:
    corpora = {
        name: read_domain(root, suffixes)
        for name, (root, suffixes) in SEARCH_DOMAINS.items()
    }
    # Stylesheets themselves are not a reference: a rule referring to another
    # rule's class does not make either of them reachable from the product.
    stylesheets: dict[str, set[str]] = {}
    defined_vars: dict[str, set[str]] = {}
    used_vars: dict[str, set[str]] = {}
    for relative in STYLESHEETS:
        css = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        stylesheets[relative] = classes_in(css)
        defined_vars[relative] = set(VAR_DEFINITION.findall(css))
        used_vars[relative] = set(VAR_USAGE.findall(css))

    records: list[dict[str, object]] = []
    for relative, names in stylesheets.items():
        for name in sorted(names):
            word = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")
            referenced_in = sorted(
                domain for domain, text in corpora.items() if word.search(text)
            )
            records.append(
                {
                    "stylesheet": relative,
                    "class": name,
                    "referenced_in": referenced_in,
                    "referenced": bool(referenced_in),
                }
            )

    return {
        "schema": SCHEMA,
        "domains": {
            name: {"root": root, "suffixes": list(suffixes)}
            for name, (root, suffixes) in SEARCH_DOMAINS.items()
        },
        "classes": records,
        "unreferenced": sorted(
            {str(r["class"]) for r in records if not r["referenced"]}
        ),
        "variables": {
            relative: {
                "defined": sorted(defined_vars[relative]),
                "used": sorted(used_vars[relative]),
                "used_but_not_defined_here": sorted(
                    used_vars[relative] - defined_vars[relative]
                ),
            }
            for relative in STYLESHEETS
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unreferenced", action="store_true")
    args = parser.parse_args()
    report = collect()
    if args.unreferenced:
        for name in report["unreferenced"]:  # type: ignore[index]
            print(name)
        return 0
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
