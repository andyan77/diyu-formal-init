#!/usr/bin/env python3
"""EXE-V1 · 变更面门：本包只许动 docs/EXE-V1/** 与 scripts/exev1/**。

窗口口径沿 EXE-V0 先例：以授权基线 SHA 为起点、当前 HEAD 为终点做两点 diff，
并断言基线确实是 HEAD 的祖先——分支被改写过时窗口就不再描述本分支，必须报错
而不是给出一份"看起来干净"的清单。

`git diff --name-only` 在 CI runner 的 `core.quotePath` 默认值下会把中文路径转义成
八进制串（EXE-01R 与 EXE-V0 各踩过一次），因此这里一律用 `-z` + NUL 切分。
"""

from __future__ import annotations

import subprocess
import sys

AUTHORIZED_BASE = "95fa010aedf886bddd553520e405d0160da22c81"

ALLOWED_PREFIXES = (
    "docs/EXE-V1/",
    "scripts/exev1/",
)

FORBIDDEN_PREFIXES = (
    "src/",
    "frontend/",
    "alembic/",
    "deploy/",
    "config/",
    "tests/",
    "scripts/exe01/",
    "scripts/exev0/",
    ".github/",
    "Makefile",
    "MILESTONE.md",
    "AGENTS.md",
    "openapi.json",
    "docs/COMM-01-执行包排产与工程对照指南.md",
    "docs/COMM-01-品牌价值可见创作参谋确认提案与付费试点最小闭环执行包.md",
    "docs/UX-04R-前端产品化增量与工程边界执行包.md",
)


def _git(*arguments: str) -> str:
    completed = subprocess.run(
        ("git", *arguments),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(arguments)} 失败：{completed.stderr.strip()}")
    return completed.stdout


def is_ancestor(sha: str) -> bool:
    """基线必须是当前 HEAD 的祖先；对象不存在也算不成立。"""
    exists = subprocess.run(
        ("git", "cat-file", "-e", f"{sha}^{{commit}}"),
        capture_output=True,
        check=False,
    )
    if exists.returncode != 0:
        return False
    ancestry = subprocess.run(
        ("git", "merge-base", "--is-ancestor", sha, "HEAD"),
        capture_output=True,
        check=False,
    )
    return ancestry.returncode == 0


def changed_files(base: str) -> list[str]:
    raw = _git("diff", "--name-only", "-z", f"{base}..HEAD")
    return [path for path in raw.split("\0") if path]


def classify(paths: list[str]) -> tuple[list[str], list[str]]:
    trespasses: list[str] = []
    for path in paths:
        if any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
            trespasses.append(f"{path}（明确禁改）")
        elif not any(path.startswith(prefix) for prefix in ALLOWED_PREFIXES):
            trespasses.append(f"{path}（不在 allowlist 内）")
    return sorted(trespasses), sorted(paths)


def main() -> int:
    if not is_ancestor(AUTHORIZED_BASE):
        print(
            f"FAIL 授权基线 {AUTHORIZED_BASE[:7]} 不是当前 HEAD 的祖先；"
            "分支被改写过，这个窗口已经不描述本分支",
            file=sys.stderr,
        )
        return 1

    paths = changed_files(AUTHORIZED_BASE)
    trespasses, everything = classify(paths)

    if trespasses:
        print("FAIL 越界改动：", file=sys.stderr)
        for item in trespasses:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print(f"PASS change surface within scope ({len(everything)} files, {AUTHORIZED_BASE[:7]}..HEAD)")
    for path in everything:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
