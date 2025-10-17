"""merge migration heads

Revision ID: 06792567caa2
Revises: e56cbc189cb1, 8bfaa7ebb160
Create Date: 2025-10-08 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "06792567caa2"
down_revision = ("e56cbc189cb1", "8bfaa7ebb160")
branch_labels = None
depends_on = None


def upgrade():
    # This is a merge migration - no schema changes
    pass


def downgrade():
    # This is a merge migration - no schema changes
    pass
