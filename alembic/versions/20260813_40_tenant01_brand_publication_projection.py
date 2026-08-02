"""Add the confirmed brand publication boundary used by new content tasks.

Revision ID: 20260813_40
Revises: 20260812_39

The migration is expand-only.  Existing images ignore the new pointer and
tables.  A confirmed expression baseline receives a minimal compatibility
projection so existing tenants do not lose the ability to create new tasks;
TENANT-01 replaces that projection with its source-bound reviewed projection.
"""

from alembic import op

revision = "20260813_40"
down_revision = "20260812_39"
branch_labels = None
depends_on = None


def _tenant_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_scope ON {table} "
        "USING (tenant_id = current_setting('app.tenant_id')::uuid) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid)"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO diyu_app")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE brand_publication_projections (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL,
            version_number integer NOT NULL CHECK (version_number > 0),
            status text NOT NULL CHECK (status IN ('candidate', 'confirmed', 'retired')),
            digest text NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$'),
            created_by uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            confirmed_by uuid,
            confirmed_at timestamptz,
            UNIQUE (tenant_id, brand_id, version_number),
            UNIQUE (tenant_id, brand_id, id),
            FOREIGN KEY (tenant_id, brand_id) REFERENCES brands(tenant_id, id),
            FOREIGN KEY (tenant_id, created_by) REFERENCES users(tenant_id, id),
            FOREIGN KEY (tenant_id, confirmed_by) REFERENCES users(tenant_id, id),
            CHECK (
                (status = 'candidate' AND confirmed_by IS NULL AND confirmed_at IS NULL)
                OR (status IN ('confirmed', 'retired') AND confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL)
            )
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX brand_publication_one_confirmed "
        "ON brand_publication_projections (tenant_id, brand_id) "
        "WHERE status = 'confirmed'"
    )
    op.execute(
        """
        CREATE FUNCTION reject_brand_publication_projection_content_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.tenant_id <> OLD.tenant_id
               OR NEW.brand_id <> OLD.brand_id
               OR NEW.version_number <> OLD.version_number
               OR NEW.digest <> OLD.digest
               OR NEW.created_by <> OLD.created_by
               OR NEW.created_at <> OLD.created_at THEN
                RAISE EXCEPTION 'brand publication projection content is immutable';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER brand_publication_projection_content_immutable "
        "BEFORE UPDATE ON brand_publication_projections FOR EACH ROW "
        "EXECUTE FUNCTION reject_brand_publication_projection_content_mutation()"
    )

    op.execute(
        """
        CREATE TABLE brand_publication_projection_items (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL,
            projection_id uuid NOT NULL,
            position integer NOT NULL CHECK (position > 0),
            publication_role text NOT NULL CHECK (publication_role IN (
                'public_brand_fact', 'expression_constraint',
                'creative_method', 'internal_only'
            )),
            published_text text NOT NULL CHECK (length(btrim(published_text)) > 0),
            applicability text[] NOT NULL DEFAULT '{}',
            source_kind text NOT NULL CHECK (source_kind IN (
                'brand_source_segment', 'brand_expression_baseline'
            )),
            source_segment_id uuid,
            source_ref text NOT NULL,
            source_version text NOT NULL,
            source_digest text NOT NULL CHECK (source_digest ~ '^[0-9a-f]{64}$'),
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, projection_id, position),
            UNIQUE (tenant_id, projection_id, id),
            FOREIGN KEY (tenant_id, brand_id, projection_id)
                REFERENCES brand_publication_projections(tenant_id, brand_id, id),
            FOREIGN KEY (tenant_id, brand_id, source_segment_id)
                REFERENCES brand_source_segments(tenant_id, brand_id, id),
            CHECK (
                (source_kind = 'brand_source_segment' AND source_segment_id IS NOT NULL)
                OR (source_kind = 'brand_expression_baseline' AND source_segment_id IS NULL)
            )
        )
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_brand_publication_projection_item_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'brand publication projection items are immutable';
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER brand_publication_projection_items_immutable "
        "BEFORE UPDATE OR DELETE ON brand_publication_projection_items FOR EACH ROW "
        "EXECUTE FUNCTION reject_brand_publication_projection_item_mutation()"
    )

    op.execute("ALTER TABLE brands ADD COLUMN current_publication_projection_id uuid")

    # Production owns these pre-existing FORCE-RLS tables with the deliberately
    # non-BYPASSRLS migrator role.  The compatibility backfill is a global DDL
    # operation, so let only the owning role see every tenant inside this
    # transaction.  ENABLE RLS remains active for the application role, and
    # FORCE is restored before the migration can commit.
    op.execute("ALTER TABLE brand_expression_baselines NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE brands NO FORCE ROW LEVEL SECURITY")

    # Confirmed baseline content already had a user-confirmed source and was
    # consumed by the old image.  Preserve that capability without inventing
    # raw-source facts; it is an expression constraint until an administrator
    # confirms a source-bound publication projection.
    op.execute(
        """
        WITH compatible AS (
            SELECT baseline.tenant_id, baseline.brand_id, baseline.id AS baseline_id,
                   baseline.version, baseline.draft, baseline.confirmed_by,
                   baseline.confirmed_at, gen_random_uuid() AS projection_id
              FROM brand_expression_baselines baseline
             WHERE baseline.status = 'confirmed'
               AND baseline.confirmed_by IS NOT NULL
               AND baseline.confirmed_at IS NOT NULL
        ), inserted AS (
            INSERT INTO brand_publication_projections
                (id, tenant_id, brand_id, version_number, status, digest,
                 created_by, created_at, confirmed_by, confirmed_at)
            SELECT projection_id, tenant_id, brand_id, 1, 'confirmed',
                   encode(sha256(convert_to(
                       'brand-publication-projection-v1|' || baseline_id::text || '|' ||
                       version::text || '|' || draft, 'UTF8')), 'hex'),
                   confirmed_by, confirmed_at, confirmed_by, confirmed_at
              FROM compatible
            RETURNING id, tenant_id, brand_id
        )
        INSERT INTO brand_publication_projection_items
            (id, tenant_id, brand_id, projection_id, position,
             publication_role, published_text, applicability, source_kind,
             source_ref, source_version, source_digest)
        SELECT gen_random_uuid(), compatible.tenant_id, compatible.brand_id,
               compatible.projection_id, 1, 'expression_constraint',
               compatible.draft, '{}', 'brand_expression_baseline',
               compatible.baseline_id::text, compatible.version::text,
               encode(sha256(convert_to(compatible.draft, 'UTF8')), 'hex')
          FROM compatible
          JOIN inserted
            ON inserted.id = compatible.projection_id
           AND inserted.tenant_id = compatible.tenant_id
           AND inserted.brand_id = compatible.brand_id
        """
    )
    op.execute(
        """
        UPDATE brands brand
           SET current_publication_projection_id = projection.id
          FROM brand_publication_projections projection
         WHERE projection.tenant_id = brand.tenant_id
           AND projection.brand_id = brand.id
           AND projection.status = 'confirmed'
        """
    )
    op.execute(
        """
        ALTER TABLE brands
        ADD CONSTRAINT brands_current_publication_projection_fk
        FOREIGN KEY (tenant_id, id, current_publication_projection_id)
        REFERENCES brand_publication_projections(tenant_id, brand_id, id)
        """
    )
    op.execute("ALTER TABLE brands FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE brand_expression_baselines FORCE ROW LEVEL SECURITY")
    # The production migrator is deliberately NOBYPASSRLS and this migration
    # backfills every tenant in one transaction.  Enable and force tenant RLS
    # only after the cross-tenant compatibility backfill has completed; the
    # new tables are not visible to application sessions before commit.
    _tenant_rls("brand_publication_projections")
    _tenant_rls("brand_publication_projection_items")


def downgrade() -> None:
    raise RuntimeError(
        "TENANT-01 publication projections are expand-forward only; application rollback never downgrades tenant data."
    )
