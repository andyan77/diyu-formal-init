from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import cast

from src.shared.errors import DomainError
from src.tool.record_formal_capability_observations import _registry_ids

_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _dictionary(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DomainError(message)
    return cast(dict[str, object], value)


def _list(value: object, message: str) -> list[object]:
    if not isinstance(value, list):
        raise DomainError(message)
    return cast(list[object], value)


def _text(value: object, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainError(message)
    return value.strip()


def _markdown_text(value: object, message: str) -> str:
    return _text(value, message).replace("|", "\\|").replace("\n", " ")


def _state_label(value: object) -> str:
    labels = {
        "satisfied": "满足",
        "partial": "部分满足",
        "missing": "缺失",
        "not_required": "无需资料",
        "granted": "已获权",
        "not_granted": "未获权",
        "not_applicable": "不适用",
    }
    text = _text(value, "说明书状态无效")
    if text not in labels:
        raise DomainError("说明书状态不在正式枚举内")
    return labels[text]


def validate_readiness_document(
    document: object,
    *,
    candidate_sha: str,
    schema_revision: str,
) -> tuple[dict[str, object], dict[str, object]]:
    readiness = _dictionary(document, "说明书真值必须来自正式 readiness JSON")
    matrix = _dictionary(readiness.get("capability_matrix"), "说明书缺少四列能力矩阵")
    guide = _dictionary(readiness.get("usage_guide"), "说明书缺少共享使用说明真值")
    if (
        not _SHA_PATTERN.fullmatch(candidate_sha)
        or matrix.get("runtime_sha") != candidate_sha
        or matrix.get("schema_revision") != schema_revision
    ):
        raise DomainError("说明书 readiness 与运行 SHA 或 schema 不一致")
    generated_at = _text(matrix.get("generated_at"), "说明书缺少真值生成时间")
    try:
        datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DomainError("说明书真值生成时间无效") from exc
    items = [
        _dictionary(value, "说明书能力条目无效")
        for value in _list(matrix.get("items"), "说明书能力矩阵无效")
    ]
    identifiers = tuple(_text(item.get("id"), "说明书能力 ID 缺失") for item in items)
    if identifiers != _registry_ids():
        raise DomainError("说明书必须按注册表顺序逐项覆盖 58 项正式支持面")
    counts = _dictionary(guide.get("current_counts"), "说明书缺少当前租户数量")
    required_counts = {
        "source_documents": 21,
        "authorized_source_documents": 19,
        "template_documents": 2,
        "source_segments": 5046,
        "active_products": 14,
        "allowed_product_fact_fields": 26,
    }
    if any(counts.get(key) != expected for key, expected in required_counts.items()):
        raise DomainError("说明书来源、商品或 ProductFact 数量与正式真值不一致")
    products = _list(guide.get("product_fact_readiness"), "说明书缺少按 SKU 的 P2 清单")
    if len(products) != 14:
        raise DomainError("说明书必须逐项覆盖 14 个正式候选商品")
    gaps = [
        _dictionary(value, "说明书资料缺口无效")
        for value in _list(guide.get("data_missing"), "说明书缺少资料缺口")
    ]
    if {
        _text(item.get("id"), "说明书资料缺口 ID 缺失")
        for item in gaps
        if item.get("missing") is True
    } != {"P4", "P5", "DM01"}:
        raise DomainError("说明书必须如实保留 P4、P5、DM01 data_missing")
    return matrix, guide


def render_usage_guide(
    document: object,
    *,
    candidate_sha: str,
    schema_revision: str,
    readiness_sha256: str,
) -> str:
    matrix, guide = validate_readiness_document(
        document,
        candidate_sha=candidate_sha,
        schema_revision=schema_revision,
    )
    summary = _dictionary(matrix.get("summary"), "说明书能力汇总无效")
    lines = [
        "# 笛语服饰使用说明与能力就绪清单",
        "",
        f"- 生成时间：`{_text(matrix['generated_at'], '生成时间缺失')}`",
        f"- 运行 SHA：`{candidate_sha}`",
        f"- Schema：`{schema_revision}`",
        f"- Readiness JSON SHA-256：`{readiness_sha256}`",
        "- 真值来源：正式 API、当前租户 PostgreSQL 业务对象与权限、同一候选追加式正式实测观察。",
        "- 边界：软件生成、修改、复制和导出；采用与发布由用户完成，系统不自动发布。",
        "",
        "## 三种身份",
        "",
    ]
    lines.extend(
        f"- {_text(value, '身份说明无效')}"
        for value in _list(guide.get("identity_model"), "说明书身份说明缺失")
    )
    lines.extend(
        [
            "",
            f"身份关系：{_text(guide.get('relationship'), '身份关系缺失')}。",
            "",
            "## 发送与生成内容",
            "",
        ]
    )
    send_vs_generate = _dictionary(guide.get("send_vs_generate"), "发送与生成说明缺失")
    lines.extend(
        [
            f"- 发送：{_text(send_vs_generate.get('send'), '发送说明缺失')}",
            f"- 生成内容：{_text(send_vs_generate.get('generate'), '生成说明缺失')}",
            "",
            "## 管理员从零建立成员",
            "",
        ]
    )
    lines.extend(
        f"{index}. {_text(value, '管理员步骤无效')}"
        for index, value in enumerate(
            _list(guide.get("administrator_steps"), "管理员步骤缺失"), start=1
        )
    )
    lines.extend(["", "成员示例："])
    lines.extend(
        f"- {_text(value, '成员示例无效')}"
        for value in _list(guide.get("named_member_examples"), "成员示例缺失")
    )
    counts = _dictionary(guide.get("current_counts"), "当前数量缺失")
    lines.extend(
        [
            "",
            "## 当前租户资料真值",
            "",
            "| 指标 | 当前数量 |",
            "|---|---:|",
        ]
    )
    count_labels = {
        "source_documents": "来源文档总数",
        "authorized_source_documents": "品牌已授权来源文档",
        "template_documents": "模板资料",
        "source_segments": "不可变来源 segment",
        "publication_version": "当前正式发布投影版本",
        "publication_items": "当前正式发布投影条目",
        "formal_users": "正式用户",
        "content_users": "正式内容用户",
        "logical_accounts": "逻辑发布账号",
        "platform_targets": "平台和形式目标",
        "profile_accounts": "完整五段画像账号",
        "active_products": "品牌授权候选商品",
        "allowed_product_fact_fields": "可进入 ProductFact 的字段",
        "organization_media": "组织官方素材",
        "product_media_products": "具备媒体绑定的商品",
        "confirmed_stores": "正式门店",
        "formal_inventory_snapshots": "正式库存快照",
    }
    for key, label in count_labels.items():
        value = counts.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            raise DomainError(f"说明书数量 {key} 无效")
        lines.append(f"| {label} | {value} |")

    lines.extend(
        [
            "",
            "## 58 项正式支持面四列真值",
            "",
            (
                "注册表共 58 项；这里的 58 只表示软件支持面，不代表当前品牌资料、本人权限或正式实测全部满足。"
            ),
            "",
            (
                f"汇总：软件实现 {summary.get('implemented')}；资料满足或无需资料 "
                f"{summary.get('data_satisfied')}；当前身份获权 {summary.get('permission_granted')}；"
                f"同一候选正式实测 {summary.get('formally_tested')}。"
            ),
            "",
            "| ID | 能力 | 软件实现 | 当前资料 | 当前身份权限 | 正式实测 | 补充入口 |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for item in cast(list[dict[str, object]], matrix["items"]):
        lines.append(
            "| {id} | {title} | {software} | {data} | {permission} | {tested} | {href} |".format(
                id=_markdown_text(item.get("id"), "能力 ID 缺失"),
                title=_markdown_text(item.get("title"), "能力标题缺失"),
                software="已实现" if item.get("software_implemented") is True else "未实现",
                data=_state_label(item.get("data_state")),
                permission=_state_label(item.get("permission_state")),
                tested="已实测" if item.get("formally_tested") is True else "尚未实测",
                href=_markdown_text(item.get("supplement_href"), "补充入口缺失"),
            )
        )

    lines.extend(["", "## P2：按 SKU 的商品事实边界", ""])
    for raw_product in _list(guide.get("product_fact_readiness"), "P2 清单缺失"):
        product = _dictionary(raw_product, "P2 商品条目无效")
        lines.extend(
            [
                f"### {_markdown_text(product.get('sku'), 'SKU 缺失')} · {_markdown_text(product.get('display_name'), '商品名称缺失')}",
                "",
                f"- 能做：{_text(product.get('can_do'), '商品可做边界缺失')}",
                "- 当前可用事实：",
            ]
        )
        facts = _list(product.get("current_facts"), "商品事实清单无效")
        if not facts:
            lines.append("  - 无")
        for raw_fact in facts:
            fact = _dictionary(raw_fact, "商品事实条目无效")
            lines.append(
                f"  - {_text(fact.get('field'), '商品事实字段缺失')}：{_text(fact.get('value'), '商品事实值缺失')}"
            )
        missing = [
            _text(value, "商品缺失字段无效")
            for value in _list(product.get("missing_fields"), "商品缺失字段清单无效")
        ]
        lines.extend(
            [
                f"- 尚缺字段：{'、'.join(missing) if missing else '无'}",
                f"- 不能承诺：{_text(product.get('cannot_promise'), '商品不可承诺边界缺失')}",
                "",
            ]
        )

    lines.extend(["## 当前资料不足", ""])
    for raw_gap in _list(guide.get("data_missing"), "资料缺口清单缺失"):
        gap = _dictionary(raw_gap, "资料缺口条目无效")
        if gap.get("missing") is True:
            lines.append(
                f"- **{_text(gap.get('id'), '资料缺口 ID 缺失')} `data_missing`**："
                f"{_text(gap.get('message'), '资料缺口说明缺失')} 补充入口："
                f"`{_text(gap.get('supplement_href'), '资料补充入口缺失')}`。"
            )

    lines.extend(["", "## 一次性陈述、可复用事实与常见错误", ""])
    lines.extend(
        f"- {_text(value, '事实边界说明无效')}"
        for value in _list(guide.get("truth_boundaries"), "事实边界缺失")
    )
    lines.extend(["", "| 错误码 | 含义与处理 |", "|---|---|"])
    for raw_error in _list(guide.get("common_errors"), "常见错误缺失"):
        error = _dictionary(raw_error, "常见错误条目无效")
        lines.append(
            f"| `{_markdown_text(error.get('code'), '错误码缺失')}` | "
            f"{_markdown_text(error.get('meaning'), '错误处理缺失')} |"
        )
    lines.extend(
        [
            "",
            "## 当前尚未证明",
            "",
            "- P4：没有正式门店事实，不能证明可复用的门店内容生产。",
            "- P5：没有正式商品图片、视频及商品绑定，不能证明商品视觉成品生产。",
            "- DM01：没有正式门店和库存，不能证明正式陈列参考方案生产。",
            "- 不证明正式员工长期采用、真实发布、流量、排名、GMV 或经营效果。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render the authoritative TENANT-01 usage/readiness guide from live truth."
    )
    parser.add_argument("--readiness", required=True, type=Path)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--schema-revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    readiness_path = args.readiness.resolve(strict=True)
    readiness_bytes = readiness_path.read_bytes()
    try:
        document = json.loads(readiness_bytes)
    except json.JSONDecodeError as exc:
        raise DomainError("说明书 readiness 不是有效 JSON") from exc
    rendered = render_usage_guide(
        document,
        candidate_sha=args.candidate_sha,
        schema_revision=args.schema_revision,
        readiness_sha256=hashlib.sha256(readiness_bytes).hexdigest(),
    )
    output = args.output.resolve()
    if output.exists():
        raise DomainError("说明书已存在，拒绝静默覆盖")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "verdict": "PASS",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
