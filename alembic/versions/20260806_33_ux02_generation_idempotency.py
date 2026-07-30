"""Bind one visible content result to one browser request.

The migration is expand-first. Existing runs keep a null request id; new formal
clients may retry the same request without creating another immutable version.

Revision ID: 20260806_33
Revises: 20260805_32
"""

from alembic import op

revision = "20260806_33"
down_revision = "20260805_32"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE generation_runs ADD COLUMN client_request_id uuid")
    op.execute(
        """
        CREATE UNIQUE INDEX generation_runs_active_client_request
            ON generation_runs (tenant_id, client_request_id)
         WHERE client_request_id IS NOT NULL
           AND status IN ('running', 'succeeded')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX generation_runs_active_client_request")
    op.execute("ALTER TABLE generation_runs DROP COLUMN client_request_id")
