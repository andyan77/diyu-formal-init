"""Make content versions append-only for the UI-12 audit contract.

The migration is expand-first: it changes no stored row and preserves schema 30
columns. Legacy images retain SELECT/INSERT compatibility on the newer schema.

Revision ID: 20260804_31
Revises: 20260803_30
"""

from alembic import op

revision = "20260804_31"
down_revision = "20260803_30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TRIGGER content_versions_audit_immutable ON content_versions")
    op.execute("DROP FUNCTION reject_content_version_audit_mutation()")
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


def downgrade() -> None:
    op.execute("GRANT UPDATE ON content_versions TO diyu_app")
    op.execute("DROP TRIGGER content_versions_append_only ON content_versions")
    op.execute("DROP FUNCTION reject_content_version_mutation()")
    op.execute(
        """
        CREATE FUNCTION reject_content_version_audit_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.artifact_digest IS DISTINCT FROM OLD.artifact_digest
               OR NEW.version_audit_snapshot IS DISTINCT FROM OLD.version_audit_snapshot THEN
                RAISE EXCEPTION 'content version audit evidence is immutable';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER content_versions_audit_immutable
        BEFORE UPDATE ON content_versions
        FOR EACH ROW EXECUTE FUNCTION reject_content_version_audit_mutation()
        """
    )
