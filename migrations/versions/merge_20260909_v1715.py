"""Merge upstream v1.7.15 head into the fork's merge chain

Merges upstream's 7b8bf43fa079 (backfill NULL community.total_subscriptions_count
to 0 so sorting on that column behaves) with the fork's
20260817_manual_approve_backfill head (SP-030).

Revision ID: merge_20260909_v1715
Revises: 20260817_manual_approve_backfill, 7b8bf43fa079
Create Date: 2026-09-09

"""

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision = "merge_20260909_v1715"
down_revision = ("20260817_manual_approve_backfill", "7b8bf43fa079")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
