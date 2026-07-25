from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import cast

from src.shared.errors import GenerationFailed
from src.shared.types import GeneratedDisplayArtifact

_POSITIONS = ("left", "center", "right")


def assert_display_complete(
    artifact: GeneratedDisplayArtifact,
    inventory: tuple[tuple[str, int], ...],
    revision: bool = False,
) -> None:
    del revision
    plan = artifact.plan
    mounted, unmounted, layout = plan.get("mounted"), plan.get("unmounted"), plan.get("layout")
    if not isinstance(mounted, dict) or not isinstance(unmounted, dict) or not isinstance(layout, dict):
        raise GenerationFailed("陈列方案结构不完整")
    available = dict(inventory)
    _assert_quantities(mounted, unmounted, available)
    placed, rail_totals = _placed_quantities(layout, available)
    if dict(placed) != mounted:
        raise GenerationFailed("上墙数量必须由上下挂杆槽位唯一聚合")
    capacities = layout.get("capacities")
    if not isinstance(capacities, dict):
        raise GenerationFailed("陈列方案缺少上下杆舒适容量")
    for rail in ("upper", "lower"):
        capacity = capacities.get(rail)
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise GenerationFailed("陈列方案容量必须是正整数")
        if rail_totals[rail] > capacity:
            raise GenerationFailed("陈列方案超过已确认的舒适容量")
    _assert_focus(layout)


def assert_display_revision(prior_plan: dict[str, object], current_plan: dict[str, object]) -> None:
    """Require one local one-item reduction while every unaffected field remains byte-equivalent."""
    prior_mounted = _string_int_dict(prior_plan.get("mounted"), "上一版上墙数量")
    current_mounted = _string_int_dict(current_plan.get("mounted"), "当前上墙数量")
    prior_unmounted = _string_int_dict(prior_plan.get("unmounted"), "上一版不上墙数量")
    current_unmounted = _string_int_dict(current_plan.get("unmounted"), "当前不上墙数量")
    if set(prior_mounted) != set(current_mounted) or set(prior_unmounted) != set(current_unmounted):
        raise GenerationFailed("修订方案不能切换本次商品范围")
    reduced = [
        sku
        for sku in prior_mounted
        if (
            current_mounted[sku] - prior_mounted[sku],
            current_unmounted[sku] - prior_unmounted[sku],
        )
        == (-1, 1)
    ]
    unchanged = [
        sku
        for sku in prior_mounted
        if current_mounted[sku] == prior_mounted[sku] and current_unmounted[sku] == prior_unmounted[sku]
    ]
    if len(reduced) != 1 or len(unchanged) != len(prior_mounted) - 1:
        raise GenerationFailed("修订只能减少一个明确位置的一件商品")

    prior_layout = _layout(prior_plan.get("layout"), "上一版布局")
    current_layout = _layout(current_plan.get("layout"), "当前布局")
    prior_base = deepcopy(prior_layout)
    current_base = deepcopy(current_layout)
    prior_zones = cast(dict[str, dict[str, object]], prior_base.pop("zones"))
    current_zones = cast(dict[str, dict[str, object]], current_base.pop("zones"))
    current_base.pop("revision_note", None)
    prior_base.pop("revision_note", None)
    if prior_base != current_base:
        raise GenerationFailed("修订不能改变现场条件、焦点、动线或执行合同")
    changed_rails = 0
    for position in _POSITIONS:
        prior_zone = deepcopy(prior_zones[position])
        current_zone = deepcopy(current_zones[position])
        for rail in ("upper", "lower"):
            prior_slots = prior_zone.pop(rail)
            current_slots = current_zone.pop(rail)
            if prior_slots != current_slots:
                if not _is_one_slot_reduction(prior_slots, current_slots, reduced[0]):
                    raise GenerationFailed("修订只能减少反馈所指挂杆的一件商品")
                changed_rails += 1
        if prior_zone != current_zone:
            raise GenerationFailed("修订不能改变未受影响区域角色")
    if changed_rails != 1:
        raise GenerationFailed("修订必须且只能改变一个明确挂杆")
    note = current_layout.get("revision_note")
    if not isinstance(note, str) or not note.strip():
        raise GenerationFailed("修订必须自然说明本次局部变化")


def _assert_quantities(
    mounted: dict[object, object],
    unmounted: dict[object, object],
    available: dict[str, int],
) -> None:
    if set(mounted) != set(available) or set(unmounted) != set(available):
        raise GenerationFailed("陈列方案包含不在本次清单中的商品")
    for sku, amount in available.items():
        if not isinstance(mounted[sku], int) or not isinstance(unmounted[sku], int):
            raise GenerationFailed("陈列方案数量必须是整数")
        mounted_count = cast(int, mounted[sku])
        unmounted_count = cast(int, unmounted[sku])
        if mounted_count < 0 or unmounted_count < 0 or mounted_count + unmounted_count != amount:
            raise GenerationFailed("陈列方案数量无法与本次清单对账")


def _placed_quantities(
    layout: dict[object, object],
    available: dict[str, int],
) -> tuple[Counter[str], dict[str, int]]:
    order, reading_order, zones = (
        layout.get("physical_order"),
        layout.get("reading_order"),
        layout.get("zones"),
    )
    if order != list(_POSITIONS) or not isinstance(reading_order, list) or set(reading_order) != set(_POSITIONS):
        raise GenerationFailed("陈列方案必须明确左右物理顺序和来客阅读顺序")
    if not isinstance(zones, dict) or set(zones) != set(_POSITIONS):
        raise GenerationFailed("陈列方案必须明确左、中、右区域")
    placed: Counter[str] = Counter()
    rail_totals = {"upper": 0, "lower": 0}
    for position in _POSITIONS:
        zone = zones[position]
        if not isinstance(zone, dict) or zone.get("role") not in {
            "primary_focus",
            "neutral",
            "secondary_response",
        }:
            raise GenerationFailed("陈列方案缺少焦点角色")
        for rail in ("upper", "lower"):
            slots = zone.get(rail)
            if not isinstance(slots, list):
                raise GenerationFailed("陈列方案必须显式说明每区上下挂杆")
            for slot in slots:
                if not isinstance(slot, dict):
                    raise GenerationFailed("陈列槽位无效")
                sku, label, quantity, mount = (
                    slot.get("sku"),
                    slot.get("label"),
                    slot.get("quantity"),
                    slot.get("mount"),
                )
                if (
                    not isinstance(sku, str)
                    or sku not in available
                    or not isinstance(label, str)
                    or not label.strip()
                    or not isinstance(quantity, int)
                    or isinstance(quantity, bool)
                    or quantity < 1
                ):
                    raise GenerationFailed("陈列槽位商品、名称或数量无效")
                if mount not in {"front_facing", "front_facing_layered", "side_hang"}:
                    raise GenerationFailed("陈列槽位缺少正挂或侧挂表达")
                placed[sku] += quantity
                rail_totals[rail] += quantity
    if rail_totals["upper"] < 1 or rail_totals["lower"] < 1:
        raise GenerationFailed("双层挂杆方案必须同时明确上杆与下杆")
    return placed, rail_totals


def _assert_focus(layout: dict[object, object]) -> None:
    zones = cast(dict[str, dict[str, object]], layout["zones"])
    primary_position = layout.get("primary_position")
    secondary_position = layout.get("secondary_position")
    focus = layout.get("focus_contract")
    if primary_position not in _POSITIONS or secondary_position not in _POSITIONS or not isinstance(focus, dict):
        raise GenerationFailed("陈列方案缺少主次焦点位置")
    primary_skus = focus.get("primary_skus")
    secondary_skus = focus.get("secondary_skus")
    secondary_present = focus.get("secondary_present")
    if (
        not isinstance(primary_skus, list)
        or not primary_skus
        or not all(isinstance(item, str) for item in primary_skus)
        or not isinstance(secondary_skus, list)
        or not all(isinstance(item, str) for item in secondary_skus)
        or not isinstance(secondary_present, bool)
    ):
        raise GenerationFailed("陈列方案主次焦点商品无效")
    if zones[primary_position]["role"] != "primary_focus":
        raise GenerationFailed("主焦点角色与固定位置不一致")
    primary_front = _front_skus(zones[primary_position]["upper"])
    if not set(cast(list[str], primary_skus)) <= primary_front:
        raise GenerationFailed("业务指定主焦点没有进入固定上杆正挂")
    secondary_front = _front_skus(zones[secondary_position]["upper"])
    if secondary_present and not set(cast(list[str], secondary_skus)) <= secondary_front:
        raise GenerationFailed("较弱回应没有进入固定上杆正挂")
    fixed_front_count = sum(
        1
        for zone in zones.values()
        for slot in cast(list[dict[str, object]], zone["upper"])
        if slot.get("mount") == "front_facing"
    )
    if fixed_front_count != (2 if secondary_present else 1):
        raise GenerationFailed("方案使用的固定正挂点数量与主次焦点不一致")


def _front_skus(value: object) -> set[str]:
    if not isinstance(value, list):
        raise GenerationFailed("上杆槽位无效")
    return {
        str(slot["sku"])
        for slot in cast(list[dict[str, object]], value)
        if slot.get("mount") in {"front_facing", "front_facing_layered"}
    }


def _string_int_dict(value: object, label: str) -> dict[str, int]:
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or not isinstance(amount, int) for key, amount in value.items()
    ):
        raise GenerationFailed(f"{label}无效")
    return cast(dict[str, int], value)


def _layout(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not isinstance(value.get("zones"), dict):
        raise GenerationFailed(f"{label}无效")
    zones = cast(dict[object, object], value["zones"])
    if set(zones) != set(_POSITIONS) or any(not isinstance(zone, dict) for zone in zones.values()):
        raise GenerationFailed(f"{label}缺少左、中、右区域")
    return cast(dict[str, object], value)


def _is_one_slot_reduction(prior: object, current: object, sku: str) -> bool:
    if not isinstance(prior, list) or not isinstance(current, list):
        return False
    prior_slots = cast(list[dict[str, object]], prior)
    current_slots = cast(list[dict[str, object]], current)

    def quantities(slots: list[dict[str, object]]) -> Counter[tuple[str, str, str]]:
        return Counter(
            {
                (str(slot.get("sku")), str(slot.get("label")), str(slot.get("mount"))): cast(int, slot.get("quantity"))
                for slot in slots
            }
        )

    before, after = quantities(prior_slots), quantities(current_slots)
    keys = set(before) | set(after)
    deltas = {key: after[key] - before[key] for key in keys if after[key] != before[key]}
    return len(deltas) == 1 and next(iter(deltas.items()))[0][0] == sku and next(iter(deltas.values())) == -1
