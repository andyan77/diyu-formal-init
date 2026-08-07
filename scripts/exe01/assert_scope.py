#!/usr/bin/env python3
"""Assert EXE-01 stayed inside its allowed change surface.

The package may rebuild the frontend and adapt the SPA entry points, and
nothing else. Content and domain services, repositories, database schema,
generation semantics, permission semantics, the three specification documents
and MILESTONE.md are all out of bounds. Reviewing that by eye across sixty
changed files is how a boundary quietly moves, so it is checked here instead.

Usage:
    python3 scripts/exe01/assert_scope.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_COMMIT = "8c9f2ac60de7d23248f03add9f971e2c1bab5572"

# Prefixes this package is allowed to touch, each with the clause that allows it.
ALLOWED: tuple[tuple[str, str], ...] = (
    ("frontend/", "FE-00—FE-04 主交付面"),
    ("scripts/exe01/", "本包断言与工具"),
    ("scripts/golden.sh", "前端 codegen 漂移门接入（明文允许）"),
    ("src/gateway/api/html.py", "SPA shell / bootstrap 适配（SEAM-06）"),
    ("src/gateway/api/app.py", "新旧 SPA 入口注册与重定向（SEAM-06）"),
    ("tests/test_exe01_", "对应后端路由测试（明文允许）"),
    ("docs/前端UI架构/", "FE-00 设计交付物与截图回归"),
)

# Paths that are forbidden even though a prefix above might otherwise cover
# them, plus the explicit red lines from the execution prompt.
FORBIDDEN: tuple[tuple[str, str], ...] = (
    ("MILESTONE.md", "里程碑状态文件只读"),
    ("docs/COMM-01-", "规范真源只读"),
    ("docs/UX-04R-", "规范真源只读"),
    ("alembic/", "数据库 schema 禁改"),
    (".env", "密钥禁改"),
    ("deploy/", "生产配置禁改"),
    ("config/", "运行配置禁改"),
    ("src/brain/", "内容服务与领域服务禁改"),
    ("src/shared/", "领域共享层禁改"),
    ("src/infrastructure/", "Repository 与基础设施禁改"),
    ("src/tool/", "运维工具禁改"),
    ("docker-compose", "生产编排禁改"),
    ("Dockerfile", "生产镜像禁改"),
    ("pyproject.toml", "依赖与构建配置禁改"),
)

# Files that exist to prove the two giant components did not grow.
NO_GROWTH = (
    "frontend/src/app/CreatorApp.tsx",
    "frontend/src/app/TenantAdminApp.tsx",
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


def line_count_at(ref: str, path: str) -> int | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return len(result.stdout.splitlines())


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

    for path in NO_GROWTH:
        before = line_count_at(BASE_COMMIT, path)
        after = line_count_at("HEAD", path)
        if before is None or after is None:
            failures.append(f"{path}: 无法比对行数")
        elif after > before:
            failures.append(
                f"{path}: 净行数增长 {before} -> {after}；触碰这两个文件时必须同时搬出"
                "等量或更大的职责"
            )

    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1

    print(f"PASS change surface within scope ({len(files)} files vs {BASE_COMMIT[:7]})")
    for prefix, why in ALLOWED:
        hits = sum(1 for path in files if path.startswith(prefix))
        if hits:
            print(f"  {prefix:34s} {hits:3d} 个文件 — {why}")
    for path in NO_GROWTH:
        print(
            f"  {path}: {line_count_at(BASE_COMMIT, path)} -> {line_count_at('HEAD', path)} 行"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
