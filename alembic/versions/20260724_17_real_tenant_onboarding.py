"""Create an account-independent tenant onboarding scope and atomic brand draft.

Revision ID: 20260724_17
Revises: 20260724_16
Create Date: 2026-07-24
"""

from alembic import op

revision = "20260724_17"
down_revision = "20260724_16"
branch_labels = None
depends_on = None

_OLD_SIGNATURE = "uuid, text, uuid, uuid, text, text, uuid, uuid, text, timestamptz"
_NEW_SIGNATURE = _OLD_SIGNATURE + ", uuid, uuid, uuid, text, text, text, text, text"


def upgrade() -> None:
    op.execute(f"DROP FUNCTION ops_provision_tenant({_OLD_SIGNATURE})")
    op.execute(
        """
        CREATE FUNCTION ops_provision_tenant(
            p_tenant_id uuid, p_tenant_name text, p_organization_id uuid, p_user_id uuid,
            p_display_name text, p_username text, p_credential_id uuid, p_activation_id uuid,
            p_token_digest text, p_expires_at timestamptz,
            p_brand_id uuid, p_baseline_id uuid, p_audience_id uuid, p_brand_draft text,
            p_positioning text, p_decision_order text, p_tone text, p_audience_description text
        ) RETURNS TABLE (tenant_id uuid, user_id uuid, username text, brand_id uuid)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        DECLARE
            v_tenant_id uuid;
            v_credential_tenant_id uuid;
            v_user_id uuid;
            v_username text;
            v_password_hash text;
            v_display_name text;
            v_brand_id uuid;
        BEGIN
            SELECT tenant_record.id
              INTO v_tenant_id
              FROM public.tenants tenant_record
             WHERE tenant_record.name = p_tenant_name;

            SELECT credential.tenant_id, credential.user_id, credential.username,
                   credential.password_hash
              INTO v_credential_tenant_id, v_user_id, v_username, v_password_hash
              FROM public.user_credentials credential
             WHERE lower(credential.username) = lower(p_username);

            IF v_tenant_id IS NOT NULL OR v_user_id IS NOT NULL THEN
                IF v_tenant_id IS NULL
                   OR v_user_id IS NULL
                   OR v_credential_tenant_id <> v_tenant_id THEN
                    RAISE EXCEPTION 'tenant name or username belongs to another identity'
                        USING ERRCODE = '23505';
                END IF;

                PERFORM set_config('app.tenant_id', v_tenant_id::text, true);
                SELECT user_record.display_name
                  INTO v_display_name
                  FROM public.users user_record
                  JOIN public.tenant_management_grants management_grant
                    ON management_grant.tenant_id = user_record.tenant_id
                   AND management_grant.user_id = user_record.id
                   AND management_grant.enabled = true
                 WHERE user_record.tenant_id = v_tenant_id
                   AND user_record.id = v_user_id
                   AND user_record.enabled = true;
                IF v_display_name IS NULL OR v_display_name <> p_display_name THEN
                    RAISE EXCEPTION 'existing tenant shell does not match this request'
                        USING ERRCODE = '23505';
                END IF;
                IF v_password_hash IS NOT NULL THEN
                    RAISE EXCEPTION 'activated tenant cannot be reprovisioned'
                        USING ERRCODE = '23505';
                END IF;

                SELECT brand_record.id
                  INTO v_brand_id
                  FROM public.brands brand_record
                 WHERE brand_record.tenant_id = v_tenant_id
                   AND brand_record.name = p_tenant_name;
                IF v_brand_id IS NULL THEN
                    v_brand_id := p_brand_id;
                    INSERT INTO public.brands
                        (id, tenant_id, name, positioning, decision_order, tone)
                    VALUES
                        (v_brand_id, v_tenant_id, p_tenant_name, p_positioning, p_decision_order, p_tone);
                END IF;

                INSERT INTO public.brand_expression_baselines
                    (id, tenant_id, brand_id, version, draft, status)
                VALUES
                    (p_baseline_id, v_tenant_id, v_brand_id, 1, p_brand_draft, 'draft')
                ON CONFLICT DO NOTHING;
                INSERT INTO public.brand_audiences
                    (id, tenant_id, brand_id, description)
                VALUES
                    (p_audience_id, v_tenant_id, v_brand_id, p_audience_description)
                ON CONFLICT DO NOTHING;
                UPDATE public.user_activation_tokens activation_token
                   SET used_at = now()
                 WHERE activation_token.tenant_id = v_tenant_id
                   AND activation_token.user_id = v_user_id
                   AND activation_token.used_at IS NULL;
                INSERT INTO public.user_activation_tokens
                    (id, tenant_id, user_id, purpose, token_digest, expires_at)
                VALUES
                    (p_activation_id, v_tenant_id, v_user_id, 'activate', p_token_digest, p_expires_at);
                INSERT INTO public.ops_tenant_registry (tenant_id)
                VALUES (v_tenant_id)
                ON CONFLICT ON CONSTRAINT ops_tenant_registry_pkey DO UPDATE
                    SET enabled = true, disabled_at = NULL;

                RETURN QUERY SELECT v_tenant_id, v_user_id, v_username, v_brand_id;
                RETURN;
            END IF;

            INSERT INTO public.tenants (id, name)
            VALUES (p_tenant_id, p_tenant_name);
            PERFORM set_config('app.tenant_id', p_tenant_id::text, true);
            INSERT INTO public.organizations (id, tenant_id, name)
            VALUES (p_organization_id, p_tenant_id, p_tenant_name || '管理组织');
            INSERT INTO public.users (id, tenant_id, organization_id, display_name)
            VALUES (p_user_id, p_tenant_id, p_organization_id, p_display_name);
            INSERT INTO public.tenant_management_grants (id, tenant_id, user_id)
            VALUES (gen_random_uuid(), p_tenant_id, p_user_id);
            INSERT INTO public.user_credentials (user_id, tenant_id, username)
            VALUES (p_user_id, p_tenant_id, p_username);
            INSERT INTO public.brands
                (id, tenant_id, name, positioning, decision_order, tone)
            VALUES
                (p_brand_id, p_tenant_id, p_tenant_name, p_positioning, p_decision_order, p_tone);
            INSERT INTO public.brand_expression_baselines
                (id, tenant_id, brand_id, version, draft, status)
            VALUES
                (p_baseline_id, p_tenant_id, p_brand_id, 1, p_brand_draft, 'draft');
            INSERT INTO public.brand_audiences
                (id, tenant_id, brand_id, description)
            VALUES
                (p_audience_id, p_tenant_id, p_brand_id, p_audience_description);
            INSERT INTO public.user_activation_tokens
                (id, tenant_id, user_id, purpose, token_digest, expires_at)
            VALUES
                (p_activation_id, p_tenant_id, p_user_id, 'activate', p_token_digest, p_expires_at);
            INSERT INTO public.ops_tenant_registry (tenant_id)
            VALUES (p_tenant_id);

            RETURN QUERY SELECT p_tenant_id, p_user_id, p_username, p_brand_id;
        END;
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION ops_provision_tenant FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION ops_provision_tenant TO diyu_app")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION ops_provision_tenant({_NEW_SIGNATURE})")
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
