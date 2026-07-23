"""Persist M5-3 portal grants, one-persona boundary and material integrity metadata.

Revision ID: 20260723_11
Revises: 20260723_10
"""

from alembic import op

revision = "20260723_11"
down_revision = "20260723_10"
branch_labels = None
depends_on = None

TENANT_TABLES = ("tenant_management_grants", "user_default_personas")


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
        "CREATE TABLE tenant_management_grants ("
        "id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), "
        "user_id uuid NOT NULL REFERENCES users(id), enabled boolean NOT NULL DEFAULT true, "
        "UNIQUE (tenant_id, user_id)"
        ")"
    )
    op.execute(
        "CREATE TABLE user_default_personas ("
        "id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), "
        "user_id uuid NOT NULL REFERENCES users(id), name text NOT NULL, boundary text NOT NULL, "
        "version integer NOT NULL DEFAULT 1, updated_at timestamptz NOT NULL DEFAULT now(), "
        "UNIQUE (tenant_id, user_id)"
        ")"
    )
    for table in TENANT_TABLES:
        _rls(table)

    op.execute(
        "ALTER TABLE material_assets ADD COLUMN original_filename text NOT NULL DEFAULT 'original'"
    )
    op.execute("ALTER TABLE material_assets ADD COLUMN checksum_sha256 text NOT NULL DEFAULT ''")
    op.execute(
        "ALTER TABLE material_assets ADD COLUMN reference_version integer NOT NULL DEFAULT 1"
    )
    op.execute(
        "ALTER TABLE material_assets DROP CONSTRAINT IF EXISTS material_assets_media_type_check"
    )
    op.execute(
        "ALTER TABLE material_assets ADD CONSTRAINT material_assets_media_type_check "
        "CHECK (media_type IN ('text', 'image', 'video'))"
    )
    op.execute("ALTER TABLE material_assets DROP CONSTRAINT IF EXISTS material_assets_status_check")
    op.execute(
        "ALTER TABLE material_assets ADD CONSTRAINT material_assets_status_check "
        "CHECK (status IN ('active', 'deletion_pending', 'deleted'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE material_assets DROP CONSTRAINT IF EXISTS material_assets_status_check")
    op.execute(
        "ALTER TABLE material_assets ADD CONSTRAINT material_assets_status_check CHECK (status IN ('active', 'deleted'))"
    )
    op.execute(
        "ALTER TABLE material_assets DROP CONSTRAINT IF EXISTS material_assets_media_type_check"
    )
    op.execute(
        "ALTER TABLE material_assets ADD CONSTRAINT material_assets_media_type_check CHECK (media_type IN ('image', 'video'))"
    )
    op.execute("ALTER TABLE material_assets DROP COLUMN reference_version")
    op.execute("ALTER TABLE material_assets DROP COLUMN checksum_sha256")
    op.execute("ALTER TABLE material_assets DROP COLUMN original_filename")
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP TABLE {table}")
