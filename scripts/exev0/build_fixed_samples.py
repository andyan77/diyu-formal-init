#!/usr/bin/env python3
"""Generate the EXE-V0 fixed-sample comparison, deterministically.

One row per sampled task shape.  The point is not that every sentence is good —
templated assembly cannot promise that — but that a founder can read, in one
table, what changed for every 题材 and where the engine honestly gives up.

No production profile text is written into the repository: profiles enter as
which of the五段 carry text, and the onboarding draft is referenced by digest.

Usage:
    python3 scripts/exev0/build_fixed_samples.py            # verify, fail on drift
    python3 scripts/exev0/build_fixed_samples.py --write    # regenerate
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.brain.payoff_assembly import (  # noqa: E402
    CONTENT_PRODUCTS,
    PAYOFF_RULESET_VERSION,
    RULESET_V0,
    assemble_task_value,
    build_payoff_request,
    payoff_ruleset_digest,
    static_payoff_defaults,
)
from src.shared.publication_contract import (  # noqa: E402
    ProductDecisionBasisRefV2,
    SeriesDeltaV1,
    product_brief,
)
from src.shared.task_value_assembly import normalized_payoff  # noqa: E402
from src.shared.types import AccountExpression  # noqa: E402

BASE_COMMIT = "c37ae78594220a3ada9ad73020c67b1aec99aa4f"
ONBOARDING_PROFILE = PROJECT_ROOT / "config" / "onboarding" / "diyu-m7-2b-prefill-v1.json"
REPORT_PATH = PROJECT_ROOT / "docs" / "EXE-V0" / "固定样本对照.md"
MANIFEST_PATH = PROJECT_ROOT / "docs" / "EXE-V0" / "固定样本对照.json"
TOPIC_ORIGINS = ("explicit_user", "system_selected")

_PRODUCT_LABELS = {
    "dressing_decision": "穿衣决策",
    "product_truth": "商品事实解释",
    "brand_life_narrative": "品牌生活叙事",
    "local_response": "本地回应",
    "visual_styling_story": "商品视觉造型",
}
_ORIGIN_LABELS = {"explicit_user": "用户指定题材", "system_selected": "系统自选题材"}


@dataclass(frozen=True)
class SampleProfile:
    profile_id: str
    role: str
    note: str
    expression: AccountExpression


def _expression(**segments: str) -> AccountExpression:
    blank = dict.fromkeys(
        (
            "identity_position",
            "authority_boundary",
            "audience_relationship",
            "content_territories",
            "default_production_conditions",
        ),
        "",
    )
    blank.update(segments)
    return AccountExpression(profile_id=None, version=1, is_draft=False, **blank)


def _onboarding_segments() -> dict[str, str]:
    document = json.loads(ONBOARDING_PROFILE.read_text(encoding="utf-8"))
    segments = document["account_profiles"][0]["segments"]
    return {str(key): str(value) for key, value in segments.items()}


def _profiles() -> tuple[SampleProfile, ...]:
    onboarding = _onboarding_segments()
    without_audience = {key: value for key, value in onboarding.items() if key != "audience_relationship"}
    return (
        SampleProfile(
            "onboarding_prefill",
            "design",
            "config/onboarding 的五段全在（品牌官方账号草案）",
            _expression(**onboarding),
        ),
        SampleProfile(
            "onboarding_without_audience_segment",
            "design",
            "同上，但「主要受众关系」一段留空",
            _expression(**without_audience),
        ),
        SampleProfile(
            "holdout_identity_only",
            "holdout",
            "留出组：只填「表达身份」一段，用来看规则是否还站得住",
            _expression(identity_position=onboarding["identity_position"]),
        ),
        SampleProfile(
            "empty_profile",
            "fallback",
            "五段全空，用来看降级是否可见",
            _expression(),
        ),
    )


def _product_basis(present: bool) -> ProductDecisionBasisRefV2 | None:
    if not present:
        return None
    return ProductDecisionBasisRefV2(
        contract_version="product-decision-basis-v2",
        digest="a" * 64,
        supporting_fact_refs=("source:product:fixed-sample",),
    )


def _series_delta(present: bool) -> SeriesDeltaV1 | None:
    if not present:
        return None
    return SeriesDeltaV1(
        contract_version="series-episode-contract-v1",
        prior_episode_facts=(),
        prior_judgments=("上一篇已经给出的判断",),
        current_episode_job="完成系列第 2 篇并推进冻结主线",
        required_new_judgment="必须给出一条尚未出现过的判断",
        series_position=2,
        topic_origin="explicit_user",
    )


def _rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for profile in _profiles():
        for content_product in CONTENT_PRODUCTS:
            for topic_origin in TOPIC_ORIGINS:
                for has_basis in (False, True):
                    for has_series in (False, True):
                        rows.append(
                            _row(profile, content_product, topic_origin, has_basis, has_series)
                        )
    return rows


def _row(
    profile: SampleProfile,
    content_product: str,
    topic_origin: str,
    has_basis: bool,
    has_series: bool,
) -> dict[str, object]:
    static_payoff = product_brief(content_product, topic_origin)[1]
    request = build_payoff_request(
        content_product=content_product,
        topic_origin=topic_origin,
        account_expression=profile.expression,
        product_basis=_product_basis(has_basis),
        series_delta=_series_delta(has_series),
        static_payoff=static_payoff,
    )
    assembly = assemble_task_value(request)
    return {
        "profile_id": profile.profile_id,
        "profile_role": profile.role,
        "profile_signals": list(request.profile_signals),
        "content_product": content_product,
        "topic_origin": topic_origin,
        "product_basis_present": has_basis,
        "series_basis_present": has_series,
        "static_payoff_before": static_payoff,
        "payoff_after": assembly.audience_payoff,
        "payoff_length": len(assembly.audience_payoff),
        "payoff_origin": assembly.payoff_origin,
        "payoff_degraded": assembly.payoff_degraded,
        "payoff_degradation_reason": assembly.payoff_degradation_reason,
        "brand_relevance_path": assembly.brand_relevance_path,
        "template_id": assembly.assembly_trace.template_id,
        "used_profile_fields": list(assembly.assembly_trace.used_profile_fields),
        "unchanged_from_static": assembly.audience_payoff == static_payoff,
    }


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _summary(rows: list[dict[str, object]]) -> dict[str, object]:
    paths: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for row in rows:
        key = str(row["brand_relevance_path"] or "—")
        paths[key] = paths.get(key, 0) + 1
        if row["payoff_degraded"]:
            reason = str(row["payoff_degradation_reason"])
            reasons[reason] = reasons.get(reason, 0) + 1
    degraded = sum(1 for row in rows if row["payoff_degraded"])
    static_overlap = sum(1 for row in rows if row["unchanged_from_static"])
    return {
        "sample_count": len(rows),
        "server_assembled": len(rows) - degraded,
        "degraded": degraded,
        "degraded_rate": round(degraded / len(rows), 4),
        "static_overlap": static_overlap,
        "static_overlap_rate": round(static_overlap / len(rows), 4),
        "path_distribution": dict(sorted(paths.items())),
        "degradation_reasons": dict(sorted(reasons.items())),
    }


def _six_topic_kinds(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    kinds = (
        ("dressing_decision", "explicit_user"),
        ("product_truth", "explicit_user"),
        ("local_response", "explicit_user"),
        ("visual_styling_story", "explicit_user"),
        ("brand_life_narrative", "explicit_user"),
        ("brand_life_narrative", "system_selected"),
    )
    selected = []
    for content_product, topic_origin in kinds:
        selected.append(
            next(
                row
                for row in rows
                if row["profile_id"] == "onboarding_prefill"
                and row["content_product"] == content_product
                and row["topic_origin"] == topic_origin
                and row["product_basis_present"] is False
                and row["series_basis_present"] is False
            )
        )
    return selected


def _manifest(rows: list[dict[str, object]]) -> dict[str, object]:
    inputs = [
        {
            key: row[key]
            for key in (
                "profile_id",
                "profile_signals",
                "content_product",
                "topic_origin",
                "product_basis_present",
                "series_basis_present",
            )
        }
        for row in rows
    ]
    outputs = [
        {
            key: row[key]
            for key in (
                "payoff_after",
                "payoff_origin",
                "payoff_degraded",
                "payoff_degradation_reason",
                "brand_relevance_path",
                "template_id",
                "used_profile_fields",
            )
        }
        for row in rows
    ]
    six = _six_topic_kinds(rows)
    return {
        "base_sha": BASE_COMMIT,
        "ruleset_version": PAYOFF_RULESET_VERSION,
        "ruleset_digest": payoff_ruleset_digest(RULESET_V0),
        "onboarding_profile_source": ONBOARDING_PROFILE.relative_to(PROJECT_ROOT).as_posix(),
        "onboarding_profile_digest": hashlib.sha256(ONBOARDING_PROFILE.read_bytes()).hexdigest(),
        "production_profile_calibration": "UNVERIFIED",
        "input_digest": _digest(inputs),
        "output_digest": _digest(outputs),
        "static_payoff_defaults_count": len(static_payoff_defaults()),
        "six_topic_kinds_distinct": len({normalized_payoff(str(row["payoff_after"])) for row in six}),
        "summary": _summary(rows),
        "rows": rows,
    }


def _markdown(manifest: dict[str, object]) -> str:
    rows = list(manifest["rows"])  # type: ignore[call-overload]
    summary = manifest["summary"]
    assert isinstance(summary, dict)
    lines = [
        "# EXE-V0 · 固定样本对照",
        "",
        "> 本文件由 `scripts/exev0/build_fixed_samples.py` 确定性生成，不要手改。",
        f"> 基线 `{manifest['base_sha']}`；规则集 `{manifest['ruleset_version']}`"
        f"（digest `{str(manifest['ruleset_digest'])[:12]}…`）。",
        f"> `production_profile_calibration = {manifest['production_profile_calibration']}`"
        "：仓内没有 P0 裁决摘要，画像取自 "
        f"`{manifest['onboarding_profile_source']}`（onboarding 草案，非生效生产画像）。",
        "",
        "## 一、六个题材：改之前 / 改之后",
        "",
        "同一组画像、无商品依据、无系列时，六个题材原本共用静态查表；下表是同口径对照。",
        "",
        "| 题材 | 改之前（静态查表） | 改之后（服务端组装） | 关联路径 | 指回画像字段 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in _six_topic_kinds(rows):
        label = f"{_PRODUCT_LABELS[str(row['content_product'])]} · {_ORIGIN_LABELS[str(row['topic_origin'])]}"
        fields = "、".join(str(item) for item in row["used_profile_fields"]) or "—"
        lines.append(
            f"| {label} | {row['static_payoff_before']} | {row['payoff_after']} "
            f"| `{row['brand_relevance_path']}` | {fields} |"
        )
    lines += [
        "",
        f"六个题材规范化后互不相同：**{manifest['six_topic_kinds_distinct']} / 6**"
        "（样本验收目标，不是运行时硬门）。",
        "",
        "## 二、全样本汇总",
        "",
        f"- 样本数：{summary['sample_count']}",
        f"- 服务端组装：{summary['server_assembled']}；降级：{summary['degraded']}"
        f"（{summary['degraded_rate']:.1%}）",
        f"- 与静态默认句重合：{summary['static_overlap']}（{summary['static_overlap_rate']:.1%}）",
        f"- 路径分布：{json.dumps(summary['path_distribution'], ensure_ascii=False)}",
        f"- 降级原因分布：{json.dumps(summary['degradation_reasons'], ensure_ascii=False)}",
        "",
        "## 三、逐行样本",
        "",
        "| # | 画像 | 用途 | 题材 | 商品依据 | 系列 | 溯源 | 路径 | 降级原因 | 模板 | 回报句 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, row in enumerate(rows, start=1):
        label = f"{_PRODUCT_LABELS[str(row['content_product'])]}·{_ORIGIN_LABELS[str(row['topic_origin'])]}"
        lines.append(
            f"| {index} | `{row['profile_id']}` | {row['profile_role']} | {label} "
            f"| {'有' if row['product_basis_present'] else '无'} "
            f"| {'有' if row['series_basis_present'] else '无'} "
            f"| `{row['payoff_origin']}` | `{row['brand_relevance_path'] or '—'}` "
            f"| `{row['payoff_degradation_reason'] or '—'}` | `{row['template_id']}` "
            f"| {row['payoff_after']} |"
        )
    lines += [
        "",
        "## 四、这份对照证明不了什么",
        "",
        "- 「每篇不同」不等于「每篇都好」：回报句由版本化模板组装，表达上限就是模板的上限。",
        "- 画像只以「哪几段有内容」参与决策，原文不进入任何回报句、trace 或本文件。",
        "- 未经 P0 生产只读核查，以上画像不代表任何租户的生效画像。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    rows = _rows()
    manifest = _manifest(rows)
    report = _markdown(manifest)
    document = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if "--write" in sys.argv[1:]:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(report, encoding="utf-8")
        MANIFEST_PATH.write_text(document, encoding="utf-8")
        print(f"WROTE {REPORT_PATH.relative_to(PROJECT_ROOT)} ({len(rows)} 行样本)")
        print(f"WROTE {MANIFEST_PATH.relative_to(PROJECT_ROOT)}")
        return 0

    failures = []
    if not REPORT_PATH.exists() or REPORT_PATH.read_text(encoding="utf-8") != report:
        failures.append(f"{REPORT_PATH.name}: 与当前规则集不一致，重跑 --write")
    if not MANIFEST_PATH.exists() or MANIFEST_PATH.read_text(encoding="utf-8") != document:
        failures.append(f"{MANIFEST_PATH.name}: 与当前规则集不一致，重跑 --write")
    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    print(f"PASS fixed samples reproduce byte-for-byte ({len(rows)} 行；output digest {manifest['output_digest'][:12]}…)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
