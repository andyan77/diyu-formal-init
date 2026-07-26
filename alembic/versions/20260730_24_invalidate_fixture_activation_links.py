"""Invalidate outstanding synthetic-fixture activation links.

Revision ID: 20260730_24
Revises: 20260729_23
Create Date: 2026-07-25
"""

from alembic import op

revision = "20260730_24"
down_revision = "20260729_23"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            affected record;
        BEGIN
            FOR affected IN
                SELECT DISTINCT token.tenant_id, token.user_id
                FROM public.user_activation_tokens token
                JOIN public.auth_grants grant_record
                  ON grant_record.tenant_id = token.tenant_id
                 AND grant_record.user_id = token.user_id
                JOIN public.content_accounts account
                  ON account.tenant_id = grant_record.tenant_id
                 AND account.id = grant_record.account_id
                WHERE token.used_at IS NULL
                  AND account.business_data_kind = 'synthetic_business_fixture'
            LOOP
                PERFORM set_config('app.tenant_id', affected.tenant_id::text, true);
                UPDATE public.user_activation_tokens
                   SET used_at = now()
                 WHERE tenant_id = affected.tenant_id
                   AND user_id = affected.user_id
                   AND used_at IS NULL;
                INSERT INTO public.activity_events
                    (id, tenant_id, actor_id, event_type, entity_type, entity_id)
                VALUES
                    (gen_random_uuid(), affected.tenant_id, affected.user_id,
                     'password.pending_links_invalidated_by_migration',
                     'formal_identity', affected.user_id);
            END LOOP;
        END
        $$
        """
    )


def downgrade() -> None:
    # Security invalidation is intentionally irreversible. No schema object was changed.
    pass
