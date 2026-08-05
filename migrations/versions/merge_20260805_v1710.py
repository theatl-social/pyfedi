"""Merge upstream v1.7.10 head into the fork's merge chain

Merges upstream's 8ed167b06fd7 (override comment collapse — adds
post_reply.collapsible) with the fork's merge_20260730_v178 head.

Revision ID: merge_20260805_v1710
Revises: merge_20260730_v178, 8ed167b06fd7
Create Date: 2026-08-05

"""

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision = "merge_20260805_v1710"
down_revision = ("merge_20260730_v178", "8ed167b06fd7")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
