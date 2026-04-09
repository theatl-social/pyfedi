"""remove materialized view

Revision ID: 8457362452d9
Revises: bf436ec2a94b
Create Date: 2026-04-10 10:28:59.053693

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8457362452d9'
down_revision = 'bf436ec2a94b'
branch_labels = None
depends_on = None


def upgrade():
    # Drop all indexes first
    op.execute("DROP INDEX IF EXISTS post_view_common_query_idx")
    op.execute("DROP INDEX IF EXISTS post_view_community_private_idx")
    op.execute("DROP INDEX IF EXISTS post_view_type_idx")
    op.execute("DROP INDEX IF EXISTS post_view_from_bot_idx")
    op.execute("DROP INDEX IF EXISTS post_view_ai_generated_idx")
    op.execute("DROP INDEX IF EXISTS post_view_nsfl_idx")
    op.execute("DROP INDEX IF EXISTS post_view_nsfw_idx")
    op.execute("DROP INDEX IF EXISTS post_view_community_name_idx")
    op.execute("DROP INDEX IF EXISTS post_view_user_posted_at_idx")
    op.execute("DROP INDEX IF EXISTS post_view_active_idx")
    op.execute("DROP INDEX IF EXISTS post_view_scaled_idx")
    op.execute("DROP INDEX IF EXISTS post_view_popular_idx")
    op.execute("DROP INDEX IF EXISTS post_view_home_active_idx")
    op.execute("DROP INDEX IF EXISTS post_view_home_top_idx")
    op.execute("DROP INDEX IF EXISTS post_view_home_new_idx")
    op.execute("DROP INDEX IF EXISTS post_view_home_hot_idx")
    op.execute("DROP INDEX IF EXISTS post_view_community_active_idx")
    op.execute("DROP INDEX IF EXISTS post_view_community_top_idx")
    op.execute("DROP INDEX IF EXISTS post_view_community_new_idx")
    op.execute("DROP INDEX IF EXISTS post_view_community_hot_idx")
    op.execute("DROP INDEX IF EXISTS post_view_pkey")

    # drop the view
    op.execute("DROP MATERIALIZED VIEW IF EXISTS post_view")


def downgrade():
    pass
