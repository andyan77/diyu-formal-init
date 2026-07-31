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
_DISPLAY_RUN_LEASE_SECONDS = 900
_DISPLAY_FAILURE_MESSAGE = "这次纯文字方案没有生成完成，请保留输入后再试。"


class DisplayService:
    def __init__(self, repository: DisplayRepository, generator: DisplayGenerator) -> None:
        self._repository = repository
        self._generator = generator

    def create(
        self,
        scope: DisplayScope,
        inventory_text: str,
        product_version_inventory: tuple[tuple[UUID, int], ...] = (),
    ) -> dict[str, object]:
        self._repository.recover_stale_runs(scope, _DISPLAY_RUN_LEASE_SECONDS)
        if product_version_inventory:
            self._assert_structured_inventory(product_version_inventory)
            context = self._repository.load_context(
                scope,
                product_version_inventory=product_version_inventory,
            )
            if context is None:
                return self._missing_store_question()
            inventory = self._inventory_from_context(context, product_version_inventory)
            stored_inventory_text = inventory_text.strip() or self._inventory_text(inventory)
        else:
            inventory = self._inventory(inventory_text)
            context = self._repository.load_context(scope, inventory)
            stored_inventory_text = inventory_text
        if context is None:
            return self._missing_store_question()
        assert_dm01_rule_bundle(context.rule_bundle, revision=False, error_type=DomainError)
        hard_requirements, clarification = parse_hard_requirements(inventory_text, context)
        if clarification is not None:
            return {"kind": "question", "message": clarification}
        gap = required_inventory_gap(inventory, context, hard_requirements)
        if gap is not None:
            return {"kind": "question", "message": gap}
        assert context.rule_bundle is not None
        assets = self._active_assets(context.rule_bundle.generation_assets)
        task_id, run_id = self._repository.create_run(
            scope,
            stored_inventory_text,
            inventory,
            context,
            self._generator.model_name,
            assets,
            hard_requirements,
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
        self._repository.recover_stale_runs(scope, _DISPLAY_RUN_LEASE_SECONDS)
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
            completed = self._repository.complete_run(
                scope,
                task_id,
                run_id,
                {"body": body, "plan": artifact.plan},
                artifact.model,
                artifact.latency_ms,
                artifact.retry_count,
                artifact.provider_usage,
            )
        except GenerationFailed as exc:
            self._fail_run(scope, task_id, run_id, str(exc))
            raise
        except Exception as exc:
            self._fail_run(scope, task_id, run_id, _DISPLAY_FAILURE_MESSAGE)
            raise GenerationFailed(_DISPLAY_FAILURE_MESSAGE) from exc
        return completed | {"kind": "display"}

    def _fail_run(self, scope: DisplayScope, task_id: UUID, run_id: UUID, reason: str) -> None:
        try:
            self._repository.fail_run(scope, task_id, run_id, reason)
        except Exception:
            # A lost database connection cannot be repaired in the same request. The next safe
            # scoped access reclaims only runs whose explicit lease has expired.
            return

    @staticmethod
    def _inventory(text: str) -> tuple[tuple[str, int], ...]:
        lines = tuple((sku, int(amount)) for sku, amount in _LINE.findall(text.upper()))
        if not lines or len({sku for sku, _ in lines}) != len(lines) or any(amount < 1 for _, amount in lines):
            raise DomainError("请用“商品编号 3 件”这样的自然清单说明本次可用商品和数量")
        return lines

    @staticmethod
    def _assert_structured_inventory(inventory: tuple[tuple[UUID, int], ...]) -> None:
        product_version_ids = tuple(product_version_id for product_version_id, _ in inventory)
        if (
            not inventory
            or len(set(product_version_ids)) != len(product_version_ids)
            or any(quantity < 1 for _, quantity in inventory)
        ):
            raise DomainError("请为本次选择的每件商品填写正整数数量，且不要重复选择同一商品")

    @staticmethod
    def _inventory_from_context(
        context: DisplayContext,
        requested: tuple[tuple[UUID, int], ...],
    ) -> tuple[tuple[str, int], ...]:
        snapshots = {
            UUID(str(item["product_version_id"])): str(item["sku"])
            for item in context.product_snapshots
        }
        if len(snapshots) != len(requested):
            raise DomainError("本次选择中有商品版本不可用，请重新选择")
        try:
            return tuple((snapshots[product_version_id], quantity) for product_version_id, quantity in requested)
        except KeyError as exc:
            raise DomainError("本次选择中有商品版本不可用，请重新选择") from exc

    @staticmethod
    def _inventory_text(inventory: tuple[tuple[str, int], ...]) -> str:
        return "本次可用：" + "、".join(f"{sku} {quantity} 件" for sku, quantity in inventory) + "。"

    @staticmethod
    def _missing_store_question() -> dict[str, object]:
        return {
            "kind": "question",
            "message": "这家门店还缺少上下挂杆、固定正挂点和来客方向这项条件；请先补充它。",
        }

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
