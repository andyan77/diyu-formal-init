"""Add UI-05 entry, logical-account and brand-library scope invariants.

This migration is expand-first.  Existing tasks, versions, carrier rows and audit records stay
in place.  Tenant-owned backfills run with an explicit tenant context because the production
migrator does not bypass FORCE RLS.

Revision ID: 20260801_28
Revises: 20260731_27
"""

from alembic import op

revision = "20260801_28"
down_revision = "20260731_27"
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


def _preflight_existing_identity_data() -> None:
    """Reject ambiguous legacy identity data before the first schema or data write."""
    op.execute(
        """
        DO $$
        DECLARE
            tenant_record record;
        BEGIN
            FOR tenant_record IN SELECT id FROM public.tenants LOOP
                PERFORM set_config('app.tenant_id', tenant_record.id::text, true);
                IF EXISTS (
                    SELECT 1
                      FROM public.content_accounts AS carrier
                      LEFT JOIN public.content_accounts AS root_account
                        ON root_account.tenant_id = carrier.tenant_id
                       AND root_account.brand_id = carrier.brand_id
                       AND root_account.id = carrier.carrier_of_account_id
                       AND root_account.carrier_of_account_id IS NULL
                     WHERE carrier.tenant_id = tenant_record.id
                       AND carrier.carrier_of_account_id IS NOT NULL
                       AND (
                           root_account.id IS NULL
                           OR (carrier.enabled = true AND root_account.enabled = false)
                       )
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: a carrier is outside its tenant, brand or logical root';
                END IF;
                IF EXISTS (
                    SELECT 1
                      FROM public.content_accounts AS carrier
                      JOIN public.content_accounts AS root_account
                        ON root_account.tenant_id = carrier.tenant_id
                       AND root_account.id = carrier.carrier_of_account_id
                     WHERE carrier.tenant_id = tenant_record.id
                       AND carrier.carrier_of_account_id IS NOT NULL
                       AND (
                           carrier.control_organization_id IS DISTINCT FROM
                               root_account.control_organization_id
                           OR carrier.control_organization_source IS DISTINCT FROM
                               root_account.control_organization_source
                       )
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: a carrier control organization differs from its logical root';
                END IF;
                IF EXISTS (
                    SELECT 1
                      FROM public.content_accounts AS physical_account
                     WHERE physical_account.tenant_id = tenant_record.id
                       AND physical_account.enabled = true
                     GROUP BY
                       COALESCE(
                           physical_account.carrier_of_account_id,
                           physical_account.id
                       ),
                       physical_account.channel
                    HAVING count(*) > 1
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: a logical account has an ambiguous platform target';
                END IF;
                IF EXISTS (
                    SELECT 1
                      FROM public.auth_grants AS carrier_grant
                      JOIN public.content_accounts AS carrier
                        ON carrier.tenant_id = carrier_grant.tenant_id
                       AND carrier.id = carrier_grant.account_id
                       AND carrier.carrier_of_account_id IS NOT NULL
                     WHERE carrier_grant.tenant_id = tenant_record.id
                       AND carrier_grant.enabled = true
                       AND NOT EXISTS (
                           SELECT 1
                             FROM public.auth_grants AS root_grant
                            WHERE root_grant.tenant_id = carrier_grant.tenant_id
                              AND root_grant.user_id = carrier_grant.user_id
                              AND root_grant.account_id =
                                  carrier.carrier_of_account_id
                              AND root_grant.enabled = true
                              AND (
                                  carrier_grant.can_maintain_expression_profile = false
                                  OR root_grant.can_maintain_expression_profile = true
                              )
                       )
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: a carrier operator lacks an explicit logical-account grant';
                END IF;
                IF EXISTS (
                    SELECT 1
                      FROM public.account_content_roles AS account_role
                     WHERE account_role.tenant_id = tenant_record.id
                     GROUP BY account_role.account_id
                    HAVING count(*) > 1
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: a publishing account has multiple ContentRoles';
                END IF;
                IF EXISTS (
                    SELECT root_account.id
                      FROM public.content_accounts AS root_account
                      LEFT JOIN public.account_content_roles AS root_role
                        ON root_role.tenant_id = root_account.tenant_id
                       AND root_role.account_id = root_account.id
                     WHERE root_account.tenant_id = tenant_record.id
                       AND root_account.carrier_of_account_id IS NULL
                     GROUP BY root_account.id
                    HAVING count(root_role.id) <> 1
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: every logical publishing account needs one ContentRole';
                END IF;
                IF EXISTS (
                    SELECT 1
                      FROM public.content_accounts AS carrier
                      JOIN public.account_content_roles AS carrier_role
                        ON carrier_role.tenant_id = carrier.tenant_id
                       AND carrier_role.account_id = carrier.id
                      JOIN public.account_content_roles AS root_role
                        ON root_role.tenant_id = carrier.tenant_id
                       AND root_role.account_id = carrier.carrier_of_account_id
                     WHERE carrier.tenant_id = tenant_record.id
                       AND carrier.carrier_of_account_id IS NOT NULL
                       AND carrier_role.content_role_id <> root_role.content_role_id
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: a carrier ContentRole conflicts with its logical account';
                END IF;
                IF EXISTS (
                    SELECT 1
                      FROM public.content_accounts AS account
                     WHERE account.tenant_id = tenant_record.id
                       AND account.carrier_of_account_id IS NOT NULL
                       AND account.current_expression_profile_id IS NOT NULL
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: a platform carrier owns an expression profile';
                END IF;
                IF EXISTS (
                    SELECT 1
                      FROM public.account_expression_profile_versions AS profile
                      JOIN public.content_accounts AS account
                        ON account.tenant_id = profile.tenant_id
                       AND account.id = profile.account_id
                     WHERE profile.tenant_id = tenant_record.id
                       AND account.carrier_of_account_id IS NOT NULL
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: a platform carrier owns historical profile versions';
                END IF;
            END LOOP;
        END $$
        """
    )


def upgrade() -> None:
    _preflight_existing_identity_data()

    op.execute("ALTER TABLE organizations ADD COLUMN organization_level text NOT NULL DEFAULT 'unspecified'")
    op.execute(
        "ALTER TABLE organizations ADD CONSTRAINT organizations_level_check "
        "CHECK (organization_level IN "
        "('company', 'region', 'operating_unit', 'unspecified'))"
    )
    op.execute("ALTER TABLE users ADD COLUMN entry_kind text NOT NULL DEFAULT 'tenant_user'")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT users_entry_kind_check CHECK (entry_kind IN ('tenant_admin', 'tenant_user'))"
    )
    # Before UI-05 there was no level column.  The organization that already owns an
    # active tenant-management qualification is the only existing relation strong enough
    # to preserve as a company-level management organization; names are never inspected.
    op.execute(
        """
        DO $$
        DECLARE
            tenant_record record;
        BEGIN
            FOR tenant_record IN SELECT id FROM public.tenants LOOP
                PERFORM set_config('app.tenant_id', tenant_record.id::text, true);
                UPDATE public.organizations AS organization
                   SET organization_level = 'company'
                 WHERE organization.tenant_id = tenant_record.id
                   AND EXISTS (
                       SELECT 1
                         FROM public.users AS user_record
                         JOIN public.tenant_management_grants AS management_grant
                           ON management_grant.tenant_id = user_record.tenant_id
                          AND management_grant.user_id = user_record.id
                          AND management_grant.enabled = true
                        WHERE user_record.tenant_id = organization.tenant_id
                          AND user_record.organization_id = organization.id
                   );
            END LOOP;
        END $$
        """
    )

    op.execute(
        """
        CREATE TABLE display_access_grants (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            enabled boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, user_id)
        )
        """
    )
    _tenant_rls("display_access_grants")

    # Preserve management authority while making the two tenant entry kinds mutually exclusive.
    # A former dual-qualified identity keeps administration and loses content/display sessions;
    # no user, task, version, audit event or foreign key is deleted.
    op.execute(
        """
        DO $$
        DECLARE
            tenant_record record;
        BEGIN
            FOR tenant_record IN SELECT id FROM public.tenants LOOP
                PERFORM set_config('app.tenant_id', tenant_record.id::text, true);

                UPDATE public.users AS user_record
                   SET entry_kind = CASE
                       WHEN EXISTS (
                           SELECT 1
                             FROM public.tenant_management_grants AS management_grant
                            WHERE management_grant.tenant_id = tenant_record.id
                              AND management_grant.user_id = user_record.id
                              AND management_grant.enabled = true
                       )
                       THEN 'tenant_admin'
                       ELSE 'tenant_user'
                   END
                 WHERE user_record.tenant_id = tenant_record.id;

                UPDATE public.auth_grants AS account_grant
                   SET enabled = false,
                       can_maintain_expression_profile = false
                 WHERE account_grant.tenant_id = tenant_record.id
                   AND account_grant.enabled = true
                   AND EXISTS (
                       SELECT 1
                         FROM public.users AS user_record
                        WHERE user_record.tenant_id = tenant_record.id
                          AND user_record.id = account_grant.user_id
                          AND user_record.entry_kind = 'tenant_admin'
                   );

                UPDATE public.tenant_sessions AS session
                   SET revoked_at = now()
                 WHERE session.tenant_id = tenant_record.id
                   AND session.revoked_at IS NULL
                   AND EXISTS (
                       SELECT 1
                         FROM public.users AS user_record
                        WHERE user_record.tenant_id = tenant_record.id
                          AND user_record.id = session.user_id
                          AND user_record.entry_kind = 'tenant_admin'
                   );

                INSERT INTO public.display_access_grants
                    (id, tenant_id, user_id, enabled)
                SELECT gen_random_uuid(), tenant_record.id, user_record.id, true
                  FROM public.users AS user_record
                 WHERE user_record.tenant_id = tenant_record.id
                   AND user_record.entry_kind = 'tenant_user'
                   AND user_record.enabled = true
                   AND EXISTS (
                       SELECT 1
                         FROM public.display_stores AS store
                        WHERE store.tenant_id = tenant_record.id
                          AND store.execution_organization_id =
                              user_record.organization_id
                   )
                ON CONFLICT (tenant_id, user_id) DO UPDATE
                    SET enabled = EXCLUDED.enabled;
            END LOOP;
        END $$
        """
    )

    op.execute("ALTER TABLE business_tasks ADD COLUMN logical_account_id uuid REFERENCES content_accounts(id)")
    # Keep the physical account on a series for the previous application during
    # the rollback window.  The new application scopes across carriers with the
    # additional canonical logical account instead of rewriting history in place.
    op.execute("ALTER TABLE content_series ADD COLUMN logical_account_id uuid REFERENCES content_accounts(id)")
    op.execute(
        """
        DO $$
        DECLARE
            tenant_record record;
        BEGIN
            FOR tenant_record IN SELECT id FROM public.tenants LOOP
                PERFORM set_config('app.tenant_id', tenant_record.id::text, true);

                UPDATE public.business_tasks AS task
                   SET logical_account_id =
                       COALESCE(account.carrier_of_account_id, account.id)
                  FROM public.content_accounts AS account
                 WHERE task.tenant_id = tenant_record.id
                   AND account.tenant_id = tenant_record.id
                   AND account.id = task.account_id
                   AND task.logical_account_id IS NULL;

                UPDATE public.content_series AS series
                   SET logical_account_id =
                       COALESCE(account.carrier_of_account_id, account.id)
                  FROM public.content_accounts AS account
                 WHERE series.tenant_id = tenant_record.id
                   AND account.tenant_id = tenant_record.id
                   AND account.id = series.account_id
                   AND series.logical_account_id IS NULL;
            END LOOP;
        END $$
        """
    )
    op.execute("ALTER TABLE business_tasks ALTER COLUMN logical_account_id SET NOT NULL")
    op.execute("ALTER TABLE content_series ALTER COLUMN logical_account_id SET NOT NULL")
    op.execute(
        "CREATE INDEX business_tasks_logical_account_scope_idx "
        "ON business_tasks (tenant_id, brand_id, logical_account_id, created_by)"
    )
    op.execute(
        "CREATE INDEX content_series_logical_account_scope_idx "
        "ON content_series (tenant_id, brand_id, logical_account_id, created_by)"
    )

    # Keep inserts safe during a rolling application replacement: the database derives the
    # canonical root even when the previous application version does not send the new column.
    op.execute(
        """
        CREATE FUNCTION set_business_task_logical_account()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            canonical_account_id uuid;
        BEGIN
            SELECT COALESCE(account.carrier_of_account_id, account.id)
              INTO canonical_account_id
              FROM public.content_accounts AS account
             WHERE account.tenant_id = NEW.tenant_id
               AND account.id = NEW.account_id;
            IF canonical_account_id IS NULL THEN
                RAISE EXCEPTION 'content account is outside the task tenant'
                    USING ERRCODE = '23503';
            END IF;
            IF NEW.logical_account_id IS NOT NULL
               AND NEW.logical_account_id <> canonical_account_id THEN
                RAISE EXCEPTION 'logical account does not match the physical carrier'
                    USING ERRCODE = '23514';
            END IF;
            NEW.logical_account_id := canonical_account_id;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION set_business_task_logical_account() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION set_business_task_logical_account() TO diyu_app")
    op.execute(
        "CREATE TRIGGER business_tasks_logical_account "
        "BEFORE INSERT OR UPDATE OF account_id, logical_account_id ON business_tasks "
        "FOR EACH ROW EXECUTE FUNCTION set_business_task_logical_account()"
    )
    op.execute(
        """
        CREATE FUNCTION set_content_series_logical_account()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            canonical_account_id uuid;
        BEGIN
            IF NEW.account_id IS NULL THEN
                RETURN NEW;
            END IF;
            SELECT COALESCE(account.carrier_of_account_id, account.id)
              INTO canonical_account_id
              FROM public.content_accounts AS account
             WHERE account.tenant_id = NEW.tenant_id
               AND account.id = NEW.account_id;
            IF canonical_account_id IS NULL THEN
                RAISE EXCEPTION 'content account is outside the series tenant'
                    USING ERRCODE = '23503';
            END IF;
            IF NEW.logical_account_id IS NOT NULL
               AND NEW.logical_account_id <> canonical_account_id THEN
                RAISE EXCEPTION 'logical account does not match the physical series account'
                    USING ERRCODE = '23514';
            END IF;
            NEW.logical_account_id := canonical_account_id;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION set_content_series_logical_account() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION set_content_series_logical_account() TO diyu_app")
    op.execute(
        "CREATE TRIGGER content_series_logical_account "
        "BEFORE INSERT OR UPDATE OF account_id, logical_account_id ON content_series "
        "FOR EACH ROW EXECUTE FUNCTION set_content_series_logical_account()"
    )

    # Recheck legacy identity invariants and verify the task/series backfill before
    # installing permanent constraints. A failure still aborts this transaction.
    op.execute(
        """
        DO $$
        DECLARE
            tenant_record record;
        BEGIN
            FOR tenant_record IN SELECT id FROM public.tenants LOOP
                PERFORM set_config('app.tenant_id', tenant_record.id::text, true);
                IF EXISTS (
                    SELECT 1
                      FROM public.content_accounts AS carrier
                      LEFT JOIN public.content_accounts AS root_account
                        ON root_account.tenant_id = carrier.tenant_id
                       AND root_account.brand_id = carrier.brand_id
                       AND root_account.id = carrier.carrier_of_account_id
                       AND root_account.carrier_of_account_id IS NULL
                     WHERE carrier.tenant_id = tenant_record.id
                       AND carrier.carrier_of_account_id IS NOT NULL
                       AND (
                           root_account.id IS NULL
                           OR (carrier.enabled = true AND root_account.enabled = false)
                       )
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: a carrier is outside its tenant, brand or logical root';
                END IF;
                IF EXISTS (
                    SELECT 1
                      FROM public.content_accounts AS carrier
                      JOIN public.content_accounts AS root_account
                        ON root_account.tenant_id = carrier.tenant_id
                       AND root_account.id = carrier.carrier_of_account_id
                     WHERE carrier.tenant_id = tenant_record.id
                       AND carrier.carrier_of_account_id IS NOT NULL
                       AND (
                           carrier.control_organization_id IS DISTINCT FROM
                               root_account.control_organization_id
                           OR carrier.control_organization_source IS DISTINCT FROM
                               root_account.control_organization_source
                       )
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: a carrier control organization differs from its logical root';
                END IF;
                IF EXISTS (
                    SELECT 1
                      FROM public.content_accounts AS physical_account
                     WHERE physical_account.tenant_id = tenant_record.id
                       AND physical_account.enabled = true
                     GROUP BY
                       COALESCE(
                           physical_account.carrier_of_account_id,
                           physical_account.id
                       ),
                       physical_account.channel
                    HAVING count(*) > 1
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: a logical account has an ambiguous platform target';
                END IF;
                IF EXISTS (
                    SELECT 1
                      FROM public.auth_grants AS carrier_grant
                      JOIN public.content_accounts AS carrier
                        ON carrier.tenant_id = carrier_grant.tenant_id
                       AND carrier.id = carrier_grant.account_id
                       AND carrier.carrier_of_account_id IS NOT NULL
                     WHERE carrier_grant.tenant_id = tenant_record.id
                       AND carrier_grant.enabled = true
                       AND NOT EXISTS (
                           SELECT 1
                             FROM public.auth_grants AS root_grant
                            WHERE root_grant.tenant_id = carrier_grant.tenant_id
                              AND root_grant.user_id = carrier_grant.user_id
                              AND root_grant.account_id =
                                  carrier.carrier_of_account_id
                              AND root_grant.enabled = true
                              AND (
                                  carrier_grant.can_maintain_expression_profile = false
                                  OR root_grant.can_maintain_expression_profile = true
                              )
                       )
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: a carrier operator lacks an explicit logical-account grant';
                END IF;
                IF EXISTS (
                    SELECT 1
                      FROM public.account_content_roles AS account_role
                     WHERE account_role.tenant_id = tenant_record.id
                     GROUP BY account_role.account_id
                    HAVING count(*) > 1
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: a publishing account has multiple ContentRoles';
                END IF;
                IF EXISTS (
                    SELECT root_account.id
                      FROM public.content_accounts AS root_account
                      LEFT JOIN public.account_content_roles AS root_role
                        ON root_role.tenant_id = root_account.tenant_id
                       AND root_role.account_id = root_account.id
                     WHERE root_account.tenant_id = tenant_record.id
                       AND root_account.carrier_of_account_id IS NULL
                     GROUP BY root_account.id
                    HAVING count(root_role.id) <> 1
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: every logical publishing account needs one ContentRole';
                END IF;
                IF EXISTS (
                    SELECT 1
                      FROM public.content_accounts AS carrier
                      JOIN public.account_content_roles AS carrier_role
                        ON carrier_role.tenant_id = carrier.tenant_id
                       AND carrier_role.account_id = carrier.id
                      JOIN public.account_content_roles AS root_role
                        ON root_role.tenant_id = carrier.tenant_id
                       AND root_role.account_id = carrier.carrier_of_account_id
                     WHERE carrier.tenant_id = tenant_record.id
                       AND carrier.carrier_of_account_id IS NOT NULL
                       AND carrier_role.content_role_id <> root_role.content_role_id
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: a carrier ContentRole conflicts with its logical account';
                END IF;
                IF EXISTS (
                    SELECT 1
                      FROM public.content_accounts AS account
                     WHERE account.tenant_id = tenant_record.id
                       AND account.carrier_of_account_id IS NOT NULL
                       AND account.current_expression_profile_id IS NOT NULL
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: a platform carrier owns an expression profile';
                END IF;
                IF EXISTS (
                    SELECT 1
                      FROM public.account_expression_profile_versions AS profile
                      JOIN public.content_accounts AS account
                        ON account.tenant_id = profile.tenant_id
                       AND account.id = profile.account_id
                     WHERE profile.tenant_id = tenant_record.id
                       AND account.carrier_of_account_id IS NOT NULL
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: a platform carrier owns historical profile versions';
                END IF;
                IF EXISTS (
                    SELECT 1
                      FROM public.business_tasks AS task
                      JOIN public.content_accounts AS physical_account
                        ON physical_account.tenant_id = task.tenant_id
                       AND physical_account.id = task.account_id
                     WHERE task.tenant_id = tenant_record.id
                       AND task.logical_account_id IS DISTINCT FROM
                           COALESCE(
                               physical_account.carrier_of_account_id,
                               physical_account.id
                           )
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: a task logical account backfill is inconsistent';
                END IF;
                IF EXISTS (
                    SELECT 1
                      FROM public.content_series AS series
                      JOIN public.content_accounts AS physical_account
                        ON physical_account.tenant_id = series.tenant_id
                       AND physical_account.id = series.account_id
                     WHERE series.tenant_id = tenant_record.id
                       AND series.logical_account_id IS DISTINCT FROM
                           COALESCE(
                               physical_account.carrier_of_account_id,
                               physical_account.id
                           )
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: a series logical account backfill is inconsistent';
                END IF;
                IF EXISTS (
                    SELECT 1
                      FROM public.content_series_items AS item
                      JOIN public.content_series AS series
                        ON series.tenant_id = item.tenant_id
                       AND series.id = item.series_id
                      JOIN public.business_tasks AS task
                        ON task.tenant_id = item.tenant_id
                       AND task.id = item.task_id
                     WHERE item.tenant_id = tenant_record.id
                       AND (
                           task.brand_id <> series.brand_id
                           OR task.created_by <> series.created_by
                           OR task.logical_account_id <>
                               series.logical_account_id
                       )
                ) THEN
                    RAISE EXCEPTION
                        'UI-05 preflight: a series item crosses its frozen scope';
                END IF;
            END LOOP;
        END $$
        """
    )
    op.execute(
        "ALTER TABLE account_content_roles "
        "ADD CONSTRAINT account_content_roles_one_role_per_account "
        "UNIQUE (tenant_id, account_id)"
    )
    # The new runtime always resolves the ContentRole through the logical root.
    # Matching carrier relations remain writable only for compatibility with the
    # previous healthy image during the no-downgrade rollback window.  The
    # preflight above rejects any divergent relation, so this is not a second
    # product source of truth.
    op.execute(
        "ALTER TABLE content_accounts "
        "ADD CONSTRAINT content_account_carrier_has_no_current_profile "
        "CHECK (carrier_of_account_id IS NULL OR current_expression_profile_id IS NULL)"
    )

    op.execute("ALTER TABLE brand_products ADD COLUMN visibility_scope text NOT NULL DEFAULT 'brand_all'")
    op.execute(
        "ALTER TABLE brand_products ADD CONSTRAINT brand_products_visibility_scope_check "
        "CHECK (visibility_scope IN ('brand_all', 'headquarters', 'organizations'))"
    )
    op.execute(
        """
        CREATE TABLE brand_product_scope_organizations (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            product_id uuid NOT NULL REFERENCES brand_products(id) ON DELETE CASCADE,
            organization_id uuid NOT NULL REFERENCES organizations(id),
            UNIQUE (tenant_id, product_id, organization_id)
        )
        """
    )
    _tenant_rls("brand_product_scope_organizations")

    op.execute("ALTER TABLE material_assets ADD COLUMN visibility_scope text NOT NULL DEFAULT 'brand_all'")
    op.execute(
        "ALTER TABLE material_assets ADD CONSTRAINT material_assets_visibility_scope_check "
        "CHECK (visibility_scope IN ('brand_all', 'headquarters', 'organizations'))"
    )
    op.execute(
        """
        CREATE TABLE material_asset_scope_organizations (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            asset_id uuid NOT NULL REFERENCES material_assets(id) ON DELETE CASCADE,
            organization_id uuid NOT NULL REFERENCES organizations(id),
            UNIQUE (tenant_id, asset_id, organization_id)
        )
        """
    )
    _tenant_rls("material_asset_scope_organizations")
    op.execute(
        """
        DO $$
        DECLARE
            tenant_record record;
        BEGIN
            FOR tenant_record IN SELECT id FROM public.tenants LOOP
                PERFORM set_config('app.tenant_id', tenant_record.id::text, true);
                UPDATE public.material_assets
                   SET visibility_scope = 'organizations'
                 WHERE tenant_id = tenant_record.id
                   AND scope = 'organization'
                   AND owner_organization_id IS NOT NULL;
                INSERT INTO public.material_asset_scope_organizations
                    (id, tenant_id, asset_id, organization_id)
                SELECT gen_random_uuid(),
                       tenant_record.id,
                       asset.id,
                       asset.owner_organization_id
                  FROM public.material_assets AS asset
                 WHERE asset.tenant_id = tenant_record.id
                   AND asset.scope = 'organization'
                   AND asset.owner_organization_id IS NOT NULL
                ON CONFLICT (tenant_id, asset_id, organization_id) DO NOTHING;
            END LOOP;
        END $$
        """
    )

    op.execute(
        """
        CREATE TABLE brand_library_entries (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL REFERENCES brands(id),
            category text NOT NULL,
            title text NOT NULL,
            source_note text NOT NULL,
            content text NOT NULL,
            version text NOT NULL,
            status text NOT NULL DEFAULT 'candidate'
                CHECK (status IN ('candidate', 'active', 'retired')),
            visibility_scope text NOT NULL DEFAULT 'brand_all'
                CHECK (visibility_scope IN
                    ('brand_all', 'headquarters', 'organizations')),
            updated_by uuid NOT NULL REFERENCES users(id),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, brand_id, title, version)
        )
        """
    )
    _tenant_rls("brand_library_entries")
    op.execute(
        """
        CREATE TABLE brand_library_entry_organizations (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            entry_id uuid NOT NULL REFERENCES brand_library_entries(id) ON DELETE CASCADE,
            organization_id uuid NOT NULL REFERENCES organizations(id),
            UNIQUE (tenant_id, entry_id, organization_id)
        )
        """
    )
    _tenant_rls("brand_library_entry_organizations")


def downgrade() -> None:
    # Production never executes a database downgrade.  This only describes structural reversal;
    # it deliberately does not try to recreate revoked sessions or dual qualifications.
    op.execute("DROP TABLE brand_library_entry_organizations")
    op.execute("DROP TABLE brand_library_entries")
    op.execute("DROP TABLE material_asset_scope_organizations")
    op.execute("ALTER TABLE material_assets DROP CONSTRAINT material_assets_visibility_scope_check")
    op.execute("ALTER TABLE material_assets DROP COLUMN visibility_scope")
    op.execute("DROP TABLE brand_product_scope_organizations")
    op.execute("ALTER TABLE brand_products DROP CONSTRAINT brand_products_visibility_scope_check")
    op.execute("ALTER TABLE brand_products DROP COLUMN visibility_scope")
    op.execute("ALTER TABLE content_accounts DROP CONSTRAINT content_account_carrier_has_no_current_profile")
    op.execute("ALTER TABLE account_content_roles DROP CONSTRAINT account_content_roles_one_role_per_account")
    op.execute("DROP TRIGGER content_series_logical_account ON content_series")
    op.execute("DROP FUNCTION set_content_series_logical_account()")
    op.execute("DROP INDEX content_series_logical_account_scope_idx")
    op.execute("ALTER TABLE content_series DROP COLUMN logical_account_id")
    op.execute("DROP TRIGGER business_tasks_logical_account ON business_tasks")
    op.execute("DROP FUNCTION set_business_task_logical_account()")
    op.execute("DROP INDEX business_tasks_logical_account_scope_idx")
    op.execute("ALTER TABLE business_tasks DROP COLUMN logical_account_id")
    op.execute("DROP TABLE display_access_grants")
    op.execute("ALTER TABLE users DROP CONSTRAINT users_entry_kind_check")
    op.execute("ALTER TABLE users DROP COLUMN entry_kind")
    op.execute("ALTER TABLE organizations DROP CONSTRAINT organizations_level_check")
    op.execute("ALTER TABLE organizations DROP COLUMN organization_level")
