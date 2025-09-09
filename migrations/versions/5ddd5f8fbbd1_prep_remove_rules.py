"""prep remove rules

Revision ID: 5ddd5f8fbbd1
Revises: 8e49c7efa647
Create Date: 2025-06-13 19:42:56.606325

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "5ddd5f8fbbd1"
down_revision = "8e49c7efa647"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(
        text(
            "UPDATE \"community\" SET description = description || '\n\n## Rules\n\n' || rules WHERE ap_id is null and rules != ''"
        )
    )


def downgrade():
    pass
