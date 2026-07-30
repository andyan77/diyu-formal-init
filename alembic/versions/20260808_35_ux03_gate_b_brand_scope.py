"""Version brand inputs and register explicit organization ancestry.

Revision ID: 20260808_35
Revises: 20260807_34

This migration is expand-first. Existing projection rows remain readable by the
previous healthy image. New immutable version rows and current pointers are
additive, and no existing tenant row is reclassified by its name.
"""

from alembic import op

revision = "20260808_35"
down_revision = "20260807_34"
branch_labels = None
depends_on = None


def _tenant_rls(table: str, write: str = "SELECT, INSERT") -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_scope ON {table} "
        "USING (tenant_id = current_setting('app.tenant_id')::uuid) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid)"
    )
    op.execute(f"GRANT {write} ON {table} TO diyu_app")


def _immutable_versions(table: str) -> None:
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


def upgrade() -> None:
    op.execute(
        "ALTER TABLE organizations "
        "ADD CONSTRAINT organizations_tenant_id_id_key UNIQUE (tenant_id, id)"
    )
    op.execute(
        "ALTER TABLE organizations "
        "ADD COLUMN parent_organization_id uuid"
    )
    op.execute(
        "ALTER TABLE organizations "
        "ADD CONSTRAINT organizations_parent_not_self "
        "CHECK (parent_organization_id IS NULL OR parent_organization_id <> id)"
    )
    op.execute(
        "ALTER TABLE organizations "
        "ADD CONSTRAINT organizations_parent_same_tenant "
        "FOREIGN KEY (tenant_id, parent_organization_id) "
        "REFERENCES organizations(tenant_id, id)"
    )
    op.execute(
        """
        CREATE FUNCTION reject_organization_cycle()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            found_cycle boolean;
        BEGIN
            IF NEW.parent_organization_id IS NULL THEN
                RETURN NEW;
            END IF;
            WITH RECURSIVE ancestors(id, parent_id) AS (
                SELECT organization.id, organization.parent_organization_id
                  FROM organizations organization
                 WHERE organization.tenant_id = NEW.tenant_id
                   AND organization.id = NEW.parent_organization_id
                UNION ALL
                SELECT organization.id, organization.parent_organization_id
                  FROM organizations organization
                  JOIN ancestors ancestor
                    ON organization.id = ancestor.parent_id
                 WHERE organization.tenant_id = NEW.tenant_id
            )
            SELECT EXISTS (
                SELECT 1 FROM ancestors WHERE id = NEW.id
            ) INTO found_cycle;
            IF found_cycle THEN
                RAISE EXCEPTION 'organization ancestry cannot contain a cycle';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER organizations_no_cycle
        BEFORE INSERT OR UPDATE OF parent_organization_id ON organizations
        FOR EACH ROW EXECUTE FUNCTION reject_organization_cycle()
        """
    )
    op.execute(
        """
        CREATE FUNCTION organization_is_same_or_descendant(
            requested_tenant_id uuid,
            organization_id uuid,
            ancestor_id uuid
        )
        RETURNS boolean
        LANGUAGE sql
        STABLE
        AS $$
            WITH RECURSIVE ancestry(id, parent_id) AS (
                SELECT organization.id, organization.parent_organization_id
                  FROM organizations organization
                 WHERE organization.tenant_id = requested_tenant_id
                   AND organization.id = organization_id
                UNION ALL
                SELECT parent.id, parent.parent_organization_id
                  FROM organizations parent
                  JOIN ancestry child ON parent.id = child.parent_id
                 WHERE parent.tenant_id = requested_tenant_id
            )
            SELECT EXISTS (
                SELECT 1 FROM ancestry WHERE id = ancestor_id
            )
        $$
        """
    )

    op.execute(
        """
        CREATE TABLE brand_library_entry_versions (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL REFERENCES brands(id),
            entry_id uuid NOT NULL REFERENCES brand_library_entries(id),
            version_number integer NOT NULL CHECK (version_number > 0),
            version_label text NOT NULL,
            category text NOT NULL,
            title text NOT NULL,
            source_note text NOT NULL,
            content text NOT NULL,
            visibility_scope text NOT NULL
                CHECK (visibility_scope IN
                    ('brand_all', 'headquarters', 'organizations')),
            scope_organization_ids uuid[] NOT NULL DEFAULT '{}',
            created_by uuid REFERENCES users(id),
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, entry_id, version_number)
        )
        """
    )
    _tenant_rls("brand_library_entry_versions")
    _immutable_versions("brand_library_entry_versions")
    op.execute(
        "ALTER TABLE brand_library_entries "
        "ADD COLUMN current_version_id uuid "
        "REFERENCES brand_library_entry_versions(id)"
    )

    op.execute(
        """
        CREATE TABLE brand_product_versions (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL REFERENCES brands(id),
            product_id uuid NOT NULL REFERENCES brand_products(id),
            version_number integer NOT NULL CHECK (version_number > 0),
            display_name text NOT NULL,
            facts jsonb NOT NULL,
            source_kind text NOT NULL,
            source_note text NOT NULL,
            applicability text NOT NULL,
            visibility_scope text NOT NULL
                CHECK (visibility_scope IN
                    ('brand_all', 'headquarters', 'organizations')),
            scope_organization_ids uuid[] NOT NULL DEFAULT '{}',
            created_by uuid REFERENCES users(id),
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, product_id, version_number)
        )
        """
    )
    _tenant_rls("brand_product_versions")
    _immutable_versions("brand_product_versions")
    op.execute(
        "ALTER TABLE brand_products "
        "ADD COLUMN current_version_id uuid REFERENCES brand_product_versions(id)"
    )

    op.execute(
        """
        CREATE TABLE material_asset_versions (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL REFERENCES brands(id),
            asset_id uuid NOT NULL REFERENCES material_assets(id),
            version_number integer NOT NULL CHECK (version_number > 0),
            title text NOT NULL,
            reference_note text NOT NULL,
            visibility_scope text NOT NULL
                CHECK (visibility_scope IN
                    ('brand_all', 'headquarters', 'organizations')),
            scope_organization_ids uuid[] NOT NULL DEFAULT '{}',
            source_filename text NOT NULL,
            source_checksum_sha256 text NOT NULL,
            created_by uuid REFERENCES users(id),
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, asset_id, version_number)
        )
        """
    )
    _tenant_rls("material_asset_versions")
    _immutable_versions("material_asset_versions")
    op.execute(
        "ALTER TABLE material_assets "
        "ADD COLUMN current_version_id uuid REFERENCES material_asset_versions(id)"
    )
    op.execute(
        "ALTER TABLE material_assets "
        "DROP CONSTRAINT material_assets_status_check"
    )
    op.execute(
        "ALTER TABLE material_assets "
        "ADD CONSTRAINT material_assets_status_check "
        "CHECK (status IN ('active', 'inactive', 'deletion_pending', 'deleted'))"
    )

    op.execute(
        """
        DO $$
        DECLARE
            tenant_record record;
        BEGIN
            FOR tenant_record IN SELECT id FROM tenants LOOP
                PERFORM set_config('app.tenant_id', tenant_record.id::text, true);

                INSERT INTO brand_library_entry_versions (
                    id, tenant_id, brand_id, entry_id, version_number,
                    version_label, category, title, source_note, content,
                    visibility_scope, scope_organization_ids, created_by, created_at
                )
                SELECT gen_random_uuid(), entry.tenant_id, entry.brand_id, entry.id, 1,
                       entry.version, entry.category, entry.title, entry.source_note,
                       entry.content, entry.visibility_scope,
                       COALESCE((
                           SELECT array_agg(scope.organization_id ORDER BY scope.organization_id)
                             FROM brand_library_entry_organizations scope
                            WHERE scope.tenant_id = entry.tenant_id
                              AND scope.entry_id = entry.id
                       ), '{}'::uuid[]),
                       entry.updated_by, entry.updated_at
                  FROM brand_library_entries entry
                 WHERE entry.tenant_id = tenant_record.id;
                UPDATE brand_library_entries entry
                   SET current_version_id = version.id
                  FROM brand_library_entry_versions version
                 WHERE entry.tenant_id = tenant_record.id
                   AND version.tenant_id = entry.tenant_id
                   AND version.entry_id = entry.id
                   AND version.version_number = 1;

                INSERT INTO brand_product_versions (
                    id, tenant_id, brand_id, product_id, version_number,
                    display_name, facts, source_kind, source_note, applicability,
                    visibility_scope, scope_organization_ids, created_by, created_at
                )
                SELECT gen_random_uuid(), product.tenant_id, product.brand_id,
                       product.id, product.fact_version, product.display_name,
                       product.facts, product.source_kind, product.source_note,
                       product.applicability, product.visibility_scope,
                       COALESCE((
                           SELECT array_agg(scope.organization_id ORDER BY scope.organization_id)
                             FROM brand_product_scope_organizations scope
                            WHERE scope.tenant_id = product.tenant_id
                              AND scope.product_id = product.id
                       ), '{}'::uuid[]),
                       product.updated_by, product.updated_at
                  FROM brand_products product
                 WHERE product.tenant_id = tenant_record.id;
                UPDATE brand_products product
                   SET current_version_id = version.id
                  FROM brand_product_versions version
                 WHERE product.tenant_id = tenant_record.id
                   AND version.tenant_id = product.tenant_id
                   AND version.product_id = product.id
                   AND version.version_number = product.fact_version;

                INSERT INTO material_asset_versions (
                    id, tenant_id, brand_id, asset_id, version_number,
                    title, reference_note, visibility_scope,
                    scope_organization_ids, source_filename,
                    source_checksum_sha256, created_at
                )
                SELECT gen_random_uuid(), asset.tenant_id, asset.brand_id,
                       asset.id, asset.reference_version, asset.title,
                       asset.reference_note, asset.visibility_scope,
                       COALESCE((
                           SELECT array_agg(scope.organization_id ORDER BY scope.organization_id)
                             FROM material_asset_scope_organizations scope
                            WHERE scope.tenant_id = asset.tenant_id
                              AND scope.asset_id = asset.id
                       ), '{}'::uuid[]),
                       asset.original_filename, asset.checksum_sha256,
                       asset.created_at
                  FROM material_assets asset
                 WHERE asset.tenant_id = tenant_record.id
                   AND asset.scope = 'organization';
                UPDATE material_assets asset
                   SET current_version_id = version.id
                  FROM material_asset_versions version
                 WHERE asset.tenant_id = tenant_record.id
                   AND version.tenant_id = asset.tenant_id
                   AND version.asset_id = asset.id
                   AND version.version_number = asset.reference_version;
            END LOOP;
        END
        $$
        """
    )

    op.execute(
        "CREATE INDEX organizations_parent_lookup "
        "ON organizations (tenant_id, parent_organization_id)"
    )
    op.execute(
        "CREATE INDEX brand_library_entry_versions_lookup "
        "ON brand_library_entry_versions (tenant_id, entry_id, version_number DESC)"
    )
    op.execute(
        "CREATE INDEX brand_product_versions_lookup "
        "ON brand_product_versions (tenant_id, product_id, version_number DESC)"
    )
    op.execute(
        "CREATE INDEX material_asset_versions_lookup "
        "ON material_asset_versions (tenant_id, asset_id, version_number DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX material_asset_versions_lookup")
    op.execute("DROP INDEX brand_product_versions_lookup")
    op.execute("DROP INDEX brand_library_entry_versions_lookup")
    op.execute("DROP INDEX organizations_parent_lookup")
    op.execute("ALTER TABLE material_assets DROP COLUMN current_version_id")
    op.execute(
        "ALTER TABLE material_assets "
        "DROP CONSTRAINT material_assets_status_check"
    )
    op.execute(
        "ALTER TABLE material_assets "
        "ADD CONSTRAINT material_assets_status_check "
        "CHECK (status IN ('active', 'deletion_pending', 'deleted'))"
    )
    op.execute("DROP TRIGGER material_asset_versions_immutable ON material_asset_versions")
    op.execute("DROP FUNCTION reject_material_asset_versions_mutation()")
    op.execute("DROP TABLE material_asset_versions")
    op.execute("ALTER TABLE brand_products DROP COLUMN current_version_id")
    op.execute("DROP TRIGGER brand_product_versions_immutable ON brand_product_versions")
    op.execute("DROP FUNCTION reject_brand_product_versions_mutation()")
    op.execute("DROP TABLE brand_product_versions")
    op.execute("ALTER TABLE brand_library_entries DROP COLUMN current_version_id")
    op.execute(
        "DROP TRIGGER brand_library_entry_versions_immutable "
        "ON brand_library_entry_versions"
    )
    op.execute("DROP FUNCTION reject_brand_library_entry_versions_mutation()")
    op.execute("DROP TABLE brand_library_entry_versions")
    op.execute("DROP TRIGGER organizations_no_cycle ON organizations")
    op.execute(
        "DROP FUNCTION organization_is_same_or_descendant(uuid, uuid, uuid)"
    )
    op.execute("DROP FUNCTION reject_organization_cycle()")
    op.execute(
        "ALTER TABLE organizations DROP CONSTRAINT organizations_parent_same_tenant"
    )
    op.execute(
        "ALTER TABLE organizations DROP CONSTRAINT organizations_parent_not_self"
    )
    op.execute("ALTER TABLE organizations DROP COLUMN parent_organization_id")
    op.execute(
        "ALTER TABLE organizations DROP CONSTRAINT organizations_tenant_id_id_key"
    )
