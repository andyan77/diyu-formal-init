"""Separate an inferred control organization from a declared one, tie a current profile to its
own account at the database level, and give 笛语运维 a minimum classification and reply entry for
capability gap candidates.

Expand only.  The new column carries a safe default, no existing column is dropped or rewritten
in place, and the per-tenant backfill sets `app.tenant_id` first because the production migrator
is neither superuser nor `BYPASSRLS`.

Revision ID: 20260727_21
Revises: 20260726_20
Create Date: 2026-07-27
"""

from alembic import op

revision = "20260727_21"
down_revision = "20260726_20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Who controls a publishing account is a business decision, not something a creation event
    # can prove.  The migration that first filled the column read the single
    # `publishing_account.created` event; that is now recorded as an inference and no longer
    # grants profile maintenance.  Only an explicit declaration does.
    op.execute(
        "ALTER TABLE content_accounts ADD COLUMN control_organization_source text NOT NULL "
        "DEFAULT 'unset' CHECK (control_organization_source IN ('unset', 'inferred', 'declared'))"
    )
    op.execute(
        """
        DO $$
        DECLARE
            tenant_record record;
        BEGIN
            FOR tenant_record IN SELECT id FROM public.tenants LOOP
                PERFORM set_config('app.tenant_id', tenant_record.id::text, true);
                UPDATE public.content_accounts
                   SET control_organization_source = 'inferred'
                 WHERE tenant_id = tenant_record.id
                   AND control_organization_id IS NOT NULL
                   AND control_organization_source = 'unset';
            END LOOP;
        END $$
        """
    )

    # A current profile pointer must belong to the account it hangs on.  The application already
    # matches tenant, account and profile together; this makes a mismatched pointer impossible to
    # store at all.  The pointer stays nullable, and a NULL pointer satisfies the constraint.
    op.execute(
        "ALTER TABLE account_expression_profile_versions "
        "ADD CONSTRAINT account_expression_profile_versions_account_scope_key "
        "UNIQUE (tenant_id, account_id, id)"
    )
    op.execute(
        "ALTER TABLE content_accounts ADD CONSTRAINT content_accounts_current_profile_scope_fkey "
        "FOREIGN KEY (tenant_id, id, current_expression_profile_id) "
        "REFERENCES account_expression_profile_versions (tenant_id, account_id, id)"
    )

    # 笛语运维 consumes gap candidates through the same controlled-function boundary the runtime
    # summary already uses: no direct cross-tenant table access, no queue and no approval state
    # machine, only the columns the candidate already has.
    op.execute(
        """
        CREATE FUNCTION ops_unmet_capability_requests()
        RETURNS TABLE (
            tenant_id uuid,
            stable_request_id text,
            request_text text,
            catalog_version text,
            gap_type text,
            status text,
            response_text text,
            created_at timestamptz,
            responded_at timestamptz
        )
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        DECLARE
            registry_row record;
        BEGIN
            FOR registry_row IN
                SELECT r.tenant_id FROM public.ops_tenant_registry r WHERE r.enabled = true
            LOOP
                PERFORM set_config('app.tenant_id', registry_row.tenant_id::text, true);
                RETURN QUERY
                    SELECT registry_row.tenant_id,
                           request.stable_request_id,
                           request.request_text,
                           request.catalog_version,
                           request.gap_type,
                           request.status,
                           request.response_text,
                           request.created_at,
                           request.responded_at
                      FROM public.unmet_capability_requests request
                     ORDER BY request.created_at DESC;
            END LOOP;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION ops_classify_unmet_capability_request(
            request_key text, new_gap_type text, new_status text, new_response text)
        RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        DECLARE
            registry_row record;
            answered uuid := NULL;
        BEGIN
            FOR registry_row IN
                SELECT r.tenant_id FROM public.ops_tenant_registry r WHERE r.enabled = true
            LOOP
                PERFORM set_config('app.tenant_id', registry_row.tenant_id::text, true);
                UPDATE public.unmet_capability_requests
                   SET gap_type = new_gap_type,
                       status = new_status,
                       response_text = new_response,
                       responded_at = CASE
                           WHEN new_status = 'answered' THEN now() ELSE responded_at END
                 WHERE stable_request_id = request_key;
                IF FOUND THEN
                    answered := registry_row.tenant_id;
                    EXIT;
                END IF;
            END LOOP;
            RETURN answered;
        END;
        $$
        """
    )
    for routine in (
        "ops_unmet_capability_requests",
        "ops_classify_unmet_capability_request",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {routine} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {routine} TO diyu_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION ops_classify_unmet_capability_request")
    op.execute("DROP FUNCTION ops_unmet_capability_requests")
    op.execute(
        "ALTER TABLE content_accounts DROP CONSTRAINT content_accounts_current_profile_scope_fkey"
    )
    op.execute(
        "ALTER TABLE account_expression_profile_versions "
        "DROP CONSTRAINT account_expression_profile_versions_account_scope_key"
    )
    op.execute("ALTER TABLE content_accounts DROP COLUMN control_organization_source")
