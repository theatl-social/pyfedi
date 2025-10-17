"""merge migration heads

Revision ID: 349e99c9b2ef
Revises: a7b9f2c8e1d4, c86d6e395aea
Create Date: 2025-09-15 09:55:21.466185

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "349e99c9b2ef"
down_revision = ("a7b9f2c8e1d4", "c86d6e395aea")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
