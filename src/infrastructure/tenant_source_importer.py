from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4, uuid5

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.shared.errors import DomainError
from src.shared.tenant_brand_sources import (
    TENANT_SOURCE_CONTRACT_VERSION,
    TENANT_SOURCE_NAMESPACE,
    ProductCandidateDraft,
    SourceDocumentDraft,
    freeze_source_batch,
)
from src.shared.types import TenantManagementScope

TENANT_SOURCE_IMPORT_CONTRACT_VERSION = "tenant-source-import-v1"


@dataclass(frozen=True)
class TenantSourceImportPlan:
    contract_version: str
    tenant_id: UUID
    brand_id: UUID
    manager_user_id: UUID
    source_root: Path
    batch_digest: str
    source_digests: tuple[tuple[str, str, str], ...]
    document_actions: tuple[tuple[str, str], ...]
    product_actions: tuple[tuple[str, str], ...]
    document_count: int
    segment_count: int
    product_count: int
    product_field_count: int
    product_fact_field_count: int

    def public_manifest(self) -> dict[str, object]:
        """Return provenance and counts only; private source text never leaves staging."""
        return {
            "contract_version": self.contract_version,
            "tenant_id": str(self.tenant_id),
            "brand_id": str(self.brand_id),
            "batch_digest": self.batch_digest,
            "source_contract_version": TENANT_SOURCE_CONTRACT_VERSION,
            "source_digests": [
                {
                    "source_id": source_id,
                    "version": version,
                    "normalized_sha256": digest,
                }
                for source_id, version, digest in self.source_digests
            ],
            "document_actions": [
                {"source_id": source_id, "action": action} for source_id, action in self.document_actions
            ],
            "product_actions": [{"sku": sku, "action": action} for sku, action in self.product_actions],
            "counts": {
                "documents": self.document_count,
                "segments": self.segment_count,
                "products": self.product_count,
                "product_fields": self.product_field_count,
                "product_fact_fields": self.product_fact_field_count,
            },
        }


class TenantSourceImporter:
    """Atomic first-tenant import through the tenant-scoped application role."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    @contextmanager
    def _tx(self, tenant_id: UUID) -> Iterator[psycopg.Cursor[dict[str, object]]]:
        with (
            psycopg.connect(self._database_url, row_factory=dict_row) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
            yield cursor

    @staticmethod
    def _batch_digest(documents: Sequence[SourceDocumentDraft]) -> str:
        document = [
            {
                "source_id": item.source_id,
                "source_version": item.source_version,
                "raw_sha256": item.raw_sha256,
                "normalized_sha256": item.normalized_sha256,
            }
            for item in documents
        ]
        return sha256(
            json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()

    @staticmethod
    def _scoped_id(tenant_id: UUID, *parts: str) -> UUID:
        return uuid5(TENANT_SOURCE_NAMESPACE, ":".join((str(tenant_id), *parts)))

    def dry_run(
        self,
        scope: TenantManagementScope,
        source_root: Path,
    ) -> TenantSourceImportPlan:
        documents = freeze_source_batch(source_root)
        products = tuple(product for document in documents for product in document.products)
        with self._tx(scope.tenant_id) as cursor:
            self._lock_scope(cursor, scope)
            document_actions = tuple(
                (document.source_id, self._document_action(cursor, scope, document)) for document in documents
            )
            product_actions = tuple((product.sku, self._product_action(cursor, scope, product)) for product in products)
        return TenantSourceImportPlan(
            contract_version=TENANT_SOURCE_IMPORT_CONTRACT_VERSION,
            tenant_id=scope.tenant_id,
            brand_id=scope.brand_id,
            manager_user_id=scope.user_id,
            source_root=source_root,
            batch_digest=self._batch_digest(documents),
            source_digests=tuple(
                (document.source_id, document.source_version, document.normalized_sha256) for document in documents
            ),
            document_actions=document_actions,
            product_actions=product_actions,
            document_count=len(documents),
            segment_count=sum(len(document.segments) for document in documents),
            product_count=len(products),
            product_field_count=sum(len(product.fields) for product in products),
            product_fact_field_count=sum(len(product.fact_fields) for product in products),
        )

    def apply(self, plan: TenantSourceImportPlan) -> dict[str, object]:
        documents = freeze_source_batch(plan.source_root)
        if self._batch_digest(documents) != plan.batch_digest:
            raise DomainError("源文件在 dry-run 后发生变化，请重新冻结本批资料。")
        scope = TenantManagementScope(plan.tenant_id, plan.manager_user_id, plan.brand_id)
        products = tuple(product for document in documents for product in document.products)
        with self._tx(scope.tenant_id) as cursor:
            self._lock_scope(cursor, scope)
            document_actions = tuple(
                (document.source_id, self._document_action(cursor, scope, document)) for document in documents
            )
            product_actions = tuple((product.sku, self._product_action(cursor, scope, product)) for product in products)
            if document_actions != plan.document_actions or product_actions != plan.product_actions:
                raise DomainError("数据库在 dry-run 后发生变化，请重新生成导入计划。")
            cursor.execute(
                "UPDATE brands SET public_name = '笛语', search_aliases = ARRAY['笛语服饰'] "
                "WHERE tenant_id = %s AND id = %s",
                (scope.tenant_id, scope.brand_id),
            )
            inserted_documents = 0
            inserted_segments = 0
            for document in documents:
                action = dict(document_actions)[document.source_id]
                if action == "no_op":
                    continue
                inserted_segments += self._insert_document(cursor, scope, document)
                inserted_documents += 1
            inserted_products = 0
            inserted_product_fields = 0
            for product in products:
                action = dict(product_actions)[product.sku]
                if action == "no_op":
                    continue
                inserted_product_fields += self._insert_product(cursor, scope, product)
                inserted_products += 1
            cursor.execute(
                "INSERT INTO activity_events "
                "(id, tenant_id, actor_id, event_type, entity_type, entity_id) "
                "VALUES (%s, %s, %s, 'tenant_source_batch.activated', 'brand', %s)",
                (
                    uuid4(),
                    scope.tenant_id,
                    scope.user_id,
                    scope.brand_id,
                ),
            )
        return {
            "batch_digest": plan.batch_digest,
            "inserted_documents": inserted_documents,
            "inserted_segments": inserted_segments,
            "inserted_products": inserted_products,
            "inserted_product_fields": inserted_product_fields,
        }

    @staticmethod
    def _lock_scope(
        cursor: psycopg.Cursor[dict[str, object]],
        scope: TenantManagementScope,
    ) -> None:
        cursor.execute(
            """
            SELECT brand.id
              FROM brands brand
              JOIN users manager
                ON manager.tenant_id = brand.tenant_id
               AND manager.id = %s
               AND manager.enabled = true
               AND manager.entry_kind = 'tenant_admin'
              JOIN tenant_management_grants grant_record
                ON grant_record.tenant_id = manager.tenant_id
               AND grant_record.user_id = manager.id
               AND grant_record.enabled = true
             WHERE brand.tenant_id = %s AND brand.id = %s
             FOR UPDATE OF brand
            """,
            (scope.user_id, scope.tenant_id, scope.brand_id),
        )
        if cursor.fetchone() is None:
            raise DomainError("当前自然人没有这个品牌的正式导入资格。")

    def _document_action(
        self,
        cursor: psycopg.Cursor[dict[str, object]],
        scope: TenantManagementScope,
        document: SourceDocumentDraft,
    ) -> str:
        cursor.execute(
            """
            SELECT version_record.normalized_sha256
              FROM brand_source_documents source
              JOIN brand_source_document_versions version_record
                ON version_record.tenant_id = source.tenant_id
               AND version_record.document_id = source.id
               AND version_record.source_version = %s
             WHERE source.tenant_id = %s
               AND source.brand_id = %s
               AND source.source_id = %s
            """,
            (document.source_version, scope.tenant_id, scope.brand_id, document.source_id),
        )
        row = cursor.fetchone()
        if row is None:
            return "insert_version"
        if str(row["normalized_sha256"]) != document.normalized_sha256:
            raise DomainError(f"文档 {document.source_id} {document.source_version} 已存在不同摘要，拒绝覆盖。")
        return "no_op"

    def _product_action(
        self,
        cursor: psycopg.Cursor[dict[str, object]],
        scope: TenantManagementScope,
        product: ProductCandidateDraft,
    ) -> str:
        source_digest = self._product_digest(product)
        cursor.execute(
            """
            SELECT version_record.source_note, product.record_kind
              FROM brand_products product
              LEFT JOIN brand_product_versions version_record
                ON version_record.tenant_id = product.tenant_id
               AND version_record.id = product.current_version_id
             WHERE product.tenant_id = %s
               AND product.brand_id = %s
               AND product.sku = %s
            """,
            (scope.tenant_id, scope.brand_id, product.sku),
        )
        row = cursor.fetchone()
        if row is None:
            return "insert_candidate"
        if (
            str(row["record_kind"]) == "brand_authorized_candidate"
            and str(row["source_note"]) == f"tenant-source:{source_digest}"
        ):
            return "no_op"
        return "append_formal_candidate_version"

    @staticmethod
    def _product_digest(product: ProductCandidateDraft) -> str:
        return sha256(
            json.dumps(
                {
                    "sku": product.sku,
                    "display_name": product.display_name,
                    "fields": [
                        {
                            "name": field.field_name,
                            "text": field.exact_text,
                            "levels": list(field.evidence_levels),
                            "source_digest": field.source_digest,
                        }
                        for field in product.fields
                    ],
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()

    def _insert_document(
        self,
        cursor: psycopg.Cursor[dict[str, object]],
        scope: TenantManagementScope,
        document: SourceDocumentDraft,
    ) -> int:
        document_id = self._scoped_id(scope.tenant_id, "source", document.source_id)
        version_id = self._scoped_id(
            scope.tenant_id,
            "source-version",
            document.source_id,
            document.source_version,
            document.normalized_sha256,
        )
        cursor.execute(
            """
            INSERT INTO brand_source_documents
                (id, tenant_id, brand_id, source_id, embedded_title,
                 provenance_filename, source_version, original_status,
                 activation_status, authorization_source, authorization_at,
                 status, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    CASE WHEN %s = 'brand_user_authorized' THEN now() ELSE NULL END,
                    'active', %s)
            ON CONFLICT (tenant_id, brand_id, source_id) DO UPDATE SET
                embedded_title = EXCLUDED.embedded_title,
                provenance_filename = EXCLUDED.provenance_filename,
                source_version = EXCLUDED.source_version,
                original_status = EXCLUDED.original_status,
                activation_status = EXCLUDED.activation_status,
                authorization_source = EXCLUDED.authorization_source,
                authorization_at = EXCLUDED.authorization_at,
                status = 'active',
                updated_at = now()
            """,
            (
                document_id,
                scope.tenant_id,
                scope.brand_id,
                document.source_id,
                document.embedded_title,
                document.provenance_filename,
                document.source_version,
                document.original_status,
                document.activation_status,
                document.authorization_source,
                document.activation_status,
                scope.user_id,
            ),
        )
        cursor.execute(
            """
            INSERT INTO brand_source_document_versions
                (id, tenant_id, brand_id, document_id, source_version,
                 embedded_title, provenance_filename, original_status,
                 activation_status, authorization_source, authorization_at,
                 raw_sha256, normalized_sha256, source_size, source_mtime_ns,
                 content, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    CASE WHEN %s = 'brand_user_authorized' THEN now() ELSE NULL END,
                    %s, %s, %s, %s, %s, %s)
            """,
            (
                version_id,
                scope.tenant_id,
                scope.brand_id,
                document_id,
                document.source_version,
                document.embedded_title,
                document.provenance_filename,
                document.original_status,
                document.activation_status,
                document.authorization_source,
                document.activation_status,
                document.raw_sha256,
                document.normalized_sha256,
                document.source_size,
                document.source_mtime_ns,
                document.normalized_content,
                scope.user_id,
            ),
        )
        for segment in document.segments:
            segment_id = self._scoped_id(
                scope.tenant_id,
                "segment",
                document.source_id,
                document.source_version,
                segment.segment_key,
            )
            cursor.execute(
                """
                INSERT INTO brand_source_segments
                    (id, tenant_id, brand_id, document_id, document_version_id,
                     segment_key, heading_path, source_locator, exact_text,
                     semantic_kind, evidence_level, applicability, digest)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    segment_id,
                    scope.tenant_id,
                    scope.brand_id,
                    document_id,
                    version_id,
                    segment.segment_key,
                    list(segment.heading_path),
                    segment.source_locator,
                    segment.exact_text,
                    segment.semantic_kind,
                    segment.evidence_level,
                    segment.applicability,
                    segment.digest,
                ),
            )
        cursor.execute(
            "UPDATE brand_source_documents SET current_version_id = %s WHERE tenant_id = %s AND id = %s",
            (version_id, scope.tenant_id, document_id),
        )
        return len(document.segments)

    def _insert_product(
        self,
        cursor: psycopg.Cursor[dict[str, object]],
        scope: TenantManagementScope,
        product: ProductCandidateDraft,
    ) -> int:
        cursor.execute(
            "SELECT id, fact_version FROM brand_products "
            "WHERE tenant_id = %s AND brand_id = %s AND sku = %s FOR UPDATE",
            (scope.tenant_id, scope.brand_id, product.sku),
        )
        existing = cursor.fetchone()
        product_id = (
            UUID(str(existing["id"]))
            if existing is not None
            else self._scoped_id(scope.tenant_id, "candidate-product", product.sku)
        )
        version_number = int(str(existing["fact_version"])) + 1 if existing is not None else 1
        product_digest = self._product_digest(product)
        version_id = self._scoped_id(
            scope.tenant_id,
            "candidate-product-version",
            product.sku,
            str(version_number),
            product_digest,
        )
        facts = self._product_fact_document(product)
        source_note = f"tenant-source:{product_digest}"
        if existing is None:
            cursor.execute(
                """
                INSERT INTO brand_products
                    (id, tenant_id, brand_id, sku, display_name, facts,
                     source_kind, source_note, fact_version, applicability,
                     status, updated_by, updated_at, visibility_scope,
                     current_version_id, business_data_kind, record_kind)
                VALUES (%s, %s, %s, %s, %s, %s,
                        'brand_user_authorized_candidate', %s, 1,
                        '仅限品牌授权候选商品中纯 V 级字段', 'active', %s,
                        now(), 'brand_all', NULL, 'formal_business_data',
                        'brand_authorized_candidate')
                """,
                (
                    product_id,
                    scope.tenant_id,
                    scope.brand_id,
                    product.sku,
                    product.display_name,
                    Jsonb(facts),
                    source_note,
                    scope.user_id,
                ),
            )
        cursor.execute(
            """
            INSERT INTO brand_product_versions
                (id, tenant_id, brand_id, product_id, version_number,
                 display_name, facts, source_kind, source_note, applicability,
                 visibility_scope, scope_organization_ids, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s,
                    'brand_user_authorized_candidate', %s,
                    '仅限品牌授权候选商品中纯 V 级字段', 'brand_all', '{}', %s)
            """,
            (
                version_id,
                scope.tenant_id,
                scope.brand_id,
                product_id,
                version_number,
                product.display_name,
                Jsonb(facts),
                source_note,
                scope.user_id,
            ),
        )
        cursor.execute(
            """
            UPDATE brand_products
               SET display_name = %s, facts = %s,
                   source_kind = 'brand_user_authorized_candidate',
                   source_note = %s, fact_version = %s,
                   applicability = '仅限品牌授权候选商品中纯 V 级字段',
                   status = 'active', visibility_scope = 'brand_all',
                   current_version_id = %s, updated_by = %s, updated_at = now(),
                   business_data_kind = 'formal_business_data',
                   record_kind = 'brand_authorized_candidate'
             WHERE tenant_id = %s AND brand_id = %s AND id = %s
            """,
            (
                product.display_name,
                Jsonb(facts),
                source_note,
                version_number,
                version_id,
                scope.user_id,
                scope.tenant_id,
                scope.brand_id,
                product_id,
            ),
        )
        document_id = self._scoped_id(scope.tenant_id, "source", "DIYU-CANDIDATE-PRODUCT-MASTER-001")
        inserted_fields = 0
        for field in product.fields:
            # The segment UUID above follows the parser identity. Resolve the
            # actual tenant-scoped row by its immutable source digest/locator,
            # keeping the product import independent of filename ordering.
            cursor.execute(
                """
                SELECT segment.id
                  FROM brand_source_segments segment
                 WHERE segment.tenant_id = %s
                   AND segment.document_id = %s
                   AND segment.source_locator = %s
                   AND segment.digest = %s
                """,
                (
                    scope.tenant_id,
                    document_id,
                    field.source_locator,
                    field.source_digest,
                ),
            )
            segment_row = cursor.fetchone()
            if segment_row is None:
                raise DomainError("候选商品字段无法绑定到冻结源段。")
            segment_id = UUID(str(segment_row["id"]))
            for evidence_level in field.evidence_levels:
                cursor.execute(
                    """
                    INSERT INTO brand_product_field_evidence
                        (id, tenant_id, brand_id, product_id, product_version_id,
                         field_name, exact_text, evidence_level,
                         source_document_id, source_segment_id, source_digest,
                         authorization_source, allowed_in_product_fact)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, 'TENANT-01 user-authorized import', %s)
                    """,
                    (
                        uuid4(),
                        scope.tenant_id,
                        scope.brand_id,
                        product_id,
                        version_id,
                        field.field_name,
                        field.exact_text,
                        evidence_level,
                        document_id,
                        segment_id,
                        field.source_digest,
                        field.allowed_in_product_fact and evidence_level == "V",
                    ),
                )
                inserted_fields += 1
        return inserted_fields

    @staticmethod
    def _product_fact_document(product: ProductCandidateDraft) -> dict[str, object]:
        facts: dict[str, object] = {
            "category": "",
            "colors": [],
            "material_or_structure": "",
            "silhouette": "",
            "observable_features": "",
        }
        observable: list[str] = []
        for field in product.fields:
            if not field.allowed_in_product_fact:
                continue
            compact_name = field.field_name.replace(" ", "")
            if not facts["category"] and any(label in compact_name for label in ("品类", "类别")):
                facts["category"] = field.exact_text
            elif any(label in compact_name for label in ("颜色", "色彩", "主色")):
                colors = facts["colors"]
                assert isinstance(colors, list)
                colors.extend(
                    part.strip()
                    for part in field.exact_text.replace("，", ",").replace("、", ",").split(",")
                    if part.strip()
                )
            elif not facts["material_or_structure"] and any(label in compact_name for label in ("材质", "结构")):
                facts["material_or_structure"] = field.exact_text
            elif not facts["silhouette"] and any(label in compact_name for label in ("廓形", "版型")):
                facts["silhouette"] = field.exact_text
            else:
                observable.append(f"{field.field_name}：{field.exact_text}")
        raw_colors = facts["colors"]
        assert isinstance(raw_colors, list)
        facts["colors"] = list(dict.fromkeys(raw_colors))
        facts["observable_features"] = "；".join(observable)
        if not any(facts.values()):
            raise DomainError(f"候选商品 {product.sku} 没有可进入 ProductFact 的纯 V 字段。")
        return facts
