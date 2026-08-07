#!/usr/bin/env python3
"""Assert EXE-V0 stayed inside its allowed change surface.

EXE-V0 and EXE-01R were implemented in parallel under the AGENTS.md §9 bounded
dual-executor exception, which only holds while the two allowlists stay mutually
exclusive.  This package owns the value assembler and the two files it hangs
off; the frontend, CI, the three specification documents, the database schema
and — above all — the Writer prompt are somebody else's, or nobody's.

The window is what makes that judgeable, and it is now frozen at both ends.
It ran from the authorized base to HEAD while the branch stood alone; after the
mainline was merged in, the near side moved to the merged mainline commit so that
EXE-01R's files stopped reading as EXE-V0 trespasses.  Both ends are now pinned
SHAs: once this lands on the mainline, every later mainline commit is somebody
else's package, and a window that still said HEAD would keep judging them by this
package's allowlist forever.

The commit that performs the freeze necessarily falls outside the window it
freezes.  That is the same trade EXE-01R made at `eb6bb5d`, and it is why the
head SHA is worth an ancestor assertion rather than a comment: a pinned SHA that
is no longer behind us describes a tree nobody has.

Usage:
    python3 scripts/exev0/assert_scope.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# The base this package was authorized to build on (COMM-01 REVISION-7 / D-COMM-09).
AUTHORIZED_BASE = "c37ae78594220a3ada9ad73020c67b1aec99aa4f"

# The frozen comparison window: the mainline merged in at serialized integration
# (EXE-01R already inside it) and this package's implementation-final commit.
# Pinned to SHAs rather than to `origin/...` or HEAD: a gate that resolves a
# remote ref judges whatever that ref points at today, a CI checkout may not have
# the ref at all, and a HEAD-anchored far side would keep scanning the mainline
# long after this package stopped being the thing changing it.
WINDOW_BASE = "8d909cf958c5241d70c8715252e881f89a047f50"
WINDOW_HEAD = "877566ace648e3bef2a7f44ee6808b51613c3560"

# Exact paths and prefixes this package may touch, each with the clause allowing it.
ALLOWED: tuple[tuple[str, str], ...] = (
    ("src/brain/payoff_assembly.py", "确定性组装器（新）"),
    ("src/brain/content_service.py", "手术点 _new_publication_contract 与任务快照挂载"),
    ("src/shared/task_value_assembly.py", "TaskValueAssemblyV1 独立版本化对象（新）"),
    ("src/shared/content_snapshot.py", "冻结价值组装的只读读取口"),
    ("src/shared/publication_contract.py", "仅确需时；禁破坏历史 digest"),
    ("tests/test_exev0_", "本包测试"),
    ("scripts/exev0/", "本包两门与固定样本脚本"),
    ("docs/EXE-V0/", "本包交付材料"),
    ("Makefile", "监理解禁：make exev0-gates 入口（仅限此目的）"),
    (".github/workflows/ci.yml", "监理解禁：exev0 三门远端接入（仅限此目的）"),
)

# Both were red lines until the supervisor lifted them, verbatim, for one purpose:
# 「授权微轮补 `make exev0-gates` 并接入 ci.yml（Makefile 与 ci.yml 两文件解禁仅限此目的）」
# (COMM-01 排产与工程对照指南, e5038bf).  Exact paths only — everything else under
# .github/ stays forbidden, so lifting one file did not open the directory.
NARROW_EXCEPTIONS = frozenset({"Makefile", ".github/workflows/ci.yml"})

# Red lines from the execution prompt, checked before the allowlist.
FORBIDDEN: tuple[tuple[str, str], ...] = (
    ("src/tool/llm_gateway/deepseek.py", "Writer 已读 contract.audience_payoff，一行不改"),
    ("Makefile", "构建入口禁改"),
    (".github/", "CI 定义禁改"),
    ("scripts/exe01/", "EXE-01R 互斥面"),
    ("scripts/golden.sh", "EXE-01R 互斥面"),
    ("frontend/", "EXE-01R 互斥面"),
    ("openapi.json", "无 API 变化不得漂移"),
    ("alembic/", "快照 jsonb expand-only，零 migration"),
    ("MILESTONE.md", "里程碑状态文件只读"),
    ("docs/COMM-01-", "规范真源只读"),
    ("docs/UX-04R-", "规范真源只读"),
    ("AGENTS.md", "协作基线只读"),
    (".env", "密钥禁改"),
    ("deploy/", "生产配置禁改"),
    ("config/", "运行配置禁改"),
    ("docker-compose", "生产编排禁改"),
    ("Dockerfile", "生产镜像禁改"),
    ("pyproject.toml", "依赖与构建配置禁改"),
)

# Files whose bytes must be identical to the base: proving "not modified" by
# absence from the diff is enough, but these are the ones worth naming.
BYTE_IDENTICAL: tuple[tuple[str, str], ...] = (
    ("src/tool/llm_gateway/deepseek.py", "Writer prompt 该行未被本包修改"),
    ("openapi.json", "无 API 变化"),
)


def is_ancestor(commit: str) -> bool:
    known = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
    )
    if known.returncode != 0:
        return False
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def changed_files(base: str, head: str) -> list[str]:
    # -z, not --name-only alone.  With core.quotePath at its default a CI runner
    # emits "docs/EXE-V0/\345\233\272..." where this machine emits the path,
    # and every 中文 filename then fails its prefix check on the runner only.
    result = subprocess.run(
        ["git", "diff", "--name-only", "-z", base, head],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [path for path in result.stdout.split("\0") if path]


def blob_at(ref: str, path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
    )
    return None if result.returncode != 0 else result.stdout


def main() -> int:
    failures: list[str] = []
    for label, commit in (("窗口起点", WINDOW_BASE), ("窗口终点", WINDOW_HEAD)):
        if not is_ancestor(commit):
            print(
                f"FAIL {label} {commit[:12]} 不是当前 HEAD 的祖先；"
                "分支被改写过，这个窗口已经不描述本分支",
                file=sys.stderr,
            )
            return 1
    files = changed_files(WINDOW_BASE, WINDOW_HEAD)

    for path in files:
        for forbidden, why in FORBIDDEN:
            if path.startswith(forbidden) and path not in NARROW_EXCEPTIONS:
                failures.append(f"{path}: 越界（{why}）")
                break
        else:
            if not any(path.startswith(prefix) for prefix, _ in ALLOWED):
                failures.append(f"{path}: 不在本包允许的改动面内")

    for path, why in BYTE_IDENTICAL:
        # Anchored at the authorized base, not the window base: the honest claim
        # is that this package never touched these, not merely that it stopped.
        before = blob_at(AUTHORIZED_BASE, path)
        after = blob_at(WINDOW_HEAD, path)
        if before is None or after is None:
            failures.append(f"{path}: 无法比对基线字节（{why}）")
        elif before != after:
            failures.append(f"{path}: 与基线字节不一致（{why}）")

    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1

    window = f"{WINDOW_BASE[:7]}..{WINDOW_HEAD[:7]}（已冻结）"
    print(f"PASS change surface within scope ({len(files)} files, {window})")
    for prefix, why in ALLOWED:
        hits = sum(1 for path in files if path.startswith(prefix))
        if hits:
            print(f"  {prefix:42s} {hits:3d} 个文件 — {why}")
    for path, why in BYTE_IDENTICAL:
        print(f"  {path}: 与基线字节一致 — {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
