from __future__ import annotations

from typing import cast

from src.shared.types import DisplayContext

_POSITION_TEXT = {"left": "左侧", "center": "中间", "right": "右侧"}


def compile_display_body(context: DisplayContext, plan: dict[str, object], revision: bool) -> str:
    mounted = cast(dict[str, int], plan["mounted"])
    unmounted = cast(dict[str, int], plan["unmounted"])
    layout = cast(dict[str, object], plan["layout"])
    zones = cast(dict[str, dict[str, object]], layout["zones"])
    total_mounted, total_unmounted = sum(mounted.values()), sum(unmounted.values())
    position_names = " → ".join(_POSITION_TEXT[item] for item in cast(list[str], layout["reading_order"]))
    confirmation = context.rail_profile.get("confirmation")
    confirmed_at = ""
    if isinstance(confirmation, dict) and isinstance(confirmation.get("confirmed_at"), str):
        confirmed_at = f"，现场确认日期 {confirmation['confirmed_at']}"
    change = f"{layout['revision_note']}\n\n" if revision else ""
    sections = [
        (
            f"适用范围：{context.brand_name}｜{context.store_name}｜{context.organization_name}；"
            f"现场执行人 {context.operator_name}，系统代录人 {context.submitter_name}{confirmed_at}。"
        ),
        f"主题：{layout['theme']}。密度：{layout['density']}；只做一个主焦点和最多一个较弱回应。",
        (
            f"本次人工库存共 {total_mounted + total_unmounted} 件；选择 {total_mounted} 件上墙，"
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
    sections.extend(
        [
            f"正挂、侧挂与间距：{layout['spacing']}",
            f"替代与收窄：{layout['substitution']}",
            "不上墙："
            + "、".join(
                f"{_product_label(context, sku)}（{sku}）×{amount}" for sku, amount in unmounted.items() if amount > 0
            )
            + "。这些仍属于本次人工库存，不表示缺货或不可销售。",
            "现场硬限制：" + "；".join(cast(list[str], layout["constraints"])) + "。",
            "执行步骤："
            + " ".join(
                f"{index}. {step}" for index, step in enumerate(cast(list[str], layout["execution_steps"]), start=1)
            ),
            "这是一份内部执行建议，不表示总部批准、系统核验库存或门店已经执行。",
        ]
    )
    return "内部执行建议\n\n" + change + "\n\n".join(sections)


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
    facts = dict(context.products)[sku]
    name = facts.get("name")
    return str(name) if isinstance(name, str) and name else sku
