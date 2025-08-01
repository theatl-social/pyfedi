"""post_reply language

Revision ID: 9ad372b72d7c
Revises: e73996747d7e
Create Date: 2024-05-09 14:26:48.888908

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9ad372b72d7c'
down_revision = 'e73996747d7e'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('post', schema=None) as batch_op:
        batch_op.create_foreign_key(None, 'language', ['language_id'], ['id'])
        batch_op.drop_column('language')

    with op.batch_alter_table('post_reply', schema=None) as batch_op:
        batch_op.add_column(sa.Column('language_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_post_reply_language_id'), ['language_id'], unique=False)
        batch_op.create_foreign_key(None, 'language', ['language_id'], ['id'])
        batch_op.drop_column('language')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('post_reply', schema=None) as batch_op:
        batch_op.add_column(sa.Column('language', sa.VARCHAR(length=10), autoincrement=False, nullable=True))
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_post_reply_language_id'))
        batch_op.drop_column('language_id')

    with op.batch_alter_table('post', schema=None) as batch_op:
        batch_op.add_column(sa.Column('language', sa.VARCHAR(length=10), autoincrement=False, nullable=True))
        batch_op.drop_constraint(None, type_='foreignkey')

    # ### end Alembic commands ###
