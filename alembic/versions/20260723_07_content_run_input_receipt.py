"""Record the trusted M5 content compilation receipt.

Revision ID: 20260723_07
Revises: 20260723_06
"""

from alembic import op

revision = "20260723_07"
down_revision = "20260723_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE generation_runs ADD COLUMN input_receipt jsonb NOT NULL DEFAULT '{}'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE generation_runs DROP COLUMN input_receipt")
