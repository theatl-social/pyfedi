"""adding hide_read_posts bool to User

Revision ID: 6e0b98e1fdc6
Revises: 27b71f6cb21e
Create Date: 2024-09-27 10:35:19.451448

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6e0b98e1fdc6'
down_revision = '27b71f6cb21e'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hide_read_posts', sa.Boolean(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('hide_read_posts')

    # ### end Alembic commands ###
