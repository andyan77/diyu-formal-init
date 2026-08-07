#!/usr/bin/env python3
"""Assert every removed CSS class was genuinely unreferenced, in all four domains.

Grepping TSX alone is not enough: `src/gateway/api/html.py` emits `entry-page`,
`entry-choice` and `eyebrow` as plain strings, so a TSX-only proof would happily
delete the styling of every server-rendered recovery page. This checks each
class removed since the base commit against all four domains, and additionally
requires the tree to be left with no unreferenced class at all.

Usage:
    python3 scripts/exe01/assert_dead_css.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import css_usage  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_COMMIT = "af20ae5601a53551bb0d50288d69ff3f08e29163"
SCREENSHOTS = PROJECT_ROOT / "docs/前端UI架构/EXE-01-死样式截图回归"


def base_stylesheet(relative: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{BASE_COMMIT}:{relative}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def removed_selectors(css: str, current: str) -> list[str]:
    """Selector parts present in the base sheet and gone from the current one."""
    return sorted(set(css_usage.selector_parts(css)) - set(css_usage.selector_parts(current)))


def unreferenced(name: str, corpora: dict[str, str]) -> bool:
    word = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")
    return not any(word.search(text) for text in corpora.values())


def main() -> int:
    report = css_usage.collect()
    corpora = {
        name: css_usage.read_domain(root, suffixes)
        for name, (root, suffixes) in css_usage.SEARCH_DOMAINS.items()
    }
    failures: list[str] = []

    # 1. Every deleted selector must have been unable to match: it names at
    #    least one class with zero references in all four domains.
    total_removed = 0
    per_sheet: dict[str, int] = {}
    for relative in css_usage.STYLESHEETS:
        original = base_stylesheet(relative)
        if original is None:
            continue
        current = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        gone = removed_selectors(original, current)
        per_sheet[relative] = len(gone)
        total_removed += len(gone)
        for selector in gone:
            names = set(css_usage.CLASS_SELECTOR.findall(selector))
            if not names:
                failures.append(
                    f"{relative}: removed selector {selector!r} names no class; "
                    "element and pseudo selectors are out of scope for EXE-01"
                )
                continue
            if not any(unreferenced(name, corpora) for name in sorted(names)):
                failures.append(
                    f"{relative}: removed selector {selector!r} could still "
                    f"match — every class in it is referenced ({sorted(names)})"
                )

    # 2. Nothing left behind may be dead either.
    if report["unreferenced"]:
        failures.append(
            "stylesheets still contain unreferenced classes: "
            + ", ".join(report["unreferenced"])  # type: ignore[arg-type]
        )

    # 3. The screenshot regression artifacts must exist.
    shots = sorted(SCREENSHOTS.glob("*.png")) if SCREENSHOTS.exists() else []
    desktop = [p for p in shots if "desktop-1440x900" in p.name]
    mobile = [p for p in shots if "mobile-390x844" in p.name]
    if not desktop or not mobile:
        failures.append(
            f"missing desktop/mobile screenshot regression under {SCREENSHOTS}"
        )

    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1

    print("PASS dead-style removal proven across four domains")
    for name, (root, suffixes) in css_usage.SEARCH_DOMAINS.items():
        print(f"  domain {name}: {root} {list(suffixes)}")
    print(f"  selectors removed since {BASE_COMMIT[:7]}: {total_removed}")
    for relative, count in sorted(per_sheet.items()):
        if count:
            print(f"    {relative}: {count}")
    print(f"  unreferenced classes remaining: {len(report['unreferenced'])}")
    print(f"  screenshots: desktop={len(desktop)} mobile={len(mobile)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
