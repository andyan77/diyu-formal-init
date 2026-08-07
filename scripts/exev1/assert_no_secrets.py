#!/usr/bin/env python3
"""EXE-V1 · 敏感落盘门：本包文件里不许出现秘密、连接信息与生产 PII。

按 v1.1 第 13 条，仓库只落聚合摘要；画像原文、seed、成品全文、用户名、task id、
session、token、主机连接信息与密钥路径一律只留在私有证据根。

本门扫描**本包自己的文件**（docs/EXE-V1/**、scripts/exev1/**）。
它是一道形状门：能拦住"忘了脱敏就提交"，拦不住语义上的越界（例如把画像原文
改写成看不出是原文的段落）。这条局限性写进交付说明，不假装它是完备的。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCANNED_ROOTS = ("docs/EXE-V1", "scripts/exev1")

# 每条规则 = (人类可读的名字, 正则)
RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("私钥块", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("模型 API key", re.compile(r"\bsk-[A-Za-z0-9]{16,}")),
    ("Bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}")),
    ("带口令的数据库连接串", re.compile(r"\b(?:postgres|postgresql)://[^\s:@/]+:[^\s@/]+@")),
    ("裸密钥文件路径", re.compile(r"/[\w./-]*\.pem\b")),
    ("home 下的 ssh 目录", re.compile(r"(?:/home/|~/)[\w./-]*\.ssh/")),
    # 规则名刻意不写成 "user@host" 的字面形式，否则规则表会命中自己。
    ("SSH 主机连接（用户@主机）", re.compile(r"\broot@(?!<)[\w.-]+")),
    # 只防生产公网地址；环回与 0.0.0.0 是本仓到处都有的工程常量，不是秘密。
    ("公网 IPv4 地址", re.compile(r"\b(?!127\.|0\.0\.0\.0)(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("UUID（task/tenant/session 一类标识）", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)),
    ("赋了值的口令变量", re.compile(r"(?i)\b(?:password|passwd|secret|api_key|apikey|token)\s*[=:]\s*['\"]?[A-Za-z0-9/+._-]{8,}")),
)

# 明确豁免：这些是本包必须写清楚的工程事实，不是秘密。
ALLOWED = (
    # 变量名与占位符形态的连接信息
    "$DIYU_ECS_HOST",
    "$DIYU_ECS_USER",
    "$DIYU_ECS_SSH_KEY",
    "DIYU_ECS_SSH_KEY",
    "root@<",
    # 键名（不是值）
    "DEEPSEEK_API_KEY",
    "DIYU_S3_ACCESS_KEY_ID",
    "DIYU_S3_SECRET_ACCESS_KEY",
    "DIYU_SESSION_SECRET",
    "DIYU_INITIAL_OPS_PASSWORD",
    "DIYU_LOCAL_FORMAL_OPS_PASSWORD",
)


def _is_git_ignored(path: Path) -> bool:
    """构建产物（__pycache__ 等）不会进仓库，不该被当成落盘内容扫描。

    判据用 git 自己的忽略规则，而不是硬编码后缀名——这样门扫的正是
    「真会提交进去的东西」，不留人为盲区。
    """
    completed = subprocess.run(
        ("git", "check-ignore", "-q", str(path)),
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def scanned_files() -> list[Path]:
    files: list[Path] = []
    for root in SCANNED_ROOTS:
        base = REPOSITORY_ROOT / root
        if not base.is_dir():
            continue
        files.extend(
            path
            for path in sorted(base.rglob("*"))
            if path.is_file() and not _is_git_ignored(path)
        )
    return files


def _line_is_exempt(line: str) -> bool:
    return any(token in line for token in ALLOWED)


def findings(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return [f"{path.relative_to(REPOSITORY_ROOT)}: 读不了或不是 UTF-8 文本"]

    hits: list[str] = []
    relative = path.relative_to(REPOSITORY_ROOT)
    for number, line in enumerate(text.splitlines(), start=1):
        if _line_is_exempt(line):
            continue
        for name, pattern in RULES:
            match = pattern.search(line)
            if match:
                snippet = match.group(0)
                masked = snippet[:6] + "…" if len(snippet) > 6 else snippet
                hits.append(f"{relative}:{number} 命中「{name}」→ {masked}")
    return hits


def main() -> int:
    files = scanned_files()
    if not files:
        print("FAIL 没有可扫描的文件——本包目录不存在？", file=sys.stderr)
        return 1

    all_hits: list[str] = []
    for path in files:
        all_hits.extend(findings(path))

    if all_hits:
        print("FAIL 疑似敏感内容落盘：", file=sys.stderr)
        for hit in all_hits:
            print(f"  - {hit}", file=sys.stderr)
        return 1

    print(f"PASS no secrets on disk ({len(files)} files scanned, {len(RULES)} rules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
