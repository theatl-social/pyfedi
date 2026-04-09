"""Merge migration heads after upstream v1.6.17 sync

Revision ID: merge_20260409
Revises: merge_20260316, 8f05d68118d0
Create Date: 2026-04-09
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'merge_20260409'
down_revision = ('merge_20260316', '8f05d68118d0')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
