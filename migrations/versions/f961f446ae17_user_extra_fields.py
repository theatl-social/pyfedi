"""user extra fields

Revision ID: f961f446ae17
Revises: 1189f921aca6
Create Date: 2024-12-22 14:56:43.714502

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f961f446ae17'
down_revision = '1189f921aca6'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('user_extra_field',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('label', sa.String(length=50), nullable=True),
    sa.Column('text', sa.String(length=256), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('user_extra_field', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_extra_field_user_id'), ['user_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user_extra_field', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_extra_field_user_id'))

    op.drop_table('user_extra_field')
    # ### end Alembic commands ###
