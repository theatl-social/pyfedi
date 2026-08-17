"""Merge upstream v1.7.11 head into the fork's merge chain

Merges upstream's 46b2b16d498b (community RSS feeds — adds rss_feed and
rss_feed_item) with the fork's 20260805_local_user_uniq head.

Revision ID: merge_20260817_v1711
Revises: 20260805_local_user_uniq, 46b2b16d498b
Create Date: 2026-08-17

"""

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision = "merge_20260817_v1711"
down_revision = ("20260805_local_user_uniq", "46b2b16d498b")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
