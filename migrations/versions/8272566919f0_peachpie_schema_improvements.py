"""PeachPie schema improvements

Revision ID: 8272566919f0
Revises: 01b92d7ec7fb
Create Date: 2025-01-27 16:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '8272566919f0'
down_revision = '01b92d7ec7fb'
branch_labels = None
depends_on = None


def upgrade():
    """Upgrade PyFedi schema to PeachPie standards."""
    
    # 1. Fix URL field lengths - CRITICAL
    # These fields often contain ActivityPub URLs that exceed 255 chars
    print("Fixing URL field lengths...")
    
    # User table URL fields
    with op.batch_alter_table('user') as batch_op:
        batch_op.alter_column('ap_profile_id', type_=sa.Text())
        batch_op.alter_column('ap_public_url', type_=sa.Text())
        batch_op.alter_column('ap_inbox_url', type_=sa.Text())
        batch_op.alter_column('email', type_=sa.String(320))  # Max valid email length
    
    # Community table URL fields
    with op.batch_alter_table('community') as batch_op:
        batch_op.alter_column('ap_id', type_=sa.Text())
        batch_op.alter_column('ap_profile_id', type_=sa.Text())
        batch_op.alter_column('ap_followers_url', type_=sa.Text())
        batch_op.alter_column('ap_public_url', type_=sa.Text())
        batch_op.alter_column('ap_inbox_url', type_=sa.Text())
        batch_op.alter_column('ap_outbox_url', type_=sa.Text())
        batch_op.alter_column('ap_featured_url', type_=sa.Text())
        batch_op.alter_column('ap_moderators_url', type_=sa.Text())
        batch_op.alter_column('rss_url', type_=sa.Text())
    
    # Post table URL fields
    with op.batch_alter_table('post') as batch_op:
        batch_op.alter_column('ap_id', type_=sa.Text())
        batch_op.alter_column('url', type_=sa.Text())
    
    # PostReply table URL fields
    with op.batch_alter_table('post_reply') as batch_op:
        batch_op.alter_column('ap_id', type_=sa.Text())
    
    # File table URL fields
    with op.batch_alter_table('file') as batch_op:
        batch_op.alter_column('source_url', type_=sa.Text())
        batch_op.alter_column('file_path', type_=sa.Text())
        batch_op.alter_column('thumbnail_path', type_=sa.Text())
    
    # Instance table URL fields
    with op.batch_alter_table('instance') as batch_op:
        batch_op.alter_column('inbox', type_=sa.Text())
        batch_op.alter_column('shared_inbox', type_=sa.Text())
        batch_op.alter_column('outbox', type_=sa.Text())
        batch_op.alter_column('nodeinfo_href', type_=sa.Text())
    
    # 2. Add performance indexes
    print("Adding performance indexes...")
    
    # User queries by instance and activity
    op.create_index('idx_user_instance_active', 'user', 
                    ['instance_id', 'deleted', 'banned'],
                    postgresql_where=sa.text('deleted = false'))
    
    # Post queries by community and time
    op.create_index('idx_post_community_created', 'post', 
                    ['community_id', 'created_at'],
                    postgresql_where=sa.text('deleted = false'))
    
    # Activity log performance
    op.create_index('idx_activitypublog_result_timestamp', 'activitypub_log', 
                    ['result', 'created_at'])
    
    # Post reply queries
    op.create_index('idx_postreply_post_created', 'post_reply',
                    ['post_id', 'created_at'],
                    postgresql_where=sa.text('deleted = false'))
    
    # Community member queries
    op.create_index('idx_communitymember_user_community', 'community_member',
                    ['user_id', 'community_id', 'is_banned'])
    
    # 3. Add FederationError table if it doesn't exist
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if 'federation_error' not in inspector.get_table_names():
        print("Creating FederationError table...")
        op.create_table('federation_error',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('instance_id', sa.Integer(), nullable=True),
            sa.Column('activity_id', sa.String(255), nullable=True),
            sa.Column('activity_type', sa.String(50), nullable=True),
            sa.Column('error_type', sa.String(100), nullable=False),
            sa.Column('error_message', sa.Text(), nullable=False),
            sa.Column('retry_count', sa.Integer(), default=0),
            sa.Column('resolved', sa.Boolean(), default=False),
            sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['instance_id'], ['instance.id'], )
        )
        op.create_index('idx_federationerror_instance_created', 'federation_error',
                        ['instance_id', 'created_at'])
        op.create_index('idx_federationerror_resolved', 'federation_error',
                        ['resolved', 'created_at'])
    
    # 4. Update software name in instance table
    print("Updating software identification...")
    op.execute("UPDATE instance SET software = 'PeachPie' WHERE id = 1")
    
    # 5. Add new settings for PeachPie features
    # Check if settings exist before adding
    existing_settings = connection.execute(
        sa.text("SELECT name FROM settings WHERE name IN ('redis_streams_enabled', 'monitoring_enabled')")
    ).fetchall()
    existing_names = [row[0] for row in existing_settings]
    
    if 'redis_streams_enabled' not in existing_names:
        op.execute(
            "INSERT INTO settings (name, value) VALUES ('redis_streams_enabled', 'true')"
        )
    
    if 'monitoring_enabled' not in existing_names:
        op.execute(
            "INSERT INTO settings (name, value) VALUES ('monitoring_enabled', 'true')"
        )
    
    print("✓ Schema improvements complete!")


def downgrade():
    """Downgrade to PyFedi schema (not recommended)."""
    
    # Remove PeachPie-specific indexes
    op.drop_index('idx_user_instance_active', 'user')
    op.drop_index('idx_post_community_created', 'post')
    op.drop_index('idx_activitypublog_result_timestamp', 'activitypub_log')
    op.drop_index('idx_postreply_post_created', 'post_reply')
    op.drop_index('idx_communitymember_user_community', 'community_member')
    
    # Drop federation error table
    op.drop_table('federation_error')
    
    # Revert URL fields to varchar(255) - WARNING: This may truncate data!
    print("WARNING: Reverting URL fields may truncate data!")
    
    with op.batch_alter_table('user') as batch_op:
        batch_op.alter_column('ap_profile_id', type_=sa.String(255))
        batch_op.alter_column('ap_public_url', type_=sa.String(255))
        batch_op.alter_column('ap_inbox_url', type_=sa.String(255))
        batch_op.alter_column('email', type_=sa.String(255))
    
    with op.batch_alter_table('community') as batch_op:
        batch_op.alter_column('ap_id', type_=sa.String(255))
        batch_op.alter_column('ap_profile_id', type_=sa.String(255))
        batch_op.alter_column('ap_followers_url', type_=sa.String(255))
        batch_op.alter_column('ap_public_url', type_=sa.String(255))
        batch_op.alter_column('ap_inbox_url', type_=sa.String(255))
        batch_op.alter_column('ap_outbox_url', type_=sa.String(255))
        batch_op.alter_column('ap_featured_url', type_=sa.String(255))
        batch_op.alter_column('ap_moderators_url', type_=sa.String(255))
        batch_op.alter_column('rss_url', type_=sa.String(1024))
    
    with op.batch_alter_table('post') as batch_op:
        batch_op.alter_column('ap_id', type_=sa.String(255))
        batch_op.alter_column('url', type_=sa.String(512))
    
    with op.batch_alter_table('post_reply') as batch_op:
        batch_op.alter_column('ap_id', type_=sa.String(255))
    
    with op.batch_alter_table('file') as batch_op:
        batch_op.alter_column('source_url', type_=sa.String(1024))
        batch_op.alter_column('file_path', type_=sa.String(255))
        batch_op.alter_column('thumbnail_path', type_=sa.String(255))
    
    with op.batch_alter_table('instance') as batch_op:
        batch_op.alter_column('inbox', type_=sa.String(256))
        batch_op.alter_column('shared_inbox', type_=sa.String(256))
        batch_op.alter_column('outbox', type_=sa.String(256))
        batch_op.alter_column('nodeinfo_href', type_=sa.String(256))
    
    # Revert software name
    op.execute("UPDATE instance SET software = 'PieFed' WHERE id = 1")
    
    # Remove PeachPie settings
    op.execute("DELETE FROM settings WHERE name IN ('redis_streams_enabled', 'monitoring_enabled')")