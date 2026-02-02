"""merge heads v1.6.0

Revision ID: 7dfa0b456a51
Revises: f26c13621774, merge_20260114
Create Date: 2026-02-02 12:00:09.319293

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7dfa0b456a51"
down_revision = ("f26c13621774", "merge_20260114")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
