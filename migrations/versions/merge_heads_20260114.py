"""Merge heads for v1.5.0 upstream merge

Revision ID: merge_20260114
Revises: ('merge_20251224', '7524920417ef')
Create Date: 2026-01-14

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "merge_20260114"
down_revision = ("merge_20251224", "7524920417ef")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
