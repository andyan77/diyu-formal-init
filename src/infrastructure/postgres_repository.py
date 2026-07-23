from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.ports.content_repository import ContentRepository
from src.shared.errors import DomainError
from src.shared.types import ActiveAsset, BrandContext, TrustedScope


class PostgresContentRepository(ContentRepository):
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    @contextmanager
    def _tx(self, scope: TrustedScope) -> Iterator[psycopg.Cursor[dict[str, object]]]:
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

    def load_brand_context(self, scope: TrustedScope) -> BrandContext:
        with self._tx(scope) as cursor:
            cursor.execute(
                """
                SELECT b.name AS brand_name, b.positioning, b.decision_order, b.tone, a.name AS account_name,
                       u.display_name AS operator_name, o.name AS organization_name,
                       cr.name AS content_role_name, cr.voice_boundary, ba.description AS audience_description,
                       b.strategy_version, a.channel
                FROM brands b
                JOIN content_accounts a ON a.brand_id = b.id AND a.tenant_id = b.tenant_id
                JOIN auth_grants g ON g.account_id = a.id AND g.tenant_id = a.tenant_id
                JOIN users u ON u.id = g.user_id AND u.tenant_id = g.tenant_id
                JOIN organizations o ON o.id = u.organization_id AND o.tenant_id = u.tenant_id
                JOIN account_content_roles acr ON acr.account_id = a.id AND acr.tenant_id = a.tenant_id
                JOIN content_roles cr ON cr.id = acr.content_role_id AND cr.tenant_id = acr.tenant_id
                    AND cr.brand_id = b.id
                JOIN brand_audiences ba ON ba.brand_id = b.id AND ba.tenant_id = b.tenant_id
                WHERE b.tenant_id = %s AND b.id = %s AND a.id = %s AND g.user_id = %s
                  AND a.enabled AND g.enabled AND u.enabled
                """,
                (scope.tenant_id, scope.brand_id, scope.account_id, scope.user_id),
            )
            row = self._one(cursor, "当前身份没有可用内容账号授权")
        return BrandContext(
            brand_name=str(row["brand_name"]),
            positioning=str(row["positioning"]),
            decision_order=str(row["decision_order"]),
            tone=str(row["tone"]),
            account_name=str(row["account_name"]),
            operator_name=str(row["operator_name"]),
            organization_name=str(row["organization_name"]),
            content_role_name=str(row["content_role_name"]),
            content_role_boundary=str(row["voice_boundary"]),
            audience_description=str(row["audience_description"]),
            strategy_version=str(row["strategy_version"]),
            platform=str(row["channel"]),
            media_format="视频",
            production_conditions="未说明时按一人一部手机可完成的拍摄、录音和剪辑条件编写。",
        )

    def create_task_and_running_run(
        self,
        scope: TrustedScope,
        weak_seed: str,
        parent_version_id: UUID | None,
        model: str,
        used_assets: tuple[ActiveAsset, ...],
    ) -> tuple[UUID, UUID, str | None]:
        task_id, run_id = uuid4(), uuid4()
        with self._tx(scope) as cursor:
            prior_body: str | None = None
            if parent_version_id is not None:
                cursor.execute(
                    """
                    SELECT cv.body FROM content_versions cv
                    JOIN business_tasks t ON t.id = cv.task_id AND t.tenant_id = cv.tenant_id
                    WHERE cv.tenant_id = %s AND cv.id = %s
                      AND t.brand_id = %s AND t.account_id = %s AND t.created_by = %s
                    """,
                    (
                        scope.tenant_id,
                        parent_version_id,
                        scope.brand_id,
                        scope.account_id,
                        scope.user_id,
                    ),
                )
                row = self._one(cursor, "只能明确复用当前用户当前作用域中的内容")
                prior_body = str(row["body"])
            cursor.execute(
                """
                INSERT INTO business_tasks
                    (id, tenant_id, brand_id, account_id, created_by, weak_seed, parent_version_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    task_id,
                    scope.tenant_id,
                    scope.brand_id,
                    scope.account_id,
                    scope.user_id,
                    weak_seed,
                    parent_version_id,
                ),
            )
            cursor.execute(
                """
                INSERT INTO generation_runs (id, tenant_id, task_id, model, status, used_assets)
                VALUES (%s, %s, %s, %s, 'running', %s)
                """,
                (run_id, scope.tenant_id, task_id, model, Jsonb(self._asset_receipts(used_assets))),
            )
            self._event(
                cursor,
                scope,
                "generation.started",
                "generation_run",
                run_id,
                {"task_id": str(task_id)},
            )
        return task_id, run_id, prior_body

    def complete_run_with_version(
        self,
        scope: TrustedScope,
        task_id: UUID,
        run_id: UUID,
        outline: str,
        body: str,
        model: str,
        latency_ms: int,
        retry_count: int,
        provider_usage: dict[str, int] | None,
    ) -> dict[str, object]:
        version_id = uuid4()
        with self._tx(scope) as cursor:
            cursor.execute(
                """
                SELECT t.id FROM business_tasks t
                JOIN generation_runs r ON r.task_id = t.id AND r.tenant_id = t.tenant_id
                WHERE t.tenant_id = %s AND t.id = %s AND t.brand_id = %s
                  AND t.account_id = %s AND t.created_by = %s
                  AND r.id = %s AND r.status = 'running'
                FOR UPDATE
                """,
                (
                    scope.tenant_id,
                    task_id,
                    scope.brand_id,
                    scope.account_id,
                    scope.user_id,
                    run_id,
                ),
            )
            self._one(cursor, "当前作用域不能完成此生成")
            cursor.execute(
                "SELECT id, current_version FROM content_items WHERE tenant_id = %s AND task_id = %s FOR UPDATE",
                (scope.tenant_id, task_id),
            )
            item = cursor.fetchone()
            if item is None:
                item_id, next_version = uuid4(), 1
                cursor.execute(
                    "INSERT INTO content_items (id, tenant_id, task_id, current_version) VALUES (%s, %s, %s, %s)",
                    (item_id, scope.tenant_id, task_id, next_version),
                )
            else:
                item_id = UUID(str(item["id"]))
                current_version = item["current_version"]
                if not isinstance(current_version, int):
                    raise DomainError("内容版本数据无效")
                next_version = current_version + 1
                cursor.execute(
                    "UPDATE content_items SET current_version = %s WHERE tenant_id = %s AND id = %s",
                    (next_version, scope.tenant_id, item_id),
                )
            cursor.execute(
                """
                UPDATE generation_runs
                SET status = 'succeeded', model = %s, latency_ms = %s, retry_count = %s,
                    provider_usage = %s, completed_at = now()
                WHERE tenant_id = %s AND id = %s AND task_id = %s AND status = 'running'
                """,
                (
                    model,
                    latency_ms,
                    retry_count,
                    Jsonb(provider_usage) if provider_usage else None,
                    scope.tenant_id,
                    run_id,
                    task_id,
                ),
            )
            if cursor.rowcount != 1:
                raise DomainError("生成运行不存在或已结束")
            cursor.execute(
                """
                INSERT INTO content_versions
                    (id, tenant_id, item_id, task_id, run_id, version_number, outline, body, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    version_id,
                    scope.tenant_id,
                    item_id,
                    task_id,
                    run_id,
                    next_version,
                    outline,
                    body,
                    scope.user_id,
                ),
            )
            self._event(
                cursor,
                scope,
                "content.version_created",
                "content_version",
                version_id,
                {"task_id": str(task_id), "version": next_version, "run_id": str(run_id)},
            )
        return {
            "task_id": str(task_id),
            "version_id": str(version_id),
            "version": next_version,
            "outline": outline,
            "body": body,
            "model": model,
        }

    def fail_run(self, scope: TrustedScope, task_id: UUID, run_id: UUID, reason: str) -> None:
        with self._tx(scope) as cursor:
            cursor.execute(
                """
                UPDATE generation_runs r SET status = 'failed', failure_reason = %s, completed_at = now()
                FROM business_tasks t
                WHERE r.tenant_id = %s AND r.id = %s AND r.task_id = %s AND r.status = 'running'
                  AND t.id = r.task_id AND t.tenant_id = r.tenant_id
                  AND t.brand_id = %s AND t.account_id = %s AND t.created_by = %s
                """,
                (
                    reason[:300],
                    scope.tenant_id,
                    run_id,
                    task_id,
                    scope.brand_id,
                    scope.account_id,
                    scope.user_id,
                ),
            )
            if cursor.rowcount != 1:
                raise DomainError("当前作用域不能结束此生成")
            self._event(
                cursor,
                scope,
                "generation.failed",
                "generation_run",
                run_id,
                {"task_id": str(task_id)},
            )

    def revise_task(
        self,
        scope: TrustedScope,
        task_id: UUID,
        instruction: str,
        model: str,
        used_assets: tuple[ActiveAsset, ...],
    ) -> tuple[UUID, UUID, str]:
        run_id = uuid4()
        with self._tx(scope) as cursor:
            cursor.execute(
                """
                SELECT weak_seed FROM business_tasks
                WHERE tenant_id = %s AND id = %s AND brand_id = %s AND account_id = %s AND created_by = %s
                FOR UPDATE
                """,
                (scope.tenant_id, task_id, scope.brand_id, scope.account_id, scope.user_id),
            )
            task = self._one(cursor, "找不到当前租户中的内容任务")
            cursor.execute(
                "SELECT id FROM content_versions WHERE tenant_id = %s AND task_id = %s ORDER BY version_number DESC LIMIT 1",
                (scope.tenant_id, task_id),
            )
            version = self._one(cursor, "原版本不存在，不能修改")
            parent_version_id = UUID(str(version["id"]))
            cursor.execute(
                "UPDATE business_tasks SET revision_instruction = %s WHERE tenant_id = %s AND id = %s",
                (instruction, scope.tenant_id, task_id),
            )
            cursor.execute(
                """
                INSERT INTO generation_runs (id, tenant_id, task_id, model, status, used_assets)
                VALUES (%s, %s, %s, %s, 'running', %s)
                """,
                (run_id, scope.tenant_id, task_id, model, Jsonb(self._asset_receipts(used_assets))),
            )
            self._event(
                cursor,
                scope,
                "content.revision_requested",
                "business_task",
                task_id,
                {"run_id": str(run_id)},
            )
        return run_id, parent_version_id, str(task["weak_seed"])

    def fetch_version(self, scope: TrustedScope, task_id: UUID, version: int) -> dict[str, object]:
        with self._tx(scope) as cursor:
            cursor.execute(
                """
                SELECT cv.id, cv.task_id, cv.version_number, cv.outline, cv.body, cv.created_at, gr.model
                FROM content_versions cv
                JOIN generation_runs gr ON gr.id = cv.run_id AND gr.tenant_id = cv.tenant_id
                JOIN business_tasks t ON t.id = cv.task_id AND t.tenant_id = cv.tenant_id
                WHERE cv.tenant_id = %s AND cv.task_id = %s AND cv.version_number = %s
                  AND t.brand_id = %s AND t.account_id = %s AND t.created_by = %s
                """,
                (
                    scope.tenant_id,
                    task_id,
                    version,
                    scope.brand_id,
                    scope.account_id,
                    scope.user_id,
                ),
            )
            row = self._one(cursor, "找不到该版本")
        return {
            "version_id": str(row["id"]),
            "task_id": str(row["task_id"]),
            "version": self._integer(row["version_number"]),
            "outline": str(row["outline"]),
            "body": str(row["body"]),
            "model": str(row["model"]),
            "created_at": row["created_at"],
        }

    def fetch_version_body(self, scope: TrustedScope, version_id: UUID) -> str:
        with self._tx(scope) as cursor:
            cursor.execute(
                """
                SELECT cv.body FROM content_versions cv
                JOIN business_tasks t ON t.id = cv.task_id AND t.tenant_id = cv.tenant_id
                WHERE cv.tenant_id = %s AND cv.id = %s
                  AND t.brand_id = %s AND t.account_id = %s AND t.created_by = %s
                """,
                (scope.tenant_id, version_id, scope.brand_id, scope.account_id, scope.user_id),
            )
            row = self._one(cursor, "找不到可承接的历史版本")
        return str(row["body"])

    def save_version(self, scope: TrustedScope, version_id: UUID) -> dict[str, object]:
        with self._tx(scope) as cursor:
            cursor.execute(
                """
                SELECT cv.id FROM content_versions cv
                JOIN business_tasks t ON t.id = cv.task_id AND t.tenant_id = cv.tenant_id
                WHERE cv.tenant_id = %s AND cv.id = %s
                  AND t.brand_id = %s AND t.account_id = %s AND t.created_by = %s
                """,
                (scope.tenant_id, version_id, scope.brand_id, scope.account_id, scope.user_id),
            )
            self._one(cursor, "找不到可保存版本")
            cursor.execute(
                """
                INSERT INTO saved_content_versions (id, tenant_id, version_id, user_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id, version_id, user_id) DO UPDATE SET saved_at = now()
                RETURNING saved_at
                """,
                (uuid4(), scope.tenant_id, version_id, scope.user_id),
            )
            saved_at = self._one(cursor, "保存失败")["saved_at"]
            self._event(cursor, scope, "content.saved", "content_version", version_id, {})
        return {"version_id": str(version_id), "saved_at": saved_at}

    def latest_visible_version(self, scope: TrustedScope) -> UUID | None:
        with self._tx(scope) as cursor:
            cursor.execute(
                """
                SELECT cv.id FROM content_versions cv
                JOIN business_tasks t ON t.id = cv.task_id AND t.tenant_id = cv.tenant_id
                WHERE cv.tenant_id = %s AND t.brand_id = %s AND t.account_id = %s AND t.created_by = %s
                ORDER BY cv.created_at DESC LIMIT 1
                """,
                (scope.tenant_id, scope.brand_id, scope.account_id, scope.user_id),
            )
            row = cursor.fetchone()
        return UUID(str(row["id"])) if row is not None else None

    def task_seed(self, scope: TrustedScope, task_id: UUID) -> str:
        with self._tx(scope) as cursor:
            cursor.execute(
                """
                SELECT weak_seed FROM business_tasks
                WHERE tenant_id = %s AND id = %s AND brand_id = %s AND account_id = %s AND created_by = %s
                """,
                (scope.tenant_id, task_id, scope.brand_id, scope.account_id, scope.user_id),
            )
            row = self._one(cursor, "找不到当前作用域中的内容任务")
        return str(row["weak_seed"])

    def load_active_assets(self, scope: TrustedScope, weak_seed: str) -> tuple[ActiveAsset, ...]:
        with self._tx(scope) as cursor:
            cursor.execute(
                """
                SELECT a.asset_id, a.schema_version, a.asset_type, a.display_name, a.structured_body
                FROM system_domain_assets a
                JOIN system_asset_activations active ON active.asset_id = a.asset_id
                WHERE a.status = 'active' ORDER BY a.asset_id
                """
            )
            rows = cursor.fetchall()
        return tuple(
            self._active_asset(row)
            for row in rows
            if self._applies(str(row["asset_id"]), weak_seed)
        )

    @staticmethod
    def _event(
        cursor: psycopg.Cursor[dict[str, object]],
        scope: TrustedScope,
        event_type: str,
        entity_type: str,
        entity_id: UUID,
        metadata: dict[str, object],
    ) -> None:
        cursor.execute(
            """
            INSERT INTO activity_events (id, tenant_id, actor_id, event_type, entity_type, entity_id, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uuid4(),
                scope.tenant_id,
                scope.user_id,
                event_type,
                entity_type,
                entity_id,
                Jsonb(metadata),
            ),
        )

    @staticmethod
    def _integer(value: object) -> int:
        if not isinstance(value, int):
            raise DomainError("内容版本数据无效")
        return value

    @staticmethod
    def _asset_receipts(assets: tuple[ActiveAsset, ...]) -> list[dict[str, str]]:
        return [
            {"asset_id": asset.asset_id, "schema_version": asset.schema_version} for asset in assets
        ]

    @staticmethod
    def _active_asset(row: dict[str, object]) -> ActiveAsset:
        body = row["structured_body"]
        if not isinstance(body, dict):
            raise DomainError("系统领域资产数据无效")
        summary = (
            body.get("statement") or body.get("name") or body.get("title") or row["display_name"]
        )
        return ActiveAsset(
            asset_id=str(row["asset_id"]),
            schema_version=str(row["schema_version"]),
            asset_type=str(row["asset_type"]),
            display_name=str(row["display_name"]),
            body=str(summary),
        )

    @staticmethod
    def _applies(asset_id: str, weak_seed: str) -> bool:
        if asset_id == "B-TPO-001":
            return any(word in weak_seed for word in ("会", "正式", "工作", "见", "场合"))
        if asset_id == "C-COMMUTE-001":
            return any(
                word in weak_seed for word in ("之后", "后", "再", "转身", "接孩子", "接人", "换场")
            )
        return asset_id in {"D-DIRECT-001", "D-CRAFT-001"}
