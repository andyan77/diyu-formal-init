from __future__ import annotations

from src.ports.display_generator import DisplayGenerator
from src.shared.types import DisplayGenerationInput, GeneratedDisplayArtifact


class DeterministicDisplayGenerator(DisplayGenerator):
    """Offline DM01 test double generated from input quantities, never a real-model claim."""

    @property
    def model_name(self) -> str:
        return "deterministic-display-test-stub"

    def generate(self, request: DisplayGenerationInput) -> GeneratedDisplayArtifact:
        inventory = dict(request.inventory)
        coat = min(inventory.get("ZX-C218", 0), 2)
        vest = min(inventory.get("ZX-V113", 0), 1 if request.feedback else 2)
        mounted = {
            "ZX-C218": coat,
            "ZX-S104": min(inventory.get("ZX-S104", 0), 2),
            "ZX-K126": min(inventory.get("ZX-K126", 0), 2),
            "ZX-P211": min(inventory.get("ZX-P211", 0), 3),
            "ZX-V113": vest,
            "ZX-Q117": min(inventory.get("ZX-Q117", 0), 4),
        }
        mounted = {sku: amount for sku, amount in mounted.items() if amount}
        unmounted = {sku: amount - mounted.get(sku, 0) for sku, amount in inventory.items()}
        response = "ZX-C218 ×1 炭灰面正挂" if coat == 2 else "取消同款右侧回应，保留左侧唯一主焦点"
        layout = {
            "A": {"upper": "ZX-C218 ×1 深绿细格面正挂", "lower": "ZX-P211 ×2"},
            "B": {"upper": "ZX-S104 ×2、ZX-K126 ×2", "lower": "ZX-Q117 ×2"},
            "C": {"upper": f"{response}；ZX-V113 ×{vest} 侧挂", "lower": "ZX-P211 ×1、ZX-Q117 ×2"},
        }
        zones = {
            "A": {"ZX-C218": 1, "ZX-P211": 2},
            "B": {"ZX-S104": 2, "ZX-K126": 2, "ZX-Q117": 2},
            "C": {"ZX-C218": 1, "ZX-V113": vest, "ZX-P211": 1, "ZX-Q117": 2},
        }
        revision = (
            "本次只改 C 区上杆，其他区域、下杆、主焦点、回应和动线保持不变。"
            if request.feedback
            else "这是首次方案。"
        )
        body = (
            f"这版选择 {sum(mounted.values())} 件上墙、{sum(unmounted.values())} 件不上墙；容量是上限，先保证看见、抽取和复位。{revision}\n\n"
            f"A 区入口主焦点：{layout['A']['upper']}，下杆垂直对应 {layout['A']['lower']}；左侧来客先读到主焦点。\n"
            f"B 区中间基础：上杆 {layout['B']['upper']}，下杆 {layout['B']['lower']}，留出浅色呼吸。\n"
            f"C 区右侧回应：上杆 {layout['C']['upper']}，下杆 {layout['C']['lower']}；它是较弱回应。\n\n"
            "正挂、侧挂与间距：两个固定正挂均在上杆；上杆侧挂不超过 6 件，下杆不超过 8 件。搭配区间留约一个衣架宽，侧挂以容易抽取为先。\n\n"
            "替代：ZX-C218 临时少一件时先用本次未上墙同款；若只剩一件，保留左侧主焦点并取消回应。衣袖或厚度压住相邻商品时，先减少该处侧挂。\n\n"
            "执行步骤：1. 分出上墙与未上墙商品。2. 先完成两个正挂。3. 依次完成中间与下杆搭配区。4. 统一衣架方向并确认可抽取。\n\n"
            "这是一份内部执行建议，不表示总部批准、系统核验或门店已经完成。"
        )
        return GeneratedDisplayArtifact(
            body,
            {"mounted": mounted, "unmounted": unmounted, "zones": zones},
            self.model_name,
            0,
            0,
            None,
        )
