from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import cast

from src.ports.display_generator import DisplayGenerator
from src.shared.errors import GenerationFailed
from src.shared.types import DisplayContext, DisplayGenerationInput, GeneratedDisplayArtifact

_POSITIONS = ("left", "center", "right")
_REDUCTION_MARKERS = ("减少", "少挂", "拿掉", "撤下", "太挤", "挂不下", "遮挡", "难取", "不好拿")


def required_inventory_gap(
    inventory: tuple[tuple[str, int], ...],
    context: DisplayContext,
) -> str | None:
    """Return one actionable gap against the trusted store-scoped product facts."""
    available = dict(inventory)
    products = dict(context.products)
    unsupported = sorted(set(available) - set(products))
    if unsupported:
        return f"本次清单包含当前门店档案未登记的 {unsupported[0]}；请先确认这件商品。"
    policy = _object(context.policy, "品牌陈列标准")
    primary_skus = _string_tuple(policy.get("primary_focus_skus"), "主焦点商品")
    secondary_skus = _string_tuple(policy.get("secondary_response_skus"), "较弱回应商品")
    required = Counter(primary_skus)
    if bool(policy.get("secondary_required", False)):
        required.update(secondary_skus)
    for sku, minimum in required.items():
        if available.get(sku, 0) < minimum:
            return f"本次缺少业务指定的 {sku} 至少 {minimum} 件；请确认可用数量后再生成。"

    snapshot = context.rail_profile.get("inventory_snapshot")
    if isinstance(snapshot, dict) and bool(snapshot.get("enforce_exact", False)):
        confirmed = {
            sku: _positive_int(facts.get("confirmed_quantity"), f"{sku} 确认数量") for sku, facts in context.products
        }
        if set(available) != set(confirmed):
            missing = sorted(set(confirmed) - set(available))
            extra = sorted(set(available) - set(confirmed))
            changed = missing[0] if missing else extra[0]
            return f"本次一次性库存没有完整覆盖已确认清单，首先需要核对 {changed}。"
        for sku, amount in confirmed.items():
            if available[sku] != amount:
                return f"{sku} 已确认 {amount} 件，本次填写为 {available[sku]} 件；请先确认差异。"
    return None


def parse_revision_target(
    feedback: str,
    context: DisplayContext,
) -> tuple[str, str, str] | None:
    """Resolve an explicit local reduction without guessing a vague field comment."""
    normalized = feedback.casefold()
    if not any(marker in normalized for marker in _REDUCTION_MARKERS):
        return None
    matched_products: list[str] = []
    for sku, facts in context.products:
        labels = (sku, str(facts.get("name", "")), str(facts.get("category", "")))
        if any(label and label.casefold() in normalized for label in labels):
            matched_products.append(sku)
    positions = [
        position
        for position, markers in {
            "left": ("左侧", "左边", "左区"),
            "center": ("中间", "中区", "中央"),
            "right": ("右侧", "右边", "右区"),
        }.items()
        if any(marker in normalized for marker in markers)
    ]
    rails = [
        rail
        for rail, markers in {"upper": ("上杆", "上层"), "lower": ("下杆", "下层")}.items()
        if any(marker in normalized for marker in markers)
    ]
    if len(set(matched_products)) != 1 or len(positions) != 1 or len(rails) != 1:
        return None
    return matched_products[0], positions[0], rails[0]


class DM01DisplayCompiler(DisplayGenerator):
    """Compile one double-rail wall plan entirely from trusted DM01 context."""

    @property
    def model_name(self) -> str:
        return "dm01-rule-compiler-v1"

    def generate(self, request: DisplayGenerationInput) -> GeneratedDisplayArtifact:
        if request.feedback is not None:
            return self._revise(request)
        return self._compile_v1(request)

    def _compile_v1(self, request: DisplayGenerationInput) -> GeneratedDisplayArtifact:
        gap = required_inventory_gap(request.inventory, request.context)
        if gap is not None:
            raise GenerationFailed(gap)
        inventory = dict(request.inventory)
        products = dict(request.context.products)
        policy = _object(request.context.policy, "品牌陈列标准")
        profile = _object(request.context.rail_profile, "门店挂杆档案")
        if policy.get("schema") != "dm01-wall-double-rail-v1":
            raise GenerationFailed("品牌陈列标准不属于当前 DM01 双层挂杆合同")
        if profile.get("schema") != "dm01-wall-double-rail-v1":
            raise GenerationFailed("门店挂杆档案不属于当前 DM01 双层挂杆合同")

        upper_capacity = _positive_int(profile.get("upper_comfort_capacity"), "上杆舒适容量")
        lower_capacity = _positive_int(profile.get("lower_comfort_capacity"), "下杆舒适容量")
        primary_position = _position(profile.get("primary_position"), "主焦点位置")
        secondary_position = _position(profile.get("secondary_position"), "较弱回应位置")
        if primary_position == secondary_position:
            raise GenerationFailed("主焦点与较弱回应不能占用同一个固定正挂位置")
        approach = _position(profile.get("approach"), "主要来客方向")
        physical_order = list(_POSITIONS)
        reading_order = list(reversed(_POSITIONS)) if approach == "right" else physical_order
        zones = _empty_zones(primary_position, secondary_position)
        mounted = {sku: 0 for sku in inventory}

        primary_skus = _string_tuple(policy.get("primary_focus_skus"), "主焦点商品")
        secondary_skus = _string_tuple(policy.get("secondary_response_skus"), "较弱回应商品")
        for index, sku in enumerate(primary_skus):
            mount = "front_facing" if index == 0 else "front_facing_layered"
            _add_slot(zones, primary_position, "upper", sku, products, mounted, inventory, 1, mount)
        secondary_present = True
        for sku in secondary_skus:
            if mounted.get(sku, 0) >= inventory.get(sku, 0):
                secondary_present = False
                break
            _add_slot(
                zones,
                secondary_position,
                "upper",
                sku,
                products,
                mounted,
                inventory,
                1,
                "front_facing",
            )

        upper_count = sum(mounted.values())
        for sku, facts in request.context.products:
            if facts.get("display_family") != "upper":
                continue
            target = (
                primary_position if sku in primary_skus else secondary_position if sku in secondary_skus else "center"
            )
            per_sku_cap = 1 if bool(facts.get("accent", False)) else 2
            if bool(facts.get("is_long", False)) and mounted[sku] > 0:
                per_sku_cap = mounted[sku]
            amount = min(inventory[sku] - mounted[sku], per_sku_cap - mounted[sku])
            amount = min(amount, upper_capacity - upper_count)
            if amount > 0:
                _add_slot(zones, target, "upper", sku, products, mounted, inventory, amount, "side_hang")
                upper_count += amount

        reserved_lower = set(
            _string_tuple(profile.get("lower_reserved_positions", ()), "下杆保留位置", allow_empty=True)
        )
        blocked_lower = set(reserved_lower)
        if bool(profile.get("avoid_long_upper_lower_overlap", False)):
            for position in _POSITIONS:
                upper_slots = cast(list[dict[str, object]], zones[position]["upper"])
                if any(bool(products[str(slot["sku"])].get("is_long", False)) for slot in upper_slots):
                    blocked_lower.add(position)
        lower_positions = [position for position in _POSITIONS if position not in blocked_lower]
        if not lower_positions:
            raise GenerationFailed("当前硬限制没有留下可用下杆位置")
        lower_count = 0
        lower_index = 0
        for sku, facts in request.context.products:
            if facts.get("display_family") != "lower":
                continue
            amount = min(inventory[sku] - mounted[sku], lower_capacity - lower_count)
            if amount < 1:
                continue
            target = lower_positions[lower_index % len(lower_positions)]
            _add_slot(zones, target, "lower", sku, products, mounted, inventory, amount, "side_hang")
            lower_count += amount
            lower_index += 1

        unmounted = {sku: amount - mounted[sku] for sku, amount in inventory.items()}
        constraints = _string_tuple(profile.get("constraints"), "现场硬限制")
        layout: dict[str, object] = {
            "schema": "dm01-wall-double-rail-v1",
            "physical_order": physical_order,
            "reading_order": reading_order,
            "approach": approach,
            "golden_sight": _nonempty_text(profile.get("golden_sight"), "黄金视线"),
            "capacities": {"upper": upper_capacity, "lower": lower_capacity},
            "primary_position": primary_position,
            "secondary_position": secondary_position,
            "focus_contract": {
                "primary_skus": list(primary_skus),
                "secondary_skus": list(secondary_skus),
                "secondary_present": secondary_present,
            },
            "theme": _nonempty_text(policy.get("theme"), "本次主题"),
            "density": _nonempty_text(policy.get("density"), "陈列密度"),
            "spacing": "侧挂之间保留约一个衣架宽，正挂两侧各留出清楚边界，保证单手抽取和复位。",
            "substitution": "缺少业务指定焦点商品时停止并确认；其他商品不足时保留主次焦点，缩减对应中性组，不跨用未登记商品。",
            "constraints": list(constraints),
            "blocked_lower_positions": sorted(blocked_lower),
            "execution_steps": [
                "按上墙与不上墙数量逐项对账",
                f"先完成{_position_text(primary_position)}主焦点，再完成{_position_text(secondary_position)}较弱回应",
                "按来客阅读顺序完成中性上装和下装分组",
                "统一衣架方向、留出间距，并逐件确认可抽取、可试穿、可复位",
                "复核价格、消防、监控、通道和补货操作空间均未被遮挡",
            ],
            "zones": zones,
        }
        return GeneratedDisplayArtifact(
            "Visible text is deterministically compiled after the plan contract passes.",
            {"mounted": mounted, "unmounted": unmounted, "layout": layout},
            self.model_name,
            0,
            0,
            None,
        )

    def _revise(self, request: DisplayGenerationInput) -> GeneratedDisplayArtifact:
        if request.prior_plan is None or request.revision_target is None:
            raise GenerationFailed("修订缺少上一版或明确的受影响位置")
        sku, position, rail = request.revision_target
        plan = deepcopy(request.prior_plan)
        mounted = cast(dict[str, int], plan.get("mounted"))
        unmounted = cast(dict[str, int], plan.get("unmounted"))
        layout = cast(dict[str, object], plan.get("layout"))
        zones = cast(dict[str, dict[str, object]], layout.get("zones"))
        if sku not in mounted or position not in zones or rail not in {"upper", "lower"}:
            raise GenerationFailed("现场反馈指向的商品或挂杆不在上一版中")
        slots = cast(list[dict[str, object]], zones[position][rail])
        slot = next((item for item in slots if item.get("sku") == sku), None)
        if slot is None:
            raise GenerationFailed("现场反馈指向的位置没有这件商品")
        quantity = cast(int, slot["quantity"])
        if quantity == 1:
            slots.remove(slot)
        else:
            slot["quantity"] = quantity - 1
        mounted[sku] -= 1
        unmounted[sku] += 1
        label = str(slot["label"])
        layout["revision_note"] = (
            f"根据现场反馈，仅将{_position_text(position)}{_rail_text(rail)}的"
            f"{label}（{sku}）减少 1 件；其他区域、焦点和左右动线继承 V1。"
        )
        return GeneratedDisplayArtifact(
            "Visible revision text is compiled only after local-delta validation.",
            plan,
            self.model_name,
            0,
            0,
            None,
        )


def _empty_zones(primary: str, secondary: str) -> dict[str, dict[str, object]]:
    zones: dict[str, dict[str, object]] = {}
    for position in _POSITIONS:
        role = "primary_focus" if position == primary else "secondary_response" if position == secondary else "neutral"
        zones[position] = {"role": role, "upper": [], "lower": []}
    return zones


def _add_slot(
    zones: dict[str, dict[str, object]],
    position: str,
    rail: str,
    sku: str,
    products: dict[str, dict[str, object]],
    mounted: dict[str, int],
    inventory: dict[str, int],
    amount: int,
    mount: str,
) -> None:
    if sku not in products or sku not in inventory or amount < 1 or mounted[sku] + amount > inventory[sku]:
        raise GenerationFailed("陈列分配超出本次已确认商品或数量")
    facts = products[sku]
    slots = cast(list[dict[str, object]], zones[position][rail])
    slots.append(
        {
            "sku": sku,
            "label": _nonempty_text(facts.get("name"), f"{sku} 商品名称"),
            "quantity": amount,
            "mount": mount,
        }
    )
    mounted[sku] += amount


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise GenerationFailed(f"{label}结构无效")
    return cast(dict[str, object], value)


def _string_tuple(value: object, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise GenerationFailed(f"{label}结构无效")
    result = tuple(cast(str, item).strip() for item in value)
    if not result and not allow_empty:
        raise GenerationFailed(f"{label}不能为空")
    return result


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise GenerationFailed(f"{label}必须是正整数")
    return value


def _nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GenerationFailed(f"{label}不能为空")
    return value.strip()


def _position(value: object, label: str) -> str:
    position = _nonempty_text(value, label)
    if position not in _POSITIONS:
        raise GenerationFailed(f"{label}必须是左、中、右之一")
    return position


def _position_text(position: str) -> str:
    return {"left": "左侧", "center": "中间", "right": "右侧"}[position]


def _rail_text(rail: str) -> str:
    return {"upper": "上杆", "lower": "下杆"}[rail]
