"""Set an explicit tenant context while operations reads and updates gap candidates.

Revision ID: 20260731_27
Revises: 20260731_26
"""

from alembic import op

revision = "20260731_27"
down_revision = "20260731_26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ops_unmet_capability_requests()
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
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            registry_row record;
        BEGIN
            FOR registry_row IN
                SELECT registry.tenant_id
                  FROM public.ops_tenant_registry AS registry
                 WHERE registry.enabled = true
            LOOP
                PERFORM set_config('app.tenant_id', registry_row.tenant_id::text, true);
                RETURN QUERY
                    SELECT request.tenant_id,
                           request.stable_request_id,
                           request.request_text,
                           request.catalog_version,
                           request.gap_type,
                           request.status,
                           request.response_text,
                           request.created_at,
                           request.responded_at
                      FROM public.unmet_capability_requests AS request
                     WHERE request.tenant_id = registry_row.tenant_id;
            END LOOP;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ops_classify_unmet_capability_request(
            request_key text,
            new_gap_type text,
            new_status text,
            new_response text
        )
        RETURNS uuid
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            registry_row record;
            matched_tenant uuid := NULL;
            tenant_matches integer := 0;
            match_count integer := 0;
        BEGIN
            FOR registry_row IN
                SELECT registry.tenant_id
                  FROM public.ops_tenant_registry AS registry
                 WHERE registry.enabled = true
            LOOP
                PERFORM set_config('app.tenant_id', registry_row.tenant_id::text, true);
                SELECT count(*)
                  INTO tenant_matches
                  FROM public.unmet_capability_requests AS request
                 WHERE request.tenant_id = registry_row.tenant_id
                   AND request.stable_request_id = request_key;

                IF tenant_matches > 0 THEN
                    match_count := match_count + tenant_matches;
                    IF matched_tenant IS NULL THEN
                        matched_tenant := registry_row.tenant_id;
                    END IF;
                END IF;
            END LOOP;

            IF match_count <> 1 OR matched_tenant IS NULL THEN
                RETURN NULL;
            END IF;

            PERFORM set_config('app.tenant_id', matched_tenant::text, true);
            UPDATE public.unmet_capability_requests AS request
               SET gap_type = new_gap_type,
                   status = new_status,
                   response_text = new_response,
                   responded_at = CASE
                       WHEN new_status = 'answered' THEN now() ELSE request.responded_at END
             WHERE request.tenant_id = matched_tenant
               AND request.stable_request_id = request_key;

            IF NOT FOUND THEN
                RETURN NULL;
            END IF;
            RETURN matched_tenant;
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
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ops_unmet_capability_requests()
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
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT request.tenant_id,
                   request.stable_request_id,
                   request.request_text,
                   request.catalog_version,
                   request.gap_type,
                   request.status,
                   request.response_text,
                   request.created_at,
                   request.responded_at
            FROM public.unmet_capability_requests AS request
            JOIN public.ops_tenant_registry AS registry
              ON registry.tenant_id = request.tenant_id
             AND registry.enabled = true
            ORDER BY request.created_at DESC
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ops_classify_unmet_capability_request(
            request_key text,
            new_gap_type text,
            new_status text,
            new_response text
        )
        RETURNS uuid
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            answered uuid := NULL;
            match_count integer := 0;
        BEGIN
            SELECT count(*), min(request.tenant_id::text)::uuid
              INTO match_count, answered
              FROM public.unmet_capability_requests AS request
              JOIN public.ops_tenant_registry AS registry
                ON registry.tenant_id = request.tenant_id
               AND registry.enabled = true
             WHERE request.stable_request_id = request_key;

            IF match_count <> 1 THEN
                RETURN NULL;
            END IF;

            UPDATE public.unmet_capability_requests
               SET gap_type = new_gap_type,
                   status = new_status,
                   response_text = new_response,
                   responded_at = CASE
                       WHEN new_status = 'answered' THEN now() ELSE responded_at END
             WHERE tenant_id = answered
               AND stable_request_id = request_key;
            RETURN answered;
        END;
        $$
        """
    )
