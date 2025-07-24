"""Add ActivityPub request tracking tables

Revision ID: 01b92d7ec7fb
Revises: feef49234599
Create Date: 2025-01-24 03:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '01b92d7ec7fb'
down_revision = '755fa58fd603'
branch_labels = None
depends_on = None


def upgrade():
    # Create ap_request_status table
    op.create_table('ap_request_status',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_id', postgresql.UUID(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('checkpoint', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('activity_id', sa.Text(), nullable=True),
        sa.Column('post_object_uri', sa.Text(), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for ap_request_status
    op.create_index('idx_ap_request_status_request_id', 'ap_request_status', ['request_id'], unique=False)
    op.create_index('idx_ap_request_status_activity_id', 'ap_request_status', ['activity_id'], unique=False)
    op.create_index('idx_ap_request_status_post_object_uri', 'ap_request_status', ['post_object_uri'], unique=False)
    op.create_index('idx_ap_request_status_timestamp', 'ap_request_status', ['timestamp'], unique=False)
    
    # Create ap_request_body table
    op.create_table('ap_request_body',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_id', postgresql.UUID(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('headers', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('parsed_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('content_type', sa.String(length=128), nullable=True),
        sa.Column('content_length', sa.Integer(), nullable=True),
        sa.Column('remote_addr', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for ap_request_body
    op.create_index('idx_ap_request_body_request_id', 'ap_request_body', ['request_id'], unique=False)
    op.create_index('idx_ap_request_body_timestamp', 'ap_request_body', ['timestamp'], unique=False)
    op.create_index('idx_ap_request_body_remote_addr', 'ap_request_body', ['remote_addr'], unique=False)
    
    # Create views
    op.execute("""
        CREATE OR REPLACE VIEW ap_request_status_last AS
        SELECT DISTINCT ON (request_id)
            id,
            request_id,
            timestamp,
            checkpoint,
            status,
            activity_id,
            post_object_uri,
            details
        FROM ap_request_status
        ORDER BY request_id, timestamp DESC;
    """)
    
    op.execute("""
        CREATE OR REPLACE VIEW ap_request_status_incomplete AS
        SELECT l.*
        FROM ap_request_status_last l
        WHERE NOT (l.checkpoint = 'process_inbox_request' AND l.status = 'ok');
    """)
    
    op.execute("""
        CREATE OR REPLACE VIEW ap_request_combined AS
        SELECT 
            s.request_id,
            s.timestamp as status_timestamp,
            s.checkpoint,
            s.status,
            s.activity_id,
            s.post_object_uri,
            s.details,
            b.timestamp as body_timestamp,
            b.headers,
            b.body,
            b.parsed_json,
            b.content_type,
            b.content_length,
            b.remote_addr,
            b.user_agent
        FROM ap_request_status s
        LEFT JOIN ap_request_body b ON s.request_id = b.request_id
        ORDER BY s.timestamp DESC;
    """)
    
    op.execute("""
        CREATE OR REPLACE VIEW ap_request_summary AS
        SELECT DISTINCT ON (s.request_id)
            s.request_id,
            s.timestamp as last_status_time,
            s.checkpoint as last_checkpoint,
            s.status as last_status,
            s.activity_id,
            s.post_object_uri,
            b.remote_addr,
            b.content_type,
            b.content_length,
            CASE 
                WHEN b.parsed_json IS NOT NULL THEN b.parsed_json->>'type'
                ELSE NULL 
            END as activity_type,
            CASE 
                WHEN b.parsed_json IS NOT NULL THEN b.parsed_json->>'actor'
                ELSE NULL 
            END as actor
        FROM ap_request_status s
        LEFT JOIN ap_request_body b ON s.request_id = b.request_id
        ORDER BY s.request_id, s.timestamp DESC;
    """)


def downgrade():
    # Drop views first
    op.execute("DROP VIEW IF EXISTS ap_request_summary;")
    op.execute("DROP VIEW IF EXISTS ap_request_combined;")
    op.execute("DROP VIEW IF EXISTS ap_request_status_incomplete;")
    op.execute("DROP VIEW IF EXISTS ap_request_status_last;")
    
    # Drop indexes
    op.drop_index('idx_ap_request_body_remote_addr', table_name='ap_request_body')
    op.drop_index('idx_ap_request_body_timestamp', table_name='ap_request_body')
    op.drop_index('idx_ap_request_body_request_id', table_name='ap_request_body')
    op.drop_index('idx_ap_request_status_timestamp', table_name='ap_request_status')
    op.drop_index('idx_ap_request_status_post_object_uri', table_name='ap_request_status')
    op.drop_index('idx_ap_request_status_activity_id', table_name='ap_request_status')
    op.drop_index('idx_ap_request_status_request_id', table_name='ap_request_status')
    
    # Drop tables
    op.drop_table('ap_request_body')
    op.drop_table('ap_request_status')