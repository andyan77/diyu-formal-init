"""Create the minimal DM01 DisplayArtifact persistence and tenant RLS.

Revision ID: 20260722_04
Revises: 20260722_03
"""

from alembic import op

revision = "20260722_04"
down_revision = "20260722_03"
branch_labels = None
depends_on = None

TABLES = (
    "display_policies",
    "display_stores",
    "display_products",
    "display_tasks",
    "display_artifacts",
    "display_generation_runs",
    "display_artifact_versions",
)


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_scope ON {table} "
        "USING (tenant_id = current_setting('app.tenant_id')::uuid) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid)"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO diyu_app")


def upgrade() -> None:
    op.execute(
        "CREATE TABLE display_policies (id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), brand_id uuid NOT NULL REFERENCES brands(id), version text NOT NULL, body jsonb NOT NULL, UNIQUE (tenant_id, brand_id, version))"
    )
    op.execute(
        "CREATE TABLE display_stores (id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), brand_id uuid NOT NULL REFERENCES brands(id), control_organization_id uuid NOT NULL REFERENCES organizations(id), execution_organization_id uuid NOT NULL REFERENCES organizations(id), name text NOT NULL, profile_version text NOT NULL, rail_profile jsonb NOT NULL, UNIQUE (tenant_id, brand_id, execution_organization_id))"
    )
    op.execute(
        "CREATE TABLE display_products (id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), brand_id uuid NOT NULL REFERENCES brands(id), sku text NOT NULL, facts jsonb NOT NULL, UNIQUE (tenant_id, brand_id, sku))"
    )
    op.execute(
        "CREATE TABLE display_tasks (id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), brand_id uuid NOT NULL REFERENCES brands(id), organization_id uuid NOT NULL REFERENCES organizations(id), created_by uuid NOT NULL REFERENCES users(id), store_id uuid NOT NULL REFERENCES display_stores(id), inventory_text text NOT NULL, inventory jsonb NOT NULL, feedback text, created_at timestamptz NOT NULL DEFAULT now())"
    )
    op.execute(
        "CREATE TABLE display_artifacts (id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), task_id uuid NOT NULL UNIQUE REFERENCES display_tasks(id), current_version integer NOT NULL DEFAULT 0, created_at timestamptz NOT NULL DEFAULT now())"
    )
    op.execute(
        "CREATE TABLE display_generation_runs (id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), task_id uuid NOT NULL REFERENCES display_tasks(id), model text NOT NULL, status text NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')), used_assets jsonb NOT NULL DEFAULT '[]'::jsonb, latency_ms integer, retry_count integer NOT NULL DEFAULT 0, provider_usage jsonb, failure_reason text, started_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz)"
    )
    op.execute(
        "CREATE TABLE display_artifact_versions (id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), artifact_id uuid NOT NULL REFERENCES display_artifacts(id), task_id uuid NOT NULL REFERENCES display_tasks(id), run_id uuid NOT NULL UNIQUE REFERENCES display_generation_runs(id), version_number integer NOT NULL, body text NOT NULL, plan jsonb NOT NULL, created_by uuid NOT NULL REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (task_id, version_number))"
    )
    for table in TABLES:
        _rls(table)


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE {table}")
