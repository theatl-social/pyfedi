"""joined_via_feed

Revision ID: 1cc1c8ff75fe
Revises: e9062ab3305e
Create Date: 2025-03-01 16:52:00.857011

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1cc1c8ff75fe'
down_revision = 'e9062ab3305e'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('community_member', schema=None) as batch_op:
        batch_op.add_column(sa.Column('joined_via_feed', sa.Boolean(), nullable=True))

    op.execute(sa.DDL('UPDATE "community_member" SET joined_via_feed = false'))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('community_member', schema=None) as batch_op:
        batch_op.drop_column('joined_via_feed')

    # ### end Alembic commands ###
