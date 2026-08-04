"""Add an explicit, non-destructive lifecycle to tenant organizations.

Revision ID: 20260817_44
Revises: 20260816_43

Organizations remain durable identity and history anchors. Disabling one only
removes it from new assignments; the application refuses to disable an
organization while a live business object still references it.
"""

from alembic import op

revision = "20260817_44"
down_revision = "20260816_43"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE organizations "
        "ADD COLUMN enabled boolean NOT NULL DEFAULT true"
    )
    op.execute(
        "CREATE INDEX organizations_assignment_lookup "
        "ON organizations (tenant_id, enabled, name)"
    )


def downgrade() -> None:
    raise RuntimeError(
        "TENANT-01 organization lifecycle is append-forward only; "
        "application rollback never removes lifecycle truth."
    )
