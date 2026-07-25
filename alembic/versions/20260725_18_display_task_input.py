"""Separate the reusable wall structure from this task's own input (expand only).

This task's theme, focus suggestion and product snapshot are copied into
display_stores.current_task_input, which is the only place the application reads
them from now on. The application never reads the old rail_profile.confirmation
block again, so no confirmer, confirmation date or proxy submitter can reach a
user-visible plan.

The old keys are deliberately left in place as invisible, never-written fallback
data, so a rollback inside the rollback window still finds the structure it was
built against. Dropping them is a separate contract step taken only after that
window closes; this revision performs no irrecoverable delete.

Revision ID: 20260725_18
Revises: 20260724_17
Create Date: 2026-07-25
"""

from alembic import op

revision = "20260725_18"
down_revision = "20260724_17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE display_stores ADD COLUMN current_task_input jsonb")
    # display_stores and display_policies force row-level security, and the production migrator is
    # neither superuser nor BYPASSRLS, so the backfill sets each tenant's scope in turn instead of
    # relying on an unscoped cross-tenant UPDATE.
    op.execute(
        """
        DO $$
        DECLARE
            tenant_record record;
        BEGIN
            FOR tenant_record IN SELECT id FROM tenants LOOP
                PERFORM set_config('app.tenant_id', tenant_record.id::text, true);
                UPDATE display_stores s
                   SET current_task_input = jsonb_build_object(
                           'version', COALESCE(
                               s.rail_profile #>> '{inventory_snapshot,record_version}', s.profile_version),
                           'source', 'user_task_snapshot',
                           'expression', COALESCE(
                               (SELECT p.body
                                  FROM display_policies p
                                 WHERE p.tenant_id = s.tenant_id AND p.brand_id = s.brand_id
                                   AND p.version = s.profile_version),
                               '{}'::jsonb),
                           'products', s.rail_profile #> '{inventory_snapshot,items}')
                 WHERE s.tenant_id = tenant_record.id
                   AND s.rail_profile ? 'inventory_snapshot';
            END LOOP;
        END $$
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE display_stores DROP COLUMN current_task_input")
