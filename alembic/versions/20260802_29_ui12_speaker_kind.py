"""Add the explicit publishing speaker kind used by UI-12.

Existing roles stay ``unknown``.  The migration never infers a speaker kind
from a role name, account name, or expression-profile prose.

Revision ID: 20260802_29
Revises: 20260801_28
"""

from alembic import op

revision = "20260802_29"
down_revision = "20260801_28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE content_roles "
        "ADD COLUMN speaker_kind text NOT NULL DEFAULT 'unknown'"
    )
    op.execute(
        "ALTER TABLE content_roles "
        "ADD CONSTRAINT content_roles_speaker_kind_check "
        "CHECK (speaker_kind IN "
        "('institutional_account', 'personal_ip_account', 'unknown'))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE content_roles "
        "DROP CONSTRAINT content_roles_speaker_kind_check"
    )
    op.execute("ALTER TABLE content_roles DROP COLUMN speaker_kind")
