"""Allow duplicate display names and add safe pre-task diagnostics.

Revision ID: 20260814_41
Revises: 20260813_40

The immutable user id remains the identity key.  Login usernames stay
globally case-insensitively unique.  The diagnostic table stores only safe
ids and failure classification; user text, prompts, credentials and provider
payloads have no columns in which they could be persisted.
"""

from alembic import op

revision = "20260814_41"
down_revision = "20260813_40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users DROP CONSTRAINT users_tenant_id_display_name_key"
    )
    op.execute(
        "CREATE INDEX users_tenant_display_name_idx "
        "ON users (tenant_id, display_name)"
    )
    op.execute(
        "ALTER TABLE content_accounts ADD CONSTRAINT "
        "content_accounts_tenant_id_id_key UNIQUE (tenant_id, id)"
    )

    op.execute(
        """
        CREATE FUNCTION available_login_username_candidates(p_display_name text)
        RETURNS TABLE(username text)
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        SET search_path = pg_catalog, public
        AS $$
            WITH normalized AS (
                SELECT CASE
                    WHEN btrim(p_display_name) LIKE '笛语%'
                    THEN btrim(p_display_name)
                    ELSE '笛语' || btrim(p_display_name)
                END AS base
            ), candidates AS (
                SELECT CASE
                    WHEN suffix = 1 THEN base
                    ELSE base || suffix::text
                END AS candidate,
                suffix
                FROM normalized
                CROSS JOIN generate_series(1, 20) AS suffix
                WHERE length(base) BETWEEN 3 AND 76
            )
            SELECT candidate
            FROM candidates
            WHERE NOT EXISTS (
                SELECT 1
                FROM public.user_credentials credential
                WHERE lower(credential.username) = lower(candidate)
            )
            ORDER BY suffix
            LIMIT 3
        $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION available_login_username_candidates(text) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION available_login_username_candidates(text) TO diyu_app"
    )

    op.execute(
        """
        CREATE TABLE content_request_failures (
            trace_id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            user_id uuid NOT NULL,
            account_id uuid NOT NULL,
            target text NOT NULL CHECK (target IN (
                'douyin_video', 'xiaohongshu_video',
                'xiaohongshu_graphic', 'wechat_channels_video'
            )),
            error_code text NOT NULL CHECK (
                error_code ~ '^[A-Z][A-Z0-9_]{2,63}$'
            ),
            failure_stage text NOT NULL CHECK (failure_stage IN (
                'authentication', 'authorization', 'csrf', 'intake',
                'context', 'provider', 'validation', 'persistence',
                'rate_limit', 'transport', 'unknown'
            )),
            retryable boolean NOT NULL,
            occurred_at timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (tenant_id, user_id)
                REFERENCES users(tenant_id, id),
            FOREIGN KEY (tenant_id, account_id)
                REFERENCES content_accounts(tenant_id, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX content_request_failures_tenant_time_idx "
        "ON content_request_failures (tenant_id, occurred_at DESC)"
    )
    op.execute(
        """
        CREATE FUNCTION reject_content_request_failure_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'content request failure diagnostics are append-only';
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER content_request_failures_immutable "
        "BEFORE UPDATE OR DELETE ON content_request_failures "
        "FOR EACH ROW EXECUTE FUNCTION reject_content_request_failure_mutation()"
    )
    op.execute(
        "ALTER TABLE content_request_failures ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE content_request_failures FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        "CREATE POLICY content_request_failures_tenant_scope "
        "ON content_request_failures "
        "USING (tenant_id = current_setting('app.tenant_id')::uuid) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid)"
    )
    op.execute(
        "GRANT SELECT, INSERT ON content_request_failures TO diyu_app"
    )


def downgrade() -> None:
    raise RuntimeError(
        "TENANT-01 formal usability changes are expand-forward only; "
        "application rollback never downgrades tenant data."
    )
