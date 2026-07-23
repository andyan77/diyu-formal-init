"""Add stable content product contracts and rename shared brand products.

Revision ID: 20260723_06
Revises: 20260723_05
"""

from alembic import op

revision = "20260723_06"
down_revision = "20260723_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE display_products RENAME TO brand_products")
    op.execute(
        "ALTER POLICY display_products_tenant_scope ON brand_products RENAME TO brand_products_tenant_scope"
    )
    op.execute(
        "ALTER TABLE business_tasks ADD COLUMN primary_content_product text NOT NULL DEFAULT 'dressing_decision' "
        "CHECK (primary_content_product IN ('dressing_decision', 'product_truth', 'brand_life_narrative', "
        "'local_response', 'visual_styling_story'))"
    )
    op.execute(
        "ALTER TABLE content_versions ADD COLUMN product_contract jsonb NOT NULL DEFAULT '{}'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE content_versions DROP COLUMN product_contract")
    op.execute("ALTER TABLE business_tasks DROP COLUMN primary_content_product")
    op.execute(
        "ALTER POLICY brand_products_tenant_scope ON brand_products RENAME TO display_products_tenant_scope"
    )
    op.execute("ALTER TABLE brand_products RENAME TO display_products")
