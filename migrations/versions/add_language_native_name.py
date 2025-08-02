"""Add native_name column to language table

Revision ID: add_language_native_name
Revises: feef49234599
Create Date: 2025-08-02 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_language_native_name'
down_revision = 'feef49234599'
branch_labels = None
depends_on = None


def upgrade():
    # Add native_name column to language table
    op.add_column('language', sa.Column('native_name', sa.String(length=50), nullable=True))


def downgrade():
    # Remove native_name column from language table
    op.drop_column('language', 'native_name')