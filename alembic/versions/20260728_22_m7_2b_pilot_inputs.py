"""Add the minimum M7-2B series, platform-carrier and product-fact metadata.

Revision ID: 20260728_22
Revises: 20260727_21
"""

from alembic import op

revision = "20260728_22"
down_revision = "20260727_21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A carrier is one explicit platform account for one existing expression identity.
    # It is not an account group and cannot be selected by same-channel ordering.
    op.execute(
        "ALTER TABLE content_accounts ADD COLUMN carrier_of_account_id uuid "
        "REFERENCES content_accounts(id)"
    )
    op.execute(
        "ALTER TABLE content_accounts ADD CONSTRAINT content_account_not_own_carrier "
        "CHECK (carrier_of_account_id IS NULL OR carrier_of_account_id <> id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX content_account_unique_carrier_target "
        "ON content_accounts (tenant_id, carrier_of_account_id, channel) "
        "WHERE carrier_of_account_id IS NOT NULL"
    )

    # Existing rows remain readable as legacy inputs.  Only rows written through the new
    # management entrance can be presented as responsibility-sourced real product facts.
    op.execute("ALTER TABLE brand_products ADD COLUMN display_name text NOT NULL DEFAULT ''")
    # Production migrations run as a narrow role and the table has FORCE RLS.  Backfill one
    # tenant at a time after setting the trusted tenant context; never assume table ownership can
    # bypass the policy.
    op.execute(
        """
        DO $$
        DECLARE
            tenant_record record;
        BEGIN
            FOR tenant_record IN SELECT id FROM public.tenants LOOP
                PERFORM set_config('app.tenant_id', tenant_record.id::text, true);
                UPDATE public.brand_products
                   SET display_name = COALESCE(
                       NULLIF(facts ->> 'name', ''),
                       NULLIF(facts ->> 'product_name', ''),
                       sku
                   )
                 WHERE tenant_id = tenant_record.id;
            END LOOP;
        END $$
        """
    )
    op.execute(
        "ALTER TABLE brand_products ADD COLUMN source_kind text NOT NULL DEFAULT 'legacy_seed'"
    )
    op.execute("ALTER TABLE brand_products ADD COLUMN source_note text NOT NULL DEFAULT ''")
    op.execute(
        "ALTER TABLE brand_products ADD COLUMN fact_version integer NOT NULL DEFAULT 1 "
        "CHECK (fact_version > 0)"
    )
    op.execute(
        "ALTER TABLE brand_products ADD COLUMN applicability text NOT NULL "
        "DEFAULT 'legacy_scope'"
    )
    op.execute(
        "ALTER TABLE brand_products ADD COLUMN status text NOT NULL DEFAULT 'active' "
        "CHECK (status IN ('active', 'retired'))"
    )
    op.execute(
        "ALTER TABLE brand_products ADD COLUMN updated_by uuid REFERENCES users(id)"
    )
    op.execute(
        "ALTER TABLE brand_products ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now()"
    )

    op.execute(
        "ALTER TABLE content_series ADD COLUMN revision integer NOT NULL DEFAULT 1 "
        "CHECK (revision > 0)"
    )
    op.execute(
        "ALTER TABLE business_tasks ADD COLUMN series_id uuid REFERENCES content_series(id)"
    )
    op.execute(
        "ALTER TABLE business_tasks ADD COLUMN series_position integer "
        "CHECK (series_position IS NULL OR series_position > 0)"
    )
    op.execute(
        "ALTER TABLE business_tasks ADD COLUMN series_revision_used integer "
        "CHECK (series_revision_used IS NULL OR series_revision_used > 0)"
    )
    op.execute(
        "ALTER TABLE business_tasks ADD CONSTRAINT business_task_series_fields_together CHECK ("
        "(series_id IS NULL AND series_position IS NULL AND series_revision_used IS NULL) OR "
        "(series_id IS NOT NULL AND series_position IS NOT NULL "
        "AND series_revision_used IS NOT NULL))"
    )
    op.execute(
        "CREATE INDEX business_tasks_series_scope_idx "
        "ON business_tasks (tenant_id, series_id, series_position)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX business_tasks_series_scope_idx")
    op.execute(
        "ALTER TABLE business_tasks DROP CONSTRAINT business_task_series_fields_together"
    )
    op.execute("ALTER TABLE business_tasks DROP COLUMN series_revision_used")
    op.execute("ALTER TABLE business_tasks DROP COLUMN series_position")
    op.execute("ALTER TABLE business_tasks DROP COLUMN series_id")
    op.execute("ALTER TABLE content_series DROP COLUMN revision")

    op.execute("ALTER TABLE brand_products DROP COLUMN updated_at")
    op.execute("ALTER TABLE brand_products DROP COLUMN updated_by")
    op.execute("ALTER TABLE brand_products DROP COLUMN status")
    op.execute("ALTER TABLE brand_products DROP COLUMN applicability")
    op.execute("ALTER TABLE brand_products DROP COLUMN fact_version")
    op.execute("ALTER TABLE brand_products DROP COLUMN source_note")
    op.execute("ALTER TABLE brand_products DROP COLUMN source_kind")
    op.execute("ALTER TABLE brand_products DROP COLUMN display_name")

    op.execute("DROP INDEX content_account_unique_carrier_target")
    op.execute(
        "ALTER TABLE content_accounts DROP CONSTRAINT content_account_not_own_carrier"
    )
    op.execute("ALTER TABLE content_accounts DROP COLUMN carrier_of_account_id")
