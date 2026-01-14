"""Merge migration heads - v1.3.0 merge

Revision ID: merge_20251111
Revises: merge_20251029, fa8677acf5ee
Create Date: 2025-11-11 10:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "merge_20251111"
down_revision = ("merge_20251029", "fa8677acf5ee")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
