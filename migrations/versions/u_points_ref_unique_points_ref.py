"""unique points_ledger (user_id, ref)

Revision ID: u_points_ref
Revises: 260225142333
Create Date: 2026-03-01

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "u_points_ref"
down_revision = "260225142333"
branch_labels = None
depends_on = None


def upgrade():
    # Idempotency: prevent duplicate credits with same ref per user
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_points_ledger_user_ref "
        "ON points_ledger (user_id, ref) "
        "WHERE ref IS NOT NULL"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ux_points_ledger_user_ref")