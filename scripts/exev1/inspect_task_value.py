#!/usr/bin/env python3
"""EXE-V1 · 任务价值组装检查器（陪跑期"逐条检查降级"的唯一执行手段）。

当前创作端界面不显示 payoff 溯源（该面板属 EXE-06），因此陪跑辅导脚本中的
"关 4 · 降级检查"只能靠本工具完成。

设计取舍——**本脚本不连接数据库、不读取任何凭据**：

    生产侧只负责按"只读三件套"（READ ONLY 事务 + set_config('app.tenant_id')
    + SQL 显式 tenant_id 谓词）把快照 JSON 导出到私有证据根；本脚本只做
    digest 校验与安全渲染。这样凭据面与渲染面彻底分离，脚本本身零秘密。

输出**只含**以下字段，其余一律不出现：

    payoff_origin / payoff_confirmation_state / brand_relevance_path /
    payoff_degraded / payoff_degradation_reason / ruleset_version / digest_valid

明确**不输出**：画像原文、seed 原文、成品正文、audience_payoff 文本、
账号名、task UUID、session、token、任何 PII。详单只留在私有证据根的输入文件里。

用法：

    # 单条（快照 JSON 从文件或 stdin 读入）
    python3 scripts/exev1/inspect_task_value.py --snapshot-file <私有证据根>/task-01.json

    # 批量（JSON 数组，或 JSON Lines）
    python3 scripts/exev1/inspect_task_value.py --snapshot-file <私有证据根>/batch.jsonl --lines

    # 机器可读
    python3 scripts/exev1/inspect_task_value.py --snapshot-file … --json

生产侧导出命令见 docs/EXE-V1/部署runbook.md 与 L0观察报告.md。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.shared.task_value_assembly import (  # noqa: E402
    task_value_assembly_digest,
    task_value_assembly_from_document,
)

SAFE_FIELDS = (
    "payoff_origin",
    "payoff_confirmation_state",
    "brand_relevance_path",
    "payoff_degraded",
    "payoff_degradation_reason",
    "ruleset_version",
)
ASSEMBLY_KEY = "task_value_assembly"
DIGEST_KEY = "task_value_assembly_digest"


class InspectionError(RuntimeError):
    """输入不是一个可检查的快照。"""


def _assembly_document(snapshot: Any) -> tuple[dict[str, Any], str | None]:
    """从快照里取出组装对象与其冻结 digest。

    同时接受两种形状：完整任务快照（含 task_value_assembly 键），
    或已经剥出来的组装文档本身。
    """
    if not isinstance(snapshot, dict):
        raise InspectionError("快照不是 JSON 对象")
    if ASSEMBLY_KEY in snapshot:
        document = snapshot[ASSEMBLY_KEY]
        if not isinstance(document, dict):
            raise InspectionError("task_value_assembly 不是 JSON 对象")
        frozen = snapshot.get(DIGEST_KEY)
        return document, frozen if isinstance(frozen, str) else None
    if "contract_version" in snapshot and "payoff_origin" in snapshot:
        return snapshot, None
    raise InspectionError("快照里没有 task_value_assembly（可能是 pre-V0 任务）")


def inspect_snapshot(snapshot: Any) -> dict[str, Any]:
    """把一条快照压成只含安全字段的结论。"""
    document, frozen_digest = _assembly_document(snapshot)
    assembly = task_value_assembly_from_document(document)
    recomputed = task_value_assembly_digest(assembly)
    result: dict[str, Any] = {field: getattr(assembly, field) for field in SAFE_FIELDS}
    if frozen_digest is None:
        result["digest_valid"] = None
        result["digest_note"] = "快照未随附冻结 digest，只校验了结构"
    else:
        result["digest_valid"] = recomputed == frozen_digest
    return result


def _load(path: Path | None, as_lines: bool) -> list[Any]:
    raw = sys.stdin.read() if path is None else path.read_text(encoding="utf-8")
    if as_lines:
        return [json.loads(line) for line in raw.splitlines() if line.strip()]
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, list) else [parsed]


def _render_row(index: int, outcome: dict[str, Any]) -> str:
    if "error" in outcome:
        return f"#{index:02d}  ERROR  {outcome['error']}"
    degraded = "是" if outcome["payoff_degraded"] else "否"
    digest_valid = outcome["digest_valid"]
    digest_text = {True: "OK", False: "不一致", None: "未随附"}[digest_valid]
    path = outcome["brand_relevance_path"] or "-"
    reason = outcome["payoff_degradation_reason"] or "-"
    return (
        f"#{index:02d}  origin={outcome['payoff_origin']:<16} "
        f"path={path:<22} 降级={degraded:<2} reason={reason:<24} "
        f"digest={digest_text}"
    )


def _summarise(outcomes: list[dict[str, Any]]) -> list[str]:
    usable = [item for item in outcomes if "error" not in item]
    if not usable:
        return ["（无可统计条目）"]
    total = len(usable)
    degraded = sum(1 for item in usable if item["payoff_degraded"])
    invalid = sum(1 for item in usable if item["digest_valid"] is False)
    paths = Counter(item["brand_relevance_path"] or "（降级·无路径）" for item in usable)
    reasons = Counter(
        item["payoff_degradation_reason"] for item in usable if item["payoff_degraded"]
    )
    lines = [
        f"总数 {total}　降级 {degraded}（{degraded / total:.0%}）　digest 不一致 {invalid}",
        "路径分布：" + "　".join(f"{name} {count}" for name, count in paths.most_common()),
    ]
    if reasons:
        lines.append(
            "降级原因：" + "　".join(f"{name} {count}" for name, count in reasons.most_common())
        )
    if invalid:
        lines.append("⚠ 存在 digest 不一致的条目——按事故回滚协议当作疑似数据损坏处理")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="检查任务快照里的价值组装（只输出安全字段）",
        allow_abbrev=False,
    )
    parser.add_argument("--snapshot-file", type=Path, default=None, help="快照 JSON 路径；省略则读 stdin")
    parser.add_argument("--lines", action="store_true", help="按 JSON Lines 解析")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    arguments = parser.parse_args(argv)

    try:
        snapshots = _load(arguments.snapshot_file, arguments.lines)
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL 读不了输入：{error}", file=sys.stderr)
        return 2

    outcomes: list[dict[str, Any]] = []
    for snapshot in snapshots:
        try:
            outcomes.append(inspect_snapshot(snapshot))
        except Exception as error:  # noqa: BLE001 —— 单条坏数据不该中断整批检查
            outcomes.append({"error": str(error)})

    if arguments.json:
        print(json.dumps(outcomes, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for index, outcome in enumerate(outcomes, start=1):
            print(_render_row(index, outcome))
        print()
        for line in _summarise(outcomes):
            print(line)

    return 1 if any(item.get("digest_valid") is False for item in outcomes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
