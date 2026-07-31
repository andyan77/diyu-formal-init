"""Make DM01 artifact versions append-only.

Revision ID: 20260810_37
Revises: 20260809_36

This migration changes no stored row. Normal application sessions retain only
SELECT and INSERT. The database owner can delete one precisely identified
synthetic-fixture version inside a transaction-local maintenance boundary.
"""

from alembic import op

revision = "20260810_37"
down_revision = "20260809_36"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION reject_display_artifact_version_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            table_owner name;
            synthetic_fixture boolean;
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                RAISE EXCEPTION 'display artifact versions are append-only';
            END IF;

            SELECT pg_get_userbyid(relation.relowner)
              INTO table_owner
              FROM pg_class relation
             WHERE relation.oid = TG_RELID;
            IF current_user <> table_owner
               AND current_user <> 'diyu_migrator' THEN
                RAISE EXCEPTION 'display version deletion requires the maintenance role';
            END IF;
            IF current_setting(
                   'diyu.display_version_maintenance', true
               ) IS DISTINCT FROM 'delete_synthetic_fixture'
               OR current_setting(
                   'diyu.display_version_maintenance_transaction_id', true
               ) IS DISTINCT FROM pg_current_xact_id()::text
               OR current_setting(
                   'diyu.display_version_maintenance_tenant_id', true
               ) IS DISTINCT FROM OLD.tenant_id::text
               OR current_setting(
                   'diyu.display_version_maintenance_version_id', true
               ) IS DISTINCT FROM OLD.id::text THEN
                RAISE EXCEPTION 'display version deletion requires an exact transaction-local maintenance boundary';
            END IF;

            SELECT organization.business_data_kind = 'synthetic_business_fixture'
              INTO synthetic_fixture
              FROM display_tasks task_record
              JOIN display_stores store_record
                ON store_record.tenant_id = task_record.tenant_id
               AND store_record.id = task_record.store_id
              JOIN organizations organization
                ON organization.tenant_id = store_record.tenant_id
               AND organization.id = store_record.execution_organization_id
             WHERE task_record.tenant_id = OLD.tenant_id
               AND task_record.id = OLD.task_id;
            IF synthetic_fixture IS DISTINCT FROM true THEN
                RAISE EXCEPTION 'only a synthetic fixture display version can be deleted';
            END IF;
            RETURN OLD;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER display_artifact_versions_append_only
        BEFORE UPDATE OR DELETE ON display_artifact_versions
        FOR EACH ROW EXECUTE FUNCTION reject_display_artifact_version_mutation()
        """
    )
    op.execute("REVOKE UPDATE, DELETE ON display_artifact_versions FROM diyu_app")


def downgrade() -> None:
    op.execute("DROP TRIGGER display_artifact_versions_append_only ON display_artifact_versions")
    op.execute("DROP FUNCTION reject_display_artifact_version_mutation()")
    op.execute("GRANT UPDATE, DELETE ON display_artifact_versions TO diyu_app")
