"""Add the confirmed brand strategy version required by the P1 media contract.

Revision ID: 20260722_03
Revises: 20260722_02
Create Date: 2026-07-22
"""

from alembic import op

revision = "20260722_03"
down_revision = "20260722_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE brands ADD COLUMN strategy_version text NOT NULL DEFAULT 'unversioned'")


def downgrade() -> None:
    op.execute("ALTER TABLE brands DROP COLUMN strategy_version")
