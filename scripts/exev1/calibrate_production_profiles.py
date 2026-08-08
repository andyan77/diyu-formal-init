#!/usr/bin/env python3
"""EXE-V1 · A 层：真实生产画像的固定样本组装 dry-run（零 LLM、零任务写入）。

用途：核销 `production_profile_calibration`。

输入：私有证据根里的画像 JSON（由生产侧按只读三件套导出）。
      **画像原文只从私有证据根读，绝不写回仓库。**

输出：
  --summary-out  聚合摘要（可进仓库）：路径分布 / 降级计数与原因 / digest 有效性 /
                 静态默认重合数 / 泄漏检查结论。零原文、零账号名、零 account_id。
  --detail-out   逐行详单（只进私有证据根）：含每行的 payoff 文本，供人工抽查。

同时执行一项硬检查——**泄漏检查**：组装出来的每一句 payoff 都不得包含画像五段里
任何一个长度 ≥6 的连续片段。这是 v1.1 第 9 条"零画像原文泄漏"的可执行判据。

用法：
    python3 scripts/exev1/calibrate_production_profiles.py \
        --profiles <私有证据根>/15_production_profiles.json \
        --summary-out docs/EXE-V1/生产画像校准摘要.md \
        --detail-out <私有证据根>/16_calibration_detail.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.brain.payoff_assembly import (  # noqa: E402
    CONTENT_PRODUCTS,
    PayoffAssemblyRequest,
    profile_signals,
    TOPIC_ORIGINS,
    assemble_task_value,
    build_payoff_request,
    RULESET_V0,
    payoff_ruleset_digest,
    static_payoff_defaults,
)
from src.shared.publication_contract import product_brief  # noqa: E402
from src.shared.task_value_assembly import (  # noqa: E402
    PROFILE_SIGNAL_FIELDS,
    normalized_payoff,
    task_value_assembly_digest,
)
from src.shared.types import AccountExpression  # noqa: E402

LEAK_WINDOW = 6


def _expression(row: dict[str, Any]) -> AccountExpression:
    return AccountExpression(
        profile_id=None,
        version=int(row["version"]),
        is_draft=False,
        identity_position=row["identity_position"],
        authority_boundary=row["authority_boundary"],
        audience_relationship=row["audience_relationship"],
        content_territories=row["content_territories"],
        default_production_conditions=row["default_production_conditions"],
    )


def _leak_fragments(row: dict[str, Any]) -> set[str]:
    """画像五段里所有长度为 LEAK_WINDOW 的连续片段。"""
    fragments: set[str] = set()
    for field in PROFILE_SIGNAL_FIELDS:
        text = str(row[field])
        for start in range(0, max(0, len(text) - LEAK_WINDOW + 1)):
            fragments.add(text[start : start + LEAK_WINDOW])
    return fragments


def _account_label(row: dict[str, Any], index: int) -> str:
    """对外只用序号 + account_id 的短哈希，绝不用账号名。"""
    short = hashlib.sha256(str(row["account_id"]).encode("utf-8")).hexdigest()[:8]
    return f"A{index}·{short}"


def run_matrix(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    statics = {normalized_payoff(value) for value in static_payoff_defaults()}
    results: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        expression = _expression(row)
        fragments = _leak_fragments(row)
        label = _account_label(row, index)
        for product in CONTENT_PRODUCTS:
            for origin in TOPIC_ORIGINS:
                assembly = assemble_task_value(
                    build_payoff_request(
                        content_product=product,
                        topic_origin=origin,
                        account_expression=expression,
                        product_basis=None,
                        series_delta=None,
                        static_payoff=product_brief(product, origin)[1],
                    )
                )
                payoff = assembly.audience_payoff
                leaked = sorted(piece for piece in fragments if piece in payoff)
                results.append(
                    {
                        "account": label,
                        "profile_version": int(row["version"]),
                        "content_product": product,
                        "topic_origin": origin,
                        "payoff_origin": assembly.payoff_origin,
                        "brand_relevance_path": assembly.brand_relevance_path,
                        "payoff_degraded": assembly.payoff_degraded,
                        "payoff_degradation_reason": assembly.payoff_degradation_reason,
                        "payoff_confirmation_state": assembly.payoff_confirmation_state,
                        "ruleset_version": assembly.ruleset_version,
                        "assembly_digest": task_value_assembly_digest(assembly),
                        "payoff_length": len(payoff),
                        "matches_static_default": normalized_payoff(payoff) in statics,
                        "leaked_fragments": leaked,
                        "_payoff": payoff,
                    }
                )
    return results


def determinism_holds(rows: list[dict[str, Any]]) -> bool:
    """同输入必须同输出：整跑第二遍，逐行比 digest。"""
    return [item["assembly_digest"] for item in run_matrix(rows)] == [
        item["assembly_digest"] for item in run_matrix(rows)
    ]



def differentiation_axes(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """回答一个业务问题：payoff 的差异到底沿哪条轴产生？

    组装器看到的画像信息只有 `profile_signals`——**五段里哪几段非空的字段名**，
    不看内容。若三个账号五段都填满，它们对组装器就是等价输入，必然同句。
    这一节把该事实算出来，并对照「任务上下文」轴的分化程度。
    """
    signals = [profile_signals(_expression(row)) for row in rows]
    identical_signals = len(set(signals)) == 1

    statics = static_payoff_defaults()
    paths: Counter[str] = Counter()
    if rows:
        signal = signals[0]
        for product in CONTENT_PRODUCTS:
            for origin in TOPIC_ORIGINS:
                for has_product in (False, True):
                    for has_series in (False, True):
                        assembly = assemble_task_value(
                            PayoffAssemblyRequest(
                                content_product=product,
                                topic_origin=origin,
                                profile_signals=signal,
                                product_basis_present=has_product,
                                series_basis_present=has_series,
                                series_position=2 if has_series else 0,
                                static_payoff=product_brief(product, origin)[1],
                                static_defaults=statics,
                            )
                        )
                        paths[assembly.brand_relevance_path or "（降级）"] += 1
    return {
        "identical_profile_signals": identical_signals,
        "signal_fields_present": sorted(set(signals[0])) if signals else [],
        "task_axis_paths": dict(paths),
        "task_axis_contexts": sum(paths.values()),
    }

def summarise(results: list[dict[str, Any]], accounts: int) -> dict[str, Any]:
    degraded = [item for item in results if item["payoff_degraded"]]
    leaked = [item for item in results if item["leaked_fragments"]]
    static_hits = [item for item in results if item["matches_static_default"]]
    by_account_paths = {}
    for item in results:
        by_account_paths.setdefault(item["account"], Counter())[
            item["brand_relevance_path"] or "（降级·无路径）"
        ] += 1
    distinct_payoffs = len({item["_payoff"] for item in results})
    return {
        "accounts": accounts,
        "rows": len(results),
        "ruleset_digest": payoff_ruleset_digest(RULESET_V0),
        "path_distribution": dict(
            Counter(item["brand_relevance_path"] or "（降级·无路径）" for item in results)
        ),
        "path_distribution_by_account": {
            name: dict(counter) for name, counter in by_account_paths.items()
        },
        "degraded": len(degraded),
        "degradation_reasons": dict(
            Counter(item["payoff_degradation_reason"] for item in degraded)
        ),
        "matches_static_default": len(static_hits),
        "leaked_rows": len(leaked),
        "distinct_payoffs": distinct_payoffs,
        "payoff_length_range": [
            min(item["payoff_length"] for item in results),
            max(item["payoff_length"] for item in results),
        ],
        "confirmation_states": dict(
            Counter(item["payoff_confirmation_state"] for item in results)
        ),
    }


def render_summary(summary: dict[str, Any], verdict: str, determinism: bool, axes: dict[str, Any]) -> str:
    lines = [
        "# 生产画像校准摘要（A 层 · 纯组装 dry-run）",
        "",
        "> 由 `scripts/exev1/calibrate_production_profiles.py` 生成。",
        "> **零 LLM 调用、零任务写入、零画像原文落盘。**",
        "> 画像原文与逐行详单只在私有证据根，仓库只留本摘要。",
        "",
        f"- 账号数：**{summary['accounts']}**（笛语服饰真实逻辑账号）",
        f"- 样本行数：**{summary['rows']}**（{len(CONTENT_PRODUCTS)} 内容产品 × {len(TOPIC_ORIGINS)} 题材来源 × 账号）",
        f"- ruleset digest：`{summary['ruleset_digest']}`",
        f"- 确定性（整跑两遍逐行比 digest）：**{'一致' if determinism else '不一致'}**",
        "",
        "## 路径分布",
        "",
        "| brand_relevance_path | 条数 |",
        "|---|---|",
    ]
    for name, count in sorted(summary["path_distribution"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {name} | {count} |")
    lines += [
        "",
        "## 分账号路径分布（验证「不同账号走不同路径」）",
        "",
        "| 账号 | 路径分布 |",
        "|---|---|",
    ]
    for name, dist in summary["path_distribution_by_account"].items():
        cells = "　".join(f"{key} {value}" for key, value in dist.items())
        lines.append(f"| {name} | {cells} |")
    lines += [
        "",
        "## 合规计数",
        "",
        "| 项 | 值 | 判据 |",
        "|---|---|---|",
        f"| 降级条数 | {summary['degraded']} | 降级本身不是故障，但必须有 reason |",
        f"| 降级原因分布 | {summary['degradation_reasons'] or '（无）'} | 每条降级必须归因 |",
        f"| 与静态默认句重合 | {summary['matches_static_default']} | **必须为 0**——重合即价值引擎没起作用 |",
        f"| 画像原文泄漏行数 | {summary['leaked_rows']} | **必须为 0**（≥{LEAK_WINDOW} 字连续片段判据） |",
        f"| 不同 payoff 句数 | {summary['distinct_payoffs']} / {summary['rows']} | 越接近行数说明区分度越高 |",
        f"| payoff 长度范围 | {summary['payoff_length_range'][0]}–{summary['payoff_length_range'][1]} 字 | 硬门要求 10–120 |",
        f"| confirmation_state | {summary['confirmation_states']} | 提案前一律 unavailable_pre_proposal |",
        "",
        "## 差异沿哪条轴产生（本轮最重要的业务发现）",
        "",
        f"- 三个真实账号的 `profile_signals`：**{'完全相同' if axes['identical_profile_signals'] else '存在差异'}**"
        f"（非空字段 = {'、'.join(axes['signal_fields_present'])}）",
        "- 组装器读画像时**只看五段里哪几段非空的字段名，不看内容**"
        "（这是 EXE-V0 刻意的安全构造：不拼接画像原文）。"
        "三个账号五段都填满 ⇒ 对组装器是**等价输入** ⇒ 必然产出同一句。",
        "",
        f"- 对照：**单账号 × {axes['task_axis_contexts']} 种任务上下文**"
        f"（商品依据有无 × 系列有无 × 内容产品 × 题材来源）→ 路径分布 "
        + "　".join(f"{k} {v}" for k, v in sorted(axes["task_axis_paths"].items(), key=lambda kv: -kv[1])),
        "",
        "> **结论：当前 payoff 的差异来自「这条内容是什么任务」，不来自「这是哪个账号」。**",
        "> 账号级差异要等 `product_expertise` / `existing_series` 路径被真实商品依据或系列触发才出现。",
        "> 这一条必须让 founder 知道——它直接关系到「不同账号写出不同内容」这个目标当前到什么程度。",
        "",
        f"## 结论：{verdict}",
        "",
        "### 这个结论证明了什么",
        "",
        "- 真实画像可被读取，结构满足组装器输入要求；",
        "- 组装规则在生产数据上确定性运行（同输入同输出）；",
        "- 路径 / 降级标记 / 降级原因 / digest 全部合规；",
        "- 组装结果零画像原文泄漏。",
        "",
        "### 这个结论**没有**证明什么",
        "",
        "- ❌ 三个账号的内容语义差异**足够大**——本表只证机制跑通与路径有分化，不证结果有业务区分度；",
        "- ❌ 内容**质量好**——校准与质量是两回事；",
        "- ❌ 使用者会满意。",
        "",
        "边界口径与 [已知边界卡.md](已知边界卡.md) 第二节一致。",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A 层生产画像组装校准", allow_abbrev=False)
    parser.add_argument("--profiles", type=Path, required=True, help="画像 JSON（私有证据根）")
    parser.add_argument("--summary-out", type=Path, required=True, help="聚合摘要输出（可进仓库）")
    parser.add_argument("--detail-out", type=Path, required=True, help="逐行详单输出（私有证据根）")
    arguments = parser.parse_args(argv)

    raw = arguments.profiles.read_text(encoding="utf-8")
    payload = next((line for line in raw.splitlines() if line.strip().startswith("[")), None)
    if payload is None:
        print("FAIL 画像文件里找不到 JSON 数组", file=sys.stderr)
        return 2
    rows = json.loads(payload)

    results = run_matrix(rows)
    determinism = determinism_holds(rows)
    summary = summarise(results, accounts=len(rows))
    axes = differentiation_axes(rows)

    failures = []
    if summary["leaked_rows"]:
        failures.append(f"画像原文泄漏 {summary['leaked_rows']} 行")
    if summary["matches_static_default"]:
        failures.append(f"与静态默认句重合 {summary['matches_static_default']} 行")
    if not determinism:
        failures.append("两遍整跑 digest 不一致，确定性不成立")
    low, high = summary["payoff_length_range"]
    if low < 10 or high > 120:
        failures.append(f"payoff 长度越界：{low}–{high}")

    verdict = "**VERIFIED**" if not failures else "**FAILED**（" + "；".join(failures) + "）"

    arguments.detail_out.parent.mkdir(parents=True, exist_ok=True)
    arguments.detail_out.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    arguments.summary_out.write_text(render_summary(summary, verdict, determinism, axes), encoding="utf-8")

    print(f"账号 {summary['accounts']}　样本 {summary['rows']} 行")
    print(f"路径分布 {summary['path_distribution']}")
    print(f"降级 {summary['degraded']}　静态重合 {summary['matches_static_default']}　泄漏 {summary['leaked_rows']}")
    print(f"不同 payoff 句 {summary['distinct_payoffs']}/{summary['rows']}　长度 {low}–{high}")
    print(f"确定性 {'一致' if determinism else '不一致'}")
    print(f"结论 {verdict}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
