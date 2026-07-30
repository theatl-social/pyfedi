"""Merge heads after upstream v1.7.8 merge

Upstream's v1.7.8 chain (c831b9c7eee9 post_boost -> 544946659eb7 float post
ranking -> e1c6576eaa4b block community flair) branches off 97e954045fd6, which
is already inside merge_20260703_v17x. Rejoin the two heads.

Revision ID: merge_20260730_v178
Revises: merge_20260703_v17x, e1c6576eaa4b
Create Date: 2026-07-30

"""

revision = "merge_20260730_v178"
down_revision = ("merge_20260703_v17x", "e1c6576eaa4b")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
