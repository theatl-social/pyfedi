"""post materialized view

Revision ID: e44dfb9a157f
Revises: fa312daf8d0a
Create Date: 2026-04-02 16:42:45.621267

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e44dfb9a157f'
down_revision = 'fa312daf8d0a'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE MATERIALIZED VIEW post_view AS
        SELECT
            p.id as post_id,
            p.user_id, p.domain_id, p.instance_id,
            p.status, p.deleted, p.deleted_by,
            p.type, p.nsfw, p.nsfl, p.sticky, p.instance_sticky, p.ai_generated,
            p.from_bot, p.created_at, p.posted_at, p.last_active,
            p.up_votes, p.down_votes, p.ranking, p.ranking_scaled, p.score,
            p.reply_count, p.language_id,
            c.id as community_id, c.show_all, c.show_popular, c.instance_id as community_instance_id,
            c.nsfw as community_nsfw, c.banned as community_banned,
            c.private as community_private, c.ap_id as community_ap_id, c.name as community_name, c.ap_domain
        FROM post p
        JOIN community c ON c.id = p.community_id
        WHERE p.deleted = FALSE AND p.status > 0 AND c.banned = FALSE
        ORDER BY p.id DESC LIMIT 10000
    """)

    # Primary key index
    op.execute("CREATE UNIQUE INDEX post_view_pkey ON post_view(post_id)")

    # Community-scoped queries: leading equality on community_id + sort column(s)
    op.execute("CREATE INDEX post_view_community_hot_idx ON post_view(community_id, ranking DESC, posted_at DESC)")
    op.execute("CREATE INDEX post_view_community_new_idx ON post_view(community_id, posted_at DESC)")
    op.execute("CREATE INDEX post_view_community_top_idx ON post_view(community_id, score DESC)")
    op.execute("CREATE INDEX post_view_community_active_idx ON post_view(community_id, last_active DESC)")

    # Home feed queries (show_all = true) + sort column(s)
    op.execute("CREATE INDEX post_view_home_hot_idx ON post_view(show_all, instance_sticky DESC, ranking DESC, posted_at DESC)")
    op.execute("CREATE INDEX post_view_home_new_idx ON post_view(show_all, posted_at DESC)")
    op.execute("CREATE INDEX post_view_home_top_idx ON post_view(show_all, score DESC)")
    op.execute("CREATE INDEX post_view_home_active_idx ON post_view(show_all, last_active DESC)")

    # Popular type: show_popular = true, sorted by score
    op.execute("CREATE INDEX post_view_popular_idx ON post_view(show_popular, score DESC) WHERE show_popular = true")

    # Scaled sort: partial index only over rows that can appear in this sort
    op.execute("CREATE INDEX post_view_scaled_idx ON post_view(ranking_scaled DESC, ranking DESC, posted_at DESC) WHERE ranking_scaled IS NOT NULL AND from_bot = false")

    # Active sort (global): partial index, reply_count > 0
    op.execute("CREATE INDEX post_view_active_idx ON post_view(reply_count, last_active DESC) WHERE reply_count > 0")

    # User/person queries (subscribed, moderator view, person_id)
    op.execute("CREATE INDEX post_view_user_posted_at_idx ON post_view(user_id, posted_at DESC)")

    # Community name lookup (for community_name queries)
    op.execute("CREATE INDEX post_view_community_name_idx ON post_view(community_name, ap_domain)")

    # Boolean filter columns (used as secondary filters alongside the above)
    op.execute("CREATE INDEX post_view_nsfw_idx ON post_view(nsfw)")
    op.execute("CREATE INDEX post_view_nsfl_idx ON post_view(nsfl)")
    op.execute("CREATE INDEX post_view_ai_generated_idx ON post_view(ai_generated)")
    op.execute("CREATE INDEX post_view_from_bot_idx ON post_view(from_bot)")
    op.execute("CREATE INDEX post_view_type_idx ON post_view(type)")
    op.execute("CREATE INDEX post_view_community_private_idx ON post_view(community_private)")

    # Composite filter index for the common combination of per-user content preferences
    op.execute("CREATE INDEX post_view_common_query_idx ON post_view(community_id, nsfw, type, from_bot, ai_generated)")


def downgrade():
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