"""Add ON DELETE CASCADE to vote foreign keys

Revision ID: b38b253309dd
Revises: d467c6c829f9
Create Date: 2025-11-03 11:16:08.989489

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b38b253309dd'
down_revision = 'd467c6c829f9'
branch_labels = None
depends_on = None


def upgrade():
    # Add ON DELETE CASCADE to post_vote.post_id foreign key
    op.drop_constraint('post_vote_post_id_fkey', 'post_vote', type_='foreignkey')
    op.create_foreign_key('post_vote_post_id_fkey', 'post_vote', 'post', ['post_id'], ['id'], ondelete='CASCADE')

    # Add ON DELETE CASCADE to post_reply_vote.post_reply_id foreign key
    op.drop_constraint('post_reply_vote_post_reply_id_fkey', 'post_reply_vote', type_='foreignkey')
    op.create_foreign_key('post_reply_vote_post_reply_id_fkey', 'post_reply_vote', 'post_reply', ['post_reply_id'], ['id'], ondelete='CASCADE')


def downgrade():
    # Revert post_vote.post_id foreign key to no cascade
    op.drop_constraint('post_vote_post_id_fkey', 'post_vote', type_='foreignkey')
    op.create_foreign_key('post_vote_post_id_fkey', 'post_vote', 'post', ['post_id'], ['id'])

    # Revert post_reply_vote.post_reply_id foreign key to no cascade
    op.drop_constraint('post_reply_vote_post_reply_id_fkey', 'post_reply_vote', type_='foreignkey')
    op.create_foreign_key('post_reply_vote_post_reply_id_fkey', 'post_reply_vote', 'post_reply', ['post_reply_id'], ['id'])
