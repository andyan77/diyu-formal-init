#!/usr/bin/env python3
"""Assert no function grew past the budget, and none crept back over it.

The rule has four tiers (EXE-01R v1.1 §9):

  1. a function that did not exist at the freeze must be <= 60 lines;
  2. a function that was <= 60 at the freeze must still be <= 60;
  3. a function that was already over 60 is frozen in the exemption ledger by
     its baseline length. It may be edited, but not lengthened — a ratchet, so
     the long functions can only shrink;
  4. deterministic generated output, lockfiles and JSON fixtures do not count.

Plus: CreatorApp.tsx may not grow as a file, because "extract as much as you
add" is the only thing keeping it from absorbing every new requirement.

Regenerate the ledger (only when the freeze SHA changes):
    python3 scripts/exe01/assert_function_budget.py --freeze

Usage:
    python3 scripts/exe01/assert_function_budget.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from function_spans import spans_for  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FREEZE_SHA = "357d17cd610d5c3c0b3fd5f7c703b8710da82d64"
LEDGER = Path(__file__).resolve().parent / "function_budget_exemptions.json"
LIMIT = 60

# Where the budget applies. Everything else is either untouched by this package
# or generated.
SCOPE_PREFIXES = (
    "frontend/src/",
    "frontend/test/",
    "frontend/tools/",
    "scripts/exe01/",
)
EXCLUDED = (
    "frontend/src/shared/contracts/gen/",  # deterministic codegen (tier 4)
)
SUFFIXES = {".ts", ".tsx", ".mts", ".mjs", ".js", ".jsx", ".py"}
NO_FILE_GROWTH = ("frontend/src/app/CreatorApp.tsx",)

# A function that moved file unchanged keeps its exemption; without this, every
# extraction would look like a brand-new 267-line function and the ratchet
# would punish exactly the refactor it is meant to encourage. Each entry is a
# claim that can be checked against the diff.
RELOCATIONS = {
    ("frontend/src/features/advisor/AccountDrawer.tsx", "AccountDrawer"):
        ("frontend/src/app/CreatorApp.tsx", "AccountDrawer"),
    ("frontend/src/features/advisor/AccountDrawer.tsx", "editableAccountProfile"):
        ("frontend/src/app/CreatorApp.tsx", "editableAccountProfile"),
    ("frontend/src/features/advisor/AccountDrawer.tsx", "AccountDrawer > toggleBodyDirections"):
        ("frontend/src/app/CreatorApp.tsx", "AccountDrawer > toggleBodyDirections"),
    ("frontend/src/features/advisor/AccountDrawer.tsx", "AccountDrawer > saveProfile"):
        ("frontend/src/app/CreatorApp.tsx", "AccountDrawer > saveProfile"),
}


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True
    ).stdout


def in_scope(path: str) -> bool:
    if any(path.startswith(prefix) for prefix in EXCLUDED):
        return False
    if not any(path.startswith(prefix) for prefix in SCOPE_PREFIXES):
        return False
    return Path(path).suffix in SUFFIXES


def tracked_at(ref: str) -> list[str]:
    listing = git("ls-tree", "-r", "--name-only", "-z", ref)
    return [path for path in listing.split("\0") if path and in_scope(path)]


def present_now() -> list[str]:
    """Committed files plus files not committed yet.

    Reading only the HEAD tree would let a brand-new module escape the budget
    until the commit after the one that introduced it — which is exactly when
    nobody is looking.
    """
    # NUL-separated for the same reason as assert_scope: git quotes
    # non-ASCII paths unless core.quotePath is explicitly turned off.
    tracked = git("ls-tree", "-r", "--name-only", "-z", "HEAD").split("\0")
    untracked = git("ls-files", "--others", "--exclude-standard", "-z").split("\0")
    seen = sorted(set(tracked) | set(untracked))
    return [path for path in seen if in_scope(path) and (PROJECT_ROOT / path).exists()]


def spans_at(ref: str, paths: list[str]) -> dict[tuple[str, str], dict[str, object]]:
    """Measure a commit's version of each file without touching the worktree."""
    staging = PROJECT_ROOT / "var" / "tmp" / "function-budget"
    subprocess.run(["rm", "-rf", str(staging)], check=True)
    materialised: list[Path] = []
    contents: dict[Path, str] = {}
    for path in paths:
        blob = git("show", f"{ref}:{path}")
        target = staging / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(blob, encoding="utf-8")
        materialised.append(target)
        contents[target] = blob
    spans = spans_for(materialised, contents)
    out: dict[tuple[str, str], dict[str, object]] = {}
    for span in spans:
        rel = str(Path(str(span["file"])).resolve().relative_to(staging.resolve()))
        out[(rel, str(span["path"]))] = span
    subprocess.run(["rm", "-rf", str(staging)], check=True)
    return out


def spans_now(paths: list[str]) -> dict[tuple[str, str], dict[str, object]]:
    files = [PROJECT_ROOT / path for path in paths]
    contents = {item: item.read_text(encoding="utf-8") for item in files}
    out: dict[tuple[str, str], dict[str, object]] = {}
    for span in spans_for(files, contents):
        rel = str(Path(str(span["file"])).resolve().relative_to(PROJECT_ROOT))
        out[(rel, str(span["path"]))] = span
    return out


def freeze() -> int:
    baseline = spans_at(FREEZE_SHA, tracked_at(FREEZE_SHA))
    over = sorted(
        (
            {
                "file": key[0],
                "path": key[1],
                "baseline_start_line": span["start_line"],
                "baseline_end_line": span["end_line"],
                "baseline_lines": span["lines"],
            }
            for key, span in baseline.items()
            if int(span["lines"]) > LIMIT
        ),
        key=lambda item: (item["file"], item["path"]),
    )
    LEDGER.write_text(
        json.dumps(
            {
                "base_sha": FREEZE_SHA,
                "limit": LIMIT,
                "note": (
                    "冻结豁免：基线中已超 60 行的函数。可修改，行数只减不增（棘轮）。"
                    "新增逻辑请抽成 ≤60 行的新函数，不得让这些函数继续变长。"
                ),
                "exemptions": over,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"froze {len(over)} exemptions from {FREEZE_SHA[:7]} into {LEDGER.name}")
    return 0


def main() -> int:
    if "--freeze" in sys.argv:
        return freeze()
    if not LEDGER.exists():
        print(f"FAIL 缺少冻结豁免清单 {LEDGER}", file=sys.stderr)
        return 1
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    if ledger["base_sha"] != FREEZE_SHA:
        print("FAIL 豁免清单的基线 SHA 与脚本不符", file=sys.stderr)
        return 1
    exempt = {
        (item["file"], item["path"]): int(item["baseline_lines"])
        for item in ledger["exemptions"]
    }

    present = present_now()
    baseline = spans_at(FREEZE_SHA, tracked_at(FREEZE_SHA))
    current = spans_now(present)

    failures: list[str] = []
    for key, span in sorted(current.items()):
        lines = int(span["lines"])
        allowed = exempt.get(RELOCATIONS.get(key, key))
        if allowed is not None:
            if lines > allowed:
                failures.append(
                    f"{key[0]} :: {key[1]} 是冻结豁免函数，只减不增，"
                    f"基线 {allowed} 行 → 现在 {lines} 行"
                )
            continue
        if lines > LIMIT:
            was = baseline.get(RELOCATIONS.get(key, key))
            origin = (
                f"基线 {was['lines']} 行" if was else "本包新增"
            )
            failures.append(
                f"{key[0]} :: {key[1]} {lines} 行，超过 {LIMIT}（{origin}，不在冻结豁免内）"
            )

    for path in NO_FILE_GROWTH:
        before = git("show", f"{FREEZE_SHA}:{path}").count("\n")
        after = (PROJECT_ROOT / path).read_text(encoding="utf-8").count("\n")
        if after > before:
            failures.append(f"{path} 净行数增长 {before} → {after}")

    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1

    longest = max(current.values(), key=lambda span: int(span["lines"]))
    print(f"PASS function budget（限 {LIMIT} 行）")
    print(f"  受检函数: {len(current)} 个，覆盖 {len(present)} 个文件")
    print(f"  冻结豁免: {len(exempt)} 个（基线 {FREEZE_SHA[:7]}，只减不增）")
    print(f"  最长非豁免函数: {longest['lines']} 行 — {longest['path'][:60]}")
    for path in NO_FILE_GROWTH:
        before = git("show", f"{FREEZE_SHA}:{path}").count("\n")
        after = (PROJECT_ROOT / path).read_text(encoding="utf-8").count("\n")
        print(f"  {path}: {before} → {after} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
