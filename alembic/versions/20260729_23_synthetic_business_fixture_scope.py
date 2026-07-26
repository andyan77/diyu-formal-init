"""Mark production-backed synthetic business fixture scopes without changing formal data.

Revision ID: 20260729_23
Revises: 20260728_22
"""

from alembic import op

revision = "20260729_23"
down_revision = "20260728_22"
branch_labels = None
depends_on = None


def upgrade() -> None:
    kind_check = (
        "CHECK (business_data_kind IN "
        "('formal_business_data', 'synthetic_business_fixture'))"
    )
    op.execute(
        "ALTER TABLE organizations ADD COLUMN business_data_kind text NOT NULL "
        f"DEFAULT 'formal_business_data' {kind_check}"
    )
    op.execute(
        "ALTER TABLE content_accounts ADD COLUMN business_data_kind text NOT NULL "
        f"DEFAULT 'formal_business_data' {kind_check}"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE content_accounts DROP COLUMN business_data_kind")
    op.execute("ALTER TABLE organizations DROP COLUMN business_data_kind")
