"""Merge heads for v1.4.0 upstream merge

Revision ID: merge_20251224
Revises: ('merge_20251111', 'b1dd589ac3f9')
Create Date: 2025-12-24

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "merge_20251224"
down_revision = ("merge_20251111", "b1dd589ac3f9")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
