"""Close the delete boundary for append-only content versions.

The migration is expand-first: it changes no stored row. Normal application
sessions cannot UPDATE or DELETE versions. The existing database owner/migrator
can delete one precisely identified synthetic-fixture version only inside a
transaction-local maintenance boundary.

Revision ID: 20260805_32
Revises: 20260804_31
"""

from alembic import op

revision = "20260805_32"
down_revision = "20260804_31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TRIGGER content_versions_append_only ON content_versions")
    op.execute("DROP FUNCTION reject_content_version_mutation()")
    op.execute(
        """
        CREATE FUNCTION reject_content_version_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            table_owner name;
            synthetic_fixture boolean;
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                RAISE EXCEPTION 'content versions are append-only';
            END IF;

            SELECT pg_get_userbyid(relation.relowner)
              INTO table_owner
              FROM pg_class relation
             WHERE relation.oid = TG_RELID;

            IF current_user <> table_owner
               AND current_user <> 'diyu_migrator' THEN
                RAISE EXCEPTION 'content version deletion requires the maintenance role';
            END IF;
            IF current_setting(
                   'diyu.content_version_maintenance',
                   true
               ) IS DISTINCT FROM 'delete_synthetic_fixture'
               OR current_setting(
                   'diyu.content_version_maintenance_transaction_id',
                   true
               ) IS DISTINCT FROM pg_current_xact_id()::text
               OR current_setting(
                   'diyu.content_version_maintenance_tenant_id',
                   true
               ) IS DISTINCT FROM OLD.tenant_id::text
               OR current_setting(
                   'diyu.content_version_maintenance_version_id',
                   true
               ) IS DISTINCT FROM OLD.id::text THEN
                RAISE EXCEPTION 'content version deletion requires an exact transaction-local maintenance boundary';
            END IF;

            SELECT account_record.business_data_kind = 'synthetic_business_fixture'
              INTO synthetic_fixture
              FROM business_tasks task_record
              JOIN content_accounts account_record
                ON account_record.tenant_id = task_record.tenant_id
               AND account_record.id = task_record.account_id
             WHERE task_record.tenant_id = OLD.tenant_id
               AND task_record.id = OLD.task_id;
            IF synthetic_fixture IS DISTINCT FROM true THEN
                RAISE EXCEPTION 'only a synthetic fixture version can be deleted';
            END IF;
            RETURN OLD;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER content_versions_append_only
        BEFORE UPDATE OR DELETE ON content_versions
        FOR EACH ROW EXECUTE FUNCTION reject_content_version_mutation()
        """
    )
    op.execute("REVOKE UPDATE, DELETE ON content_versions FROM diyu_app")


def downgrade() -> None:
    op.execute("DROP TRIGGER content_versions_append_only ON content_versions")
    op.execute("DROP FUNCTION reject_content_version_mutation()")
    op.execute(
        """
        CREATE FUNCTION reject_content_version_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'content versions are append-only';
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER content_versions_append_only
        BEFORE UPDATE ON content_versions
        FOR EACH ROW EXECUTE FUNCTION reject_content_version_mutation()
        """
    )
    op.execute("REVOKE UPDATE ON content_versions FROM diyu_app")
    op.execute("GRANT DELETE ON content_versions TO diyu_app")
