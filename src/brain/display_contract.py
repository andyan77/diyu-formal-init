from __future__ import annotations

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
_GOLD_ZONES = {
    "A": {"ZX-C218": 1, "ZX-P211": 2},
    "B": {"ZX-S104": 2, "ZX-K126": 2, "ZX-Q117": 2},
    "C": {"ZX-C218": 1, "ZX-V113": 2, "ZX-P211": 1, "ZX-Q117": 2},
}


def assert_display_complete(
    artifact: GeneratedDisplayArtifact,
    inventory: tuple[tuple[str, int], ...],
    revision: bool = False,
) -> None:
    mounted = artifact.plan.get("mounted")
    unmounted = artifact.plan.get("unmounted")
    zones = artifact.plan.get("zones")
    if (
        not isinstance(mounted, dict)
        or not isinstance(unmounted, dict)
        or not isinstance(zones, dict)
    ):
        raise GenerationFailed("陈列方案结构不完整")
    available = dict(inventory)
    for sku, amount in available.items():
        if not isinstance(mounted.get(sku, 0), int) or not isinstance(unmounted.get(sku, 0), int):
            raise GenerationFailed("陈列方案数量必须是整数")
        if int(mounted.get(sku, 0)) + int(unmounted.get(sku, 0)) != amount:
            raise GenerationFailed("陈列方案数量无法与本次清单对账")
    if any(sku not in available for sku in mounted) or not {"A", "B", "C"}.issubset(zones):
        raise GenerationFailed("陈列方案包含无效商品或缺少搭配区")
    required = ("主焦点", "回应", "侧挂", "替代", "执行步骤", "内部执行建议")
    if not artifact.body.strip() or any(part not in artifact.body for part in required):
        raise GenerationFailed("陈列方案缺少必要执行说明")
    if "G-" in artifact.body or "GM-" in artifact.body:
        raise GenerationFailed("陈列成品不能展示内部资产编号")
    if available == _GOLD_INVENTORY:
        expected = {**_GOLD_V1, "ZX-V113": 1} if revision else _GOLD_V1
        if mounted != expected:
            raise GenerationFailed("冻结黄金任务必须满足约定的上墙数量与商品分配")
        expected_zones = (
            {**_GOLD_ZONES, "C": {**_GOLD_ZONES["C"], "ZX-V113": 1}} if revision else _GOLD_ZONES
        )
        if zones != expected_zones:
            raise GenerationFailed("冻结黄金任务必须保持约定的上下左右搭配区")
