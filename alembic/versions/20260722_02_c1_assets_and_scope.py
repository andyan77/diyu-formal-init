"""Register C1 assets and narrow P1 scope beyond tenant root.

Revision ID: 20260722_02
Revises: 20260722_01
Create Date: 2026-07-22
"""

from alembic import op

revision = "20260722_02"
down_revision = "20260722_01"
branch_labels = None
depends_on = None


def _tenant_rls(table: str) -> None:
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
        """
        CREATE TABLE content_roles (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL REFERENCES brands(id), name text NOT NULL, voice_boundary text NOT NULL,
            UNIQUE (tenant_id, brand_id, name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE account_content_roles (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id),
            account_id uuid NOT NULL REFERENCES content_accounts(id),
            content_role_id uuid NOT NULL REFERENCES content_roles(id),
            UNIQUE (tenant_id, account_id, content_role_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE brand_audiences (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL UNIQUE REFERENCES brands(id), description text NOT NULL
        )
        """
    )
    for table in ("content_roles", "account_content_roles", "brand_audiences"):
        _tenant_rls(table)

    op.execute(
        """
        CREATE TABLE system_domain_assets (
            asset_id text PRIMARY KEY, asset_type text NOT NULL, schema_version text NOT NULL,
            source_batch text NOT NULL, display_name text NOT NULL, structured_body jsonb NOT NULL,
            supported_products jsonb NOT NULL, applicability jsonb NOT NULL,
            status text NOT NULL CHECK (status IN ('review_candidate', 'active'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE system_asset_activations (
            asset_id text PRIMARY KEY REFERENCES system_domain_assets(asset_id),
            consumer text NOT NULL, applicability text NOT NULL
        )
        """
    )
    op.execute("GRANT SELECT ON system_domain_assets, system_asset_activations TO diyu_app")
    op.execute(
        "ALTER TABLE generation_runs ADD COLUMN used_assets jsonb NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE generation_runs DROP COLUMN used_assets")
    op.execute("DROP TABLE system_asset_activations")
    op.execute("DROP TABLE system_domain_assets")
    op.execute("DROP TABLE brand_audiences")
    op.execute("DROP TABLE account_content_roles")
    op.execute("DROP TABLE content_roles")
