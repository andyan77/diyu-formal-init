from __future__ import annotations

from collections import Counter
from typing import cast

from src.shared.errors import GenerationFailed
from src.shared.types import GeneratedDisplayArtifact

_GOLD_INVENTORY = {
    "ZX-C218": 3,
    "ZX-S104": 3,
    "ZX-K126": 4,
    "ZX-P211": 3,
    "ZX-V113": 3,
    "ZX-Q117": 4,
}
_GOLD_V1 = {"ZX-C218": 2, "ZX-S104": 2, "ZX-K126": 2, "ZX-P211": 3, "ZX-V113": 2, "ZX-Q117": 4}


def assert_display_complete(
    artifact: GeneratedDisplayArtifact,
    inventory: tuple[tuple[str, int], ...],
    revision: bool = False,
) -> None:
    plan = artifact.plan
    mounted, unmounted, layout = plan.get("mounted"), plan.get("unmounted"), plan.get("layout")
    if (
        not isinstance(mounted, dict)
        or not isinstance(unmounted, dict)
        or not isinstance(layout, dict)
    ):
        raise GenerationFailed("陈列方案结构不完整")
    available = dict(inventory)
    _assert_quantities(mounted, unmounted, available)
    placed = _placed_quantities(layout, available)
    if dict(placed) != mounted:
        raise GenerationFailed("上墙数量必须由上下挂杆槽位唯一聚合")
    if available == _GOLD_INVENTORY:
        _assert_gold_layout(layout, mounted, unmounted, revision)


def assert_display_revision(prior_plan: dict[str, object], current_plan: dict[str, object]) -> None:
    """The only frozen revision is one C-upper ZX-V113 side-hang reduction."""
    prior_mounted = prior_plan.get("mounted")
    current_mounted = current_plan.get("mounted")
    prior_unmounted = prior_plan.get("unmounted")
    current_unmounted = current_plan.get("unmounted")
    prior_layout = prior_plan.get("layout")
    current_layout = current_plan.get("layout")
    if (
        not isinstance(prior_mounted, dict)
        or not isinstance(current_mounted, dict)
        or not isinstance(prior_unmounted, dict)
        or not isinstance(current_unmounted, dict)
        or not isinstance(prior_layout, dict)
        or not isinstance(current_layout, dict)
    ):
        raise GenerationFailed("修订方案缺少可继承的结构")
    prior_mounted_values = cast(dict[str, int], prior_mounted)
    current_mounted_values = cast(dict[str, int], current_mounted)
    prior_unmounted_values = cast(dict[str, int], prior_unmounted)
    current_unmounted_values = cast(dict[str, int], current_unmounted)
    prior_layout_values = cast(dict[str, object], prior_layout)
    current_layout_values = cast(dict[str, object], current_layout)
    if set(prior_mounted_values) != set(current_mounted_values) or set(prior_unmounted_values) != set(
        current_unmounted_values
    ):
        raise GenerationFailed("修订方案不能切换本次商品范围")
    for sku in prior_mounted_values:
        mounted_delta = current_mounted_values[sku] - prior_mounted_values[sku]
        unmounted_delta = current_unmounted_values[sku] - prior_unmounted_values[sku]
        expected = (-1, 1) if sku == "ZX-V113" else (0, 0)
        if (mounted_delta, unmounted_delta) != expected:
            raise GenerationFailed("冻结修订只能减少 C 区上杆一件 ZX-V113")
    prior_zones = prior_layout_values.get("zones")
    current_zones = current_layout_values.get("zones")
    if not isinstance(prior_zones, dict) or not isinstance(current_zones, dict):
        raise GenerationFailed("修订方案缺少搭配区")
    if any(prior_zones[zone] != current_zones[zone] for zone in ("A", "B")):
        raise GenerationFailed("冻结修订不能改变 A/B 区")
    prior_c, current_c = prior_zones.get("C"), current_zones.get("C")
    if not isinstance(prior_c, dict) or not isinstance(current_c, dict):
        raise GenerationFailed("修订方案缺少 C 区")
    if prior_c.get("role") != current_c.get("role") or prior_c.get("lower") != current_c.get("lower"):
        raise GenerationFailed("冻结修订不能改变 C 区下杆或角色")
    if _rail_quantities(prior_c.get("upper")) != {"ZX-C218": 1, "ZX-V113": 2} or _rail_quantities(
        current_c.get("upper")
    ) != {"ZX-C218": 1, "ZX-V113": 1}:
        raise GenerationFailed("冻结修订必须只减少 C 区上杆一件 ZX-V113")


def _assert_quantities(
    mounted: dict[object, object], unmounted: dict[object, object], available: dict[str, int]
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


def _placed_quantities(layout: dict[object, object], available: dict[str, int]) -> Counter[str]:
    order, zones = layout.get("order"), layout.get("zones")
    if order != ["A", "B", "C"] or not isinstance(zones, dict) or set(zones) != {"A", "B", "C"}:
        raise GenerationFailed("陈列方案必须明确 A/B/C 左右顺序")
    placed: Counter[str] = Counter()
    for zone_id in ("A", "B", "C"):
        zone = zones[zone_id]
        if not isinstance(zone, dict) or zone.get("role") not in {
            "primary_focus",
            "neutral",
            "secondary_response",
        }:
            raise GenerationFailed("陈列方案缺少焦点角色")
        for rail in ("upper", "lower"):
            slots = zone.get(rail)
            if not isinstance(slots, list) or not slots:
                raise GenerationFailed("陈列方案必须明确每区上下挂杆")
            for slot in slots:
                if not isinstance(slot, dict):
                    raise GenerationFailed("陈列槽位无效")
                sku, quantity, mount = slot.get("sku"), slot.get("quantity"), slot.get("mount")
                if (
                    not isinstance(sku, str)
                    or sku not in available
                    or not isinstance(quantity, int)
                    or quantity < 1
                ):
                    raise GenerationFailed("陈列槽位商品或数量无效")
                if mount not in {"front_facing", "side_hang"}:
                    raise GenerationFailed("陈列槽位缺少正挂或侧挂表达")
                placed[sku] += quantity
    return placed


def _assert_gold_layout(
    layout: dict[object, object],
    mounted: dict[object, object],
    unmounted: dict[object, object],
    revision: bool,
) -> None:
    expected_mounted = {**_GOLD_V1, "ZX-V113": 1} if revision else _GOLD_V1
    if mounted != expected_mounted or sum(cast(dict[str, int], unmounted).values()) != (
        6 if revision else 5
    ):
        raise GenerationFailed("冻结黄金任务必须满足约定的 15→14 数量")
    zones = cast(dict[str, dict[str, object]], layout["zones"])
    expected = {
        "A": ("primary_focus", {"ZX-C218": 1}, {"ZX-P211": 2}),
        "B": ("neutral", {"ZX-S104": 2, "ZX-K126": 2}, {"ZX-Q117": 2}),
        "C": (
            "secondary_response",
            {"ZX-C218": 1, "ZX-V113": 1 if revision else 2},
            {"ZX-P211": 1, "ZX-Q117": 2},
        ),
    }
    for zone_id, (role, upper, lower) in expected.items():
        zone = zones[zone_id]
        if (
            zone["role"] != role
            or _rail_quantities(zone["upper"]) != upper
            or _rail_quantities(zone["lower"]) != lower
        ):
            raise GenerationFailed("冻结黄金任务必须保持约定的上下左右搭配区")
    if _front_skus(zones["A"]["upper"]) != {"ZX-C218"} or _front_skus(zones["C"]["upper"]) != {
        "ZX-C218"
    }:
        raise GenerationFailed("冻结黄金任务必须保留主正挂与弱回应正挂")


def _rail_quantities(value: object) -> dict[str, int]:
    if not isinstance(value, list):
        raise GenerationFailed("陈列挂杆槽位无效")
    slots = cast(list[dict[str, object]], value)
    return {str(slot["sku"]): cast(int, slot["quantity"]) for slot in slots}


def _front_skus(value: object) -> set[str]:
    return {
        str(slot["sku"])
        for slot in cast(list[dict[str, object]], value)
        if slot["mount"] == "front_facing"
    }
