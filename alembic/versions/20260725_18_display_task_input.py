"""Separate the reusable wall structure from this task's own input.

The store profile keeps only reusable structure. This task's theme, focus
suggestion and product snapshot move to display_stores.current_task_input, and
the previously stored on-site confirmation block is removed: the system issues a
reference plan and never records a business confirmation, approval or proxy
submitter.

Revision ID: 20260725_18
Revises: 20260724_17
Create Date: 2026-07-25
"""

from alembic import op

revision = "20260725_18"
down_revision = "20260724_17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE display_stores ADD COLUMN current_task_input jsonb")
    op.execute(
        """
        UPDATE display_stores s
           SET current_task_input = jsonb_build_object(
                   'version', COALESCE(s.rail_profile #>> '{inventory_snapshot,record_version}', s.profile_version),
                   'source', 'user_task_snapshot',
                   'expression', COALESCE(
                       (SELECT p.body
                          FROM display_policies p
                         WHERE p.tenant_id = s.tenant_id AND p.brand_id = s.brand_id
                           AND p.version = s.profile_version),
                       '{}'::jsonb),
                   'products', s.rail_profile #> '{inventory_snapshot,items}')
         WHERE s.rail_profile ? 'inventory_snapshot'
        """
    )
    op.execute(
        "UPDATE display_stores SET rail_profile = rail_profile - 'inventory_snapshot' - 'confirmation' "
        "WHERE rail_profile ? 'inventory_snapshot' OR rail_profile ? 'confirmation'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE display_stores DROP COLUMN current_task_input")
