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
        c_upper = (
            [{"sku": "ZX-C218", "quantity": 1, "mount": "front_facing"}] if coat == 2 else []
        ) + ([{"sku": "ZX-V113", "quantity": vest, "mount": "side_hang"}] if vest else [])
        if not c_upper:
            c_upper = [{"sku": "ZX-K126", "quantity": 1, "mount": "side_hang"}]
        layout = {
            "order": ["A", "B", "C"],
            "spacing": "约一个衣架宽",
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
            "substitution": "同款后备优先",
            "execution_steps": ["先正挂", "再上下对应", "最后确认可抽取"],
        }
        return GeneratedDisplayArtifact(
            "model body is ignored",
            {"mounted": mounted, "unmounted": unmounted, "layout": layout},
            self.model_name,
            0,
            0,
            None,
        )
