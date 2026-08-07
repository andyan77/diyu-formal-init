#!/usr/bin/env python3
"""Assert EXE-V0 added no oversized function and grew no oversized one.

A ratchet, not a cleanup mandate.  Functions that were already over the limit at
the base commit are exempt because rewriting them is not this package's job —
but they are frozen at the length they had, so "minimal wiring" stays minimal and
new logic has to leave in a function of its own.  The exemption file is derived
from the base commit and may only shrink.

That base moves once, at serialized integration.  Measured against the authorized
base, EXE-01R's own allowed growth in `src/gateway/api/app.py` came out as an
EXE-V0 trespass — this package has to be judged against the tree it actually sits
on, which after the merge is the mainline.

Usage:
    python3 scripts/exev0/assert_function_budget.py
    python3 scripts/exev0/assert_function_budget.py --regenerate
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# The base this package was authorized to build on, and the mainline merged in at
# serialized integration.  Both pinned to SHAs for the reasons assert_scope.py
# gives; the ledger records which one it came from and this gate rechecks it.
AUTHORIZED_BASE = "c37ae78594220a3ada9ad73020c67b1aec99aa4f"
MAINLINE_COMMIT = "8d909cf958c5241d70c8715252e881f89a047f50"
MEASURED_TREE = "src"
LINE_LIMIT = 60
EXEMPTIONS_PATH = Path(__file__).resolve().parent / "function_budget_baseline.json"


def _function_lengths(source: str, path: str) -> dict[str, int]:
    lengths: dict[str, int] = {}

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}{child.name}"
                end = child.end_lineno or child.lineno
                lengths[f"{path}::{name}"] = end - child.lineno + 1
                walk(child, f"{name}.")
            elif isinstance(child, ast.ClassDef):
                walk(child, f"{prefix}{child.name}.")

    walk(ast.parse(source), "")
    return lengths


def _is_ancestor(commit: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def base_commit() -> str:
    """The tree this package sits on: the mainline once merged, the base until then."""

    return MAINLINE_COMMIT if _is_ancestor(MAINLINE_COMMIT) else AUTHORIZED_BASE


def _tracked_python_files(ref: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", ref, "--", MEASURED_TREE],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(line for line in result.stdout.splitlines() if line.endswith(".py"))


def _lengths_at_base() -> dict[str, int]:
    base = base_commit()
    lengths: dict[str, int] = {}
    for path in _tracked_python_files(base):
        blob = subprocess.run(
            ["git", "show", f"{base}:{path}"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        lengths.update(_function_lengths(blob.stdout, path))
    return lengths


def _lengths_in_working_tree() -> dict[str, int]:
    lengths: dict[str, int] = {}
    for path in sorted((PROJECT_ROOT / MEASURED_TREE).rglob("*.py")):
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        lengths.update(_function_lengths(path.read_text(encoding="utf-8"), relative))
    return lengths


def _base_exemptions() -> dict[str, int]:
    return {key: length for key, length in _lengths_at_base().items() if length > LINE_LIMIT}


def regenerate() -> int:
    exemptions = _base_exemptions()
    EXEMPTIONS_PATH.write_text(
        json.dumps(
            {
                "base_commit": base_commit(),
                "authorized_base": AUTHORIZED_BASE,
                "line_limit": LINE_LIMIT,
                "measured_tree": MEASURED_TREE,
                "frozen_over_limit_functions": dict(sorted(exemptions.items())),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"WROTE {EXEMPTIONS_PATH.relative_to(PROJECT_ROOT)} ({len(exemptions)} 个冻结豁免函数)")
    return 0


def _load_exemptions(failures: list[str]) -> dict[str, int]:
    if not EXEMPTIONS_PATH.exists():
        failures.append(f"{EXEMPTIONS_PATH.name}: 豁免台账缺失，先跑 --regenerate")
        return {}
    document = json.loads(EXEMPTIONS_PATH.read_text(encoding="utf-8"))
    if (
        document.get("base_commit") != base_commit()
        or document.get("authorized_base") != AUTHORIZED_BASE
        or document.get("line_limit") != LINE_LIMIT
        or document.get("measured_tree") != MEASURED_TREE
    ):
        failures.append(f"{EXEMPTIONS_PATH.name}: 豁免台账口径与本门不一致")
        return {}
    recorded = document.get("frozen_over_limit_functions")
    if not isinstance(recorded, dict):
        failures.append(f"{EXEMPTIONS_PATH.name}: 豁免台账格式无效")
        return {}
    derived = _base_exemptions()
    for key, length in sorted(recorded.items()):
        if key not in derived:
            failures.append(f"{key}: 豁免台账凭空新增（基线并未超限）")
        elif derived[key] != length:
            failures.append(f"{key}: 豁免长度 {length} 与基线 {derived[key]} 不符")
    return {key: length for key, length in recorded.items() if key in derived}


def main() -> int:
    if "--regenerate" in sys.argv[1:]:
        return regenerate()

    failures: list[str] = []
    exemptions = _load_exemptions(failures)
    current = _lengths_in_working_tree()
    grown: list[str] = []
    oversized: list[str] = []

    for key, length in sorted(current.items()):
        frozen = exemptions.get(key)
        if frozen is not None:
            if length > frozen:
                grown.append(f"{key}: 冻结豁免函数从 {frozen} 增长到 {length} 行")
        elif length > LINE_LIMIT:
            oversized.append(f"{key}: 新函数 {length} 行，超过 {LINE_LIMIT} 行预算")

    failures.extend(grown)
    failures.extend(oversized)
    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1

    print(
        f"PASS function budget ({len(current)} 个函数，"
        f"{len(exemptions)} 个基线冻结豁免，新函数上限 {LINE_LIMIT} 行)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
