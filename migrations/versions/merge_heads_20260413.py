"""merge heads 20260413

Revision ID: merge_20260413
Revises: e4935b360d97, merge_20260409
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'merge_20260413'
down_revision = ('e4935b360d97', 'merge_20260409')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
