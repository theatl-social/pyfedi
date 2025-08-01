"""default comment sort

Revision ID: 91c80b195029
Revises: bfb5ff64a9d5
Create Date: 2025-07-18 21:02:23.257681

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '91c80b195029'
down_revision = 'bfb5ff64a9d5'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('post_reply', schema=None) as batch_op:
        batch_op.alter_column('replies_enabled',
               existing_type=sa.BOOLEAN(),
               nullable=True,
               existing_server_default=sa.text('true'))

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('default_comment_sort', sa.String(length=10), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('default_comment_sort')

    with op.batch_alter_table('post_reply', schema=None) as batch_op:
        batch_op.alter_column('replies_enabled',
               existing_type=sa.BOOLEAN(),
               nullable=False,
               existing_server_default=sa.text('true'))

    # ### end Alembic commands ###
