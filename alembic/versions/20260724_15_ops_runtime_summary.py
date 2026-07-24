"""Expose aggregate runtime health to the operations boundary without tenant content.

Revision ID: 20260724_15
Revises: 20260724_14
Create Date: 2026-07-24
"""

from alembic import op

revision = "20260724_15"
down_revision = "20260724_14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION ops_runtime_summary()
        RETURNS TABLE (
            registered_tenants bigint,
            enabled_tenants bigint,
            enabled_content_accounts bigint,
            content_runs bigint,
            content_succeeded bigint,
            content_failed bigint,
            display_runs bigint,
            display_succeeded bigint,
            display_failed bigint,
            average_latency_ms numeric
        )
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        DECLARE
            registered_count bigint;
            enabled_count bigint;
            account_count bigint := 0;
            content_run_count bigint := 0;
            content_success_count bigint := 0;
            content_failure_count bigint := 0;
            display_run_count bigint := 0;
            display_success_count bigint := 0;
            display_failure_count bigint := 0;
            latency_sum numeric := 0;
            latency_value_count bigint := 0;
            account_current bigint;
            content_current bigint;
            content_success_current bigint;
            content_failure_current bigint;
            display_current bigint;
            display_success_current bigint;
            display_failure_current bigint;
            latency_current numeric;
            latency_current_count bigint;
            registry_row record;
        BEGIN
            SELECT COUNT(*), COUNT(*) FILTER (WHERE enabled)
            INTO registered_count, enabled_count
            FROM public.ops_tenant_registry;

            FOR registry_row IN
                SELECT tenant_id FROM public.ops_tenant_registry WHERE enabled = true
            LOOP
                PERFORM set_config('app.tenant_id', registry_row.tenant_id::text, true);
                SELECT COUNT(*) FILTER (WHERE enabled)
                INTO account_current
                FROM public.content_accounts;
                account_count := account_count + account_current;

                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE status = 'succeeded'),
                       COUNT(*) FILTER (WHERE status = 'failed'),
                       COALESCE(SUM(latency_ms), 0),
                       COUNT(latency_ms)
                INTO content_current, content_success_current, content_failure_current,
                    latency_current, latency_current_count
                FROM public.generation_runs;
                content_run_count := content_run_count + content_current;
                content_success_count := content_success_count + content_success_current;
                content_failure_count := content_failure_count + content_failure_current;
                latency_sum := latency_sum + latency_current;
                latency_value_count := latency_value_count + latency_current_count;

                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE status = 'succeeded'),
                       COUNT(*) FILTER (WHERE status = 'failed'),
                       COALESCE(SUM(latency_ms), 0),
                       COUNT(latency_ms)
                INTO display_current, display_success_current, display_failure_current,
                    latency_current, latency_current_count
                FROM public.display_generation_runs;
                display_run_count := display_run_count + display_current;
                display_success_count := display_success_count + display_success_current;
                display_failure_count := display_failure_count + display_failure_current;
                latency_sum := latency_sum + latency_current;
                latency_value_count := latency_value_count + latency_current_count;
            END LOOP;

            RETURN QUERY SELECT
                registered_count,
                enabled_count,
                account_count,
                content_run_count,
                content_success_count,
                content_failure_count,
                display_run_count,
                display_success_count,
                display_failure_count,
                CASE WHEN latency_value_count = 0 THEN NULL ELSE latency_sum / latency_value_count END;
        END;
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION ops_runtime_summary FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION ops_runtime_summary TO diyu_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION ops_runtime_summary")
