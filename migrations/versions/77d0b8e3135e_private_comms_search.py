"""private comms search

Revision ID: 77d0b8e3135e
Revises: f26c13621774
Create Date: 2026-02-02 18:10:38.082619

"""
from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = '77d0b8e3135e'
down_revision = 'f26c13621774'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(text('UPDATE "community" SET private = false WHERE private is null'))


def downgrade():
    pass
