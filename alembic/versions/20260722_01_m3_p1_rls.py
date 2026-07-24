"""Create the M3-1 P1 relational core with forced tenant RLS.

Revision ID: 20260722_01
Revises:
Create Date: 2026-07-22
"""

from alembic import op

revision = "20260722_01"
down_revision = None
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "organizations",
    "users",
    "brands",
    "content_accounts",
    "auth_grants",
    "domain_assets",
    "business_tasks",
    "content_items",
    "content_versions",
    "generation_runs",
    "activity_events",
    "saved_content_versions",
)


def upgrade() -> None:
    op.execute("CREATE TABLE tenants (id uuid PRIMARY KEY, name text NOT NULL UNIQUE)")
    op.execute(
        """
        CREATE TABLE organizations (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), name text NOT NULL,
            UNIQUE (tenant_id, name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE users (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id),
            organization_id uuid NOT NULL REFERENCES organizations(id), display_name text NOT NULL,
            enabled boolean NOT NULL DEFAULT true, UNIQUE (tenant_id, display_name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE brands (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), name text NOT NULL,
            positioning text NOT NULL, decision_order text NOT NULL, tone text NOT NULL,
            UNIQUE (tenant_id, name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE content_accounts (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL REFERENCES brands(id), name text NOT NULL, channel text NOT NULL,
            enabled boolean NOT NULL DEFAULT true, UNIQUE (tenant_id, name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE auth_grants (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id),
            user_id uuid NOT NULL REFERENCES users(id), account_id uuid NOT NULL REFERENCES content_accounts(id),
            role_name text NOT NULL, enabled boolean NOT NULL DEFAULT true,
            UNIQUE (tenant_id, user_id, account_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE domain_assets (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL REFERENCES brands(id), external_key text NOT NULL,
            asset_type text NOT NULL, title text NOT NULL, body text NOT NULL,
            activation_status text NOT NULL CHECK (activation_status IN ('review_candidate', 'active', 'rejected')),
            UNIQUE (tenant_id, external_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE business_tasks (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL REFERENCES brands(id), account_id uuid NOT NULL REFERENCES content_accounts(id),
            created_by uuid NOT NULL REFERENCES users(id), weak_seed text NOT NULL,
            revision_instruction text, parent_version_id uuid, created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE content_items (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id),
            task_id uuid NOT NULL UNIQUE REFERENCES business_tasks(id), current_version integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE generation_runs (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id),
            task_id uuid NOT NULL REFERENCES business_tasks(id), model text NOT NULL, status text NOT NULL
                CHECK (status IN ('running', 'succeeded', 'failed')),
            latency_ms integer, retry_count integer NOT NULL DEFAULT 0, provider_usage jsonb,
            failure_reason text, started_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz
        )
        """
    )
    op.execute(
        """
        CREATE TABLE content_versions (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id),
            item_id uuid NOT NULL REFERENCES content_items(id), task_id uuid NOT NULL REFERENCES business_tasks(id),
            run_id uuid NOT NULL UNIQUE REFERENCES generation_runs(id), version_number integer NOT NULL,
            outline text NOT NULL, body text NOT NULL, created_by uuid NOT NULL REFERENCES users(id),
            created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (task_id, version_number)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE activity_events (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id),
            actor_id uuid NOT NULL REFERENCES users(id), event_type text NOT NULL, entity_type text NOT NULL,
            entity_id uuid NOT NULL, metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE saved_content_versions (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id),
            version_id uuid NOT NULL REFERENCES content_versions(id), user_id uuid NOT NULL REFERENCES users(id),
            saved_at timestamptz NOT NULL DEFAULT now(), UNIQUE (tenant_id, version_id, user_id)
        )
        """
    )
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_scope ON {table} "
            "USING (tenant_id = current_setting('app.tenant_id')::uuid) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid)"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO diyu_app")
    op.execute(
        "DO $$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO diyu_app', current_database()); END $$"
    )
    op.execute("REVOKE ALL ON tenants FROM PUBLIC")


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP TABLE tenants")
