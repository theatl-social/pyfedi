"""update search vector triggers with weights

Revision ID: 7097ec286ac8
Revises: f153c932397d
Create Date: 2025-09-05 22:37:38.930828

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy_searchable import sync_trigger, SearchManager
from sqlalchemy_utils import TSVectorType


# revision identifiers, used by Alembic.
revision = '7097ec286ac8'
down_revision = 'f153c932397d'
branch_labels = None
depends_on = None


def upgrade():
    # Update the Post search vector trigger to match the model definition with weights
    conn = op.get_bind()
    
    # Drop existing trigger if it exists
    conn.execute(sa.text("DROP TRIGGER IF EXISTS post_search_vector_trigger ON post"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS post_search_vector_update()"))
    
    # Configure search manager to recognize the weights from TSVectorType
    # This recreates the trigger with proper weight handling
    metadata = sa.MetaData()
    post_table = sa.Table('post', metadata,                 # noqa F841
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('title', sa.String(255)),
        sa.Column('body', sa.Text),
        sa.Column('search_vector', TSVectorType('title', 'body', weights={"title": "A", "body": "B"}))
    )
    
    sync_trigger(conn, 'post', 'search_vector', ['title', 'body'], metadata=metadata)
    conn.execute(sa.text('UPDATE "post" SET indexable = true'))


def downgrade():
    # Revert to the original Post search vector trigger without weights  
    conn = op.get_bind()
    sync_trigger(conn, 'post', 'search_vector', ['title', 'body'])
