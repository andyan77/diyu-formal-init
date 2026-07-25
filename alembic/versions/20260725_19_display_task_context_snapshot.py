"""Freeze the context each display task actually used.

A revision must reproduce the plan its own task was compiled from, so the task keeps an immutable
snapshot of the wall structure, this task's expression, product attributes and inventory. Later
edits to the store's default seed can no longer reach a task that already exists.

Expand only: the column is nullable and older tasks keep reading the live store profile.

Revision ID: 20260725_19
Revises: 20260725_18
Create Date: 2026-07-25
"""

from alembic import op

revision = "20260725_19"
down_revision = "20260725_18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE display_tasks ADD COLUMN context_snapshot jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE display_tasks DROP COLUMN context_snapshot")
