"""Merge migration heads after upstream v1.6.12 sync

Revision ID: merge_20260316
Revises: merge_heads_20260306, a84df9b8223c
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "merge_20260316"
down_revision = ("merge_heads_20260306", "a84df9b8223c")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
