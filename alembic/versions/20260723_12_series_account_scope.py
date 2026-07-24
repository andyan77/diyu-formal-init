"""Bind content series to a trusted publishing account scope.

Revision ID: 20260723_12
Revises: 20260723_11
"""

from alembic import op

revision = "20260723_12"
down_revision = "20260723_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE content_series ADD COLUMN account_id uuid REFERENCES content_accounts(id)"
    )
    op.execute(
        """
        DO $$
        DECLARE current_tenant uuid;
        BEGIN
            FOR current_tenant IN SELECT id FROM tenants LOOP
                PERFORM set_config('app.tenant_id', current_tenant::text, true);
                UPDATE content_series series
                SET account_id = scoped.account_id
                FROM (
                    SELECT item.series_id, min(task.account_id::text)::uuid AS account_id
                    FROM content_series_items item
                    JOIN business_tasks task ON task.id = item.task_id AND task.tenant_id = item.tenant_id
                    WHERE item.tenant_id = current_tenant
                    GROUP BY item.series_id
                    HAVING count(DISTINCT task.account_id) = 1
                ) scoped
                WHERE series.id = scoped.series_id AND series.tenant_id = current_tenant;
            END LOOP;
        END;
        $$
        """
    )
    op.execute(
        "CREATE INDEX content_series_account_scope_idx "
        "ON content_series (tenant_id, brand_id, account_id, created_by)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX content_series_account_scope_idx")
    op.execute("ALTER TABLE content_series DROP COLUMN account_id")
