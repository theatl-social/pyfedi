"""reply thresholds

Revision ID: 363f2f07ff30
Revises: 745e3e985199
Create Date: 2024-06-28 17:40:49.866284

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '363f2f07ff30'
down_revision = '745e3e985199'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reply_collapse_threshold', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('reply_hide_threshold', sa.Integer(), nullable=True))

    # ### end Alembic commands ###

    op.execute(sa.DDL('UPDATE "user" SET reply_collapse_threshold = -10, reply_hide_threshold = -20 WHERE ap_id is null'))


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('reply_hide_threshold')
        batch_op.drop_column('reply_collapse_threshold')

    # ### end Alembic commands ###
