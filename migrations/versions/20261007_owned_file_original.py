"""Track owned originals without inferring ownership from remote source URLs."""

from alembic import op
import sqlalchemy as sa

revision = '20261007_owned_file_original'
down_revision = 'merge_20261007_v180'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('file') as batch_op:
        batch_op.add_column(sa.Column('original_path', sa.String(255), nullable=True))


def downgrade():
    with op.batch_alter_table('file') as batch_op:
        batch_op.drop_column('original_path')
