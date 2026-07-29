"""Add immutable per-version audit evidence for the UI-12 dual-track contract.

The migration is expand-only.  Legacy images may continue inserting versions
with the safe defaults; UI-12 code requires a complete audit snapshot for every
new deterministic dual-track version.

Revision ID: 20260803_30
Revises: 20260802_29
"""

from alembic import op

revision = "20260803_30"
down_revision = "20260802_29"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE content_versions "
        "ADD COLUMN artifact_digest text, "
        "ADD COLUMN version_audit_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute(
        "ALTER TABLE content_versions "
        "ADD CONSTRAINT content_versions_artifact_digest_check "
        "CHECK (artifact_digest IS NULL OR artifact_digest ~ '^[0-9a-f]{64}$')"
    )
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


def downgrade() -> None:
    op.execute("DROP TRIGGER content_versions_audit_immutable ON content_versions")
    op.execute("DROP FUNCTION reject_content_version_audit_mutation()")
    op.execute(
        "ALTER TABLE content_versions "
        "DROP CONSTRAINT content_versions_artifact_digest_check, "
        "DROP COLUMN version_audit_snapshot, "
        "DROP COLUMN artifact_digest"
    )
