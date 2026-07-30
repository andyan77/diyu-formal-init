"""Separate a logical account's availability from its platform targets.

Revision ID: 20260807_34
Revises: 20260806_33

The migration is expand-first. Existing rows remain available, and the previous
healthy application ignores the additive column.
"""

from alembic import op

revision = "20260807_34"
down_revision = "20260806_33"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE content_accounts "
        "ADD COLUMN platform_enabled boolean NOT NULL DEFAULT true"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE content_accounts DROP COLUMN platform_enabled")
