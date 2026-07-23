from __future__ import annotations

from typing import cast

from src.shared.types import DisplayContext


def compile_display_body(context: DisplayContext, plan: dict[str, object], revision: bool) -> str:
    mounted = cast(dict[str, int], plan["mounted"])
    unmounted = cast(dict[str, int], plan["unmounted"])
    layout = cast(dict[str, object], plan["layout"])
    zones = cast(dict[str, dict[str, object]], layout["zones"])
    total_mounted, total_unmounted = sum(mounted.values()), sum(unmounted.values())
    change = (
        "本次只改 C 区上杆的 ZX-V113；其余搭配区、下杆、主次焦点和左右动线继承上一版。\n\n"
        if revision
        else ""
    )
    sections = [
        f"本次人工库存共 {total_mounted + total_unmounted} 件；选择 {total_mounted} 件上墙，{total_unmounted} 件不上墙。容量是上限，先保证看见、抽取和复位。",
        "顾客面对墙，从左到右执行：",
    ]
    for zone_id in cast(list[str], layout["order"]):
        zone = zones[zone_id]
        role = {
            "primary_focus": "主焦点",
            "neutral": "中间基础区",
            "secondary_response": "较弱回应",
        }[str(zone["role"])]
        sections.append(
            f"{zone_id} 区（{role}）：上杆 {_rail_text(zone['upper'])}；下杆 {_rail_text(zone['lower'])}。"
        )
    c_upper = cast(list[dict[str, object]], zones["C"]["upper"])
    if not any(slot["sku"] == "ZX-C218" and slot["mount"] == "front_facing" for slot in c_upper):
        sections.append("本次 ZX-C218 只剩一件：保留左侧主焦点，取消同款右侧回应。")
    sections.extend(
        [
            "正挂、侧挂与间距：主焦点与较弱回应均使用上杆正挂；侧挂按各区保留约一个衣架宽的停顿，优先保证单手可抽取。",
            "替代：已上墙商品临时不能使用时，优先用本次未上墙同款；若同款只剩一件，保留左侧主焦点并取消右侧同款回应。衣袖或厚度挤压时，先减少受影响位置侧挂。",
            "执行步骤：1. 按上墙与未上墙数量分开商品。2. 先完成 A 区主正挂，再完成 C 区较弱回应。3. 依次按 A、B、C 的上杆和下杆摆放。4. 统一衣架方向并确认每件可抽取。",
            "这是一份内部执行建议，不表示总部批准、系统核验或门店已经完成。",
        ]
    )
    return "内部执行建议\n\n" + change + "\n\n".join(sections)


def _rail_text(value: object) -> str:
    slots = cast(list[dict[str, object]], value)
    parts = []
    for slot in slots:
        mount = "正挂" if slot["mount"] == "front_facing" else "侧挂"
        parts.append(f"{slot['sku']} ×{slot['quantity']}（{mount}）")
    return "、".join(parts)
