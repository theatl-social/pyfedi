"""fix vote fkeys

Revision ID: a5f63c1add4d
Revises: 0f79379c3e8a
Create Date: 2026-01-27 19:28:16.889519

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a5f63c1add4d'
down_revision = '0f79379c3e8a'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE post_vote
            DROP CONSTRAINT IF EXISTS post_vote_post_id_fkey,
            ADD CONSTRAINT post_vote_post_id_fkey
                FOREIGN KEY (post_id)
                REFERENCES post(id)
                ON DELETE CASCADE
    """)

    op.execute("""
        ALTER TABLE post_reply_vote
            DROP CONSTRAINT IF EXISTS post_reply_vote_post_reply_id_fkey,
            ADD CONSTRAINT post_reply_vote_post_reply_id_fkey
                FOREIGN KEY (post_reply_id)
                REFERENCES post_reply(id)
                ON DELETE CASCADE
    """)


def downgrade():
    pass
