from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.tenant_lifecycle import (
    TENANT_LIFECYCLE_CONTRACT_VERSION,
    TenantLifecycleClassifier,
    TenantLifecyclePlan,
)
from src.infrastructure.tenant_source_importer import TenantSourceImporter
from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.shared.content_snapshot import visible_context_basis
from src.shared.errors import DomainError
from src.shared.tenant_brand_sources import (
    classify_source_segment,
    freeze_source_batch,
    parse_source_document,
)
from src.shared.types import (
    BrandContext,
    ProductFact,
    TenantManagementScope,
    TrustedScope,
)
from src.tool.tenant01_evidence import (
    TENANT01_CARD_IDS,
    TENANT01_HARD_BOUNDARIES,
    TENANT01_REVIEW_DIMENSIONS,
    Tenant01ArtifactInput,
    Tenant01EvidenceError,
    Tenant01HumanReview,
    write_tenant01_evidence,
)

_SOURCE_IDS = (
    "DIYU-CANDIDATE-PRODUCT-MASTER-001",
    "DIYU-BRAND-BASELINE-001",
    "DIYU-AUDIENCE-PROFILE-001",
    "DIYU-CONTENT-ROLE-001",
    "DIYU-CONTENT-GOVERNANCE-001",
    "DIYU-BRAND-VOICE-001",
    "DIYU-ACCOUNT-AUTHORITY-001",
    "DIYU-DISPLAY-EXPRESSION-001",
    "DIYU-BRAND-VISUAL-001",
    "DIYU-ASSET-CALLING-001",
    "DIYU-ASSET-VISUAL-ANALYSIS-001",
    "DIYU-ASSET-CATALOG-001",
    "DIYU-PRODUCT-TRADEOFF-P2-001",
    "DIYU-PRODUCT-PRICE-CORRECTION-001",
    "DIYU-ASSET-PRODUCT-INFERENCE-001",
    "DIYU-ACCOUNT-MATRIX-001",
    "DIYU-ORG-IP-ACCOUNT-MATRIX-001",
    "DIYU-TENANT-ORG-AUTH-001",
    "DIYU-ASSET-BRAND-UNIFICATION-001",
    "DIYU-STORE-FIXTURE-PROFILE-001",
    "DIYU-STORE-FIXTURE-COLLECTION-001",
)


def _write_source_batch(root: Path) -> None:
    for index, source_id in enumerate(_SOURCE_IDS, start=1):
        title = f"冻结资料 {index}"
        body = (
            f"# {title}\n\n"
            f"文档编号：{source_id}\n\n"
            "文档版本：V1\n\n"
            "状态：待品牌方验收\n\n"
            "## 已确认边界\n\n"
            f"这是 {source_id} 的稳定整段内容。"
            f"{'长段落保持完整。' * 180 if source_id == 'DIYU-BRAND-BASELINE-001' else ''}\n"
        )
        if source_id == "DIYU-CANDIDATE-PRODUCT-MASTER-001":
            product_sections = []
            for product_index in range(1, 15):
                product_sections.append(
                    "\n".join(
                        (
                            f"## DIYU-CSPU-{product_index:02d} 候选商品 {product_index}",
                            "",
                            "| 字段 | 原文 | 证据等级 |",
                            "| --- | --- | --- |",
                            f"| 品类 | 可观察品类 {product_index} | V |",
                            f"| 主色 | 可观察颜色 {product_index} | V |",
                            f"| 建议价格 | 候选价格 {product_index} | P |",
                            f"| 功效 | 待正式资料覆盖 {product_index} | R |",
                        )
                    )
                )
            body += "\n\n" + "\n\n".join(product_sections) + "\n"
        # Filenames deliberately carry no authority and may even disagree with
        # the embedded identity.  The parser must remain metadata-owned.
        (root / f"外部原文件名-{22 - index:02d}.md").write_text(body, encoding="utf-8")


def _write_private_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    path.chmod(0o600)


def _tenant01_evidence_inputs(
    root: Path,
) -> tuple[
    tuple[Tenant01ArtifactInput, ...],
    tuple[Tenant01HumanReview, ...],
]:
    artifacts: list[Tenant01ArtifactInput] = []
    reviews: list[Tenant01HumanReview] = []
    for card_id in sorted(TENANT01_CARD_IDS):
        outline = f"{card_id} 标题证据"
        body = (
            f"{card_id} 正文证据，说明本篇的主要价值。\n"
            f"{card_id} 媒体编排证据，与当前平台形式对应。\n"
            f"{card_id} 发布配文证据，不扩写事实。"
        )
        artifact_file = f"{card_id}.artifact.json"
        raw_file = f"{card_id}.raw.json"
        _write_private_json(
            root / artifact_file,
            {
                "card_id": card_id,
                "task_id": str(uuid4()),
                "run_id": str(uuid4()),
                "version_id": str(uuid4()),
                "outline": outline,
                "body": body,
                "visible_digest": __import__(
                    "src.shared.narrative",
                    fromlist=["visible_digest"],
                ).visible_digest(outline, body),
            },
        )
        _write_private_json(root / raw_file, {"card_id": card_id, "response": "private"})
        artifacts.append(Tenant01ArtifactInput(card_id, artifact_file, raw_file))
        reviews.append(
            Tenant01HumanReview(
                card_id=card_id,
                artifact_file=artifact_file,
                scores={dimension: 4 for dimension in TENANT01_REVIEW_DIMENSIONS},
                excerpts={
                    "title": f"{card_id} 标题证据",
                    "body": f"{card_id} 正文证据",
                    "media": f"{card_id} 媒体编排证据",
                    "caption": f"{card_id} 发布配文证据",
                },
                hard_boundaries={boundary: True for boundary in TENANT01_HARD_BOUNDARIES},
                notes="已逐字阅读最终可见成品，与评分引用一致。",
            )
        )
    _write_private_json(
        root / "p5-no-media.json",
        {
            "card_id": "P5_no_media",
            "provider_calls": 0,
            "persistence_delta": [0, 0, 0],
            "result_kind": "question",
        },
    )
    _write_private_json(
        root / "dm01.json",
        {
            "identifiers": {
                "task_id": str(uuid4()),
                "v1_run_id": str(uuid4()),
                "v1_version_id": str(uuid4()),
                "v2_run_id": str(uuid4()),
                "v2_version_id": str(uuid4()),
            },
            "model": "dm01-rule-compiler-v1",
            "provider_calls": 0,
            "provider_usage": {},
            "rules_total": 13,
            "generation_rules": 11,
            "v1_v2_v1": True,
            "inventory_conservation": True,
            "ai_generated": False,
        },
    )
    return tuple(artifacts), tuple(reviews)


def test_tenant01_freezes_twenty_one_sources_and_fourteen_products(tmp_path: Path) -> None:
    _write_source_batch(tmp_path)

    documents = freeze_source_batch(tmp_path)

    assert len(documents) == 21
    assert {document.source_id for document in documents} == set(_SOURCE_IDS)
    assert len({document.normalized_sha256 for document in documents}) == 21
    products = tuple(product for document in documents for product in document.products)
    assert len(products) == 14
    assert len({product.sku for product in products}) == 14
    assert all(product.fact_fields for product in products)
    assert all("建议价格" not in product.fact_fields and "功效" not in product.fact_fields for product in products)
    evidence = tuple(field for product in products for field in product.fields)
    assert {level for field in evidence for level in field.evidence_levels} == {
        "V",
        "P",
        "R",
    }
    assert all(field.allowed_in_product_fact == (field.evidence_levels == ("V",)) for field in evidence)
    assert sum(len(document.segments) for document in documents) > len(documents)
    assert all(
        segment.exact_text != document.normalized_content
        for document in documents
        for segment in document.segments
    )


def test_tenant01_content_product_taxonomy_is_not_an_insertable_brand_fact() -> None:
    heading = ("十二、五类内容产品与受众价值",)

    assert classify_source_segment(
        "DIYU-AUDIENCE-PROFILE-001",
        heading,
        "内部内容产品分类只用于决定怎样表达。",
    ) == "expression_constraint"
    assert classify_source_segment(
        "DIYU-AUDIENCE-PROFILE-001",
        ("稳定目标人群",),
        "面向需要日常穿衣选择帮助的人。",
    ) == "brand_fact"


def test_source_identity_uses_embedded_metadata_not_filename(tmp_path: Path) -> None:
    source = tmp_path / "文件名与标题互换也不影响身份.md"
    source.write_text(
        "# 内嵌权威标题\n\n"
        "文档编号：DIYU-BRAND-BASELINE-001\n\n"
        "版本：V7\n\n"
        "状态：待品牌方验收\n\n"
        "## 稳定事实\n\n品牌公开名称为笛语。\n",
        encoding="utf-8",
    )

    document = parse_source_document(source)

    assert document.source_id == "DIYU-BRAND-BASELINE-001"
    assert document.embedded_title == "内嵌权威标题"
    assert document.source_version == "V7"
    assert document.provenance_filename == source.name
    assert all(
        segment.semantic_kind == "source_catalog_only"
        for segment in document.segments
        if segment.exact_text.startswith(("文档编号", "版本", "状态"))
    )
    assert document.segments[-1].semantic_kind == "brand_fact"


def test_source_batch_fails_before_partial_use(tmp_path: Path) -> None:
    _write_source_batch(tmp_path)
    missing = next(tmp_path.glob("*.md"))
    missing.unlink()

    with pytest.raises(ValueError, match="21 份 Markdown"):
        freeze_source_batch(tmp_path)


def test_private_source_text_is_not_part_of_public_import_manifest(tmp_path: Path) -> None:
    _write_source_batch(tmp_path)
    documents = freeze_source_batch(tmp_path)
    public_projection = {
        "source_digests": [
            {
                "source_id": document.source_id,
                "version": document.source_version,
                "normalized_sha256": document.normalized_sha256,
            }
            for document in documents
        ],
        "counts": {
            "documents": len(documents),
            "segments": sum(len(document.segments) for document in documents),
            "products": sum(len(document.products) for document in documents),
        },
    }

    serialized = json.dumps(public_projection, ensure_ascii=False)
    assert "稳定整段内容" not in serialized
    assert "候选价格" not in serialized
    assert "normalized_sha256" in serialized


def test_visible_context_basis_is_frozen_business_language_only() -> None:
    snapshot = {
        "brand_context_packet": {
            "segments": [
                {"semantic_kind": "brand_fact", "segment_id": "private-id"},
                {"semantic_kind": "creative_method", "segment_id": "another-id"},
            ]
        },
        "product_facts": [{"sku": "PRIVATE-SKU"}],
        "material_snapshots": [],
    }

    result = visible_context_basis(
        snapshot,
        account_name="笛语官方账号",
        channel="小红书",
        media_format="graphic",
    )

    assert result == {
        "account": "笛语官方账号",
        "platform_and_format": "小红书 · 图文",
        "brand_material_categories": ["品牌已确认资料", "品牌创作方法"],
        "has_product_facts": True,
        "selected_material_count": 0,
        "gaps": ["本次没有选择制作素材"],
    }
    assert "private-id" not in json.dumps(result)


def _import_scope(database_url: str) -> tuple[TenantManagementScope, UUID]:
    tenant_id = uuid4()
    brand_id = uuid4()
    organization_id = uuid4()
    manager_id = uuid4()
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO tenants (id, name) VALUES (%s, %s)",
            (tenant_id, f"TENANT-01 importer {tenant_id.hex[:8]}"),
        )
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
        cursor.execute(
            "INSERT INTO organizations "
            "(id, tenant_id, name, organization_level, business_data_kind) "
            "VALUES (%s, %s, '导入管理组织', 'company', 'formal_business_data')",
            (organization_id, tenant_id),
        )
        cursor.execute(
            "INSERT INTO brands "
            "(id, tenant_id, name, positioning, decision_order, tone) "
            "VALUES (%s, %s, '笛语服饰', '待导入', '待导入', '待导入')",
            (brand_id, tenant_id),
        )
        cursor.execute(
            "INSERT INTO users "
            "(id, tenant_id, organization_id, display_name, entry_kind, business_data_kind) "
            "VALUES (%s, %s, %s, '导入管理员', 'tenant_admin', 'formal_business_data')",
            (manager_id, tenant_id, organization_id),
        )
        cursor.execute(
            "INSERT INTO tenant_management_grants (id, tenant_id, user_id) VALUES (%s, %s, %s)",
            (uuid4(), tenant_id, manager_id),
        )
    return TenantManagementScope(tenant_id, manager_id, brand_id), organization_id


def _delete_import_scope(database_url: str, scope: TenantManagementScope) -> None:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(scope.tenant_id),))
        for table in (
            "brand_product_field_evidence",
            "brand_product_versions",
            "brand_source_segments",
            "brand_source_document_versions",
        ):
            cursor.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")  # noqa: S608
        try:
            cursor.execute(
                "UPDATE brand_source_documents SET current_version_id = NULL WHERE tenant_id = %s",
                (scope.tenant_id,),
            )
            cursor.execute(
                "UPDATE brand_products SET current_version_id = NULL WHERE tenant_id = %s",
                (scope.tenant_id,),
            )
            for table in (
                "brand_product_field_evidence",
                "brand_product_versions",
                "brand_products",
                "content_accounts",
                "brand_source_segments",
                "brand_source_document_versions",
                "brand_source_documents",
                "activity_events",
                "tenant_management_grants",
                "users",
                "organizations",
                "brands",
            ):
                cursor.execute(f"DELETE FROM {table} WHERE tenant_id = %s", (scope.tenant_id,))  # noqa: S608
            cursor.execute("DELETE FROM tenants WHERE id = %s", (scope.tenant_id,))
        finally:
            for table in (
                "brand_product_field_evidence",
                "brand_product_versions",
                "brand_source_segments",
                "brand_source_document_versions",
            ):
                cursor.execute(f"ALTER TABLE {table} ENABLE TRIGGER USER")  # noqa: S608


def test_tenant01_import_is_atomic_idempotent_and_evidence_bounded(
    app_database_url: str,
    migrator_database_url: str,
    tmp_path: Path,
) -> None:
    scope, _ = _import_scope(migrator_database_url)
    importer = TenantSourceImporter(app_database_url)
    try:
        _write_source_batch(tmp_path)
        product_source = next(
            path
            for path in tmp_path.glob("*.md")
            if "DIYU-CANDIDATE-PRODUCT-MASTER-001" in path.read_text(encoding="utf-8")
        )
        original_product_source = product_source.read_text(encoding="utf-8")
        product_source.write_text(
            original_product_source.replace("| V |", "| P |"),
            encoding="utf-8",
        )
        invalid_plan = importer.dry_run(scope, tmp_path)
        with pytest.raises(DomainError, match="没有可进入 ProductFact"):
            importer.apply(invalid_plan)
        with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(scope.tenant_id),))
            cursor.execute(
                "SELECT (SELECT count(*) FROM brand_source_documents), (SELECT count(*) FROM brand_products)"
            )
            assert cursor.fetchone() == (0, 0)

        product_source.write_text(original_product_source, encoding="utf-8")
        plan = importer.dry_run(scope, tmp_path)
        manifest_text = json.dumps(plan.public_manifest(), ensure_ascii=False)
        assert "稳定整段内容" not in manifest_text and "候选价格" not in manifest_text
        first = importer.apply(plan)
        assert first["inserted_documents"] == 21
        assert first["inserted_products"] == 14
        second_plan = importer.dry_run(scope, tmp_path)
        assert {action for _, action in second_plan.document_actions} == {"no_op"}
        assert {action for _, action in second_plan.product_actions} == {"no_op"}
        assert importer.apply(second_plan) == {
            "batch_digest": second_plan.batch_digest,
            "inserted_documents": 0,
            "inserted_segments": 0,
            "inserted_products": 0,
            "inserted_product_fields": 0,
        }

        with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(scope.tenant_id),))
            cursor.execute(
                "SELECT "
                "(SELECT count(*) FROM brand_source_documents), "
                "(SELECT count(*) FROM brand_source_segments), "
                "(SELECT count(*) FROM brand_products), "
                "(SELECT count(*) FROM brand_product_field_evidence "
                " WHERE allowed_in_product_fact), "
                "(SELECT count(*) FROM brand_product_field_evidence "
                " WHERE allowed_in_product_fact AND evidence_level <> 'V'), "
                "(SELECT count(*) FROM brand_product_versions "
                " WHERE facts->>'category' <> '' "
                "   AND jsonb_array_length(facts->'colors') > 0), "
                "(SELECT count(*) FROM material_assets), "
                "(SELECT count(*) FROM product_media_bindings)"
            )
            counts = cursor.fetchone()
            assert counts is not None
            assert counts[0] == 21 and counts[2:] == (14, 28, 0, 14, 0, 0)
            assert counts[1] > 21

        changed = next(path for path in tmp_path.glob("*.md") if path != product_source)
        changed.write_text(
            changed.read_text(encoding="utf-8") + "\n同版本冲突内容。\n",
            encoding="utf-8",
        )
        with pytest.raises(DomainError, match="已存在不同摘要"):
            importer.dry_run(scope, tmp_path)
    finally:
        _delete_import_scope(migrator_database_url, scope)


def test_tenant01_brand_context_is_task_relevant_typed_and_deterministic(
    app_database_url: str,
    migrator_database_url: str,
    tmp_path: Path,
) -> None:
    management_scope, organization_id = _import_scope(migrator_database_url)
    account_id = uuid4()
    legacy_taxonomy_segment_id = uuid4()
    importer = TenantSourceImporter(app_database_url)
    try:
        _write_source_batch(tmp_path)
        importer.apply(importer.dry_run(management_scope, tmp_path))
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, current_version_id FROM brand_source_documents "
                "WHERE tenant_id = %s AND source_id = 'DIYU-AUDIENCE-PROFILE-001'",
                (management_scope.tenant_id,),
            )
            source_row = cursor.fetchone()
            assert source_row is not None
            legacy_text = "P3 只是内部内容产品标签，不是可插入成品的品牌事实。"
            cursor.execute(
                "INSERT INTO brand_source_segments "
                "(id, tenant_id, brand_id, document_id, document_version_id, "
                " segment_key, heading_path, source_locator, exact_text, "
                " semantic_kind, evidence_level, applicability, digest) "
                "VALUES (%s, %s, %s, %s, %s, 'legacy-taxonomy', %s, "
                " 'line:999', %s, 'brand_fact', 'brand_user_authorized', "
                " '只用于测试旧解析器记录的安全投影', %s)",
                (
                    legacy_taxonomy_segment_id,
                    management_scope.tenant_id,
                    management_scope.brand_id,
                    source_row[0],
                    source_row[1],
                    ["十二、五类内容产品与受众价值"],
                    legacy_text,
                    sha256(legacy_text.encode()).hexdigest(),
                ),
            )
            cursor.execute(
                "INSERT INTO content_accounts "
                "(id, tenant_id, brand_id, name, channel, control_organization_id, "
                " control_organization_source) "
                "VALUES (%s, %s, %s, '笛语正式账号', '小红书', %s, 'declared')",
                (
                    account_id,
                    management_scope.tenant_id,
                    management_scope.brand_id,
                    organization_id,
                ),
            )
        scope = TrustedScope(
            management_scope.tenant_id,
            management_scope.user_id,
            management_scope.brand_id,
            account_id,
        )
        context = BrandContext(
            brand_name="笛语",
            positioning="只使用已确认的品牌选择",
            decision_order="先人后衣",
            tone="克制",
            account_name="笛语正式账号",
            operator_name="内容用户",
            organization_name="总部",
            content_role_name="品牌穿衣编辑",
            content_role_boundary="不补造商品事实",
            audience_description="需要日常选择帮助的人",
            strategy_version="V1",
            platform="小红书",
            media_format="图文",
            production_conditions="单人低成本制作",
        )
        product = ProductFact(
            sku="DIYU-CSPU-14",
            display_name="候选商品 14",
            facts={"category": "可观察品类 14", "colors": ["可观察颜色 14"]},
            source_kind="tenant_source_import",
            source_note="字段级 V 证据",
            fact_version=1,
            applicability="本次商品",
        )
        repository = PostgresContentRepository(app_database_url)

        selected = repository.select_brand_context_for_task(
            scope,
            context,
            "解释 DIYU-CSPU-14 的可见选择，同时保持内容产品边界",
            "product_truth",
            (product,),
        )
        repeated = repository.select_brand_context_for_task(
            scope,
            context,
            "解释 DIYU-CSPU-14 的可见选择，同时保持内容产品边界",
            "product_truth",
            (product,),
        )

        assert selected.context_packet is not None
        assert repeated.context_packet is not None
        assert selected.context_packet.packet_digest == repeated.context_packet.packet_digest
        assert len(selected.context_packet.segments) <= 24
        assert sum(len(item.exact_text) for item in selected.context_packet.segments) <= 12_000
        assert all(
            sha256(item.exact_text.encode()).hexdigest() == item.digest for item in selected.context_packet.segments
        )
        assert any(len(item.exact_text) > 1_200 for item in selected.context_packet.segments)
        product_segments = tuple(
            item
            for item in selected.context_packet.segments
            if "可观察品类 14" in item.exact_text or "可观察颜色 14" in item.exact_text
        )
        assert product_segments
        assert all(item.semantic_kind == "candidate_product_guidance" for item in product_segments)
        assert any("可观察品类 14" in text for text in selected.candidate_product_guidance_context)
        assert all("可观察品类 14" not in text for text in selected.brand_reference_context)
        assert selected.brand_reference_context == tuple(
            item.exact_text for item in selected.context_packet.segments if item.semantic_kind == "brand_fact"
        )
        legacy_segment = next(
            item
            for item in selected.context_packet.segments
            if item.segment_id == str(legacy_taxonomy_segment_id)
        )
        assert legacy_segment.semantic_kind == "expression_constraint"
        assert legacy_segment.exact_text in selected.expression_constraint_context
        assert legacy_segment.exact_text not in selected.brand_reference_context
        assert all(item.semantic_kind != "template_only" for item in selected.context_packet.segments)
    finally:
        _delete_import_scope(migrator_database_url, management_scope)


def test_tenant01_source_provenance_rejects_cross_tenant_brand_reference(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    first, _ = _import_scope(migrator_database_url)
    second, _ = _import_scope(migrator_database_url)
    try:
        with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(first.tenant_id),))
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                cursor.execute(
                    "INSERT INTO brand_source_documents "
                    "(id, tenant_id, brand_id, source_id, embedded_title, "
                    " provenance_filename, source_version, original_status, "
                    " activation_status, authorization_source, status, created_by) "
                    "VALUES (%s, %s, %s, 'CROSS-TENANT', '错误跨租户资料', "
                    " 'private.md', 'V1', '待确认', 'brand_user_authorized', "
                    " 'negative-test', 'active', %s)",
                    (uuid4(), first.tenant_id, second.brand_id, first.user_id),
                )
    finally:
        _delete_import_scope(migrator_database_url, first)
        _delete_import_scope(migrator_database_url, second)


def test_exact_preimage_classification_is_atomic_and_revokes_hidden_access(
    app_database_url: str,
    migrator_database_url: str,
    tmp_path: Path,
) -> None:
    scope, organization_id = _import_scope(migrator_database_url)
    synthetic_organization_id = uuid4()
    synthetic_user_id = uuid4()
    legacy_user_id = uuid4()
    synthetic_account_id = uuid4()
    session_ids = (uuid4(), uuid4())
    plan_path = tmp_path / "lifecycle.json"
    try:
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(scope.tenant_id),))
            cursor.execute(
                "INSERT INTO organizations "
                "(id, tenant_id, name, organization_level, business_data_kind) "
                "VALUES (%s, %s, '明确夹具组织', 'operating_unit', 'formal_business_data')",
                (synthetic_organization_id, scope.tenant_id),
            )
            cursor.execute(
                "INSERT INTO users "
                "(id, tenant_id, organization_id, display_name, entry_kind, business_data_kind) "
                "VALUES (%s, %s, %s, '明确夹具成员', 'tenant_user', 'formal_business_data'), "
                "       (%s, %s, %s, '来源不明旧成员', 'tenant_user', 'formal_business_data')",
                (
                    synthetic_user_id,
                    scope.tenant_id,
                    synthetic_organization_id,
                    legacy_user_id,
                    scope.tenant_id,
                    organization_id,
                ),
            )
            cursor.execute(
                "INSERT INTO content_accounts "
                "(id, tenant_id, brand_id, name, channel, carrier_of_account_id, "
                " control_organization_id, business_data_kind) "
                "VALUES (%s, %s, %s, '明确夹具账号', '小红书', NULL, %s, 'formal_business_data')",
                (
                    synthetic_account_id,
                    scope.tenant_id,
                    scope.brand_id,
                    synthetic_organization_id,
                ),
            )
            cursor.execute(
                "INSERT INTO auth_grants (id, tenant_id, user_id, account_id, role_name) "
                "VALUES (%s, %s, %s, %s, 'operator')",
                (uuid4(), scope.tenant_id, synthetic_user_id, synthetic_account_id),
            )
            for session_id, user_id in zip(session_ids, (synthetic_user_id, legacy_user_id), strict=True):
                cursor.execute(
                    "INSERT INTO tenant_sessions "
                    "(id, tenant_id, user_id, audience, token_digest, expires_at) "
                    "VALUES (%s, %s, %s, 'tenant-user', %s, now() + interval '1 day')",
                    (session_id, scope.tenant_id, user_id, sha256(str(session_id).encode()).hexdigest()),
                )
        plan_path.write_text(
            json.dumps(
                {
                    "contract_version": TENANT_LIFECYCLE_CONTRACT_VERSION,
                    "tenant_id": str(scope.tenant_id),
                    "brand_id": str(scope.brand_id),
                    "actor_user_id": str(scope.user_id),
                    "objects": [
                        {
                            "table": "organizations",
                            "object_id": str(synthetic_organization_id),
                            "target_kind": "synthetic_business_fixture",
                        },
                        {
                            "table": "users",
                            "object_id": str(synthetic_user_id),
                            "target_kind": "synthetic_business_fixture",
                        },
                        {
                            "table": "users",
                            "object_id": str(legacy_user_id),
                            "target_kind": "legacy_hidden",
                        },
                        {
                            "table": "content_accounts",
                            "object_id": str(synthetic_account_id),
                            "target_kind": "synthetic_business_fixture",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        plan = TenantLifecyclePlan.from_file(plan_path)
        result = TenantLifecycleClassifier(app_database_url).apply(plan)
        assert result["changed"] == 4
        assert TenantLifecycleClassifier(app_database_url).apply(plan)["already_classified"] == 4
        with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(scope.tenant_id),))
            cursor.execute(
                "SELECT id, business_data_kind, enabled FROM users "
                "WHERE tenant_id = %s AND id = ANY(%s) ORDER BY id",
                (scope.tenant_id, [synthetic_user_id, legacy_user_id]),
            )
            users = {UUID(str(row[0])): (str(row[1]), bool(row[2])) for row in cursor.fetchall()}
            assert users[synthetic_user_id] == ("synthetic_business_fixture", False)
            assert users[legacy_user_id] == ("legacy_hidden", True)
            cursor.execute(
                "SELECT count(*) FROM tenant_sessions "
                "WHERE tenant_id = %s AND user_id = ANY(%s) AND revoked_at IS NULL",
                (scope.tenant_id, [synthetic_user_id, legacy_user_id]),
            )
            assert cursor.fetchone() == (0,)
            cursor.execute(
                "SELECT enabled, platform_enabled, business_data_kind FROM content_accounts "
                "WHERE tenant_id = %s AND id = %s",
                (scope.tenant_id, synthetic_account_id),
            )
            assert cursor.fetchone() == (False, False, "synthetic_business_fixture")
        repository = PostgresWorkbenchRepository(app_database_url)
        visible_people = repository.management_operators(scope)
        assert synthetic_user_id not in {
            UUID(str(person["id"])) for person in visible_people
        }
        assert legacy_user_id not in {
            UUID(str(person["id"])) for person in visible_people
        }
        archived_people = repository.management_operators(
            scope,
            include_archived=True,
        )
        assert {synthetic_user_id, legacy_user_id} <= {
            UUID(str(person["id"])) for person in archived_people
        }
        visible_accounts = repository.management_accounts(scope)
        assert synthetic_account_id not in {
            UUID(str(account["id"])) for account in visible_accounts
        }
    finally:
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(scope.tenant_id),))
            cursor.execute("DELETE FROM tenant_sessions WHERE tenant_id = %s", (scope.tenant_id,))
            cursor.execute("DELETE FROM auth_grants WHERE tenant_id = %s", (scope.tenant_id,))
        _delete_import_scope(migrator_database_url, scope)


def test_tenant01_evidence_binds_artifacts_reviews_and_persistence(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)

    write_tenant01_evidence(
        tmp_path,
        implementation_sha="a" * 40,
        schema_revision="20260812_39",
        image_digest="sha256:" + "b" * 64,
        artifacts=artifacts,
        reviews=reviews,
        p5_preflight_file="p5-no-media.json",
        dm01_file="dm01.json",
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    human_review = json.loads((tmp_path / "human-review.json").read_text(encoding="utf-8"))
    assert len(manifest["artifacts"]) == len(TENANT01_CARD_IDS)
    assert all(record["task_id"] and record["run_id"] and record["version_id"] for record in manifest["artifacts"])
    assert human_review["hard_boundary_violations"] == 0
    assert all(record["excerpts"]["body"] for record in human_review["reviews"])
    assert all(not path.stat().st_mode & 0o077 for path in tmp_path.iterdir())


def test_tenant01_evidence_rejects_review_not_grounded_in_artifact(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    first = reviews[0]
    invalid = Tenant01HumanReview(
        card_id=first.card_id,
        artifact_file=first.artifact_file,
        scores=first.scores,
        excerpts={**first.excerpts, "body": "只复述任务快照，不在成品中"},
        hard_boundaries=first.hard_boundaries,
        notes=first.notes,
    )

    with pytest.raises(Tenant01EvidenceError, match="不在最终 artifact"):
        write_tenant01_evidence(
            tmp_path,
            implementation_sha="a" * 40,
            schema_revision="20260812_39",
            image_digest="sha256:" + "b" * 64,
            artifacts=artifacts,
            reviews=(invalid, *reviews[1:]),
            p5_preflight_file="p5-no-media.json",
            dm01_file="dm01.json",
        )
