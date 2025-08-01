"""180 site logo

Revision ID: 6bfd83e619dd
Revises: fc3b6ff48330
Create Date: 2025-05-22 17:33:58.351925

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6bfd83e619dd'
down_revision = 'fc3b6ff48330'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('site', schema=None) as batch_op:
        batch_op.add_column(sa.Column('logo_180', sa.String(length=40), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('site', schema=None) as batch_op:
        batch_op.drop_column('logo_180')

    # ### end Alembic commands ###
