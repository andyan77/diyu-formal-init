"""Persist the minimum target-media semantics for M5-2 recompilation.

Revision ID: 20260723_09
Revises: 20260723_08
"""

from alembic import op

revision = "20260723_09"
down_revision = "20260723_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE business_tasks ADD COLUMN media_format text NOT NULL DEFAULT 'video' "
        "CHECK (media_format IN ('video', 'graphic'))"
    )
    op.execute(
        "ALTER TABLE business_tasks ADD COLUMN production_conditions text NOT NULL "
        "DEFAULT '未说明时按一人一部手机可完成的拍摄、录音和剪辑条件编写。'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE business_tasks DROP COLUMN production_conditions")
    op.execute("ALTER TABLE business_tasks DROP COLUMN media_format")
