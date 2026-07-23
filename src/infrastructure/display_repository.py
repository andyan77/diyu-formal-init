from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.ports.display_repository import DisplayRepository
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

    def load_context(self, scope: DisplayScope) -> DisplayContext | None:
        with self._tx(scope) as cursor:
            cursor.execute(
                """SELECT b.name brand_name, u.display_name operator_name, o.name organization_name,
                          p.version policy_version, p.body policy, s.name store_name,
                          s.profile_version, s.rail_profile
                   FROM brands b JOIN users u ON u.id=%s AND u.tenant_id=b.tenant_id
                   JOIN organizations o ON o.id=u.organization_id AND o.tenant_id=u.tenant_id
                   JOIN display_policies p ON p.brand_id=b.id AND p.tenant_id=b.tenant_id
                   JOIN display_stores s ON s.brand_id=b.id AND s.tenant_id=b.tenant_id
                      AND s.execution_organization_id=%s
                   WHERE b.tenant_id=%s AND b.id=%s AND u.organization_id=%s""",
                (
                    scope.user_id,
                    scope.organization_id,
                    scope.tenant_id,
                    scope.brand_id,
                    scope.organization_id,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            cursor.execute(
                "SELECT sku, facts FROM brand_products WHERE tenant_id=%s AND brand_id=%s ORDER BY sku",
                (scope.tenant_id, scope.brand_id),
            )
            products = tuple((str(item["sku"]), str(item["facts"])) for item in cursor.fetchall())
        return DisplayContext(
            str(row["brand_name"]),
            str(row["organization_name"]),
            str(row["operator_name"]),
            str(row["policy_version"]),
            str(row["policy"]),
            str(row["store_name"]),
            str(row["profile_version"]),
            str(row["rail_profile"]),
            products,
        )

    def load_assets(self, revision: bool) -> tuple[ActiveAsset, ...]:
        with (
            psycopg.connect(self._database_url, row_factory=dict_row) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """SELECT a.asset_id, a.schema_version, a.asset_type, a.display_name, a.structured_body
                   FROM system_domain_assets a JOIN system_asset_activations x ON x.asset_id=a.asset_id
                   WHERE a.status='active' AND x.consumer='display-merchandising / DM01' ORDER BY a.asset_id"""
            )
            rows = cursor.fetchall()
        excluded = {"G-REV-003", "GM-REVISE-001"} if not revision else set()
        return tuple(
            ActiveAsset(
                str(row["asset_id"]),
                str(row["schema_version"]),
                str(row["asset_type"]),
                str(row["display_name"]),
                str(row["structured_body"]),
            )
            for row in rows
            if str(row["asset_id"]) not in excluded
        )

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
        with self._tx(scope) as cursor:
            cursor.execute(
                "SELECT id FROM display_stores WHERE tenant_id=%s AND brand_id=%s AND execution_organization_id=%s",
                (scope.tenant_id, scope.brand_id, scope.organization_id),
            )
            store_id = UUID(str(self._one(cursor, "当前组织没有可用陈列门店")["id"]))
            cursor.execute(
                "INSERT INTO display_tasks (id, tenant_id, brand_id, organization_id, created_by, store_id, inventory_text, inventory) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    task_id,
                    scope.tenant_id,
                    scope.brand_id,
                    scope.organization_id,
                    scope.user_id,
                    store_id,
                    inventory_text,
                    Jsonb(dict(inventory)),
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
        with self._tx(scope) as cursor:
            cursor.execute(
                "SELECT inventory FROM display_tasks WHERE tenant_id=%s AND id=%s AND brand_id=%s AND organization_id=%s AND created_by=%s FOR UPDATE",
                (scope.tenant_id, task_id, scope.brand_id, scope.organization_id, scope.user_id),
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
        with self._tx(scope) as cursor:
            cursor.execute(
                "SELECT id FROM display_tasks WHERE tenant_id=%s AND id=%s AND brand_id=%s AND organization_id=%s AND created_by=%s",
                (scope.tenant_id, task_id, scope.brand_id, scope.organization_id, scope.user_id),
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
                    str(artifact["body"]),
                    Jsonb(artifact["plan"]),
                    scope.user_id,
                ),
            )
        return {
            "task_id": str(task_id),
            "version_id": str(version_id),
            "version": next_version,
            "body": artifact["body"],
            "model": model,
        }

    def fail_run(self, scope: DisplayScope, task_id: UUID, run_id: UUID, reason: str) -> None:
        with self._tx(scope) as cursor:
            cursor.execute(
                "UPDATE display_generation_runs r SET status='failed',failure_reason=%s,completed_at=now() FROM display_tasks t WHERE r.tenant_id=%s AND r.id=%s AND r.task_id=%s AND r.status='running' AND t.id=r.task_id AND t.tenant_id=r.tenant_id AND t.brand_id=%s AND t.organization_id=%s AND t.created_by=%s",
                (
                    reason[:300],
                    scope.tenant_id,
                    run_id,
                    task_id,
                    scope.brand_id,
                    scope.organization_id,
                    scope.user_id,
                ),
            )
            if cursor.rowcount != 1:
                raise DomainError("当前作用域不能结束此生成")

    def fetch_version(self, scope: DisplayScope, task_id: UUID, version: int) -> dict[str, object]:
        with self._tx(scope) as cursor:
            cursor.execute(
                "SELECT v.id,v.version_number,v.body,r.model FROM display_artifact_versions v JOIN display_tasks t ON t.id=v.task_id AND t.tenant_id=v.tenant_id JOIN display_generation_runs r ON r.id=v.run_id AND r.tenant_id=v.tenant_id WHERE v.tenant_id=%s AND v.task_id=%s AND v.version_number=%s AND t.brand_id=%s AND t.organization_id=%s AND t.created_by=%s",
                (
                    scope.tenant_id,
                    task_id,
                    version,
                    scope.brand_id,
                    scope.organization_id,
                    scope.user_id,
                ),
            )
            row = self._one(cursor, "找不到该陈列版本")
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
            "brand_standard_version": context.policy_version,
            "store_profile_version": context.store_profile_version,
            "operator_organization": context.organization_name,
            "products": [{"sku": sku, "facts": facts} for sku, facts in context.products],
            "inventory": dict(inventory),
        }
        cursor.execute(
            "INSERT INTO display_generation_runs (id,tenant_id,task_id,model,status,used_assets,input_receipt) VALUES (%s,%s,%s,%s,'running',%s,%s)",
            (run_id, scope.tenant_id, task_id, model, Jsonb(receipts), Jsonb(input_receipt)),
        )
