"""merge migration heads after upstream v1.6.9 merge

Revision ID: merge_heads_20260306
Revises: ('7dfa0b456a51', '41d7b55a5fa8')
Create Date: 2026-03-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'merge_heads_20260306'
down_revision = ('7dfa0b456a51', '41d7b55a5fa8')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
