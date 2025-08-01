"""community total_subscriptions_count

Revision ID: 629e85034a4b
Revises: 0e7b7b308de4
Create Date: 2025-06-20 17:39:22.406367

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '629e85034a4b'
down_revision = '0e7b7b308de4'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('community', schema=None) as batch_op:
        batch_op.add_column(sa.Column('total_subscriptions_count', sa.Integer(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('community', schema=None) as batch_op:
        batch_op.drop_column('total_subscriptions_count')

    # ### end Alembic commands ###
