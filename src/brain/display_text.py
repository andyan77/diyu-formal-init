from __future__ import annotations

from typing import cast

from src.shared.types import DisplayContext

_POSITION_TEXT = {"left": "左侧", "center": "中间", "right": "右侧"}


def compile_display_body(context: DisplayContext, plan: dict[str, object], revision: bool) -> str:
    mounted = cast(dict[str, int], plan["mounted"])
    unmounted = cast(dict[str, int], plan["unmounted"])
    conservation = cast(dict[str, dict[str, int]], plan["inventory_conservation"])
    layout = cast(dict[str, object], plan["layout"])
    zones = cast(dict[str, dict[str, object]], layout["zones"])
    total_mounted, total_unmounted = sum(mounted.values()), sum(unmounted.values())
    position_names = " → ".join(_POSITION_TEXT[item] for item in cast(list[str], layout["reading_order"]))
    change = f"{layout['revision_note']}\n\n" if revision else ""
    sections = [
        f"适用范围：{context.brand_name}｜{context.store_name}｜{context.organization_name}。",
        f"主题：{layout['theme']}。密度：{layout['density']}；只做一个主焦点和最多一个较弱回应。",
        (
            f"本次任务库存共 {total_mounted + total_unmounted} 件；建议 {total_mounted} 件上墙，"
            f"{total_unmounted} 件不上墙。上杆、下杆分别不超过 "
            f"{cast(dict[str, int], layout['capacities'])['upper']} / "
            f"{cast(dict[str, int], layout['capacities'])['lower']} 件舒适容量。"
        ),
        f"来客主要阅读顺序：{position_names}。黄金视线：{layout['golden_sight']}。",
        "顾客面对墙，按物理位置执行：",
    ]
    for position in cast(list[str], layout["physical_order"]):
        zone = zones[position]
        role = {
            "primary_focus": "主焦点",
            "neutral": "中性承接",
            "secondary_response": "较弱回应",
        }[str(zone["role"])]
        sections.append(
            f"{_POSITION_TEXT[position]}（{role}）：上杆 {_rail_text(zone['upper'])}；"
            f"下杆 {_rail_text(zone['lower'])}。"
        )
    blocked_lower = set(cast(list[str], layout["blocked_lower_positions"]))
    if blocked_lower:
        sections.append(
            "下杆留空："
            + "、".join(
                _POSITION_TEXT[position]
                for position in cast(list[str], layout["physical_order"])
                if position in blocked_lower
            )
            + "；用于避开长款上下重叠、立柱影响或保留补货操作空间。"
        )
    if str(cast(dict[str, object], layout["focus_contract"]).get("focus_source")) == "system_narrowed":
        sections.append("本次输入建议的焦点商品这次不可用，系统已在当前商品里重新选择主焦点。")
    hard_requirements = cast(list[str], plan.get("hard_requirements", []))
    if hard_requirements:
        sections.append(
            "本次明确要求保留："
            + "、".join(f"{_product_label(context, sku)}（{sku}）" for sku in hard_requirements)
            + "；这些商品已按本次库存进入方案与逐项对账。"
        )
    sections.extend(
        [
            "逐商品库存对账："
            + "；".join(
                f"{_product_label(context, sku)}（{sku}）{proof['input']} 件"
                f" = 上墙 {proof['displayed']} 件 + 不上墙 {proof['undisplayed']} 件"
                for sku, proof in conservation.items()
            )
            + "。",
            f"正挂、侧挂与间距：{layout['spacing']}",
            f"替代与收窄：{layout['substitution']}",
            "不上墙："
            + "、".join(
                f"{_product_label(context, sku)}（{sku}）×{amount}" for sku, amount in unmounted.items() if amount > 0
            )
            + "。这些仍属于本次任务库存，不表示缺货或不可销售。",
        ]
    )
    undescribed = [sku for sku in cast(list[str], layout.get("undescribed_skus", [])) if unmounted.get(sku, 0) > 0]
    if undescribed:
        sections.append(
            "本次没有陈列资料的商品：" + "、".join(undescribed) + "；它们只计入库存对账，没有进入上墙分配。"
        )
    sections.extend(
        [
            "现场硬限制：" + "；".join(cast(list[str], layout["constraints"])) + "。",
            "执行步骤："
            + " ".join(
                f"{index}. {step}" for index, step in enumerate(cast(list[str], layout["execution_steps"]), start=1)
            ),
            "这是根据本次库存和现场条件整理的文字参考方案。",
        ]
    )
    return f"{context.store_name}墙面挂杆参考执行方案\n\n" + change + "\n\n".join(sections)


def _rail_text(value: object) -> str:
    slots = cast(list[dict[str, object]], value)
    if not slots:
        return "明确留空"
    parts = []
    for slot in slots:
        mount = {
            "front_facing": "正挂",
            "front_facing_layered": "与本组主件叠穿同一正挂",
            "side_hang": "侧挂",
        }[str(slot["mount"])]
        parts.append(f"{slot['label']}（{slot['sku']}）×{slot['quantity']}（{mount}）")
    return "、".join(parts)


def _product_label(context: DisplayContext, sku: str) -> str:
    facts = dict(context.products).get(sku, {})
    name = facts.get("name")
    return str(name) if isinstance(name, str) and name else sku
