"""avoid deadlocks

Revision ID: e5b27b52ad78
Revises: f5e09ad62de3
Create Date: 2025-04-25 21:53:40.275471

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5b27b52ad78'
down_revision = 'f5e09ad62de3'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('post_reply_vote', schema=None) as batch_op:
        batch_op.create_index('ix_post_reply_vote_user_id_id_desc', ['user_id', sa.text('id DESC')], unique=False)

    with op.batch_alter_table('post_vote', schema=None) as batch_op:
        batch_op.create_index('ix_post_vote_user_id_id_desc', ['user_id', sa.text('id DESC')], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('post_vote', schema=None) as batch_op:
        batch_op.drop_index('ix_post_vote_user_id_id_desc')

    with op.batch_alter_table('post_reply_vote', schema=None) as batch_op:
        batch_op.drop_index('ix_post_reply_vote_user_id_id_desc')

    # ### end Alembic commands ###
