"""Expose the minimum tenant registry projection through one controlled function.

Revision ID: 20260731_25
Revises: 20260730_24
"""

from alembic import op

revision = "20260731_25"
down_revision = "20260730_24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION ops_list_tenants()
        RETURNS TABLE (
            tenant_id uuid,
            tenant_name text,
            enabled boolean,
            created_at timestamptz,
            disabled_at timestamptz
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT registry.tenant_id,
                   tenant.name::text,
                   registry.enabled,
                   registry.created_at,
                   registry.disabled_at
            FROM public.ops_tenant_registry AS registry
            JOIN public.tenants AS tenant
              ON tenant.id = registry.tenant_id
            ORDER BY tenant.name
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION ops_list_tenants() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION ops_list_tenants() TO diyu_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION ops_list_tenants()")
