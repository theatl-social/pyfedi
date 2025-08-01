"""site logo

Revision ID: 1c51c3df2770
Revises: 5e84668d279e
Create Date: 2024-06-14 17:50:12.371773

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1c51c3df2770'
down_revision = '5e84668d279e'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('site', schema=None) as batch_op:
        batch_op.add_column(sa.Column('logo', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('logo_152', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('logo_32', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('logo_16', sa.String(length=40), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('site', schema=None) as batch_op:
        batch_op.drop_column('logo_16')
        batch_op.drop_column('logo_32')
        batch_op.drop_column('logo_152')
        batch_op.drop_column('logo')

    # ### end Alembic commands ###
