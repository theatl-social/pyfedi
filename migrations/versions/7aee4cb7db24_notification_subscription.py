"""notification subscription

Revision ID: 7aee4cb7db24
Revises: 944c5ae8f4ba
Create Date: 2024-04-19 19:12:59.022726

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7aee4cb7db24'
down_revision = '944c5ae8f4ba'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('notification_subscription',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=256), nullable=True),
    sa.Column('type', sa.Integer(), nullable=True),
    sa.Column('entity_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notification_subscription', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notification_subscription_entity_id'), ['entity_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_notification_subscription_type'), ['type'], unique=False)
        batch_op.create_index(batch_op.f('ix_notification_subscription_user_id'), ['user_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('notification_subscription', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_notification_subscription_user_id'))
        batch_op.drop_index(batch_op.f('ix_notification_subscription_type'))
        batch_op.drop_index(batch_op.f('ix_notification_subscription_entity_id'))

    op.drop_table('notification_subscription')
    # ### end Alembic commands ###
