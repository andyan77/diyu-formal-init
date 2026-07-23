"""Add the minimum persisted workbench, onboarding, series and material boundary.

Revision ID: 20260723_10
Revises: 20260723_09
"""

from alembic import op

revision = "20260723_10"
down_revision = "20260723_09"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "brand_expression_baselines",
    "organization_material_maintainers",
    "content_series",
    "content_series_items",
    "material_assets",
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
        "CREATE TABLE brand_expression_baselines ("
        "id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), "
        "brand_id uuid NOT NULL REFERENCES brands(id), version integer NOT NULL DEFAULT 1, "
        "draft text NOT NULL, status text NOT NULL CHECK (status IN ('draft', 'confirmed')), "
        "confirmed_by uuid REFERENCES users(id), confirmed_at timestamptz, "
        "updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE (tenant_id, brand_id)"
        ")"
    )
    op.execute(
        "CREATE TABLE organization_material_maintainers ("
        "id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), "
        "organization_id uuid NOT NULL REFERENCES organizations(id), user_id uuid NOT NULL REFERENCES users(id), "
        "UNIQUE (tenant_id, organization_id, user_id)"
        ")"
    )
    op.execute(
        "CREATE TABLE content_series ("
        "id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), "
        "brand_id uuid NOT NULL REFERENCES brands(id), created_by uuid NOT NULL REFERENCES users(id), "
        "title text NOT NULL, premise text NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now(), "
        "UNIQUE (tenant_id, created_by, title)"
        ")"
    )
    op.execute(
        "CREATE TABLE content_series_items ("
        "id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), "
        "series_id uuid NOT NULL REFERENCES content_series(id) ON DELETE CASCADE, "
        "task_id uuid NOT NULL REFERENCES business_tasks(id), position integer NOT NULL CHECK (position > 0), "
        "UNIQUE (tenant_id, series_id, task_id), UNIQUE (tenant_id, series_id, position)"
        ")"
    )
    op.execute(
        "CREATE TABLE material_assets ("
        "id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), "
        "brand_id uuid NOT NULL REFERENCES brands(id), scope text NOT NULL CHECK (scope IN ('personal', 'organization')), "
        "owner_user_id uuid REFERENCES users(id), owner_organization_id uuid REFERENCES organizations(id), "
        "title text NOT NULL, media_type text NOT NULL CHECK (media_type IN ('image', 'video')), "
        "object_key text NOT NULL UNIQUE, byte_size integer NOT NULL CHECK (byte_size > 0), "
        "status text NOT NULL CHECK (status IN ('active', 'deleted')) DEFAULT 'active', "
        "created_at timestamptz NOT NULL DEFAULT now(), "
        "CHECK ((scope = 'personal' AND owner_user_id IS NOT NULL AND owner_organization_id IS NULL) "
        "OR (scope = 'organization' AND owner_user_id IS NULL AND owner_organization_id IS NOT NULL))"
        ")"
    )
    for table in TENANT_TABLES:
        _rls(table)


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP TABLE {table}")
