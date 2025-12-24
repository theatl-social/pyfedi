"""comment search

Revision ID: 12664244e54d
Revises: 51d55a05bfca
Create Date: 2025-12-21 16:07:49.524058

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision = '12664244e54d'
down_revision = '51d55a05bfca'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(text('''
                DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'post_reply_search_vector_trigger'
            ) THEN
                CREATE TRIGGER post_reply_search_vector_trigger
                BEFORE INSERT OR UPDATE ON public.post_reply
                FOR EACH ROW EXECUTE FUNCTION
                    tsvector_update_trigger('search_vector', 'pg_catalog.english', 'body');
            END IF;
        END$$;
    '''))
    conn.execute(text('UPDATE "post_reply" SET body = body;'))


def downgrade():
    pass
