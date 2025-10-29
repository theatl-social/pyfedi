"""merge migration heads - upstream and theatl-social

Revision ID: merge_20251029
Revises: 06792567caa2, 461c871f0f58
Create Date: 2025-10-29 23:30:00.000000

This merge migration combines:
- 06792567caa2: Our previous merge from origin/main (theatl-social fork)
- 461c871f0f58: Upstream user_file_association migration

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "merge_20251029"
down_revision = ("06792567caa2", "461c871f0f58")
branch_labels = None
depends_on = None


def upgrade():
    # This is a merge migration - no schema changes
    pass


def downgrade():
    # This is a merge migration - no schema changes
    pass
