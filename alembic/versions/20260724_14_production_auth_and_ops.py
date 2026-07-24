"""Add production credentials, opaque sessions and the narrow operations boundary.

Revision ID: 20260724_14
Revises: 20260723_13
Create Date: 2026-07-24
"""

from alembic import op

revision = "20260724_14"
down_revision = "20260723_13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE user_credentials ("
        "user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, "
        "tenant_id uuid NOT NULL REFERENCES tenants(id), username text NOT NULL, password_hash text, "
        "password_changed_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()"
        ")"
    )
    op.execute("CREATE UNIQUE INDEX user_credentials_username_key ON user_credentials (lower(username))")
    op.execute(
        "CREATE TABLE user_activation_tokens ("
        "id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), "
        "user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
        "purpose text NOT NULL CHECK (purpose IN ('activate', 'reset')), token_digest text NOT NULL UNIQUE, "
        "expires_at timestamptz NOT NULL, used_at timestamptz, created_by uuid REFERENCES users(id), "
        "created_at timestamptz NOT NULL DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE TABLE tenant_sessions ("
        "id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), "
        "user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
        "audience text NOT NULL CHECK (audience IN ('tenant-user', 'tenant-admin')), "
        "token_digest text NOT NULL UNIQUE, issued_at timestamptz NOT NULL DEFAULT now(), "
        "expires_at timestamptz NOT NULL, revoked_at timestamptz"
        ")"
    )
    op.execute(
        "CREATE TABLE platform_operators ("
        "id uuid PRIMARY KEY, username text NOT NULL, password_hash text NOT NULL, "
        "totp_secret text NOT NULL, enabled boolean NOT NULL DEFAULT true, "
        "created_at timestamptz NOT NULL DEFAULT now()"
        ")"
    )
    op.execute("CREATE UNIQUE INDEX platform_operators_username_key ON platform_operators (lower(username))")
    op.execute(
        "CREATE TABLE platform_sessions ("
        "id uuid PRIMARY KEY, operator_id uuid NOT NULL REFERENCES platform_operators(id) ON DELETE CASCADE, "
        "token_digest text NOT NULL UNIQUE, issued_at timestamptz NOT NULL DEFAULT now(), "
        "expires_at timestamptz NOT NULL, revoked_at timestamptz"
        ")"
    )
    op.execute(
        "CREATE TABLE ops_tenant_registry ("
        "tenant_id uuid PRIMARY KEY REFERENCES tenants(id), enabled boolean NOT NULL DEFAULT true, "
        "created_at timestamptz NOT NULL DEFAULT now(), disabled_at timestamptz"
        ")"
    )
    op.execute(
        "CREATE TABLE ops_audit_events ("
        "id uuid PRIMARY KEY, operator_id uuid REFERENCES platform_operators(id), event_type text NOT NULL, "
        "tenant_id uuid, created_at timestamptz NOT NULL DEFAULT now()"
        ")"
    )
    for table in (
        "user_credentials",
        "user_activation_tokens",
        "tenant_sessions",
        "platform_operators",
        "platform_sessions",
        "ops_tenant_registry",
        "ops_audit_events",
    ):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO diyu_app")
    op.execute(
        """
        CREATE FUNCTION ops_provision_tenant(
            p_tenant_id uuid, p_tenant_name text, p_organization_id uuid, p_user_id uuid,
            p_display_name text, p_username text, p_credential_id uuid, p_activation_id uuid,
            p_token_digest text, p_expires_at timestamptz
        ) RETURNS TABLE (tenant_id uuid, user_id uuid, username text)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        BEGIN
            INSERT INTO public.tenants (id, name) VALUES (p_tenant_id, p_tenant_name);
            PERFORM set_config('app.tenant_id', p_tenant_id::text, true);
            INSERT INTO public.organizations (id, tenant_id, name)
            VALUES (p_organization_id, p_tenant_id, p_tenant_name || '管理组织');
            INSERT INTO public.users (id, tenant_id, organization_id, display_name)
            VALUES (p_user_id, p_tenant_id, p_organization_id, p_display_name);
            INSERT INTO public.tenant_management_grants (id, tenant_id, user_id)
            VALUES (gen_random_uuid(), p_tenant_id, p_user_id);
            INSERT INTO public.user_credentials (user_id, tenant_id, username)
            VALUES (p_user_id, p_tenant_id, p_username);
            INSERT INTO public.user_activation_tokens
                (id, tenant_id, user_id, purpose, token_digest, expires_at)
            VALUES (p_activation_id, p_tenant_id, p_user_id, 'activate', p_token_digest, p_expires_at);
            INSERT INTO public.ops_tenant_registry (tenant_id) VALUES (p_tenant_id);
            RETURN QUERY SELECT p_tenant_id, p_user_id, p_username;
        END;
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION ops_provision_tenant FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION ops_provision_tenant TO diyu_app")
    op.execute(
        """
        CREATE FUNCTION ops_set_tenant_enabled(p_tenant_id uuid, p_enabled boolean) RETURNS void
        LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
            UPDATE public.ops_tenant_registry
            SET enabled = p_enabled, disabled_at = CASE WHEN p_enabled THEN NULL ELSE now() END
            WHERE tenant_id = p_tenant_id
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION ops_set_tenant_enabled FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION ops_set_tenant_enabled TO diyu_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION ops_set_tenant_enabled")
    op.execute("DROP FUNCTION ops_provision_tenant")
    op.execute("DROP TABLE ops_audit_events")
    op.execute("DROP TABLE ops_tenant_registry")
    op.execute("DROP TABLE platform_sessions")
    op.execute("DROP TABLE platform_operators")
    op.execute("DROP TABLE tenant_sessions")
    op.execute("DROP TABLE user_activation_tokens")
    op.execute("DROP TABLE user_credentials")
