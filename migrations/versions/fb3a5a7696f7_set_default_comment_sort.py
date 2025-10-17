"""set default_comment_sort

Revision ID: fb3a5a7696f7
Revises: c86d6e395aea
Create Date: 2025-09-18 20:45:45.776281

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "fb3a5a7696f7"
down_revision = "c86d6e395aea"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "UPDATE \"user\" SET default_comment_sort = 'hot' WHERE ap_id IS NULL AND default_comment_sort IS NULL"
    )


def downgrade():
    pass
