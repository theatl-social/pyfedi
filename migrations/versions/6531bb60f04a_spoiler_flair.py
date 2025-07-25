"""spoiler flair

Revision ID: 6531bb60f04a
Revises: 436ebe26b0fe
Create Date: 2025-06-10 05:20:39.251648

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6531bb60f04a'
down_revision = '436ebe26b0fe'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('community_flair', schema=None) as batch_op:
        batch_op.add_column(sa.Column('blur_images', sa.Boolean(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('community_flair', schema=None) as batch_op:
        batch_op.drop_column('blur_images')

    # ### end Alembic commands ###
