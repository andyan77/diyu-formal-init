from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.ports.content_repository import ContentRepository
from src.shared.content_origin import aigc_disclosure, is_ai_generated_content
from src.shared.errors import DomainError
from src.shared.types import (
    ActiveAsset,
    BrandContext,
    ContentProduct,
    ContentTarget,
    FactRepairReceipt,
    MediaFormat,
    PlatformDirection,
    ProductFact,
    RecompileSource,
    TrustedScope,
)


class PostgresContentRepository(ContentRepository):
    def __init__(
        self,
        database_url: str,
        store_content_account_id: UUID | None = None,
        active_product_refs: tuple[str, ...] = (),
    ) -> None:
        self._database_url = database_url
        self._store_content_account_id = store_content_account_id
        self._active_product_refs = active_product_refs

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

    def load_brand_context(
        self, scope: TrustedScope, media_format: MediaFormat, production_conditions: str
    ) -> BrandContext:
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
            media_format="图文" if media_format == "graphic" else "视频",
            production_conditions=production_conditions,
        )

    def create_task_and_running_run(
        self,
        scope: TrustedScope,
        weak_seed: str,
        primary_product: ContentProduct,
        parent_version_id: UUID | None,
        model: str,
        used_assets: tuple[ActiveAsset, ...],
        context: BrandContext,
        products: tuple[ProductFact, ...],
        target: ContentTarget,
        media_format: MediaFormat,
        platform_direction: PlatformDirection,
        source_description: str | None,
        production_conditions: str,
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
                      AND t.brand_id = %s AND t.created_by = %s
                    """,
                    (
                        scope.tenant_id,
                        parent_version_id,
                        scope.brand_id,
                        scope.user_id,
                    ),
                )
                row = self._one(cursor, "只能明确复用当前用户当前作用域中的内容")
                prior_body = str(row["body"])
            cursor.execute(
                """
                INSERT INTO business_tasks
                    (id, tenant_id, brand_id, account_id, created_by, weak_seed, primary_content_product, product_refs, parent_version_id, media_format, production_conditions)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    task_id,
                    scope.tenant_id,
                    scope.brand_id,
                    scope.account_id,
                    scope.user_id,
                    weak_seed,
                    primary_product,
                    Jsonb([product.sku for product in products]),
                    parent_version_id,
                    media_format,
                    production_conditions,
                ),
            )
            cursor.execute(
                """
                INSERT INTO generation_runs (id, tenant_id, task_id, model, status, used_assets, input_receipt)
                VALUES (%s, %s, %s, %s, 'running', %s, %s)
                """,
                (
                    run_id,
                    scope.tenant_id,
                    task_id,
                    model,
                    Jsonb(self._asset_receipts(used_assets)),
                    Jsonb(
                        self._input_receipt(
                            primary_product,
                            context,
                            products,
                            target,
                            platform_direction,
                            parent_version_id,
                            source_description,
                        )
                    ),
                ),
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
        product_contract: dict[str, str],
        fact_repair_receipts: tuple[FactRepairReceipt, ...],
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
                    (id, tenant_id, item_id, task_id, run_id, version_number, outline, body, product_contract, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    Jsonb(product_contract),
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
            if fact_repair_receipts:
                self._event(
                    cursor,
                    scope,
                    "generation.fact_boundary_repaired",
                    "generation_run",
                    run_id,
                    {
                        "fields": [
                            {"field": receipt.field, "fragments": list(receipt.fragments)}
                            for receipt in fact_repair_receipts
                        ]
                    },
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
        context: BrandContext,
        products: tuple[ProductFact, ...],
        target: ContentTarget,
        platform_direction: PlatformDirection,
        production_conditions: str,
    ) -> tuple[UUID, UUID, str, ContentProduct]:
        run_id = uuid4()
        with self._tx(scope) as cursor:
            cursor.execute(
                """
                SELECT weak_seed, primary_content_product FROM business_tasks
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
                "UPDATE business_tasks SET revision_instruction = %s, production_conditions = %s WHERE tenant_id = %s AND id = %s",
                (instruction, production_conditions, scope.tenant_id, task_id),
            )
            cursor.execute(
                """
                INSERT INTO generation_runs (id, tenant_id, task_id, model, status, used_assets, input_receipt)
                VALUES (%s, %s, %s, %s, 'running', %s, %s)
                """,
                (
                    run_id,
                    scope.tenant_id,
                    task_id,
                    model,
                    Jsonb(self._asset_receipts(used_assets)),
                    Jsonb(
                        self._input_receipt(
                            self._product(task["primary_content_product"]),
                            context,
                            products,
                            target,
                            platform_direction,
                            parent_version_id,
                            None,
                        )
                    ),
                ),
            )
            self._event(
                cursor,
                scope,
                "content.revision_requested",
                "business_task",
                task_id,
                {"run_id": str(run_id)},
            )
        return (
            run_id,
            parent_version_id,
            str(task["weak_seed"]),
            self._product(task["primary_content_product"]),
        )

    def fetch_version(self, scope: TrustedScope, task_id: UUID, version: int) -> dict[str, object]:
        with self._tx(scope) as cursor:
            cursor.execute(
                """
                SELECT cv.id, cv.task_id, cv.version_number, cv.outline, cv.body, cv.created_at, gr.model,
                       t.media_format, a.channel, parent_cv.version_number AS parent_version_number,
                       parent_a.channel AS parent_channel, parent_t.media_format AS parent_media_format
                FROM content_versions cv
                JOIN generation_runs gr ON gr.id = cv.run_id AND gr.tenant_id = cv.tenant_id
                JOIN business_tasks t ON t.id = cv.task_id AND t.tenant_id = cv.tenant_id
                JOIN content_accounts a ON a.id = t.account_id AND a.tenant_id = t.tenant_id
                LEFT JOIN content_versions parent_cv ON parent_cv.id = t.parent_version_id AND parent_cv.tenant_id = t.tenant_id
                LEFT JOIN business_tasks parent_t ON parent_t.id = parent_cv.task_id AND parent_t.tenant_id = parent_cv.tenant_id
                LEFT JOIN content_accounts parent_a ON parent_a.id = parent_t.account_id AND parent_a.tenant_id = parent_t.tenant_id
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
        parent_channel = row["parent_channel"]
        parent_media = row["parent_media_format"]
        parent_version = row["parent_version_number"]
        adapted_from = None
        if (
            isinstance(parent_channel, str)
            and parent_media in {"video", "graphic"}
            and isinstance(parent_version, int)
            and (parent_channel, parent_media) != (row["channel"], row["media_format"])
        ):
            adapted_from = f"由{parent_channel}{'图文' if parent_media == 'graphic' else '视频'} V{parent_version} 改编"
        media_format = row["media_format"]
        channel = row["channel"]
        if not isinstance(media_format, str) or not isinstance(channel, str):
            raise DomainError("内容版本目标数据无效")
        disclosure, release_reminder = aigc_disclosure(row["model"])
        return {
            "version_id": str(row["id"]),
            "task_id": str(row["task_id"]),
            "version": self._integer(row["version_number"]),
            "outline": str(row["outline"]),
            "body": str(row["body"]),
            "model": str(row["model"]),
            "ai_generated": is_ai_generated_content(row["model"]),
            "aigc_label": disclosure,
            "aigc_release_reminder": release_reminder,
            "created_at": row["created_at"],
            "target": self._target_label(channel, media_format),
            "target_key": self._target_from_channel_media(channel, media_format),
            "adapted_from": adapted_from,
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

    def latest_task_version(self, scope: TrustedScope, task_id: UUID) -> UUID:
        with self._tx(scope) as cursor:
            cursor.execute(
                """
                SELECT cv.id FROM content_versions cv
                JOIN business_tasks t ON t.id = cv.task_id AND t.tenant_id = cv.tenant_id
                WHERE cv.tenant_id = %s AND cv.task_id = %s AND t.brand_id = %s
                  AND t.account_id = %s AND t.created_by = %s
                ORDER BY cv.version_number DESC LIMIT 1
                """,
                (scope.tenant_id, task_id, scope.brand_id, scope.account_id, scope.user_id),
            )
            row = self._one(cursor, "找不到当前版本，不能改编")
        return UUID(str(row["id"]))

    def task_details(
        self, scope: TrustedScope, task_id: UUID
    ) -> tuple[str, ContentProduct, MediaFormat, str]:
        with self._tx(scope) as cursor:
            cursor.execute(
                """
                SELECT weak_seed, primary_content_product, media_format, production_conditions FROM business_tasks
                WHERE tenant_id = %s AND id = %s AND brand_id = %s AND account_id = %s AND created_by = %s
                """,
                (scope.tenant_id, task_id, scope.brand_id, scope.account_id, scope.user_id),
            )
            row = self._one(cursor, "找不到当前作用域中的内容任务")
        media_format = row["media_format"]
        if media_format not in {"video", "graphic"}:
            raise DomainError("内容任务的媒体格式数据无效")
        return (
            str(row["weak_seed"]),
            self._product(row["primary_content_product"]),
            cast(MediaFormat, media_format),
            str(row["production_conditions"]),
        )

    def load_recompile_source(self, scope: TrustedScope, version_id: UUID) -> RecompileSource:
        with self._tx(scope) as cursor:
            cursor.execute(
                """
                SELECT t.id AS task_id, t.weak_seed, t.primary_content_product, t.product_refs, t.media_format,
                       cv.body, cv.version_number, a.channel
                FROM content_versions cv
                JOIN business_tasks t ON t.id = cv.task_id AND t.tenant_id = cv.tenant_id
                JOIN content_accounts a ON a.id = t.account_id AND a.tenant_id = t.tenant_id
                WHERE cv.tenant_id = %s AND cv.id = %s AND t.brand_id = %s AND t.created_by = %s
                """,
                (scope.tenant_id, version_id, scope.brand_id, scope.user_id),
            )
            row = self._one(cursor, "只能改编当前用户当前品牌中的明确版本")
        refs = row["product_refs"]
        if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
            raise DomainError("源版本商品引用无效")
        source_media = row["media_format"]
        if source_media not in {"video", "graphic"}:
            raise DomainError("源版本媒体格式无效")
        media_label = "图文" if source_media == "graphic" else "视频"
        return RecompileSource(
            task_id=UUID(str(row["task_id"])),
            weak_seed=str(row["weak_seed"]),
            primary_product=self._product(row["primary_content_product"]),
            products=self._product_facts_for_refs(scope, tuple(refs)),
            body=str(row["body"]),
            source_description=f"由{row['channel']}{media_label} V{row['version_number']} 改编",
            source_target=self._target_from_channel_media(str(row["channel"]), str(source_media)),
        )

    def load_active_assets(
        self,
        scope: TrustedScope,
        primary_product: ContentProduct,
        weak_seed: str,
        products: tuple[ProductFact, ...],
        target: ContentTarget,
        is_recompile: bool,
    ) -> tuple[ActiveAsset, ...]:
        with self._tx(scope) as cursor:
            cursor.execute(
                """
                SELECT a.asset_id, a.schema_version, a.asset_type, a.display_name, a.structured_body, active.consumer
                FROM system_domain_assets a
                JOIN system_asset_activations active ON active.asset_id = a.asset_id
                WHERE a.status = 'active' AND a.superseded_by IS NULL
                  AND (a.valid_until IS NULL OR a.valid_until >= CURRENT_DATE)
                  AND active.consumer = ANY(%s) ORDER BY a.asset_id
                """,
                ([self._consumer(primary_product), "content-production / M5-2-media"],),
            )
            rows = cursor.fetchall()
        return tuple(
            self._active_asset(row, primary_product, products)
            for row in rows
            if self._applies(str(row["asset_id"]), primary_product, weak_seed)
            and self._media_asset_applies(
                str(row["asset_id"]), primary_product, weak_seed, target, is_recompile
            )
        )

    def load_product_facts(self, scope: TrustedScope, weak_seed: str) -> tuple[ProductFact, ...]:
        skus = tuple(sorted(set(re.findall(r"\b[A-Z]{2}-[A-Z]\d{3}\b", weak_seed.upper()))))
        if not skus and scope.account_id == self._store_content_account_id:
            skus = self._active_product_refs
        return self._product_facts_for_refs(scope, skus)

    def load_task_product_facts(
        self, scope: TrustedScope, task_id: UUID
    ) -> tuple[ProductFact, ...]:
        with self._tx(scope) as cursor:
            cursor.execute(
                """
                SELECT product_refs FROM business_tasks
                WHERE tenant_id = %s AND id = %s AND brand_id = %s AND account_id = %s AND created_by = %s
                """,
                (scope.tenant_id, task_id, scope.brand_id, scope.account_id, scope.user_id),
            )
            row = self._one(cursor, "找不到当前作用域中的内容任务")
        stored_refs = row["product_refs"]
        if not isinstance(stored_refs, list) or not all(
            isinstance(ref, str) for ref in stored_refs
        ):
            raise DomainError("内容任务商品引用无效")
        return self._product_facts_for_refs(scope, tuple(stored_refs))

    def _product_facts_for_refs(
        self, scope: TrustedScope, refs: tuple[str, ...]
    ) -> tuple[ProductFact, ...]:
        if not refs:
            return ()
        with self._tx(scope) as cursor:
            cursor.execute(
                "SELECT sku, facts FROM brand_products WHERE tenant_id=%s AND brand_id=%s AND sku = ANY(%s)",
                (scope.tenant_id, scope.brand_id, list(refs)),
            )
            rows = cursor.fetchall()
        return tuple(
            ProductFact(str(row["sku"]), dict(row["facts"]))
            for row in rows
            if isinstance(row["facts"], dict)
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
    def _input_receipt(
        product: ContentProduct,
        context: BrandContext,
        products: tuple[ProductFact, ...],
        target: ContentTarget,
        platform_direction: PlatformDirection,
        source_version_id: UUID | None,
        source_description: str | None,
    ) -> dict[str, object]:
        return {
            "primary_content_product": product,
            "brand_strategy_version": context.strategy_version,
            "publishing_account": context.account_name,
            "content_role": context.content_role_name,
            "product_refs": [item.sku for item in products],
            "target": target,
            "target_platform": platform_direction.platform,
            "media_format": platform_direction.media_format,
            "platform_direction_version": platform_direction.version,
            "production_conditions": context.production_conditions,
            "source_version_id": str(source_version_id) if source_version_id else None,
            "source_description": source_description,
        }

    @classmethod
    def _active_asset(
        cls,
        row: dict[str, object],
        primary_product: ContentProduct,
        products: tuple[ProductFact, ...],
    ) -> ActiveAsset:
        body = row["structured_body"]
        if not isinstance(body, dict):
            raise DomainError("系统领域资产数据无效")
        asset_id = str(row["asset_id"])
        if asset_id.startswith("E-"):
            summary: object = cls._media_asset_projection(asset_id, body)
        elif primary_product == "product_truth":
            summary = cls._p2_asset_projection(asset_id, body, products)
        else:
            summary = (
                body.get("statement")
                or body.get("name")
                or body.get("title")
                or row["display_name"]
            )
        return ActiveAsset(
            asset_id=asset_id,
            schema_version=str(row["schema_version"]),
            asset_type=str(row["asset_type"]),
            display_name=str(row["display_name"]),
            body=str(summary),
        )

    @classmethod
    def _p2_asset_projection(
        cls, asset_id: str, body: dict[str, object], products: tuple[ProductFact, ...]
    ) -> str:
        """Compile only the parts of a P2 asset supported by this product input."""
        parts: list[str] = []
        if cls._p2_statement_applies(asset_id, body, products):
            statement = cls._asset_text(body.get("statement"))
            if statement:
                parts.append(f"适用理解：{statement}")
        for key, label in (
            ("not_when", "不适用边界"),
            ("anti_misuse", "防误用边界"),
            ("avoid_when", "避免条件"),
        ):
            value = cls._asset_text(body.get(key))
            if value:
                parts.append(f"{label}：{value}")
        return "；".join(parts) or "当前资料不足以启用该资产的正向主张。"

    @classmethod
    def _media_asset_projection(cls, asset_id: str, body: dict[str, object]) -> str:
        """Project only execution guidance, never legacy persistence advice or asset identifiers."""
        parts: list[str] = [cls._asset_text(body.get("name"))]
        for key in (
            "transformation_steps",
            "production_constraints",
            "avoid_when",
            "failure_patterns",
        ):
            value = cls._asset_text(body.get(key))
            if value:
                parts.append(value)
        if asset_id == "E-ADAPT-001":
            parts = [part for part in parts if "同一任务版本链" not in part and "持久" not in part]
        return (
            "；".join(part for part in parts if part)
            or "按当前媒体合同重组表达，不复用不适用制作建议。"
        )

    @staticmethod
    def _p2_statement_applies(
        asset_id: str, body: dict[str, object], products: tuple[ProductFact, ...]
    ) -> bool:
        if not isinstance(body.get("statement"), str):
            return False
        if asset_id == "A-MAT-005":
            return any(
                isinstance(product.facts.get("thickness_mm"), (int, float))
                and isinstance(product.facts.get("structure_test"), (str, bool))
                for product in products
            )
        if asset_id == "A-TRANSLATE-001":
            return any(
                any(
                    key in product.facts
                    for key in (
                        "material",
                        "material_composition",
                        "fabric_structure",
                        "craft",
                        "process",
                    )
                )
                for product in products
            )
        return asset_id == "D-EXPLAIN-001"

    @staticmethod
    def _asset_text(value: object) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return "；".join(value)
        return ""

    @staticmethod
    def _applies(asset_id: str, product: ContentProduct, weak_seed: str) -> bool:
        if product == "dressing_decision" and asset_id == "B-TPO-001":
            return any(word in weak_seed for word in ("会", "正式", "工作", "见", "场合"))
        if product == "dressing_decision" and asset_id == "C-COMMUTE-001":
            return any(
                word in weak_seed for word in ("之后", "后", "再", "转身", "接孩子", "接人", "换场")
            )
        return True

    @staticmethod
    def _media_asset_applies(
        asset_id: str,
        product: ContentProduct,
        weak_seed: str,
        target: ContentTarget,
        is_recompile: bool,
    ) -> bool:
        if not asset_id.startswith("E-"):
            return True
        if asset_id == "E-ADAPT-001":
            return is_recompile
        if asset_id == "E-FORM-006":
            return target == "xiaohongshu_graphic"
        if asset_id == "E-SOUND-001":
            return target != "xiaohongshu_graphic"
        if asset_id == "E-TEXT-001":
            return product == "visual_styling_story" or target == "xiaohongshu_graphic"
        if asset_id == "E-TIME-002":
            return any(marker in weak_seed for marker in ("压", "短", "秒"))
        if asset_id == "E-TIME-001":
            return target != "xiaohongshu_graphic"
        if asset_id in {"E-VISUAL-001", "E-VISUAL-003"}:
            return True
        return asset_id in {"E-FORM-001", "E-RESOURCE-002", "E-RESOURCE-003"}

    @staticmethod
    def _consumer(product: ContentProduct) -> str:
        return {
            "dressing_decision": "content-production / P1",
            "product_truth": "content-production / P2",
            "brand_life_narrative": "content-production / P3",
            "local_response": "content-production / P4",
            "visual_styling_story": "content-production / P5",
        }[product]

    @staticmethod
    def _product(value: object) -> ContentProduct:
        if value in {
            "dressing_decision",
            "product_truth",
            "brand_life_narrative",
            "local_response",
            "visual_styling_story",
        }:
            return cast(ContentProduct, value)
        raise DomainError("内容任务的主要产品数据无效")

    @staticmethod
    def _target_label(channel: str, media_format: str) -> str:
        labels = {
            ("抖音", "video"): "抖音视频",
            ("小红书", "video"): "小红书视频",
            ("小红书", "graphic"): "小红书图文",
            ("微信视频号", "video"): "微信视频号视频",
        }
        try:
            return labels[(channel, media_format)]
        except KeyError as exc:
            raise DomainError("当前发布账号与媒体组合不在 M5-2 范围内") from exc

    @staticmethod
    def _target_from_channel_media(channel: str, media_format: str) -> ContentTarget:
        targets: dict[tuple[str, str], ContentTarget] = {
            ("抖音", "video"): "douyin_video",
            ("小红书", "video"): "xiaohongshu_video",
            ("小红书", "graphic"): "xiaohongshu_graphic",
            ("微信视频号", "video"): "wechat_channels_video",
        }
        try:
            return targets[(channel, media_format)]
        except KeyError as exc:
            raise DomainError("当前发布账号与媒体组合不在 M5-2 范围内") from exc
