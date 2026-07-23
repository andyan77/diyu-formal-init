"""Persist the trusted product references resolved for a content task."""

from alembic import op

revision = "20260723_08"
down_revision = "20260723_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE business_tasks ADD COLUMN product_refs jsonb NOT NULL DEFAULT '[]'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE business_tasks DROP COLUMN product_refs")
