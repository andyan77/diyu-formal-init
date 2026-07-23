from __future__ import annotations

from src.shared.errors import GenerationFailed
from src.shared.types import GeneratedDisplayArtifact


def assert_display_complete(
    artifact: GeneratedDisplayArtifact, inventory: tuple[tuple[str, int], ...]
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
        if int(mounted.get(sku, 0)) + int(unmounted.get(sku, 0)) != amount:
            raise GenerationFailed("陈列方案数量无法与本次清单对账")
    if any(sku not in available for sku in mounted) or not {"A", "B", "C"}.issubset(zones):
        raise GenerationFailed("陈列方案包含无效商品或缺少搭配区")
    required = ("主焦点", "回应", "侧挂", "替代", "执行步骤", "内部执行建议")
    if not artifact.body.strip() or any(part not in artifact.body for part in required):
        raise GenerationFailed("陈列方案缺少必要执行说明")
