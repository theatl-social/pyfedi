"""bot override

Revision ID: 5a19900198e9
Revises: f80b8607e38f
Create Date: 2025-07-07 22:28:51.816430

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5a19900198e9'
down_revision = 'f80b8607e38f'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bot_override', sa.Boolean(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('bot_override')

    # ### end Alembic commands ###
