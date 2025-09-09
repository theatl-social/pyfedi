"""fts indexes

Revision ID: ae44a91945d0
Revises: b2661139d87c
Create Date: 2025-04-05 06:45:42.526710

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "ae44a91945d0"
down_revision = "b2661139d87c"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
            CREATE INDEX idx_post_fts ON post USING gin(search_vector);
        """
    )
    op.execute(
        """
                CREATE INDEX idx_post_reply_fts ON post_reply USING gin(search_vector);
            """
    )
    op.execute(
        """
                CREATE INDEX idx_community_fts ON community USING gin(search_vector);
            """
    )


def downgrade():
    op.execute(
        """
            DROP INDEX idx_post_fts;
        """
    )
    op.execute(
        """
                DROP INDEX idx_post_reply_fts;
            """
    )
    op.execute(
        """
                DROP INDEX idx_community_fts;
            """
    )
