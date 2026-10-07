"""fix post reposters

Revision ID: 366426cd4111
Revises: 230b284eaa7f
Create Date: 2026-10-03 21:03:08.200915

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '366426cd4111'
down_revision = '230b284eaa7f'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(text('UPDATE "post" SET from_reposter = false WHERE from_reposter is null'))


def downgrade():
    pass
