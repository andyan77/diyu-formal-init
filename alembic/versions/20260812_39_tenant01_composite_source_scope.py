"""Bind TENANT-01 source provenance to tenant and brand at the database edge.

Revision ID: 20260812_39
Revises: 20260811_38

All changes are additive.  Existing globally unique ids remain valid; the
composite keys make a mismatched tenant/brand reference impossible even for a
malformed application insert.
"""

from alembic import op

revision = "20260812_39"
down_revision = "20260811_38"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in (
        "ALTER TABLE brands ADD CONSTRAINT brands_tenant_id_id_key UNIQUE (tenant_id, id)",
        "ALTER TABLE users ADD CONSTRAINT users_tenant_id_id_key UNIQUE (tenant_id, id)",
        "ALTER TABLE brand_products ADD CONSTRAINT brand_products_tenant_id_id_key "
        "UNIQUE (tenant_id, id)",
        "ALTER TABLE brand_product_versions ADD CONSTRAINT "
        "brand_product_versions_tenant_brand_id_key UNIQUE (tenant_id, brand_id, id)",
        "ALTER TABLE brand_source_documents ADD CONSTRAINT "
        "brand_source_documents_tenant_brand_id_key UNIQUE (tenant_id, brand_id, id)",
        "ALTER TABLE brand_source_document_versions ADD CONSTRAINT "
        "brand_source_document_versions_tenant_brand_id_key "
        "UNIQUE (tenant_id, brand_id, id)",
        "ALTER TABLE brand_source_segments ADD CONSTRAINT "
        "brand_source_segments_tenant_brand_id_key UNIQUE (tenant_id, brand_id, id)",
        "ALTER TABLE brand_source_documents ADD CONSTRAINT "
        "brand_source_documents_brand_scope_fk FOREIGN KEY (tenant_id, brand_id) "
        "REFERENCES brands(tenant_id, id)",
        "ALTER TABLE brand_source_documents ADD CONSTRAINT "
        "brand_source_documents_creator_scope_fk FOREIGN KEY (tenant_id, created_by) "
        "REFERENCES users(tenant_id, id)",
        "ALTER TABLE brand_source_document_versions ADD CONSTRAINT "
        "brand_source_document_versions_brand_scope_fk FOREIGN KEY (tenant_id, brand_id) "
        "REFERENCES brands(tenant_id, id)",
        "ALTER TABLE brand_source_document_versions ADD CONSTRAINT "
        "brand_source_document_versions_document_scope_fk "
        "FOREIGN KEY (tenant_id, brand_id, document_id) "
        "REFERENCES brand_source_documents(tenant_id, brand_id, id)",
        "ALTER TABLE brand_source_document_versions ADD CONSTRAINT "
        "brand_source_document_versions_creator_scope_fk "
        "FOREIGN KEY (tenant_id, created_by) REFERENCES users(tenant_id, id)",
        "ALTER TABLE brand_source_segments ADD CONSTRAINT "
        "brand_source_segments_brand_scope_fk FOREIGN KEY (tenant_id, brand_id) "
        "REFERENCES brands(tenant_id, id)",
        "ALTER TABLE brand_source_segments ADD CONSTRAINT "
        "brand_source_segments_document_scope_fk "
        "FOREIGN KEY (tenant_id, brand_id, document_id) "
        "REFERENCES brand_source_documents(tenant_id, brand_id, id)",
        "ALTER TABLE brand_source_segments ADD CONSTRAINT "
        "brand_source_segments_version_scope_fk "
        "FOREIGN KEY (tenant_id, brand_id, document_version_id) "
        "REFERENCES brand_source_document_versions(tenant_id, brand_id, id)",
        "ALTER TABLE brand_product_field_evidence ADD CONSTRAINT "
        "brand_product_field_evidence_brand_scope_fk FOREIGN KEY (tenant_id, brand_id) "
        "REFERENCES brands(tenant_id, id)",
        "ALTER TABLE brand_product_field_evidence ADD CONSTRAINT "
        "brand_product_field_evidence_product_scope_fk "
        "FOREIGN KEY (tenant_id, product_id) "
        "REFERENCES brand_products(tenant_id, id)",
        "ALTER TABLE brand_product_field_evidence ADD CONSTRAINT "
        "brand_product_field_evidence_version_scope_fk "
        "FOREIGN KEY (tenant_id, brand_id, product_version_id) "
        "REFERENCES brand_product_versions(tenant_id, brand_id, id)",
        "ALTER TABLE brand_product_field_evidence ADD CONSTRAINT "
        "brand_product_field_evidence_document_scope_fk "
        "FOREIGN KEY (tenant_id, brand_id, source_document_id) "
        "REFERENCES brand_source_documents(tenant_id, brand_id, id)",
        "ALTER TABLE brand_product_field_evidence ADD CONSTRAINT "
        "brand_product_field_evidence_segment_scope_fk "
        "FOREIGN KEY (tenant_id, brand_id, source_segment_id) "
        "REFERENCES brand_source_segments(tenant_id, brand_id, id)",
        "ALTER TABLE display_store_access_grants ADD CONSTRAINT "
        "display_store_access_grants_user_scope_fk FOREIGN KEY (tenant_id, user_id) "
        "REFERENCES users(tenant_id, id)",
        "ALTER TABLE display_store_access_grants ADD CONSTRAINT "
        "display_store_access_grants_store_scope_fk FOREIGN KEY (tenant_id, store_id) "
        "REFERENCES display_stores(tenant_id, id)",
    ):
        op.execute(statement)


def downgrade() -> None:
    raise RuntimeError(
        "TENANT-01 is expand-forward only; application rollback never downgrades tenant data."
    )
