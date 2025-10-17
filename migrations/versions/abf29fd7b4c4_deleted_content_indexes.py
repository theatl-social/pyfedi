"""deleted content indexes

Revision ID: abf29fd7b4c4
Revises: ae44a91945d0
Create Date: 2025-04-08 15:10:07.728100

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "abf29fd7b4c4"
down_revision = "ae44a91945d0"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
            CREATE INDEX ix_post_reply_community_id_not_deleted
            ON post_reply (community_id)
            WHERE deleted = false;
        """)
    op.execute("""
                CREATE INDEX ix_post_community_id_not_deleted
                ON post (community_id)
                WHERE deleted = false;
            """)

    op.execute("""
                    CREATE INDEX ix_post_user_id_not_deleted
                    ON post (user_id)
                    WHERE deleted = false;
                """)


def downgrade():
    op.execute("""
            DROP INDEX ix_post_reply_community_id_not_deleted;
        """)
    op.execute("""
                DROP INDEX ix_post_community_id_not_deleted;
            """)
    op.execute("""
                    DROP INDEX ix_post_user_id_not_deleted;
                """)
