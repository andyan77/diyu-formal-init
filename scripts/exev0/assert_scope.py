#!/usr/bin/env python3
"""Assert EXE-V0 stayed inside its allowed change surface.

EXE-V0 and EXE-01R are implemented in parallel under the AGENTS.md §9 bounded
dual-executor exception, which only holds while the two allowlists stay mutually
exclusive.  This package owns the value assembler and the two files it hangs
off; the frontend, CI, the three specification documents, the database schema
and — above all — the Writer prompt are somebody else's, or nobody's.

Usage:
    python3 scripts/exev0/assert_scope.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_COMMIT = "c37ae78594220a3ada9ad73020c67b1aec99aa4f"

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
)

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


def changed_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", BASE_COMMIT, "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


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
    files = changed_files()

    for path in files:
        for forbidden, why in FORBIDDEN:
            if path.startswith(forbidden):
                failures.append(f"{path}: 越界（{why}）")
                break
        else:
            if not any(path.startswith(prefix) for prefix, _ in ALLOWED):
                failures.append(f"{path}: 不在本包允许的改动面内")

    for path, why in BYTE_IDENTICAL:
        before = blob_at(BASE_COMMIT, path)
        after = blob_at("HEAD", path)
        if before is None or after is None:
            failures.append(f"{path}: 无法比对基线字节（{why}）")
        elif before != after:
            failures.append(f"{path}: 与基线字节不一致（{why}）")

    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1

    print(f"PASS change surface within scope ({len(files)} files vs {BASE_COMMIT[:7]})")
    for prefix, why in ALLOWED:
        hits = sum(1 for path in files if path.startswith(prefix))
        if hits:
            print(f"  {prefix:42s} {hits:3d} 个文件 — {why}")
    for path, why in BYTE_IDENTICAL:
        print(f"  {path}: 与基线字节一致 — {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
