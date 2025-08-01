"""add targets to report model

Revision ID: eaf7845f39f1
Revises: 1e80c8767811
Create Date: 2025-07-10 16:54:57.547011

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'eaf7845f39f1'
down_revision = '1e80c8767811'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('report', schema=None) as batch_op:
        batch_op.add_column(sa.Column('targets', sa.JSON(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('report', schema=None) as batch_op:
        batch_op.drop_column('targets')

    # ### end Alembic commands ###
