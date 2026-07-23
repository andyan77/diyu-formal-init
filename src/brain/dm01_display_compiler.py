from __future__ import annotations

from src.ports.display_generator import DisplayGenerator
from src.shared.errors import GenerationFailed
from src.shared.types import DisplayGenerationInput, GeneratedDisplayArtifact

_REQUIRED_INVENTORY = {
    "ZX-C218": 1,
    "ZX-S104": 2,
    "ZX-K126": 2,
    "ZX-P211": 3,
    "ZX-V113": 2,
    "ZX-Q117": 4,
}


def required_inventory_gap(inventory: tuple[tuple[str, int], ...]) -> str | None:
    """Return the single missing condition needed for the frozen DM01 layout."""
    available = dict(inventory)
    unsupported = sorted(set(available) - set(_REQUIRED_INVENTORY))
    if unsupported:
        return f"本次清单包含当前挂杆档案尚未登记的 {unsupported[0]}；请先确认可用商品事实。"
    for sku, minimum in _REQUIRED_INVENTORY.items():
        if available.get(sku, 0) < minimum:
            return f"本次缺少 {sku} 至少 {minimum} 件这一必要条件；请确认可用数量后再生成。"
    return None


def is_c_upper_vest_obstruction_feedback(feedback: str) -> bool:
    """Recognize only the frozen, explicitly local C-upper vest adjustment."""
    text = feedback.casefold()
    if "右侧" in text and "外套" in text and any(marker in text for marker in ("太厚", "挂不下")):
        return True
    refers_to_vest = "马甲" in text or "zx-v113" in text
    refers_to_c_upper = any(
        marker in text for marker in ("右上", "c区上杆", "c 区上杆", "c区", "c 区")
    )
    describes_obstruction = any(
        marker in text for marker in ("压", "遮挡", "不好拿", "难取", "难拿", "挤")
    )
    return refers_to_vest and refers_to_c_upper and describes_obstruction


class DM01DisplayCompiler(DisplayGenerator):
    """The formal, deterministic executor for the frozen DM01 wall layout."""

    @property
    def model_name(self) -> str:
        return "dm01-rule-compiler-v1"

    def generate(self, request: DisplayGenerationInput) -> GeneratedDisplayArtifact:
        gap = required_inventory_gap(request.inventory)
        if gap is not None:
            raise GenerationFailed(gap)
        inventory = dict(request.inventory)
        has_right_response = inventory["ZX-C218"] >= 2
        vest_count = 1 if request.feedback else 2
        mounted = {
            "ZX-C218": 2 if has_right_response else 1,
            "ZX-S104": 2,
            "ZX-K126": 2,
            "ZX-P211": 3,
            "ZX-V113": vest_count,
            "ZX-Q117": 4,
        }
        unmounted = {sku: amount - mounted[sku] for sku, amount in inventory.items()}
        c_upper: list[dict[str, object]] = []
        if has_right_response:
            c_upper.append({"sku": "ZX-C218", "quantity": 1, "mount": "front_facing"})
        c_upper.append({"sku": "ZX-V113", "quantity": vest_count, "mount": "side_hang"})
        layout: dict[str, object] = {
            "order": ["A", "B", "C"],
            "spacing": "侧挂之间保留约一个衣架宽，确保单手可抽取",
            "substitution": "同款后备优先；同款只剩一件时保留 A 区主焦点并取消 C 区回应",
            "execution_steps": [
                "按上墙与未上墙数量分开商品",
                "先完成 A 区主正挂，再完成 C 区回应",
                "按 A、B、C 的上杆和下杆摆放",
                "统一衣架方向并确认每件可抽取",
            ],
            "zones": {
                "A": {
                    "role": "primary_focus",
                    "upper": [{"sku": "ZX-C218", "quantity": 1, "mount": "front_facing"}],
                    "lower": [{"sku": "ZX-P211", "quantity": 2, "mount": "side_hang"}],
                },
                "B": {
                    "role": "neutral",
                    "upper": [
                        {"sku": "ZX-S104", "quantity": 2, "mount": "side_hang"},
                        {"sku": "ZX-K126", "quantity": 2, "mount": "side_hang"},
                    ],
                    "lower": [{"sku": "ZX-Q117", "quantity": 2, "mount": "side_hang"}],
                },
                "C": {
                    "role": "secondary_response",
                    "upper": c_upper,
                    "lower": [
                        {"sku": "ZX-P211", "quantity": 1, "mount": "side_hang"},
                        {"sku": "ZX-Q117", "quantity": 2, "mount": "side_hang"},
                    ],
                },
            },
        }
        return GeneratedDisplayArtifact(
            "The visible DM01 text is compiled only from this verified layout.",
            {"mounted": mounted, "unmounted": unmounted, "layout": layout},
            self.model_name,
            0,
            0,
            None,
        )
