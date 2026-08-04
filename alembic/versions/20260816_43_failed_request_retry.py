"""Allow a failed idempotent request to retry on the same business task.

Revision ID: 20260816_43
Revises: 20260815_42

Only running or succeeded runs reserve a client request id.  Failed attempts
stay append-only, while a retry with an identical frozen context adds a new
run to the original task instead of creating a duplicate task.
"""

from alembic import op

revision = "20260816_43"
down_revision = "20260815_42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX generation_runs_active_client_request")
    op.execute(
        """
        CREATE UNIQUE INDEX generation_runs_active_client_request
            ON generation_runs (tenant_id, client_request_id)
         WHERE client_request_id IS NOT NULL
           AND status IN ('running', 'succeeded')
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "TENANT-01 failed-request retry history is append-forward only; "
        "application rollback never rewrites generation attempts."
    )
