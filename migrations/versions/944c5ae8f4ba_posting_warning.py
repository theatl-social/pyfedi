"""posting warning

Revision ID: 944c5ae8f4ba
Revises: 980966fba5f4
Create Date: 2024-04-18 20:42:54.287260

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '944c5ae8f4ba'
down_revision = '980966fba5f4'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('community', schema=None) as batch_op:
        batch_op.add_column(sa.Column('posting_warning', sa.String(length=512), nullable=True))

    with op.batch_alter_table('instance', schema=None) as batch_op:
        batch_op.add_column(sa.Column('posting_warning', sa.String(length=512), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('instance', schema=None) as batch_op:
        batch_op.drop_column('posting_warning')

    with op.batch_alter_table('community', schema=None) as batch_op:
        batch_op.drop_column('posting_warning')

    # ### end Alembic commands ###
