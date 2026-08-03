from __future__ import annotations

import re
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from typing import cast

from src.ports.display_generator import DisplayGenerator
from src.shared.dm01_rules import assert_dm01_rule_bundle
from src.shared.errors import GenerationFailed
from src.shared.product_references import alias_index
from src.shared.types import DisplayContext, DisplayGenerationInput, GeneratedDisplayArtifact

_POSITIONS = ("left", "center", "right")
_REDUCTION_MARKERS = ("减少", "少挂", "拿掉", "撤下", "太挤", "挂不下", "遮挡", "难取", "不好拿")
_SENTENCE = re.compile(r"[。；;.\n]")
_RAIL_TEXT = {"upper": "上杆", "lower": "下杆"}
_REFERENCE_SEPARATORS = frozenset(" \t\r\n，,。；;、：:（）()【】[]“”‘’\"'!?！？/")
_REFERENCE_LIST_SEPARATORS = frozenset(("、", "，", ",", "与", "和", "及"))
_HARD_REFERENCE_ACTIONS = ("必须保留", "务必保留")
_HARD_TRAILING_ACTIONS = ("不得更换", "不可改变", "不能改", "固定", "必须", "务必")
_RAIL_REFERENCE_MARKERS = ("上杆", "上层", "下杆", "下层")


@dataclass(frozen=True)
class _ProductReferenceResolution:
    resolved_skus: frozenset[str]
    unresolved_segments: tuple[str, ...]
    ambiguous_segments: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        return bool(self.resolved_skus) and not self.unresolved_segments and not self.ambiguous_segments


def parse_hard_requirements(
    text: str,
    context: DisplayContext,
) -> tuple[frozenset[str], str | None]:
    """Resolve mandatory products only against the already frozen product identities."""
    marked: set[str] = set()
    for sentence in _SENTENCE.split(text):
        reference_phrase = _hard_reference_phrase(sentence)
        if reference_phrase is not None:
            resolution = _resolve_product_references(reference_phrase, context)
            if resolution.ambiguous_segments:
                return (
                    frozenset(),
                    "这条必须保留的要求可能对应多件本次商品，请改用商品编号或完整商品名称再说明一次。",
                )
            if not resolution.is_complete:
                return (
                    frozenset(),
                    "我还不能确定这条必须保留的要求指哪件本次商品，请改用商品编号或完整商品名称再说明一次。",
                )
            marked.update(resolution.resolved_skus)
    return frozenset(marked), None


def _hard_reference_phrase(sentence: str) -> str | None:
    stripped = sentence.strip("".join(_REFERENCE_SEPARATORS))
    before_polite, polite_marker, after_polite = stripped.partition("请把")
    if polite_marker and not before_polite.strip() and "保留" in after_polite:
        reference_phrase, _, trailing = after_polite.rpartition("保留")
        if not trailing.strip("".join(_REFERENCE_SEPARATORS)):
            return reference_phrase
    for marker in _HARD_REFERENCE_ACTIONS:
        before, matched, after = stripped.partition(marker)
        if not matched:
            continue
        left = before.strip("".join(_REFERENCE_SEPARATORS))
        right = after.strip("".join(_REFERENCE_SEPARATORS))
        if left and right:
            return f"{left}、{right}"
        return left or right
    for marker in _HARD_TRAILING_ACTIONS:
        before, matched, after = stripped.partition(marker)
        if not matched:
            continue
        left = before.strip("".join(_REFERENCE_SEPARATORS))
        right = after.strip("".join(_REFERENCE_SEPARATORS))
        return left or right
    return None


def required_inventory_gap(
    inventory: tuple[tuple[str, int], ...],
    context: DisplayContext,
    hard_requirements: frozenset[str] = frozenset(),
) -> str | None:
    """Ask once, and only when this task cannot stand at all.

    Everything substitutable is handled by narrowing the plan instead of asking. No question ever
    requests a confirmer, an approval or an authorisation.
    """
    available = {sku: amount for sku, amount in inventory if amount > 0}
    products = dict(context.products)
    missing_hard = sorted(sku for sku in hard_requirements if available.get(sku, 0) < 1 or sku not in products)
    families = {str(products[sku].get("display_family", "")) for sku in available if sku in products}
    missing_rails = [rail for rail in ("upper", "lower") if rail not in families]
    if not missing_hard and not missing_rails:
        return None
    parts = []
    if missing_hard:
        parts.append("本次输入里没有可用的 " + "、".join(missing_hard) + "，而你写明它必须留在方案里")
    if missing_rails:
        parts.append("本次没有可以放到" + "、".join(_RAIL_TEXT[rail] for rail in missing_rails) + "的商品资料")
    return (
        "还差一点就能生成参考方案："
        + "；".join(parts)
        + "。请在一段话里补上这些商品和数量，或直接说明由系统在现有商品里选择。"
    )


def parse_revision_target(
    feedback: str,
    context: DisplayContext,
) -> tuple[str, str, str] | None:
    """Resolve an explicit local reduction without guessing a vague field comment."""
    normalized = feedback.casefold()
    if not any(marker in normalized for marker in _REDUCTION_MARKERS):
        return None
    reference_phrase = _revision_reference_phrase(feedback)
    resolution = _resolve_product_references(reference_phrase or "", context)
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
    if not resolution.is_complete or len(resolution.resolved_skus) != 1 or len(positions) != 1 or len(rails) != 1:
        return None
    return next(iter(resolution.resolved_skus)), positions[0], rails[0]


def _revision_reference_phrase(feedback: str) -> str | None:
    rail_matches = [(feedback.find(marker), marker) for marker in _RAIL_REFERENCE_MARKERS if feedback.find(marker) >= 0]
    if not rail_matches:
        return None
    rail_start, rail_marker = min(rail_matches, key=lambda match: match[0])
    remainder = feedback[rail_start + len(rail_marker) :].lstrip("".join(_REFERENCE_SEPARATORS))
    if remainder.startswith("的"):
        remainder = remainder[1:].lstrip("".join(_REFERENCE_SEPARATORS))
    reduction_starts = [remainder.find(marker) for marker in _REDUCTION_MARKERS if remainder.find(marker) >= 0]
    if not reduction_starts:
        return None
    return remainder[: min(reduction_starts)].strip("".join(_REFERENCE_SEPARATORS))


def _resolve_product_references(
    reference_phrase: str,
    context: DisplayContext,
) -> _ProductReferenceResolution:
    """Resolve every explicit list segment against literal frozen SKU/name aliases.

    Case folding is used only to compare the person's words. No normalization, SKU grammar,
    prefix match or similarity rule is allowed to mint a product identity.
    """
    aliases = alias_index(
        tuple(
            (sku, (sku, str(facts.get("name", ""))))
            for sku, facts in context.products
        )
    )

    resolved: set[str] = set()
    unresolved: list[str] = []
    ambiguous: list[str] = []
    for segment in _split_reference_phrase(reference_phrase, aliases):
        frozen_skus = aliases.get(segment.casefold())
        if frozen_skus is None:
            unresolved.append(segment)
        elif len(frozen_skus) != 1:
            ambiguous.append(segment)
        else:
            resolved.update(frozen_skus)
    return _ProductReferenceResolution(
        resolved_skus=frozenset(resolved),
        unresolved_segments=tuple(unresolved),
        ambiguous_segments=tuple(ambiguous),
    )


def _split_reference_phrase(
    reference_phrase: str,
    aliases: dict[str, frozenset[str]],
) -> tuple[str, ...]:
    stripped = reference_phrase.strip("".join(_REFERENCE_SEPARATORS))
    if not stripped:
        return ("",)
    if stripped.casefold() in aliases:
        return (stripped,)
    segments: list[str] = []
    current: list[str] = []
    for character in stripped:
        if character in _REFERENCE_LIST_SEPARATORS:
            segments.append("".join(current).strip("".join(_REFERENCE_SEPARATORS)))
            current = []
        else:
            current.append(character)
    segments.append("".join(current).strip("".join(_REFERENCE_SEPARATORS)))
    return tuple(segments)


class DM01DisplayCompiler(DisplayGenerator):
    """Compile one double-rail wall plan entirely from trusted DM01 context."""

    @property
    def model_name(self) -> str:
        return "dm01-rule-compiler-v1"

    def generate(self, request: DisplayGenerationInput) -> GeneratedDisplayArtifact:
        if request.context.rule_bundle is not None:
            assert_dm01_rule_bundle(
                request.context.rule_bundle,
                revision=request.feedback is not None,
            )
        if request.feedback is not None:
            return self._revise(request)
        return self._compile_v1(request)

    def _compile_v1(self, request: DisplayGenerationInput) -> GeneratedDisplayArtifact:
        gap = required_inventory_gap(request.inventory, request.context, request.hard_requirements)
        if gap is not None:
            raise GenerationFailed(gap)
        inventory = {sku: amount for sku, amount in request.inventory if amount > 0}
        products = dict(request.context.products)
        expression = _object(request.context.task_expression, "本次任务表达")
        profile = _object(request.context.rail_profile, "门店挂杆结构")
        schema = expression.get("schema")
        if schema is not None and schema != "dm01-wall-double-rail-v1":
            raise GenerationFailed("本次任务表达不属于当前 DM01 双层挂杆合同")
        if profile.get("schema") != "dm01-wall-double-rail-v1":
            raise GenerationFailed("门店挂杆结构不属于当前 DM01 双层挂杆合同")

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
        mounted = {sku: 0 for sku, _ in request.inventory}

        suggested_primary = _suggested_skus(expression.get("primary_focus_skus"), "主焦点建议")
        secondary_skus = _suggested_skus(expression.get("secondary_response_skus"), "较弱回应建议")
        primary_skus = _usable_primary(suggested_primary, inventory, products)
        focus_source = "task_input" if primary_skus else "system_narrowed"
        if not primary_skus:
            fallback = _first_upper_sku(request.context.products, inventory)
            if fallback is None:
                raise GenerationFailed("本次没有可以放到上杆的商品资料")
            primary_skus = (fallback,)
        for index, sku in enumerate(primary_skus):
            mount = "front_facing" if index == 0 else "front_facing_layered"
            _add_slot(zones, primary_position, "upper", sku, products, mounted, inventory, 1, mount)
        secondary_present = bool(secondary_skus)
        for sku in secondary_skus:
            if sku not in products or mounted.get(sku, 0) >= inventory.get(sku, 0):
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
            if facts.get("display_family") != "upper" or sku not in inventory:
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
            if facts.get("display_family") != "lower" or sku not in inventory:
                continue
            amount = min(inventory[sku] - mounted[sku], lower_capacity - lower_count)
            if amount < 1:
                continue
            target = lower_positions[lower_index % len(lower_positions)]
            _add_slot(zones, target, "lower", sku, products, mounted, inventory, amount, "side_hang")
            lower_count += amount
            lower_index += 1

        unmounted = {sku: amount - mounted.get(sku, 0) for sku, amount in dict(request.inventory).items()}
        undescribed = sorted(
            sku
            for sku in unmounted
            if sku not in products or products[sku].get("display_family") not in {"upper", "lower"}
        )
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
                "focus_source": focus_source,
            },
            "theme": _text_or(expression.get("theme"), "本次没有说明主题，按现有商品关系组织"),
            "density": _text_or(expression.get("density"), "中低密度"),
            "spacing": "侧挂保持正常可抽取间距，主正挂两侧各留约一个衣架宽的视觉边界。",
            "substitution": (
                "本次建议的焦点商品不可用时，系统改用当前可用商品重新形成主焦点；"
                "其他商品不足时保留主次关系，缩减对应中性组，不使用没有陈列资料的商品。"
            ),
            "constraints": list(constraints),
            "blocked_lower_positions": sorted(blocked_lower),
            "undescribed_skus": undescribed,
            "execution_steps": [
                "按上墙与不上墙数量逐项对账",
                f"先完成{_position_text(primary_position)}主焦点，再完成{_position_text(secondary_position)}较弱回应",
                "按来客阅读顺序完成中性上装和下装分组",
                "统一衣架方向、留出间距，并逐件确认可抽取、可试穿、可复位",
                "复核价格、消防、监控、通道和补货操作空间均未被遮挡",
            ],
            "zones": zones,
        }
        plan: dict[str, object] = {
            "contract_version": "dm01-plan-v2" if request.context.rule_bundle is not None else "dm01-plan-v1",
            "rule_bundle_digest": (
                request.context.rule_bundle.bundle_digest if request.context.rule_bundle is not None else None
            ),
            "hard_requirements": sorted(request.hard_requirements),
            "inventory_conservation": {
                sku: {
                    "input": amount,
                    "displayed": mounted[sku],
                    "undisplayed": unmounted[sku],
                }
                for sku, amount in request.inventory
            },
            "mounted": mounted,
            "unmounted": unmounted,
            "layout": layout,
        }
        return GeneratedDisplayArtifact(
            "Visible text is deterministically compiled after the plan contract passes.",
            plan,
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
        matching_slots = [item for item in slots if item.get("sku") == sku]
        slot = next((item for item in matching_slots if item.get("mount") == "side_hang"), None)
        if slot is None:
            slot = next(iter(matching_slots), None)
        if slot is None:
            raise GenerationFailed("现场反馈指向的位置没有这件商品")
        quantity = cast(int, slot["quantity"])
        if quantity == 1:
            slots.remove(slot)
        else:
            slot["quantity"] = quantity - 1
        mounted[sku] -= 1
        unmounted[sku] += 1
        conservation = cast(dict[str, dict[str, int]], plan.get("inventory_conservation"))
        if sku not in conservation:
            raise GenerationFailed("上一版缺少逐商品库存守恒证明")
        conservation[sku] = {
            "input": mounted[sku] + unmounted[sku],
            "displayed": mounted[sku],
            "undisplayed": unmounted[sku],
        }
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
        raise GenerationFailed("陈列分配超出本次清单商品或数量")
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


def _suggested_skus(value: object, label: str) -> tuple[str, ...]:
    """A focus list is a suggestion; an absent or empty list simply leaves the choice to the system."""
    if value is None:
        return ()
    return _string_tuple(value, label, allow_empty=True)


def _usable_primary(
    suggested: tuple[str, ...],
    inventory: dict[str, int],
    products: dict[str, dict[str, object]],
) -> tuple[str, ...]:
    if not suggested:
        return ()
    counts = Counter(suggested)
    if any(sku not in products or inventory.get(sku, 0) < amount for sku, amount in counts.items()):
        return ()
    return suggested


def _first_upper_sku(
    products: tuple[tuple[str, dict[str, object]], ...],
    inventory: dict[str, int],
) -> str | None:
    for sku, facts in products:
        if facts.get("display_family") == "upper" and inventory.get(sku, 0) > 0:
            return sku
    return None


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


def _text_or(value: object, default: str) -> str:
    """A missing non-critical field narrows the plan's wording instead of blocking this task."""
    return value.strip() if isinstance(value, str) and value.strip() else default


def _position(value: object, label: str) -> str:
    position = _nonempty_text(value, label)
    if position not in _POSITIONS:
        raise GenerationFailed(f"{label}必须是左、中、右之一")
    return position


def _position_text(position: str) -> str:
    return {"left": "左侧", "center": "中间", "right": "右侧"}[position]


def _rail_text(rail: str) -> str:
    return {"upper": "上杆", "lower": "下杆"}[rail]
