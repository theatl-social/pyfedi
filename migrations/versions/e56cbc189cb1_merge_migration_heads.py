"""merge migration heads

Revision ID: e56cbc189cb1
Revises: 349e99c9b2ef, fb3a5a7696f7
Create Date: 2025-09-19 09:17:27.869671

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e56cbc189cb1'
down_revision = ('349e99c9b2ef', 'fb3a5a7696f7')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
