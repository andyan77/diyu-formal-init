"""Add the minimum content control surface: account expression profiles, private creation
preferences, this-task material notes, a frozen content context snapshot, a lightweight plan
and unmet capability requests.

Expand only.  Every new column is nullable or carries a safe default, no existing column is
dropped or rewritten in place, and the production migrator is neither superuser nor BYPASSRLS,
so per-tenant backfills set `app.tenant_id` before touching row-level-secured tables.

Revision ID: 20260726_20
Revises: 20260725_19
Create Date: 2026-07-26
"""

from alembic import op

revision = "20260726_20"
down_revision = "20260725_19"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "account_expression_profile_versions",
    "content_plans",
    "unmet_capability_requests",
)


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
        "CREATE TABLE account_expression_profile_versions ("
        "id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), "
        "account_id uuid NOT NULL REFERENCES content_accounts(id), "
        "content_role_id uuid NOT NULL REFERENCES content_roles(id), "
        "version integer NOT NULL CHECK (version > 0), "
        "identity_position text NOT NULL, authority_boundary text NOT NULL, "
        "audience_relationship text NOT NULL, content_territories text NOT NULL, "
        "default_production_conditions text NOT NULL, "
        "created_by uuid NOT NULL REFERENCES users(id), "
        "created_at timestamptz NOT NULL DEFAULT now(), "
        "UNIQUE (tenant_id, account_id, version))"
    )
    op.execute(
        "CREATE TABLE content_plans ("
        "id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), "
        "brand_id uuid NOT NULL REFERENCES brands(id), "
        "account_id uuid NOT NULL REFERENCES content_accounts(id), "
        "created_by uuid NOT NULL REFERENCES users(id), "
        "document jsonb NOT NULL DEFAULT '{}'::jsonb, "
        "updated_at timestamptz NOT NULL DEFAULT now(), "
        "UNIQUE (tenant_id, account_id, created_by))"
    )
    op.execute(
        "CREATE TABLE unmet_capability_requests ("
        "id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), "
        "stable_request_id text NOT NULL, "
        "brand_id uuid NOT NULL REFERENCES brands(id), "
        "account_id uuid REFERENCES content_accounts(id), "
        "created_by uuid NOT NULL REFERENCES users(id), "
        "request_text text NOT NULL, catalog_version text NOT NULL, "
        "direction_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb, "
        "gap_type text NOT NULL DEFAULT 'unclassified' CHECK (gap_type IN "
        "('unclassified', 'knowledge', 'generation_method', 'media_tool', "
        "'product_scope', 'policy_conflict', 'source_gap')), "
        "status text NOT NULL DEFAULT 'received' CHECK (status IN "
        "('received', 'classified', 'answered')), "
        "response_text text NOT NULL DEFAULT '', "
        "created_at timestamptz NOT NULL DEFAULT now(), responded_at timestamptz, "
        "UNIQUE (tenant_id, stable_request_id))"
    )
    for table in TENANT_TABLES:
        _tenant_rls(table)

    # A private creation preference is the natural person's own; the tenant alone is not a
    # sufficient scope, so the policy also requires a trusted app.user_id.  A transaction that
    # never sets it sees nothing instead of erroring, which keeps every other repository safe.
    op.execute(
        "CREATE TABLE user_creation_preferences ("
        "id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), "
        "user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
        "version integer NOT NULL DEFAULT 1 CHECK (version > 0), "
        "enabled boolean NOT NULL DEFAULT true, "
        "direction_defaults jsonb NOT NULL DEFAULT '{}'::jsonb, "
        "collaboration_note text NOT NULL DEFAULT '', "
        "body_related_opt_in boolean NOT NULL DEFAULT false, "
        "updated_at timestamptz NOT NULL DEFAULT now(), "
        "UNIQUE (tenant_id, user_id))"
    )
    op.execute("ALTER TABLE user_creation_preferences ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE user_creation_preferences FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY user_creation_preferences_owner_scope ON user_creation_preferences "
        "USING (tenant_id = current_setting('app.tenant_id')::uuid "
        "AND user_id = current_setting('app.user_id', true)::uuid) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid "
        "AND user_id = current_setting('app.user_id', true)::uuid)"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON user_creation_preferences TO diyu_app")

    op.execute(
        "ALTER TABLE content_accounts ADD COLUMN control_organization_id uuid "
        "REFERENCES organizations(id)"
    )
    op.execute(
        "ALTER TABLE content_accounts ADD COLUMN current_expression_profile_id uuid "
        "REFERENCES account_expression_profile_versions(id)"
    )
    op.execute(
        "ALTER TABLE auth_grants ADD COLUMN can_maintain_expression_profile boolean "
        "NOT NULL DEFAULT false"
    )
    op.execute("ALTER TABLE material_assets ADD COLUMN reference_note text NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE business_tasks ADD COLUMN content_context_snapshot jsonb")

    # Only unique evidence may fill a control organization.  The single registered
    # publishing_account.created event carries the actor who actually created the account; when
    # there is no such event, or more than one, or the actor is gone, the column stays NULL and
    # nobody may maintain that account's profile until an unambiguous decision exists.  Account
    # names, role names and operator names are never used to guess.
    op.execute(
        """
        DO $$
        DECLARE
            tenant_record record;
        BEGIN
            FOR tenant_record IN SELECT id FROM public.tenants LOOP
                PERFORM set_config('app.tenant_id', tenant_record.id::text, true);
                UPDATE public.content_accounts account
                   SET control_organization_id = evidence.organization_id
                  FROM (
                        SELECT event.entity_id AS account_id,
                               min(actor.organization_id::text)::uuid AS organization_id,
                               count(*) AS event_count,
                               count(DISTINCT actor.organization_id) AS organization_count
                          FROM public.activity_events event
                          JOIN public.users actor
                            ON actor.id = event.actor_id
                           AND actor.tenant_id = event.tenant_id
                         WHERE event.tenant_id = tenant_record.id
                           AND event.event_type = 'publishing_account.created'
                           AND event.entity_type = 'content_account'
                         GROUP BY event.entity_id
                       ) AS evidence
                 WHERE account.tenant_id = tenant_record.id
                   AND account.id = evidence.account_id
                   AND account.control_organization_id IS NULL
                   AND evidence.event_count = 1
                   AND evidence.organization_count = 1;
            END LOOP;
        END $$
        """
    )

    # Losslessly reconstruct a legacy content snapshot from the receipt each task's first run
    # already recorded.  It never claims a profile version and never borrows today's settings.
    op.execute(
        """
        DO $$
        DECLARE
            tenant_record record;
        BEGIN
            FOR tenant_record IN SELECT id FROM public.tenants LOOP
                PERFORM set_config('app.tenant_id', tenant_record.id::text, true);
                UPDATE public.business_tasks task
                   SET content_context_snapshot = jsonb_build_object(
                        'schema', 'content-context-snapshot-legacy-v1',
                        'catalog_version', NULL,
                        'original_direction', jsonb_build_object(
                            'selections', '[]'::jsonb, 'custom_text', '',
                            'body_related_opt_in', false),
                        'applied_direction', '[]'::jsonb,
                        'translation_notice', NULL,
                        'content_role', receipt.input_receipt -> 'content_role',
                        'legacy_content_role', true,
                        'account_expression_profile_version', NULL,
                        'account_expression_profile_id', NULL,
                        'private_preference_mode', 'legacy_absent',
                        'private_preference_version', NULL,
                        'material_refs', '[]'::jsonb)
                  FROM (
                        SELECT DISTINCT ON (run.task_id) run.task_id, run.input_receipt
                          FROM public.generation_runs run
                         WHERE run.tenant_id = tenant_record.id
                           AND run.input_receipt IS NOT NULL
                         ORDER BY run.task_id, run.started_at
                       ) AS receipt
                 WHERE task.tenant_id = tenant_record.id
                   AND task.id = receipt.task_id
                   AND task.content_context_snapshot IS NULL;
            END LOOP;
        END $$
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE business_tasks DROP COLUMN content_context_snapshot")
    op.execute("ALTER TABLE material_assets DROP COLUMN reference_note")
    op.execute("ALTER TABLE auth_grants DROP COLUMN can_maintain_expression_profile")
    op.execute("ALTER TABLE content_accounts DROP COLUMN current_expression_profile_id")
    op.execute("ALTER TABLE content_accounts DROP COLUMN control_organization_id")
    op.execute("DROP TABLE user_creation_preferences")
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP TABLE {table}")
