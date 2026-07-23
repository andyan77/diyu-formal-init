"""Record the trusted deterministic DM01 inputs for each display run.

Revision ID: 20260723_05
Revises: 20260722_04
"""

from alembic import op

revision = "20260723_05"
down_revision = "20260722_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE display_generation_runs "
        "ADD COLUMN input_receipt jsonb NOT NULL DEFAULT '{}'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE display_generation_runs DROP COLUMN input_receipt")
