"""Add ON DELETE CASCADE to vote foreign keys

Revision ID: b38b253309dd
Revises: d467c6c829f9
Create Date: 2025-11-03 11:16:08.989489

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b38b253309dd"
down_revision = "d467c6c829f9"
branch_labels = None
depends_on = None


def upgrade():
    # Add ON DELETE CASCADE to post_vote.post_id foreign key
    # Use raw SQL because op.create_foreign_key with ondelete='CASCADE' doesn't actually create CASCADE
    op.execute("ALTER TABLE post_vote DROP CONSTRAINT IF EXISTS post_vote_post_id_fkey")
    op.execute(
        "ALTER TABLE post_vote ADD CONSTRAINT post_vote_post_id_fkey FOREIGN KEY (post_id) REFERENCES post(id) ON DELETE CASCADE"
    )

    # Add ON DELETE CASCADE to post_reply_vote.post_reply_id foreign key
    op.execute(
        "ALTER TABLE post_reply_vote DROP CONSTRAINT IF EXISTS post_reply_vote_post_reply_id_fkey"
    )
    op.execute(
        "ALTER TABLE post_reply_vote ADD CONSTRAINT post_reply_vote_post_reply_id_fkey FOREIGN KEY (post_reply_id) REFERENCES post_reply(id) ON DELETE CASCADE"
    )


def downgrade():
    # Revert post_vote.post_id foreign key to no cascade
    op.execute("ALTER TABLE post_vote DROP CONSTRAINT IF EXISTS post_vote_post_id_fkey")
    op.execute(
        "ALTER TABLE post_vote ADD CONSTRAINT post_vote_post_id_fkey FOREIGN KEY (post_id) REFERENCES post(id)"
    )

    # Revert post_reply_vote.post_reply_id foreign key to no cascade
    op.execute(
        "ALTER TABLE post_reply_vote DROP CONSTRAINT IF EXISTS post_reply_vote_post_reply_id_fkey"
    )
    op.execute(
        "ALTER TABLE post_reply_vote ADD CONSTRAINT post_reply_vote_post_reply_id_fkey FOREIGN KEY (post_reply_id) REFERENCES post_reply(id)"
    )
