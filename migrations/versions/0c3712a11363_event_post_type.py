"""event post type

Revision ID: 0c3712a11363
Revises: 7e58a675f67d
Create Date: 2025-05-20 22:37:56.438073

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0c3712a11363'
down_revision = '7e58a675f67d'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('event',
    sa.Column('post_id', sa.Integer(), nullable=False),
    sa.Column('start', sa.DateTime(), nullable=True),
    sa.Column('end', sa.DateTime(), nullable=True),
    sa.Column('max_attendees', sa.Integer(), nullable=True),
    sa.Column('full', sa.Boolean(), nullable=True),
    sa.Column('online_link', sa.String(length=1024), nullable=True),
    sa.Column('location', sa.Text(), nullable=True),
    sa.Column('buy_tickets_link', sa.String(length=1024), nullable=True),
    sa.Column('event_fee_currency', sa.String(length=4), nullable=True),
    sa.Column('event_fee_amount', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['post_id'], ['post.id'], ),
    sa.PrimaryKeyConstraint('post_id')
    )
    with op.batch_alter_table('event', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_event_start'), ['start'], unique=False)

    op.create_table('event_user',
    sa.Column('post_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['post_id'], ['post.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('post_id', 'user_id')
    )
    with op.batch_alter_table('community_ban', schema=None) as batch_op:
        batch_op.drop_column('banned_until')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('community_ban', schema=None) as batch_op:
        batch_op.add_column(sa.Column('banned_until', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))

    op.drop_table('event_user')
    with op.batch_alter_table('event', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_event_start'))

    op.drop_table('event')
    # ### end Alembic commands ###
