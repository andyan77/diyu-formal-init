"""Add first-tenant source provenance, lifecycle classification and store grants.

Revision ID: 20260811_38
Revises: 20260810_37

The change is expand-only.  The previous healthy image ignores every new
column/table.  Existing rows are not guessed from names during migration;
TENANT-01 applies its reviewed UUID preimage as a separate, auditable action.
"""

from alembic import op

revision = "20260811_38"
down_revision = "20260810_37"
branch_labels = None
depends_on = None


_DATA_KIND_CHECK = (
    "CHECK (business_data_kind IN "
    "('formal_business_data', 'synthetic_business_fixture', 'legacy_hidden'))"
)


def _tenant_rls(table: str, write: str = "SELECT, INSERT, UPDATE") -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_scope ON {table} "
        "USING (tenant_id = current_setting('app.tenant_id')::uuid) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid)"
    )
    op.execute(f"GRANT {write} ON {table} TO diyu_app")


def _immutable(table: str) -> None:
    function = f"reject_{table}_mutation"
    trigger = f"{table}_immutable"
    op.execute(
        f"""
        CREATE FUNCTION {function}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION '{table} rows are immutable';
        END
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {trigger}
        BEFORE UPDATE OR DELETE ON {table}
        FOR EACH ROW EXECUTE FUNCTION {function}()
        """
    )


def _add_validated_fk_as_owner(statement: str, tables: tuple[str, ...]) -> None:
    """Let a non-BYPASSRLS table owner validate a new cross-table FK.

    Production migrations run as the table owner without BYPASSRLS.  PostgreSQL
    validates an ALTER TABLE foreign key with an internal SELECT, so FORCE RLS
    would require an application tenant context even though this is a global DDL
    invariant.  ENABLE RLS remains in force for the application role throughout;
    only the owning migration role bypasses policies inside this transaction.
    """

    for table in tables:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(statement)
    for table in tables:
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def _data_kind(table: str) -> None:
    op.execute(
        f"ALTER TABLE {table} ADD COLUMN business_data_kind text NOT NULL "
        f"DEFAULT 'formal_business_data' {_DATA_KIND_CHECK}"
    )


def upgrade() -> None:
    for table in ("organizations", "content_accounts"):
        op.execute(
            f"ALTER TABLE {table} DROP CONSTRAINT {table}_business_data_kind_check"
        )
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {table}_business_data_kind_check "
            f"{_DATA_KIND_CHECK}"
        )

    for table in (
        "users",
        "brand_products",
        "material_assets",
        "display_stores",
        "brand_library_entries",
        "business_tasks",
        "display_tasks",
        "content_series",
    ):
        _data_kind(table)

    op.execute("ALTER TABLE brands ADD COLUMN public_name text NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE brands ADD COLUMN search_aliases text[] NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE display_stores ADD COLUMN enabled boolean NOT NULL DEFAULT true")
    op.execute(
        "ALTER TABLE brand_products ADD COLUMN record_kind text NOT NULL "
        "DEFAULT 'confirmed_brand_product' CHECK (record_kind IN "
        "('confirmed_brand_product', 'brand_authorized_candidate'))"
    )
    op.execute(
        "ALTER TABLE brand_product_versions ADD CONSTRAINT "
        "brand_product_versions_tenant_id_id_key UNIQUE (tenant_id, id)"
    )

    op.execute(
        """
        CREATE TABLE brand_source_documents (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL REFERENCES brands(id),
            source_id text NOT NULL,
            embedded_title text NOT NULL,
            provenance_filename text NOT NULL,
            source_version text NOT NULL,
            original_status text NOT NULL,
            activation_status text NOT NULL
                CHECK (activation_status IN
                    ('brand_user_authorized', 'template_only', 'inactive')),
            authorization_source text NOT NULL,
            authorization_at timestamptz,
            visibility_scope text NOT NULL DEFAULT 'brand_all'
                CHECK (visibility_scope IN
                    ('brand_all', 'headquarters', 'organizations')),
            status text NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'inactive')),
            current_version_id uuid,
            created_by uuid REFERENCES users(id),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, brand_id, source_id),
            UNIQUE (tenant_id, id)
        )
        """
    )
    _tenant_rls("brand_source_documents")

    op.execute(
        """
        CREATE TABLE brand_source_document_versions (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL REFERENCES brands(id),
            document_id uuid NOT NULL,
            source_version text NOT NULL,
            embedded_title text NOT NULL,
            provenance_filename text NOT NULL,
            original_status text NOT NULL,
            activation_status text NOT NULL,
            authorization_source text NOT NULL,
            authorization_at timestamptz,
            raw_sha256 text NOT NULL CHECK (raw_sha256 ~ '^[0-9a-f]{64}$'),
            normalized_sha256 text NOT NULL
                CHECK (normalized_sha256 ~ '^[0-9a-f]{64}$'),
            source_size bigint NOT NULL CHECK (source_size >= 0),
            source_mtime_ns bigint NOT NULL CHECK (source_mtime_ns >= 0),
            content text NOT NULL,
            created_by uuid REFERENCES users(id),
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, document_id, source_version),
            UNIQUE (tenant_id, id),
            FOREIGN KEY (tenant_id, document_id)
                REFERENCES brand_source_documents(tenant_id, id)
        )
        """
    )
    _tenant_rls("brand_source_document_versions", "SELECT, INSERT")
    _immutable("brand_source_document_versions")
    _add_validated_fk_as_owner(
        "ALTER TABLE brand_source_documents ADD CONSTRAINT "
        "brand_source_documents_current_version_fk "
        "FOREIGN KEY (tenant_id, current_version_id) "
        "REFERENCES brand_source_document_versions(tenant_id, id)",
        ("brand_source_documents", "brand_source_document_versions"),
    )

    op.execute(
        """
        CREATE TABLE brand_source_segments (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL REFERENCES brands(id),
            document_id uuid NOT NULL,
            document_version_id uuid NOT NULL,
            segment_key text NOT NULL,
            heading_path text[] NOT NULL DEFAULT '{}',
            source_locator text NOT NULL,
            exact_text text NOT NULL,
            semantic_kind text NOT NULL CHECK (semantic_kind IN (
                'brand_fact', 'expression_constraint', 'creative_method',
                'candidate_product_guidance', 'template_only',
                'source_catalog_only'
            )),
            evidence_level text NOT NULL,
            applicability text NOT NULL,
            visibility_scope text NOT NULL DEFAULT 'brand_all'
                CHECK (visibility_scope IN
                    ('brand_all', 'headquarters', 'organizations')),
            digest text NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$'),
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, document_version_id, segment_key),
            UNIQUE (tenant_id, id),
            FOREIGN KEY (tenant_id, document_id)
                REFERENCES brand_source_documents(tenant_id, id),
            FOREIGN KEY (tenant_id, document_version_id)
                REFERENCES brand_source_document_versions(tenant_id, id)
        )
        """
    )
    _tenant_rls("brand_source_segments", "SELECT, INSERT")
    _immutable("brand_source_segments")

    op.execute(
        """
        CREATE TABLE brand_product_field_evidence (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL REFERENCES brands(id),
            product_id uuid NOT NULL REFERENCES brand_products(id),
            product_version_id uuid NOT NULL,
            field_name text NOT NULL,
            exact_text text NOT NULL,
            evidence_level text NOT NULL CHECK (evidence_level IN ('V', 'P', 'C', 'R')),
            source_document_id uuid NOT NULL,
            source_segment_id uuid NOT NULL,
            source_digest text NOT NULL CHECK (source_digest ~ '^[0-9a-f]{64}$'),
            authorization_source text NOT NULL,
            allowed_in_product_fact boolean NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, product_version_id, field_name, evidence_level),
            FOREIGN KEY (tenant_id, product_version_id)
                REFERENCES brand_product_versions(tenant_id, id),
            FOREIGN KEY (tenant_id, source_document_id)
                REFERENCES brand_source_documents(tenant_id, id),
            FOREIGN KEY (tenant_id, source_segment_id)
                REFERENCES brand_source_segments(tenant_id, id)
        )
        """
    )
    _tenant_rls("brand_product_field_evidence", "SELECT, INSERT")
    _immutable("brand_product_field_evidence")

    op.execute(
        "ALTER TABLE brand_library_entries ADD COLUMN source_document_id uuid"
    )
    _add_validated_fk_as_owner(
        "ALTER TABLE brand_library_entries ADD CONSTRAINT "
        "brand_library_entries_source_document_fk "
        "FOREIGN KEY (tenant_id, source_document_id) "
        "REFERENCES brand_source_documents(tenant_id, id)",
        ("brand_library_entries", "brand_source_documents"),
    )

    op.execute(
        """
        CREATE TABLE display_store_access_grants (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            user_id uuid NOT NULL REFERENCES users(id),
            store_id uuid NOT NULL REFERENCES display_stores(id),
            enabled boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, user_id, store_id)
        )
        """
    )
    _tenant_rls("display_store_access_grants")
    op.execute(
        """
        DO $$
        DECLARE tenant_record record;
        BEGIN
          FOR tenant_record IN SELECT id FROM tenants LOOP
            PERFORM set_config('app.tenant_id', tenant_record.id::text, true);
            INSERT INTO display_store_access_grants
                (id, tenant_id, user_id, store_id, enabled, created_at)
            SELECT gen_random_uuid(), legacy.tenant_id, legacy.user_id,
                   store.id, legacy.enabled, legacy.created_at
              FROM display_access_grants legacy
              JOIN users person
                ON person.tenant_id = legacy.tenant_id
               AND person.id = legacy.user_id
              JOIN display_stores store
                ON store.tenant_id = legacy.tenant_id
               AND store.execution_organization_id = person.organization_id
             WHERE legacy.tenant_id = tenant_record.id
            ON CONFLICT (tenant_id, user_id, store_id) DO NOTHING;
          END LOOP;
        END $$
        """
    )

    op.execute(
        """
        CREATE TABLE display_store_profile_versions (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL REFERENCES brands(id),
            store_id uuid NOT NULL REFERENCES display_stores(id),
            version_number integer NOT NULL CHECK (version_number > 0),
            version_label text NOT NULL,
            name text NOT NULL,
            control_organization_id uuid NOT NULL REFERENCES organizations(id),
            execution_organization_id uuid NOT NULL REFERENCES organizations(id),
            rail_profile jsonb NOT NULL,
            confirmed boolean NOT NULL DEFAULT false,
            created_by uuid REFERENCES users(id),
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, store_id, version_number),
            UNIQUE (tenant_id, id)
        )
        """
    )
    _tenant_rls("display_store_profile_versions", "SELECT, INSERT")
    _immutable("display_store_profile_versions")
    op.execute(
        "ALTER TABLE display_stores ADD COLUMN current_profile_version_id uuid"
    )
    op.execute(
        "ALTER TABLE display_stores ADD CONSTRAINT display_stores_tenant_id_id_key "
        "UNIQUE (tenant_id, id)"
    )
    _add_validated_fk_as_owner(
        "ALTER TABLE display_stores ADD CONSTRAINT display_stores_current_profile_fk "
        "FOREIGN KEY (tenant_id, current_profile_version_id) "
        "REFERENCES display_store_profile_versions(tenant_id, id)",
        ("display_stores", "display_store_profile_versions"),
    )
    op.execute(
        """
        DO $$
        DECLARE tenant_record record;
        BEGIN
          FOR tenant_record IN SELECT id FROM tenants LOOP
            PERFORM set_config('app.tenant_id', tenant_record.id::text, true);
            INSERT INTO display_store_profile_versions
                (id, tenant_id, brand_id, store_id, version_number,
                 version_label, name, control_organization_id,
                 execution_organization_id, rail_profile, confirmed, created_at)
            SELECT gen_random_uuid(), store.tenant_id, store.brand_id, store.id, 1,
                   store.profile_version, store.name, store.control_organization_id,
                   store.execution_organization_id, store.rail_profile, true, now()
              FROM display_stores store
             WHERE store.tenant_id = tenant_record.id;
            UPDATE display_stores store
               SET current_profile_version_id = version.id
              FROM display_store_profile_versions version
             WHERE store.tenant_id = tenant_record.id
               AND version.tenant_id = store.tenant_id
               AND version.store_id = store.id
               AND version.version_number = 1;
          END LOOP;
        END $$
        """
    )

    for index_sql in (
        "CREATE INDEX brand_source_documents_lookup ON brand_source_documents "
        "(tenant_id, brand_id, status, source_id)",
        "CREATE INDEX brand_source_segments_context_lookup ON brand_source_segments "
        "(tenant_id, brand_id, semantic_kind, document_version_id)",
        "CREATE INDEX brand_product_field_evidence_lookup ON brand_product_field_evidence "
        "(tenant_id, product_id, product_version_id)",
        "CREATE INDEX display_store_access_grants_lookup ON display_store_access_grants "
        "(tenant_id, user_id, enabled)",
    ):
        op.execute(index_sql)


def downgrade() -> None:
    raise RuntimeError(
        "TENANT-01 is expand-forward only; application rollback never downgrades tenant data."
    )
