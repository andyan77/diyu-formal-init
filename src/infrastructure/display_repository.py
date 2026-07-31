from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.ports.display_repository import DisplayRepository
from src.shared.display_integrity import (
    assert_display_artifact_integrity,
    attach_display_artifact_audit,
)
from src.shared.dm01_rules import (
    DM01RuleAssetV1,
    DM01RuleBundleV1,
    build_dm01_rule_bundle,
    canonical_json_digest,
    dm01_rule_bundle_from_document,
)
from src.shared.errors import DomainError
from src.shared.types import ActiveAsset, DisplayContext, DisplayScope


class PostgresDisplayRepository(DisplayRepository):
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    @contextmanager
    def _tx(self, scope: DisplayScope) -> Iterator[psycopg.Cursor[dict[str, object]]]:
        with (
            psycopg.connect(self._database_url, row_factory=dict_row) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(scope.tenant_id),))
            yield cursor

    @staticmethod
    def _one(cursor: psycopg.Cursor[dict[str, object]], message: str) -> dict[str, object]:
        row = cursor.fetchone()
        if row is None:
            raise DomainError(message)
        return row

    def load_context(
        self,
        scope: DisplayScope,
        inventory: tuple[tuple[str, int], ...] | None = None,
    ) -> DisplayContext | None:
        actor_organization_id = scope.actor_organization_id or scope.organization_id
        with self._tx(scope) as cursor:
            cursor.execute(
                """SELECT b.name brand_name, u.display_name operator_name, o.name organization_name,
                          p.version policy_version, p.body policy, s.name store_name,
                          s.profile_version, s.rail_profile, s.current_task_input
                   FROM brands b JOIN users u ON u.id=%s AND u.tenant_id=b.tenant_id
                   JOIN organizations o ON o.id=%s AND o.tenant_id=u.tenant_id
                   JOIN display_stores s ON s.brand_id=b.id AND s.tenant_id=b.tenant_id
                      AND s.execution_organization_id=o.id
                   LEFT JOIN display_policies p ON p.brand_id=b.id AND p.tenant_id=b.tenant_id
                      AND p.version=s.profile_version
                   WHERE b.tenant_id=%s AND b.id=%s AND u.organization_id=%s
                     AND (s.execution_organization_id=%s OR s.control_organization_id=%s)""",
                (
                    scope.user_id,
                    scope.organization_id,
                    scope.tenant_id,
                    scope.brand_id,
                    actor_organization_id,
                    actor_organization_id,
                    actor_organization_id,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            rail_profile = self._object(row["rail_profile"], "门店挂杆结构")
            task_input = self._optional_object(row["current_task_input"], "本次任务输入")
            product_snapshots: tuple[dict[str, object], ...] = ()
            rule_bundle: DM01RuleBundleV1 | None = None
            if inventory is not None:
                products, product_snapshots = self._formal_products(
                    cursor,
                    scope,
                    tuple(sku for sku, _ in inventory),
                )
                rule_bundle = self.load_rule_bundle()
            else:
                products = self._task_products(task_input)
            if inventory is None and not products:
                cursor.execute(
                    "SELECT sku, facts FROM brand_products WHERE tenant_id=%s AND brand_id=%s ORDER BY sku",
                    (scope.tenant_id, scope.brand_id),
                )
                products = tuple(
                    (str(item["sku"]), self._object(item["facts"], "商品事实")) for item in cursor.fetchall()
                )
        expression: dict[str, object] = {}
        expression_version: object = None
        if inventory is None:
            expression = self._optional_object(task_input.get("expression"), "本次任务表达")
            expression_version = task_input.get("version")
        if not expression:
            expression = self._optional_object(row["policy"], "品牌陈列标准")
            expression_version = row["policy_version"]
        if not expression:
            expression = {"schema": "dm01-wall-double-rail-v1"}
            expression_version = "dm01-default-v1"
        return DisplayContext(
            str(row["brand_name"]),
            str(row["organization_name"]),
            str(row["operator_name"]),
            str(expression_version) if isinstance(expression_version, str) else "",
            expression,
            str(row["store_name"]),
            str(row["profile_version"]),
            rail_profile,
            products,
            product_snapshots,
            rule_bundle,
        )

    def load_task_context(self, scope: DisplayScope, task_id: UUID) -> DisplayContext | None:
        """Reproduce the context this task was compiled from, not whatever the store holds today.

        Out of scope fails closed; None means the task is visible but froze no context, and such a
        task can no longer be revised — the current store seed must never stand in for it.
        """
        actor_organization_id = scope.actor_organization_id or scope.organization_id
        with self._tx(scope) as cursor:
            cursor.execute(
                """SELECT t.context_snapshot, u.display_name operator_name
                   FROM display_tasks t
                   JOIN display_stores s ON s.id=t.store_id AND s.tenant_id=t.tenant_id
                   JOIN users u ON u.id=%s AND u.tenant_id=t.tenant_id
                   WHERE t.tenant_id=%s AND t.id=%s AND t.brand_id=%s AND t.organization_id=%s
                     AND (t.created_by=%s OR s.execution_organization_id=%s)
                     AND (s.execution_organization_id=%s OR s.control_organization_id=%s)""",
                (
                    scope.user_id,
                    scope.tenant_id,
                    task_id,
                    scope.brand_id,
                    scope.organization_id,
                    scope.user_id,
                    actor_organization_id,
                    actor_organization_id,
                    actor_organization_id,
                ),
            )
            row = self._one(cursor, "找不到当前作用域中的陈列任务")
        if row["context_snapshot"] is None:
            return None
        frozen = self._object(row["context_snapshot"], "本次任务上下文快照")
        if frozen.get("contract_version") != "dm01-context-snapshot-v2":
            return None
        product_snapshots = self._frozen_product_snapshots(frozen)
        products = tuple(
            (
                str(item["sku"]),
                self._object(item.get("facts"), "本次任务冻结商品事实"),
            )
            for item in product_snapshots
        )
        rule_bundle = dm01_rule_bundle_from_document(frozen.get("rule_bundle"))
        return DisplayContext(
            str(frozen["brand_name"]),
            str(frozen["organization_name"]),
            str(row["operator_name"]),
            str(frozen["task_expression_version"]),
            self._object(frozen["task_expression"], "本次任务表达"),
            str(frozen["store_name"]),
            str(frozen["store_profile_version"]),
            self._object(frozen["rail_profile"], "门店挂杆结构"),
            products,
            product_snapshots,
            rule_bundle,
        )

    def load_assets(self, revision: bool) -> tuple[ActiveAsset, ...]:
        bundle = self.load_rule_bundle()
        assets = bundle.revision_assets if revision else bundle.generation_assets
        return self._active_assets(assets)

    def load_rule_bundle(self) -> DM01RuleBundleV1:
        with (
            psycopg.connect(self._database_url, row_factory=dict_row) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """SELECT a.asset_id, a.schema_version, a.asset_type, a.display_name, a.structured_body
                   FROM system_domain_assets a JOIN system_asset_activations x ON x.asset_id=a.asset_id
                   WHERE a.status='active' AND a.superseded_by IS NULL
                     AND (a.valid_until IS NULL OR a.valid_until >= CURRENT_DATE)
                     AND x.consumer='display-merchandising / DM01' ORDER BY a.asset_id"""
            )
            rows = tuple(cursor.fetchall())
        return build_dm01_rule_bundle(rows)

    def available_products(self, scope: DisplayScope) -> list[dict[str, object]]:
        with self._tx(scope) as cursor:
            cursor.execute(
                """
                SELECT product.sku, version.display_name, version.facts,
                       version.id AS product_version_id
                FROM brand_products product
                JOIN brand_product_versions version
                  ON version.tenant_id = product.tenant_id
                 AND version.product_id = product.id
                 AND version.id = product.current_version_id
                WHERE product.tenant_id = %s AND product.brand_id = %s
                  AND product.status = 'active'
                  AND (
                    version.visibility_scope = 'brand_all'
                    OR (
                      version.visibility_scope = 'organizations'
                      AND EXISTS (
                        SELECT 1
                        FROM unnest(version.scope_organization_ids) AS scoped(organization_id)
                        WHERE organization_is_same_or_descendant(
                          product.tenant_id, %s, scoped.organization_id
                        )
                      )
                    )
                    OR (
                      version.visibility_scope = 'headquarters'
                      AND %s = ANY(version.scope_organization_ids)
                      AND EXISTS (
                        SELECT 1 FROM organizations organization
                        WHERE organization.tenant_id = product.tenant_id
                          AND organization.id = %s
                          AND organization.organization_level = 'company'
                      )
                    )
                  )
                ORDER BY product.sku
                """,
                (
                    scope.tenant_id,
                    scope.brand_id,
                    scope.organization_id,
                    scope.organization_id,
                    scope.organization_id,
                ),
            )
            rows = cursor.fetchall()
        return [
            {
                "sku": str(row["sku"]),
                "display_name": str(row["display_name"]),
                "display_family": str(self._object(row["facts"], "正式商品事实").get("display_family") or ""),
                "product_version_id": str(row["product_version_id"]),
            }
            for row in rows
        ]

    def create_run(
        self,
        scope: DisplayScope,
        inventory_text: str,
        inventory: tuple[tuple[str, int], ...],
        context: DisplayContext,
        model: str,
        assets: tuple[ActiveAsset, ...],
    ) -> tuple[UUID, UUID]:
        task_id, run_id = uuid4(), uuid4()
        actor_organization_id = scope.actor_organization_id or scope.organization_id
        with self._tx(scope) as cursor:
            cursor.execute(
                """SELECT id FROM display_stores
                   WHERE tenant_id=%s AND brand_id=%s AND execution_organization_id=%s
                     AND (execution_organization_id=%s OR control_organization_id=%s)""",
                (
                    scope.tenant_id,
                    scope.brand_id,
                    scope.organization_id,
                    actor_organization_id,
                    actor_organization_id,
                ),
            )
            store_id = UUID(str(self._one(cursor, "当前组织没有可用陈列门店")["id"]))
            cursor.execute(
                "INSERT INTO display_tasks (id, tenant_id, brand_id, organization_id, created_by, store_id, inventory_text, inventory, context_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    task_id,
                    scope.tenant_id,
                    scope.brand_id,
                    scope.organization_id,
                    scope.user_id,
                    store_id,
                    inventory_text,
                    Jsonb(dict(inventory)),
                    Jsonb(_frozen_context(context)),
                ),
            )
            self._run(cursor, scope, run_id, task_id, model, assets, context, inventory)
        return task_id, run_id

    def create_revision_run(
        self,
        scope: DisplayScope,
        task_id: UUID,
        feedback: str,
        context: DisplayContext,
        model: str,
        assets: tuple[ActiveAsset, ...],
    ) -> tuple[UUID, dict[str, object], tuple[tuple[str, int], ...]]:
        run_id = uuid4()
        actor_organization_id = scope.actor_organization_id or scope.organization_id
        with self._tx(scope) as cursor:
            cursor.execute(
                """SELECT t.inventory FROM display_tasks t
                   JOIN display_stores s ON s.id=t.store_id AND s.tenant_id=t.tenant_id
                   WHERE t.tenant_id=%s AND t.id=%s AND t.brand_id=%s AND t.organization_id=%s
                     AND (t.created_by=%s OR s.execution_organization_id=%s)
                     AND (s.execution_organization_id=%s OR s.control_organization_id=%s)
                   FOR UPDATE OF t""",
                (
                    scope.tenant_id,
                    task_id,
                    scope.brand_id,
                    scope.organization_id,
                    scope.user_id,
                    actor_organization_id,
                    actor_organization_id,
                    actor_organization_id,
                ),
            )
            task = self._one(cursor, "找不到当前作用域中的陈列任务")
            cursor.execute(
                "SELECT plan FROM display_artifact_versions WHERE tenant_id=%s AND task_id=%s ORDER BY version_number DESC LIMIT 1",
                (scope.tenant_id, task_id),
            )
            prior = self._one(cursor, "原陈列版本不存在")
            cursor.execute(
                "UPDATE display_tasks SET feedback=%s WHERE tenant_id=%s AND id=%s",
                (feedback, scope.tenant_id, task_id),
            )
            raw = task["inventory"]
            if not isinstance(raw, dict):
                raise DomainError("陈列库存数据无效")
            inventory = tuple((str(k), int(v)) for k, v in raw.items())
            self._run(cursor, scope, run_id, task_id, model, assets, context, inventory)
        return (
            run_id,
            dict(prior["plan"]) if isinstance(prior["plan"], dict) else {},
            inventory,
        )

    def complete_run(
        self,
        scope: DisplayScope,
        task_id: UUID,
        run_id: UUID,
        artifact: dict[str, object],
        model: str,
        latency_ms: int,
        retry_count: int,
        usage: dict[str, int] | None,
    ) -> dict[str, object]:
        version_id = uuid4()
        body = artifact.get("body")
        plan = artifact.get("plan")
        if not isinstance(body, str) or not isinstance(plan, dict):
            raise DomainError("陈列成品结构不完整")
        audited_plan = attach_display_artifact_audit(body, plan)
        actor_organization_id = scope.actor_organization_id or scope.organization_id
        with self._tx(scope) as cursor:
            cursor.execute(
                """SELECT t.id FROM display_tasks t
                   JOIN display_stores s ON s.id=t.store_id AND s.tenant_id=t.tenant_id
                   WHERE t.tenant_id=%s AND t.id=%s AND t.brand_id=%s AND t.organization_id=%s
                     AND (t.created_by=%s OR s.execution_organization_id=%s)
                     AND (s.execution_organization_id=%s OR s.control_organization_id=%s)""",
                (
                    scope.tenant_id,
                    task_id,
                    scope.brand_id,
                    scope.organization_id,
                    scope.user_id,
                    actor_organization_id,
                    actor_organization_id,
                    actor_organization_id,
                ),
            )
            self._one(cursor, "当前作用域不能完成此生成")
            cursor.execute(
                "SELECT id,current_version FROM display_artifacts WHERE tenant_id=%s AND task_id=%s FOR UPDATE",
                (scope.tenant_id, task_id),
            )
            item = cursor.fetchone()
            if item is None:
                artifact_id, next_version = uuid4(), 1
                cursor.execute(
                    "INSERT INTO display_artifacts (id,tenant_id,task_id,current_version) VALUES (%s,%s,%s,%s)",
                    (artifact_id, scope.tenant_id, task_id, next_version),
                )
            else:
                artifact_id, next_version = (
                    UUID(str(item["id"])),
                    int(str(item["current_version"])) + 1,
                )
                cursor.execute(
                    "UPDATE display_artifacts SET current_version=%s WHERE tenant_id=%s AND id=%s",
                    (next_version, scope.tenant_id, artifact_id),
                )
            cursor.execute(
                "UPDATE display_generation_runs SET status='succeeded', model=%s, latency_ms=%s, retry_count=%s, provider_usage=%s, completed_at=now() WHERE tenant_id=%s AND id=%s AND task_id=%s AND status='running'",
                (
                    model,
                    latency_ms,
                    retry_count,
                    Jsonb(usage) if usage else None,
                    scope.tenant_id,
                    run_id,
                    task_id,
                ),
            )
            if cursor.rowcount != 1:
                raise DomainError("陈列生成运行不存在或已结束")
            cursor.execute(
                "INSERT INTO display_artifact_versions (id,tenant_id,artifact_id,task_id,run_id,version_number,body,plan,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    version_id,
                    scope.tenant_id,
                    artifact_id,
                    task_id,
                    run_id,
                    next_version,
                    body,
                    Jsonb(audited_plan),
                    scope.user_id,
                ),
            )
        return {
            "task_id": str(task_id),
            "version_id": str(version_id),
            "version": next_version,
            "body": body,
            "model": model,
        }

    def fail_run(self, scope: DisplayScope, task_id: UUID, run_id: UUID, reason: str) -> None:
        actor_organization_id = scope.actor_organization_id or scope.organization_id
        with self._tx(scope) as cursor:
            cursor.execute(
                """UPDATE display_generation_runs r
                   SET status='failed',failure_reason=%s,completed_at=now()
                   FROM display_tasks t, display_stores s
                   WHERE r.tenant_id=%s AND r.id=%s AND r.task_id=%s AND r.status='running'
                     AND t.id=r.task_id AND t.tenant_id=r.tenant_id
                     AND s.id=t.store_id AND s.tenant_id=t.tenant_id
                     AND t.brand_id=%s AND t.organization_id=%s
                     AND (t.created_by=%s OR s.execution_organization_id=%s)
                     AND (s.execution_organization_id=%s OR s.control_organization_id=%s)""",
                (
                    reason[:300],
                    scope.tenant_id,
                    run_id,
                    task_id,
                    scope.brand_id,
                    scope.organization_id,
                    scope.user_id,
                    actor_organization_id,
                    actor_organization_id,
                    actor_organization_id,
                ),
            )
            if cursor.rowcount != 1:
                raise DomainError("当前作用域不能结束此生成")

    def fetch_version(self, scope: DisplayScope, task_id: UUID, version: int) -> dict[str, object]:
        actor_organization_id = scope.actor_organization_id or scope.organization_id
        with self._tx(scope) as cursor:
            cursor.execute(
                """SELECT v.id,v.version_number,v.body,v.plan,r.model
                   FROM display_artifact_versions v
                   JOIN display_tasks t ON t.id=v.task_id AND t.tenant_id=v.tenant_id
                   JOIN display_stores s ON s.id=t.store_id AND s.tenant_id=t.tenant_id
                   JOIN display_generation_runs r ON r.id=v.run_id AND r.tenant_id=v.tenant_id
                   WHERE v.tenant_id=%s AND v.task_id=%s AND v.version_number=%s
                     AND t.brand_id=%s AND t.organization_id=%s
                     AND (t.created_by=%s OR s.execution_organization_id=%s)
                     AND (s.execution_organization_id=%s OR s.control_organization_id=%s)""",
                (
                    scope.tenant_id,
                    task_id,
                    version,
                    scope.brand_id,
                    scope.organization_id,
                    scope.user_id,
                    actor_organization_id,
                    actor_organization_id,
                    actor_organization_id,
                ),
            )
            row = self._one(cursor, "找不到该陈列版本")
        assert_display_artifact_integrity(row["body"], row["plan"])
        return {
            "task_id": str(task_id),
            "version_id": str(row["id"]),
            "version": int(str(row["version_number"])),
            "body": str(row["body"]),
            "model": str(row["model"]),
        }

    @staticmethod
    def _run(
        cursor: psycopg.Cursor[dict[str, object]],
        scope: DisplayScope,
        run_id: UUID,
        task_id: UUID,
        model: str,
        assets: tuple[ActiveAsset, ...],
        context: DisplayContext,
        inventory: tuple[tuple[str, int], ...],
    ) -> None:
        receipts = [{"asset_id": a.asset_id, "schema_version": a.schema_version} for a in assets]
        input_receipt = {
            "executor": model,
            "task_expression_version": context.task_expression_version,
            "store_profile_version": context.store_profile_version,
            "operator_organization": context.organization_name,
            "operator": context.operator_name,
            "products": [{"sku": sku, "facts": facts} for sku, facts in context.products],
            "product_snapshots": list(context.product_snapshots),
            "rule_bundle": context.rule_bundle.document() if context.rule_bundle is not None else None,
            "inventory": dict(inventory),
        }
        cursor.execute(
            "INSERT INTO display_generation_runs (id,tenant_id,task_id,model,status,used_assets,input_receipt) VALUES (%s,%s,%s,%s,'running',%s,%s)",
            (run_id, scope.tenant_id, task_id, model, Jsonb(receipts), Jsonb(input_receipt)),
        )

    @staticmethod
    def _object(value: object, label: str) -> dict[str, object]:
        if not isinstance(value, dict):
            raise DomainError(f"{label}数据无效")
        return cast(dict[str, object], value)

    @staticmethod
    def _optional_object(value: object, label: str) -> dict[str, object]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise DomainError(f"{label}数据无效")
        return cast(dict[str, object], value)

    @classmethod
    def _frozen_products(cls, frozen: dict[str, object]) -> tuple[tuple[str, dict[str, object]], ...]:
        """Read the products this task froze; the SKU is kept beside the facts, never inside them."""
        items = frozen.get("products")
        if not isinstance(items, list):
            raise DomainError("本次任务上下文快照商品无效")
        result: list[tuple[str, dict[str, object]]] = []
        for raw in items:
            item = cls._object(raw, "本次任务上下文快照商品")
            sku = item.get("sku")
            if not isinstance(sku, str) or not sku.strip():
                raise DomainError("本次任务上下文快照商品缺少编号")
            result.append((sku, cls._object(item.get("facts"), "本次任务上下文快照商品事实")))
        return tuple(result)

    @classmethod
    def _task_products(
        cls,
        task_input: dict[str, object],
    ) -> tuple[tuple[str, dict[str, object]], ...]:
        """Read the light display attributes this task submitted; they are not brand product facts."""
        items = task_input.get("products")
        if items is None:
            return ()
        if not isinstance(items, list):
            raise DomainError("本次任务商品资料无效")
        result: list[tuple[str, dict[str, object]]] = []
        for raw in items:
            item = cls._object(raw, "本次任务商品")
            sku = item.get("sku")
            if not isinstance(sku, str) or not sku.strip():
                raise DomainError("本次任务商品缺少编号")
            result.append((sku, item))
        return tuple(result)

    @classmethod
    def _frozen_product_snapshots(
        cls,
        frozen: dict[str, object],
    ) -> tuple[dict[str, object], ...]:
        items = frozen.get("product_snapshots")
        if not isinstance(items, list) or not items:
            raise DomainError("历史方案缺少正式商品版本快照。")
        snapshots: list[dict[str, object]] = []
        for raw in items:
            item = cls._object(raw, "本次任务冻结商品")
            digest = item.get("snapshot_digest")
            unsigned = {key: value for key, value in item.items() if key != "snapshot_digest"}
            if not isinstance(digest, str) or canonical_json_digest(unsigned) != digest:
                raise DomainError("历史方案的商品版本快照摘要不一致。")
            snapshots.append(item)
        return tuple(snapshots)

    def _formal_products(
        self,
        cursor: psycopg.Cursor[dict[str, object]],
        scope: DisplayScope,
        skus: tuple[str, ...],
    ) -> tuple[tuple[tuple[str, dict[str, object]], ...], tuple[dict[str, object], ...]]:
        cursor.execute(
            """
            SELECT product.id AS product_id, product.sku,
                   version.id AS product_version_id, version.version_number,
                   version.display_name, version.facts, version.source_kind,
                   version.source_note, version.visibility_scope,
                   version.scope_organization_ids, version.created_at
            FROM brand_products product
            JOIN brand_product_versions version
              ON version.tenant_id = product.tenant_id
             AND version.product_id = product.id
             AND version.id = product.current_version_id
            WHERE product.tenant_id = %s AND product.brand_id = %s
              AND product.status = 'active' AND product.sku = ANY(%s)
              AND (
                version.visibility_scope = 'brand_all'
                OR (
                  version.visibility_scope = 'organizations'
                  AND EXISTS (
                    SELECT 1 FROM unnest(version.scope_organization_ids) AS scoped(organization_id)
                    WHERE organization_is_same_or_descendant(
                      product.tenant_id, %s, scoped.organization_id
                    )
                  )
                )
                OR (
                  version.visibility_scope = 'headquarters'
                  AND %s = ANY(version.scope_organization_ids)
                  AND EXISTS (
                    SELECT 1 FROM organizations organization
                    WHERE organization.tenant_id = product.tenant_id
                      AND organization.id = %s
                      AND organization.organization_level = 'company'
                  )
                )
              )
            ORDER BY array_position(%s::text[], product.sku)
            """,
            (
                scope.tenant_id,
                scope.brand_id,
                list(skus),
                scope.organization_id,
                scope.organization_id,
                scope.organization_id,
                list(skus),
            ),
        )
        rows = cursor.fetchall()
        resolved = {str(row["sku"]): row for row in rows}
        missing = tuple(sku for sku in skus if sku not in resolved)
        if missing:
            raise DomainError(
                "本次清单中的商品暂不可用于当前门店：" + "、".join(missing) + "。请检查商品状态、版本或可用范围。"
            )
        products: list[tuple[str, dict[str, object]]] = []
        snapshots: list[dict[str, object]] = []
        for sku in skus:
            row = resolved[sku]
            facts = self._object(row["facts"], "正式商品事实")
            scope_organization_ids = row["scope_organization_ids"]
            if not isinstance(scope_organization_ids, (list, tuple)):
                raise DomainError("正式商品范围记录不可用。")
            version_created_at = row["created_at"]
            if not isinstance(version_created_at, datetime):
                raise DomainError("正式商品版本时间不可用。")
            visible_facts = {**facts, "name": str(row["display_name"])}
            unsigned: dict[str, object] = {
                "snapshot_version": "dm01-product-snapshot-v1",
                "product_id": str(row["product_id"]),
                "product_version_id": str(row["product_version_id"]),
                "version_number": int(str(row["version_number"])),
                "sku": sku,
                "display_name": str(row["display_name"]),
                "facts": visible_facts,
                "source_kind": str(row["source_kind"]),
                "source_note": str(row["source_note"]),
                "visibility_scope": str(row["visibility_scope"]),
                "scope_organization_ids": [str(item) for item in scope_organization_ids],
                "scope_organization_id": str(scope.organization_id),
                "version_created_at": version_created_at.isoformat(),
            }
            snapshot = {**unsigned, "snapshot_digest": canonical_json_digest(unsigned)}
            products.append((sku, visible_facts))
            snapshots.append(snapshot)
        return tuple(products), tuple(snapshots)

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


def _frozen_context(context: DisplayContext) -> dict[str, object]:
    """Everything a later revision must reproduce; the live operator is recorded per run instead."""
    return {
        "contract_version": "dm01-context-snapshot-v2",
        "frozen_for": "display_task",
        "brand_name": context.brand_name,
        "organization_name": context.organization_name,
        "store_name": context.store_name,
        "task_expression_version": context.task_expression_version,
        "task_expression": context.task_expression,
        "store_profile_version": context.store_profile_version,
        "rail_profile": context.rail_profile,
        "products": [{"sku": sku, "facts": facts} for sku, facts in context.products],
        "product_snapshots": list(context.product_snapshots),
        "rule_bundle": context.rule_bundle.document() if context.rule_bundle is not None else None,
    }
