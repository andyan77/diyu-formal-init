"""Add a content-free provider-usage aggregate for the operations boundary.

Revision ID: 20260724_16
Revises: 20260724_15
Create Date: 2026-07-24
"""

from alembic import op

revision = "20260724_16"
down_revision = "20260724_15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION ops_runtime_provider_tokens() RETURNS bigint
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        DECLARE
            token_total bigint := 0;
            tenant_row record;
            current_total bigint;
        BEGIN
            FOR tenant_row IN SELECT tenant_id FROM public.ops_tenant_registry WHERE enabled = true LOOP
                PERFORM set_config('app.tenant_id', tenant_row.tenant_id::text, true);
                SELECT COALESCE(SUM(
                    CASE WHEN provider_usage ? 'total_tokens'
                              AND provider_usage ->> 'total_tokens' ~ '^[0-9]+$'
                         THEN (provider_usage ->> 'total_tokens')::bigint ELSE 0 END
                ), 0)
                INTO current_total FROM public.generation_runs;
                token_total := token_total + current_total;
                SELECT COALESCE(SUM(
                    CASE WHEN provider_usage ? 'total_tokens'
                              AND provider_usage ->> 'total_tokens' ~ '^[0-9]+$'
                         THEN (provider_usage ->> 'total_tokens')::bigint ELSE 0 END
                ), 0)
                INTO current_total FROM public.display_generation_runs;
                token_total := token_total + current_total;
            END LOOP;
            RETURN token_total;
        END;
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION ops_runtime_provider_tokens FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION ops_runtime_provider_tokens TO diyu_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION ops_runtime_provider_tokens")
