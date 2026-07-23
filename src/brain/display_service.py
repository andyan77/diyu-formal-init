from __future__ import annotations

import re
from uuid import UUID

from src.brain.display_contract import assert_display_complete
from src.ports.display_generator import DisplayGenerator
from src.ports.display_repository import DisplayRepository
from src.shared.errors import DomainError, GenerationFailed
from src.shared.types import ActiveAsset, DisplayContext, DisplayGenerationInput, DisplayScope

_LINE = re.compile(r"\b(ZX-[A-Z]\d{3})\s*(\d+)\s*件")


class DisplayService:
    def __init__(self, repository: DisplayRepository, generator: DisplayGenerator) -> None:
        self._repository = repository
        self._generator = generator

    def create(self, scope: DisplayScope, inventory_text: str) -> dict[str, object]:
        inventory = self._inventory(inventory_text)
        context = self._repository.load_context(scope)
        if context is None:
            return {
                "kind": "question",
                "message": "这家门店还缺少上下挂杆、固定正挂点和来客方向这项条件；请先补充它。",
            }
        assets = self._repository.load_assets(revision=False)
        task_id, run_id = self._repository.create_run(
            scope, inventory_text, inventory, self._generator.model_name, assets
        )
        return self._generate(scope, task_id, run_id, inventory, context, assets, None, None)

    def revise(self, scope: DisplayScope, task_id: UUID, feedback: str) -> dict[str, object]:
        if not feedback.strip():
            raise DomainError("请说明这次现场变化")
        context = self._repository.load_context(scope)
        if context is None:
            raise DomainError("当前门店缺少可复用的挂杆条件")
        assets = self._repository.load_assets(revision=True)
        run_id, prior, inventory = self._repository.create_revision_run(
            scope, task_id, feedback, self._generator.model_name, assets
        )
        return self._generate(scope, task_id, run_id, inventory, context, assets, feedback, prior)

    def fetch_version(self, scope: DisplayScope, task_id: UUID, version: int) -> dict[str, object]:
        return self._repository.fetch_version(scope, task_id, version)

    def _generate(
        self,
        scope: DisplayScope,
        task_id: UUID,
        run_id: UUID,
        inventory: tuple[tuple[str, int], ...],
        context: DisplayContext,
        assets: tuple[ActiveAsset, ...],
        feedback: str | None,
        prior: dict[str, object] | None,
    ) -> dict[str, object]:
        try:
            artifact = self._generator.generate(
                DisplayGenerationInput(run_id, task_id, inventory, context, assets, feedback, prior)
            )
            assert_display_complete(artifact, inventory, revision=feedback is not None)
        except GenerationFailed as exc:
            self._repository.fail_run(scope, task_id, run_id, str(exc))
            raise
        except Exception as exc:
            self._repository.fail_run(scope, task_id, run_id, "模型调用失败，请稍后重试")
            raise GenerationFailed("模型调用失败，请稍后重试") from exc
        return self._repository.complete_run(
            scope,
            task_id,
            run_id,
            {"body": artifact.body, "plan": artifact.plan},
            artifact.model,
            artifact.latency_ms,
            artifact.retry_count,
            artifact.provider_usage,
        ) | {"kind": "display"}

    @staticmethod
    def _inventory(text: str) -> tuple[tuple[str, int], ...]:
        lines = tuple((sku, int(amount)) for sku, amount in _LINE.findall(text.upper()))
        if (
            not lines
            or len({sku for sku, _ in lines}) != len(lines)
            or any(amount < 1 for _, amount in lines)
        ):
            raise DomainError("请用“ZX-C218 3 件”这样的自然清单说明本次可用商品和数量")
        return lines
