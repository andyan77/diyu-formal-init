from __future__ import annotations

import re
from uuid import UUID

from src.brain.display_contract import assert_display_complete, assert_display_revision
from src.brain.display_text import compile_display_body
from src.brain.dm01_display_compiler import (
    parse_hard_requirements,
    parse_revision_target,
    required_inventory_gap,
)
from src.ports.display_generator import DisplayGenerator
from src.ports.display_repository import DisplayRepository
from src.shared.dm01_rules import DM01RuleAssetV1, assert_dm01_rule_bundle
from src.shared.errors import DomainError, GenerationFailed
from src.shared.types import ActiveAsset, DisplayContext, DisplayGenerationInput, DisplayScope

_LINE = re.compile(r"(?<![A-Z0-9-])([A-Z0-9]+(?:-[A-Z0-9]+)+)\s*(\d+)\s*件")


class DisplayService:
    def __init__(self, repository: DisplayRepository, generator: DisplayGenerator) -> None:
        self._repository = repository
        self._generator = generator

    def create(self, scope: DisplayScope, inventory_text: str) -> dict[str, object]:
        inventory = self._inventory(inventory_text)
        context = self._repository.load_context(scope, inventory)
        if context is None:
            return {
                "kind": "question",
                "message": "这家门店还缺少上下挂杆、固定正挂点和来客方向这项条件；请先补充它。",
            }
        assert_dm01_rule_bundle(context.rule_bundle, revision=False, error_type=DomainError)
        hard_requirements = parse_hard_requirements(inventory_text)
        gap = required_inventory_gap(inventory, context, hard_requirements)
        if gap is not None:
            return {"kind": "question", "message": gap}
        assert context.rule_bundle is not None
        assets = self._active_assets(context.rule_bundle.generation_assets)
        task_id, run_id = self._repository.create_run(
            scope, inventory_text, inventory, context, self._generator.model_name, assets
        )
        return self._generate(
            scope,
            task_id,
            run_id,
            inventory,
            context,
            assets,
            None,
            None,
            hard_requirements=hard_requirements,
        )

    def revise(self, scope: DisplayScope, task_id: UUID, feedback: str) -> dict[str, object]:
        if not feedback.strip():
            raise DomainError("请说明这次现场变化")
        context = self._repository.load_task_context(scope, task_id)
        if context is None:
            return {
                "kind": "question",
                "message": "这份历史方案没有保留完整的任务条件，请按当前库存新建一份方案。",
            }
        revision_target = parse_revision_target(feedback, context)
        if revision_target is None:
            return {
                "kind": "question",
                "message": "请在一段话中说明要减少的商品，以及受影响的左/中/右位置和上杆/下杆；其余内容会保留。",
            }
        assert_dm01_rule_bundle(context.rule_bundle, revision=True, error_type=DomainError)
        assert context.rule_bundle is not None
        assets = self._active_assets(context.rule_bundle.revision_assets)
        run_id, prior, inventory = self._repository.create_revision_run(
            scope, task_id, feedback, context, self._generator.model_name, assets
        )
        return self._generate(
            scope,
            task_id,
            run_id,
            inventory,
            context,
            assets,
            feedback,
            prior,
            revision_target,
        )

    def fetch_version(self, scope: DisplayScope, task_id: UUID, version: int) -> dict[str, object]:
        return self._repository.fetch_version(scope, task_id, version)

    def identity_summary(self, scope: DisplayScope) -> dict[str, str]:
        context = self._repository.load_context(scope)
        if context is None:
            raise DomainError("当前演示会话没有可用门店身份")
        return {
            "brand": context.brand_name,
            "operator": context.operator_name,
            "organization": context.organization_name,
            "store": context.store_name,
        }

    def available_products(self, scope: DisplayScope) -> list[dict[str, object]]:
        return self._repository.available_products(scope)

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
        revision_target: tuple[str, str, str] | None = None,
        hard_requirements: frozenset[str] = frozenset(),
    ) -> dict[str, object]:
        try:
            artifact = self._generator.generate(
                DisplayGenerationInput(
                    run_id,
                    task_id,
                    inventory,
                    context,
                    assets,
                    feedback,
                    prior,
                    revision_target,
                    hard_requirements,
                )
            )
            assert_display_complete(
                artifact,
                inventory,
                revision=feedback is not None,
                product_facts=dict(context.products),
            )
            if feedback is not None and prior is not None:
                assert_display_revision(prior, artifact.plan)
            body = compile_display_body(context, artifact.plan, revision=feedback is not None)
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
            {"body": body, "plan": artifact.plan},
            artifact.model,
            artifact.latency_ms,
            artifact.retry_count,
            artifact.provider_usage,
        ) | {"kind": "display"}

    @staticmethod
    def _inventory(text: str) -> tuple[tuple[str, int], ...]:
        lines = tuple((sku, int(amount)) for sku, amount in _LINE.findall(text.upper()))
        if not lines or len({sku for sku, _ in lines}) != len(lines) or any(amount < 1 for _, amount in lines):
            raise DomainError("请用“商品编号 3 件”这样的自然清单说明本次可用商品和数量")
        return lines

    @staticmethod
    def _active_assets(assets: tuple[DM01RuleAssetV1, ...]) -> tuple[ActiveAsset, ...]:
        return tuple(
            ActiveAsset(
                asset.asset_id,
                asset.schema_version,
                "dm01_rule",
                asset.invariant_id,
                asset.body_digest,
            )
            for asset in assets
        )
