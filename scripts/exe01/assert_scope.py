#!/usr/bin/env python3
"""Assert EXE-01 and EXE-01R each stayed inside their own change surface.

Two packages have now touched this tree, and they were allowed different
things: EXE-01 could rebuild the frontend and adapt the SPA entry points,
EXE-01R could additionally add one projection field to one repository method.
Checking both against one base would either let EXE-01R's allowances back-date
onto EXE-01, or flag the supervisor's own commits between the two packages as
if this package had made them. So each window is checked against its own base,
its own allowlist, and its own red lines.

Usage:
    python3 scripts/exe01/assert_scope.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Red lines both packages share. Nothing below is reachable by any clause.
COMMON_FORBIDDEN: tuple[tuple[str, str], ...] = (
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


@dataclass(frozen=True)
class Window:
    """One package's change surface, pinned to the commits that bound it.

    `head` is a literal SHA once the package has finished. Leaving it as HEAD
    would mean every later package's commits keep arriving inside a window
    that closed, and each one would have to be argued about here — a finished
    package must not be able to fail because of work it never did.
    """

    package: str
    base: str
    head: str
    allowed: tuple[tuple[str, str], ...]
    # Exact paths that override a COMMON_FORBIDDEN prefix, each with its clause.
    exempt: tuple[tuple[str, str], ...] = ()
    no_growth: tuple[str, ...] = ()


EXE01 = Window(
    package="EXE-01",
    base="af20ae5601a53551bb0d50288d69ff3f08e29163",
    head="3043217",
    allowed=(
        ("frontend/", "FE-00—FE-04 主交付面"),
        ("scripts/exe01/", "本包断言与工具"),
        ("scripts/golden.sh", "前端 codegen 漂移门接入（明文允许）"),
        ("src/gateway/api/html.py", "SPA shell / bootstrap 适配（SEAM-06）"),
        ("src/gateway/api/app.py", "新旧 SPA 入口注册与重定向（SEAM-06）"),
        ("tests/test_exe01_", "对应后端路由测试（明文允许）"),
        ("docs/前端UI架构/", "FE-00 设计交付物与截图回归"),
        ("openapi.json", "app.py 路由表的确定性派生物；由 `make openapi` 重生，golden 门校验"),
    ),
    no_growth=(
        "frontend/src/app/CreatorApp.tsx",
        "frontend/src/app/TenantAdminApp.tsx",
    ),
)

# Frozen at the implementation-final commit. Anything after it belongs to a
# later package and is judged by that package's own window.
EXE01R_FINAL = "13cfcb2308a9c0b8efbaaa4500e4f0a723d269c7"

EXE01R = Window(
    package="EXE-01R",
    base="357d17cd610d5c3c0b3fd5f7c703b8710da82d64",
    head=EXE01R_FINAL,
    allowed=(
        ("frontend/", "R1—R4 作用域事务、流校验、深链与视觉证据"),
        ("scripts/exe01/", "本包断言、预算工具与门链 runner"),
        ("Makefile", "make exe01-gates 入口（R5）"),
        (".github/workflows/ci.yml", "九门远端接入（R5）"),
        (".python-version", "监理裁决 2：钉住 3.10，消除 uv 取 3.14 的误报"),
        ("src/gateway/api/app.py", "R2 深链最小 SPA 入口适配"),
        ("tests/test_exe01r_", "R1/R2 对应后端测试（明文允许）"),
        ("docs/前端UI架构/FE-00/", "R4 视觉证据矩阵与批准表"),
    ),
    exempt=(
        (
            "src/infrastructure/workbench_repository.py",
            "R1.4 只增投影字段 tenant_id；下方另有 additive 断言",
        ),
    ),
    no_growth=("frontend/src/app/CreatorApp.tsx",),
)

WINDOWS = (EXE01, EXE01R)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False
    )


def changed_files(window: Window) -> list[str]:
    # -z, not --name-only alone: git quotes non-ASCII paths ("docs/\345\211...")
    # whenever core.quotePath is left at its default, which is what a CI runner
    # does and what this developer's machine does not. Every docs/前端UI架构/
    # path then failed its prefix check on the runner and nowhere else.
    result = run("git", "diff", "--name-only", "-z", window.base, window.head)
    if result.returncode != 0:
        raise SystemExit(f"无法比较 {window.base}..{window.head}: {result.stderr}")
    return [path for path in result.stdout.split("\0") if path]


def line_count_at(ref: str, path: str) -> int | None:
    result = run("git", "show", f"{ref}:{path}")
    return None if result.returncode != 0 else len(result.stdout.splitlines())


def check_surface(window: Window, files: list[str]) -> list[str]:
    failures = []
    exempt = dict(window.exempt)
    for path in files:
        if path in exempt:
            continue
        hit = next((why for bad, why in COMMON_FORBIDDEN if path.startswith(bad)), None)
        if hit:
            failures.append(f"[{window.package}] {path}: 越界（{hit}）")
        elif not any(path.startswith(prefix) for prefix, _ in window.allowed):
            failures.append(f"[{window.package}] {path}: 不在本包允许的改动面内")
    return failures


def check_no_growth(window: Window) -> list[str]:
    failures = []
    for path in window.no_growth:
        before = line_count_at(window.base, path)
        after = line_count_at(window.head, path)
        if before is None or after is None:
            failures.append(f"[{window.package}] {path}: 无法比对行数")
        elif after > before:
            failures.append(
                f"[{window.package}] {path}: 净行数增长 {before} -> {after}；"
                "触碰这个文件时必须同时搬出等量或更大的职责"
            )
    return failures


def projection_keys(ref: str) -> set[str]:
    """The column aliases `content_identity` hands the bootstrap."""
    source = run("git", "show", f"{ref}:src/infrastructure/workbench_repository.py")
    if source.returncode != 0:
        return set()
    body = source.stdout.split("def content_identity(")[-1].split("\n    def ")[0]
    return set(re.findall(r"\bAS (\w+)", body))


def check_additive_projection(window: Window) -> list[str]:
    """R1.4 was allowed to add a field, not to take one away.

    Line counts cannot see this — rewriting one SELECT line both adds and
    removes — so the guarantee is checked where it actually lives: the set of
    keys the method returns may only grow.
    """
    if not any(p.endswith("workbench_repository.py") for p, _ in window.exempt):
        return []
    before, after = projection_keys(window.base), projection_keys(window.head)
    if not before:
        return [f"[{window.package}] 无法读出 {window.base[:7]} 的 content_identity 投影"]
    lost = sorted(before - after)
    if lost:
        return [
            f"[{window.package}] content_identity 少了投影字段 {lost}；"
            "R1.4 只准新增，不准改动既有键的含义"
        ]
    return []


def check_frozen_head(window: Window) -> list[str]:
    """A frozen window must still describe this branch.

    Pinning the head to a SHA is only honest while that SHA is behind us: if
    it were dropped by a rebase, or pointed at some other line of work, the
    window would keep passing while describing a tree nobody has.
    """
    if window.head == "HEAD":
        return []
    known = run("git", "cat-file", "-e", f"{window.head}^{{commit}}")
    if known.returncode != 0:
        return [f"[{window.package}] 冻结点 {window.head[:12]} 在本仓找不到"]
    reachable = run("git", "merge-base", "--is-ancestor", window.head, "HEAD")
    if reachable.returncode != 0:
        return [
            f"[{window.package}] 冻结点 {window.head[:12]} 不是当前 HEAD 的祖先；"
            "分支被改写过，这个窗口已经不描述本分支"
        ]
    return []


def report(window: Window, files: list[str]) -> None:
    edge = "HEAD" if window.head == "HEAD" else f"{window.head[:7]}（已冻结）"
    print(
        f"PASS [{window.package}] change surface within scope "
        f"({len(files)} files, {window.base[:7]}..{edge})"
    )
    for prefix, why in window.allowed:
        hits = sum(1 for path in files if path.startswith(prefix))
        if hits:
            print(f"  {prefix:34s} {hits:3d} 个文件 — {why}")
    for path, why in window.exempt:
        if path in files:
            print(f"  {path:34s}   1 个文件 — {why}")
    for path in window.no_growth:
        before, after = line_count_at(window.base, path), line_count_at(window.head, path)
        print(f"  {path}: {before} -> {after} 行")


def main() -> int:
    failures: list[str] = []
    seen: list[tuple[Window, list[str]]] = []
    for window in WINDOWS:
        files = changed_files(window)
        seen.append((window, files))
        failures += check_frozen_head(window)
        failures += check_surface(window, files)
        failures += check_no_growth(window)
        failures += check_additive_projection(window)

    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    for window, files in seen:
        report(window, files)
    return 0


if __name__ == "__main__":
    sys.exit(main())
