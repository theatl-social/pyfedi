"""adding created_at to read_posts table

Revision ID: 238d7c60d676
Revises: 6e0b98e1fdc6
Create Date: 2024-09-28 09:26:22.000646

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '238d7c60d676'
down_revision = '6e0b98e1fdc6'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('read_posts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('interacted_at', sa.DateTime(), nullable=True))
        batch_op.create_index(batch_op.f('ix_read_posts_interacted_at'), ['interacted_at'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('read_posts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_read_posts_interacted_at'))
        batch_op.drop_column('interacted_at')

    # ### end Alembic commands ###
