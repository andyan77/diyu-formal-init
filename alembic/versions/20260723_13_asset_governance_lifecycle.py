"""Add lifecycle effectiveness metadata to system domain assets.

Revision ID: 20260723_13
Revises: 20260723_12
Create Date: 2026-07-23
"""

from alembic import op

revision = "20260723_13"
down_revision = "20260723_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE system_domain_assets DROP CONSTRAINT system_domain_assets_status_check")
    op.execute(
        "ALTER TABLE system_domain_assets ADD CONSTRAINT system_domain_assets_status_check "
        "CHECK (status IN ('review_candidate', 'active', 'deprecated'))"
    )
    op.execute("ALTER TABLE system_domain_assets ADD COLUMN valid_until date")
    op.execute(
        "ALTER TABLE system_domain_assets ADD COLUMN superseded_by text "
        "REFERENCES system_domain_assets(asset_id)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE system_domain_assets DROP COLUMN superseded_by")
    op.execute("ALTER TABLE system_domain_assets DROP COLUMN valid_until")
    op.execute("ALTER TABLE system_domain_assets DROP CONSTRAINT system_domain_assets_status_check")
    op.execute(
        "ALTER TABLE system_domain_assets ADD CONSTRAINT system_domain_assets_status_check "
        "CHECK (status IN ('review_candidate', 'active'))"
    )
