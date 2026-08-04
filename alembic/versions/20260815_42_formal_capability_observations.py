"""Add append-only formal capability observations for dynamic readiness.

Revision ID: 20260815_42
Revises: 20260814_41

The application can only read these bounded proof coordinates.  A controlled
acceptance command records PASS only after the named capability has a real
browser/API/database observation and a private evidence digest.
"""

from alembic import op

revision = "20260815_42"
down_revision = "20260814_41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE formal_capability_observations (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            capability_id text NOT NULL CHECK (capability_id ~ '^FT-[0-9]{3}$'),
            candidate_sha text NOT NULL CHECK (candidate_sha ~ '^[0-9a-f]{40}$'),
            evidence_sha256 text NOT NULL CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
            verdict text NOT NULL CHECK (verdict = 'PASS'),
            observed_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, capability_id, candidate_sha, evidence_sha256)
        )
        """
    )
    op.execute(
        "CREATE INDEX formal_capability_observations_tenant_candidate_idx "
        "ON formal_capability_observations (tenant_id, candidate_sha, capability_id)"
    )
    op.execute(
        """
        CREATE TRIGGER formal_capability_observations_immutable
        BEFORE UPDATE OR DELETE ON formal_capability_observations
        FOR EACH ROW EXECUTE FUNCTION reject_content_request_failure_mutation()
        """
    )
    op.execute("ALTER TABLE formal_capability_observations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE formal_capability_observations FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY formal_capability_observations_tenant_scope "
        "ON formal_capability_observations "
        "USING (tenant_id = current_setting('app.tenant_id')::uuid)"
    )
    op.execute("GRANT SELECT ON formal_capability_observations TO diyu_app")
    op.execute(
        """
        CREATE FUNCTION current_application_schema_revision()
        RETURNS text
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        SET search_path = pg_catalog, public
        AS $$ SELECT version_num::text FROM public.alembic_version LIMIT 1 $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION current_application_schema_revision() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION current_application_schema_revision() TO diyu_app")


def downgrade() -> None:
    raise RuntimeError(
        "TENANT-01 formal capability observations are append-forward only; "
        "application rollback never downgrades proof history."
    )
