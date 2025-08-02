"""Fix test issues: add language native_name and fix circular FK constraints

Revision ID: fix_test_issues
Revises: feef49234599
Create Date: 2025-08-02 17:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250802174200'
down_revision = '20250801193400'
branch_labels = None
depends_on = None


def upgrade():
    # Add native_name column to language table
    op.add_column('language', sa.Column('native_name', sa.String(length=50), nullable=True))
    
    # Add active column to language table
    op.add_column('language', sa.Column('active', sa.Boolean(), nullable=False, server_default='true'))
    
    # Add weight column to role table if it doesn't exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('role')]
    if 'weight' not in columns:
        op.add_column('role', sa.Column('weight', sa.Integer(), nullable=False, server_default='0'))
    
    # Add role_id column to user table if it doesn't exist
    user_columns = [c['name'] for c in inspector.get_columns('user')]
    if 'role_id' not in user_columns:
        op.add_column('user', sa.Column('role_id', sa.Integer(), sa.ForeignKey('role.id'), nullable=True))
    
    # Add deleted and ban_state columns to user table if they don't exist
    if 'deleted' not in user_columns:
        op.add_column('user', sa.Column('deleted', sa.Boolean(), nullable=False, server_default='false'))
        op.create_index('ix_user_deleted', 'user', ['deleted'])
    if 'ban_state' not in user_columns:
        op.add_column('user', sa.Column('ban_state', sa.Integer(), nullable=False, server_default='0'))
    
    # Add other missing user columns
    if 'post_reply_count' not in user_columns:
        op.add_column('user', sa.Column('post_reply_count', sa.Integer(), nullable=False, server_default='0'))
    if 'suspended' not in user_columns:
        op.add_column('user', sa.Column('suspended', sa.Boolean(), nullable=False, server_default='false'))
    if 'ignore_bots' not in user_columns:
        op.add_column('user', sa.Column('ignore_bots', sa.Integer(), nullable=False, server_default='0'))
    if 'hide_read_posts' not in user_columns:
        op.add_column('user', sa.Column('hide_read_posts', sa.Boolean(), nullable=False, server_default='false'))
    if 'created' not in user_columns:
        op.add_column('user', sa.Column('created', sa.DateTime(), nullable=False, server_default=sa.func.now()))
    if 'password_updated_at' not in user_columns:
        op.add_column('user', sa.Column('password_updated_at', sa.DateTime(), nullable=True))
    
    # Add other missing user fields
    if 'alt_user_name' not in user_columns:
        op.add_column('user', sa.Column('alt_user_name', sa.String(255), nullable=True))
        op.create_index('ix_user_alt_user_name', 'user', ['alt_user_name'])
    if 'title' not in user_columns:
        op.add_column('user', sa.Column('title', sa.String(255), nullable=True))
    if 'about' not in user_columns:
        op.add_column('user', sa.Column('about', sa.Text(), nullable=True))
    if 'about_html' not in user_columns:
        op.add_column('user', sa.Column('about_html', sa.Text(), nullable=True))
    if 'avatar_id' not in user_columns:
        op.add_column('user', sa.Column('avatar_id', sa.Integer(), sa.ForeignKey('file.id'), nullable=True))
    if 'cover_id' not in user_columns:
        op.add_column('user', sa.Column('cover_id', sa.Integer(), sa.ForeignKey('file.id'), nullable=True))
    if 'default_sort' not in user_columns:
        op.add_column('user', sa.Column('default_sort', sa.String(25), nullable=False, server_default='hot'))
    if 'default_filter' not in user_columns:
        op.add_column('user', sa.Column('default_filter', sa.String(25), nullable=False, server_default='all'))
    if 'theme' not in user_columns:
        op.add_column('user', sa.Column('theme', sa.String(20), nullable=False, server_default='system'))
    if 'indexable' not in user_columns:
        op.add_column('user', sa.Column('indexable', sa.Boolean(), nullable=False, server_default='true'))
    if 'searchable' not in user_columns:
        op.add_column('user', sa.Column('searchable', sa.Boolean(), nullable=False, server_default='true'))
    if 'hide_nsfw' not in user_columns:
        op.add_column('user', sa.Column('hide_nsfw', sa.Boolean(), nullable=False, server_default='false'))
    if 'hide_nsfl' not in user_columns:
        op.add_column('user', sa.Column('hide_nsfl', sa.Integer(), nullable=False, server_default='0'))
    if 'receive_message_mode' not in user_columns:
        op.add_column('user', sa.Column('receive_message_mode', sa.String(20), nullable=False, server_default='Closed'))
    if 'post_count' not in user_columns:
        op.add_column('user', sa.Column('post_count', sa.Integer(), nullable=False, server_default='0'))
    if 'reputation' not in user_columns:
        op.add_column('user', sa.Column('reputation', sa.Float(), nullable=False, server_default='0.0'))
    if 'attitude' not in user_columns:
        op.add_column('user', sa.Column('attitude', sa.Float(), nullable=False, server_default='0.0'))
    if 'last_seen' not in user_columns:
        op.add_column('user', sa.Column('last_seen', sa.DateTime(), nullable=True))
        op.create_index('ix_user_last_seen', 'user', ['last_seen'])
    if 'totp_secret' not in user_columns:
        op.add_column('user', sa.Column('totp_secret', sa.String(64), nullable=True))
    if 'totp_enabled' not in user_columns:
        op.add_column('user', sa.Column('totp_enabled', sa.Boolean(), nullable=False, server_default='false'))
    if 'totp_recovery_codes' not in user_columns:
        op.add_column('user', sa.Column('totp_recovery_codes', sa.Text(), nullable=True))
    if 'bot' not in user_columns:
        op.add_column('user', sa.Column('bot', sa.Boolean(), nullable=False, server_default='false'))
    if 'interface_language' not in user_columns:
        op.add_column('user', sa.Column('interface_language', sa.String(10), nullable=True))
    if 'language_id' not in user_columns:
        op.add_column('user', sa.Column('language_id', sa.Integer(), sa.ForeignKey('language.id'), nullable=True))
    # ActivityPub fields
    if 'ap_id' not in user_columns:
        op.add_column('user', sa.Column('ap_id', sa.String(255), nullable=True))
        op.create_index('ix_user_ap_id', 'user', ['ap_id'])
    if 'ap_profile_id' not in user_columns:
        op.add_column('user', sa.Column('ap_profile_id', sa.String(255), nullable=True, unique=True))
        op.create_index('ix_user_ap_profile_id', 'user', ['ap_profile_id'])
    if 'ap_public_url' not in user_columns:
        op.add_column('user', sa.Column('ap_public_url', sa.String(255), nullable=True))
    if 'ap_fetched_at' not in user_columns:
        op.add_column('user', sa.Column('ap_fetched_at', sa.DateTime(), nullable=True))
    if 'ap_followers_url' not in user_columns:
        op.add_column('user', sa.Column('ap_followers_url', sa.String(255), nullable=True))
    if 'ap_inbox_url' not in user_columns:
        op.add_column('user', sa.Column('ap_inbox_url', sa.String(255), nullable=True))
    if 'ap_domain' not in user_columns:
        op.add_column('user', sa.Column('ap_domain', sa.String(255), nullable=True))
        op.create_index('ix_user_ap_domain', 'user', ['ap_domain'])
    if 'ap_preferred_username' not in user_columns:
        op.add_column('user', sa.Column('ap_preferred_username', sa.String(255), nullable=True))
    if 'ap_manually_approves_followers' not in user_columns:
        op.add_column('user', sa.Column('ap_manually_approves_followers', sa.Boolean(), nullable=False, server_default='false'))
    if 'ap_deleted_at' not in user_columns:
        op.add_column('user', sa.Column('ap_deleted_at', sa.DateTime(), nullable=True))
    if 'private_key' not in user_columns:
        op.add_column('user', sa.Column('private_key', sa.Text(), nullable=True))
    if 'public_key' not in user_columns:
        op.add_column('user', sa.Column('public_key', sa.Text(), nullable=True))
    if 'instance_id' not in user_columns:
        op.add_column('user', sa.Column('instance_id', sa.Integer(), sa.ForeignKey('instance.id'), nullable=True))
        op.create_index('ix_user_instance_id', 'user', ['instance_id'])
    
    # Add missing instance columns
    instance_columns = [c['name'] for c in inspector.get_columns('instance')]
    if 'post_count' not in instance_columns:
        op.add_column('instance', sa.Column('post_count', sa.Integer(), nullable=False, server_default='0'))
    if 'user_count' not in instance_columns:
        op.add_column('instance', sa.Column('user_count', sa.Integer(), nullable=False, server_default='0'))
    if 'nodeinfo_href' not in instance_columns:
        op.add_column('instance', sa.Column('nodeinfo_href', sa.String(256), nullable=True))
    if 'start_trying_again' not in instance_columns:
        op.add_column('instance', sa.Column('start_trying_again', sa.DateTime(), nullable=True))
    # TimestampMixin fields
    if 'created_at' not in instance_columns:
        op.add_column('instance', sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
        op.create_index('ix_instance_created_at', 'instance', ['created_at'])
    if 'updated_at' not in instance_columns:
        op.add_column('instance', sa.Column('updated_at', sa.DateTime(), nullable=True))
    # Additional Instance fields
    if 'inbox' not in instance_columns:
        op.add_column('instance', sa.Column('inbox', sa.String(256), nullable=True))
    if 'shared_inbox' not in instance_columns:
        op.add_column('instance', sa.Column('shared_inbox', sa.String(256), nullable=True))
    if 'outbox' not in instance_columns:
        op.add_column('instance', sa.Column('outbox', sa.String(256), nullable=True))
    if 'gone_forever' not in instance_columns:
        op.add_column('instance', sa.Column('gone_forever', sa.Boolean(), nullable=False, server_default='false'))
    if 'dormant' not in instance_columns:
        op.add_column('instance', sa.Column('dormant', sa.Boolean(), nullable=False, server_default='false'))
    if 'last_seen' not in instance_columns:
        op.add_column('instance', sa.Column('last_seen', sa.DateTime(), nullable=True))
    if 'last_successful_send' not in instance_columns:
        op.add_column('instance', sa.Column('last_successful_send', sa.DateTime(), nullable=True))
    if 'failures' not in instance_columns:
        op.add_column('instance', sa.Column('failures', sa.Integer(), nullable=False, server_default='0'))
    if 'most_recent_attempt' not in instance_columns:
        op.add_column('instance', sa.Column('most_recent_attempt', sa.DateTime(), nullable=True))
    
    # Add missing community columns
    community_columns = [c['name'] for c in inspector.get_columns('community')]
    # From model definition
    if 'rules_html' not in community_columns:
        op.add_column('community', sa.Column('rules_html', sa.Text(), nullable=True))
    if 'description_html' not in community_columns:
        op.add_column('community', sa.Column('description_html', sa.Text(), nullable=True))
    if 'content_retention' not in community_columns:
        op.add_column('community', sa.Column('content_retention', sa.Integer(), nullable=False, server_default='-1'))
    if 'deleted' not in community_columns:
        op.add_column('community', sa.Column('deleted', sa.Boolean(), nullable=False, server_default='false'))
    if 'deleted_by' not in community_columns:
        op.add_column('community', sa.Column('deleted_by', sa.Integer(), sa.ForeignKey('user.id'), nullable=True))
    if 'posting_warning' not in community_columns:
        op.add_column('community', sa.Column('posting_warning', sa.Text(), nullable=True))
    if 'default_layout' not in community_columns:
        op.add_column('community', sa.Column('default_layout', sa.String(15), nullable=True))
    if 'private_mods' not in community_columns:
        op.add_column('community', sa.Column('private_mods', sa.Boolean(), nullable=False, server_default='false'))
    if 'new_mods_wanted' not in community_columns:
        op.add_column('community', sa.Column('new_mods_wanted', sa.Boolean(), nullable=False, server_default='false'))
    if 'show_popular' not in community_columns:
        op.add_column('community', sa.Column('show_popular', sa.Boolean(), nullable=False, server_default='true'))
    if 'low_quality' not in community_columns:
        op.add_column('community', sa.Column('low_quality', sa.Boolean(), nullable=False, server_default='false'))
    if 'restricted_to_mods' not in community_columns:
        op.add_column('community', sa.Column('restricted_to_mods', sa.Boolean(), nullable=False, server_default='false'))
    if 'banned' not in community_columns:
        op.add_column('community', sa.Column('banned', sa.Boolean(), nullable=False, server_default='false'))
    if 'show_all' not in community_columns:
        op.add_column('community', sa.Column('show_all', sa.Boolean(), nullable=False, server_default='true'))
    if 'searchable' not in community_columns:
        op.add_column('community', sa.Column('searchable', sa.Boolean(), nullable=False, server_default='true'))
    if 'local_only' not in community_columns:
        op.add_column('community', sa.Column('local_only', sa.Boolean(), nullable=False, server_default='false'))
    if 'approval_required' not in community_columns:
        op.add_column('community', sa.Column('approval_required', sa.Boolean(), nullable=False, server_default='false'))
    if 'topic_id' not in community_columns:
        op.add_column('community', sa.Column('topic_id', sa.Integer(), sa.ForeignKey('topic.id'), nullable=True))
    if 'user_id' not in community_columns:
        op.add_column('community', sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False, server_default='1'))
    if 'instance_id' not in community_columns:
        op.add_column('community', sa.Column('instance_id', sa.Integer(), sa.ForeignKey('instance.id'), nullable=True))
    if 'ap_moderators_url' not in community_columns:
        op.add_column('community', sa.Column('ap_moderators_url', sa.String(255), nullable=True))
    if 'ap_featured_url' not in community_columns:
        op.add_column('community', sa.Column('ap_featured_url', sa.String(255), nullable=True))
    if 'ap_deleted_at' not in community_columns:
        op.add_column('community', sa.Column('ap_deleted_at', sa.DateTime(), nullable=True))
    if 'ap_domain' not in community_columns:
        op.add_column('community', sa.Column('ap_domain', sa.String(255), nullable=True))
    # From ActivityPubMixin
    if 'ap_followers_url' not in community_columns:
        op.add_column('community', sa.Column('ap_followers_url', sa.String(255), nullable=True))
    if 'ap_public_url' not in community_columns:
        op.add_column('community', sa.Column('ap_public_url', sa.String(255), nullable=True))
    if 'ap_fetched_at' not in community_columns:
        op.add_column('community', sa.Column('ap_fetched_at', sa.DateTime(), nullable=True))
    # From LanguageMixin
    if 'language' not in community_columns:
        op.add_column('community', sa.Column('language', sa.String(10), nullable=True))
    # From TimestampMixin
    if 'updated_at' not in community_columns:
        op.add_column('community', sa.Column('updated_at', sa.DateTime(), nullable=True))
    
    # Add missing post columns (from mixins)
    post_columns = [c['name'] for c in inspector.get_columns('post')]
    # TimestampMixin
    if 'created_at' not in post_columns:
        op.add_column('post', sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
        op.create_index('ix_post_created_at', 'post', ['created_at'])
    if 'updated_at' not in post_columns:
        op.add_column('post', sa.Column('updated_at', sa.DateTime(), nullable=True))
    # SoftDeleteMixin
    if 'deleted' not in post_columns:
        op.add_column('post', sa.Column('deleted', sa.Boolean(), nullable=False, server_default='false'))
        op.create_index('ix_post_deleted', 'post', ['deleted'])
    if 'deleted_at' not in post_columns:
        op.add_column('post', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    # ScoreMixin
    if 'score' not in post_columns:
        op.add_column('post', sa.Column('score', sa.Integer(), nullable=False, server_default='0'))
        op.create_index('ix_post_score', 'post', ['score'])
    if 'up_votes' not in post_columns:
        op.add_column('post', sa.Column('up_votes', sa.Integer(), nullable=False, server_default='0'))
    if 'down_votes' not in post_columns:
        op.add_column('post', sa.Column('down_votes', sa.Integer(), nullable=False, server_default='0'))
    if 'ranking' not in post_columns:
        op.add_column('post', sa.Column('ranking', sa.Float(), nullable=False, server_default='0.0'))
        op.create_index('ix_post_ranking', 'post', ['ranking'])
    # ActivityPubMixin
    if 'ap_id' not in post_columns:
        op.add_column('post', sa.Column('ap_id', sa.String(255), nullable=True, unique=True))
        op.create_index('ix_post_ap_id', 'post', ['ap_id'])
    if 'ap_profile_id' not in post_columns:
        op.add_column('post', sa.Column('ap_profile_id', sa.String(255), nullable=True, unique=True))
        op.create_index('ix_post_ap_profile_id', 'post', ['ap_profile_id'])
    if 'ap_public_url' not in post_columns:
        op.add_column('post', sa.Column('ap_public_url', sa.String(255), nullable=True))
    if 'ap_fetched_at' not in post_columns:
        op.add_column('post', sa.Column('ap_fetched_at', sa.DateTime(), nullable=True))
    if 'ap_followers_url' not in post_columns:
        op.add_column('post', sa.Column('ap_followers_url', sa.String(255), nullable=True))
    if 'ap_inbox_url' not in post_columns:
        op.add_column('post', sa.Column('ap_inbox_url', sa.String(255), nullable=True))
    if 'ap_outbox_url' not in post_columns:
        op.add_column('post', sa.Column('ap_outbox_url', sa.String(255), nullable=True))
    # LanguageMixin
    if 'language' not in post_columns:
        op.add_column('post', sa.Column('language', sa.String(10), nullable=True))
    # NSFWMixin
    if 'nsfw' not in post_columns:
        op.add_column('post', sa.Column('nsfw', sa.Boolean(), nullable=False, server_default='false'))
        op.create_index('ix_post_nsfw', 'post', ['nsfw'])
    if 'nsfl' not in post_columns:
        op.add_column('post', sa.Column('nsfl', sa.Boolean(), nullable=False, server_default='false'))
        op.create_index('ix_post_nsfl', 'post', ['nsfl'])
    # Additional Post columns from model
    if 'nsfw_mask' not in post_columns:
        op.add_column('post', sa.Column('nsfw_mask', sa.Integer(), nullable=False, server_default='0'))
    if 'from_bot' not in post_columns:
        op.add_column('post', sa.Column('from_bot', sa.Boolean(), nullable=False, server_default='false'))
    if 'reply_count' not in post_columns:
        op.add_column('post', sa.Column('reply_count', sa.Integer(), nullable=False, server_default='0'))
    if 'edited_at' not in post_columns:
        op.add_column('post', sa.Column('edited_at', sa.DateTime(), nullable=True))
    if 'edit_reason' not in post_columns:
        op.add_column('post', sa.Column('edit_reason', sa.String(255), nullable=True))
    if 'posted_at' not in post_columns:
        op.add_column('post', sa.Column('posted_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
        op.create_index('ix_post_posted_at', 'post', ['posted_at'])
    if 'last_active' not in post_columns:
        op.add_column('post', sa.Column('last_active', sa.DateTime(), nullable=False, server_default=sa.func.now()))
        op.create_index('ix_post_last_active', 'post', ['last_active'])
    if 'microblog' not in post_columns:
        op.add_column('post', sa.Column('microblog', sa.Boolean(), nullable=False, server_default='false'))
    
    # Add missing post_reply columns (from mixins)
    post_reply_columns = [c['name'] for c in inspector.get_columns('post_reply')]
    # TimestampMixin
    if 'created_at' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
        op.create_index('ix_post_reply_created_at', 'post_reply', ['created_at'])
    if 'updated_at' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('updated_at', sa.DateTime(), nullable=True))
    # SoftDeleteMixin
    if 'deleted' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('deleted', sa.Boolean(), nullable=False, server_default='false'))
        op.create_index('ix_post_reply_deleted', 'post_reply', ['deleted'])
    if 'deleted_at' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    # ScoreMixin
    if 'score' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('score', sa.Integer(), nullable=False, server_default='0'))
        op.create_index('ix_post_reply_score', 'post_reply', ['score'])
    if 'up_votes' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('up_votes', sa.Integer(), nullable=False, server_default='0'))
    if 'down_votes' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('down_votes', sa.Integer(), nullable=False, server_default='0'))
    if 'ranking' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('ranking', sa.Float(), nullable=False, server_default='0.0'))
        op.create_index('ix_post_reply_ranking', 'post_reply', ['ranking'])
    # ActivityPubMixin
    if 'ap_id' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('ap_id', sa.String(255), nullable=True, unique=True))
        op.create_index('ix_post_reply_ap_id', 'post_reply', ['ap_id'])
    if 'ap_profile_id' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('ap_profile_id', sa.String(255), nullable=True, unique=True))
        op.create_index('ix_post_reply_ap_profile_id', 'post_reply', ['ap_profile_id'])
    if 'ap_public_url' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('ap_public_url', sa.String(255), nullable=True))
    if 'ap_fetched_at' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('ap_fetched_at', sa.DateTime(), nullable=True))
    if 'ap_followers_url' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('ap_followers_url', sa.String(255), nullable=True))
    if 'ap_inbox_url' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('ap_inbox_url', sa.String(255), nullable=True))
    if 'ap_outbox_url' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('ap_outbox_url', sa.String(255), nullable=True))
    # LanguageMixin
    if 'language' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('language', sa.String(10), nullable=True))
    # NSFWMixin
    if 'nsfw' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('nsfw', sa.Boolean(), nullable=False, server_default='false'))
        op.create_index('ix_post_reply_nsfw', 'post_reply', ['nsfw'])
    if 'nsfl' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('nsfl', sa.Boolean(), nullable=False, server_default='false'))
        op.create_index('ix_post_reply_nsfl', 'post_reply', ['nsfl'])
    # Additional PostReply columns from model
    if 'from_bot' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('from_bot', sa.Boolean(), nullable=False, server_default='false'))
    if 'edited_at' not in post_reply_columns:
        op.add_column('post_reply', sa.Column('edited_at', sa.DateTime(), nullable=True))
    
    # Note: Circular dependency between conversation and chat_message tables
    # is handled by use_alter=True in the model definition


def downgrade():
    # Remove columns from language table
    op.drop_column('language', 'active')
    op.drop_column('language', 'native_name')
    
    # Remove weight column from role table
    op.drop_column('role', 'weight')
    
    # Remove role_id column from user table
    op.drop_column('user', 'role_id')
    
    # Remove deleted and ban_state columns from user table
    op.drop_index('ix_user_deleted', 'user')
    op.drop_column('user', 'deleted')
    op.drop_column('user', 'ban_state')
    
    # Remove other user columns
    op.drop_column('user', 'post_reply_count')
    op.drop_column('user', 'suspended')
    op.drop_column('user', 'ignore_bots')
    op.drop_column('user', 'hide_read_posts')
    op.drop_column('user', 'created')
    op.drop_column('user', 'password_updated_at')
    # Drop added user columns
    op.drop_index('ix_user_alt_user_name', 'user')
    op.drop_column('user', 'alt_user_name')
    op.drop_column('user', 'title')
    op.drop_column('user', 'about')
    op.drop_column('user', 'about_html')
    op.drop_column('user', 'avatar_id')
    op.drop_column('user', 'cover_id')
    op.drop_column('user', 'default_sort')
    op.drop_column('user', 'default_filter')
    op.drop_column('user', 'theme')
    op.drop_column('user', 'indexable')
    op.drop_column('user', 'searchable')
    op.drop_column('user', 'hide_nsfw')
    op.drop_column('user', 'hide_nsfl')
    op.drop_column('user', 'receive_message_mode')
    op.drop_column('user', 'post_count')
    op.drop_column('user', 'reputation')
    op.drop_column('user', 'attitude')
    op.drop_index('ix_user_last_seen', 'user')
    op.drop_column('user', 'last_seen')
    op.drop_column('user', 'totp_secret')
    op.drop_column('user', 'totp_enabled')
    op.drop_column('user', 'totp_recovery_codes')
    op.drop_column('user', 'bot')
    op.drop_column('user', 'interface_language')
    op.drop_column('user', 'language_id')
    # Drop ActivityPub columns
    op.drop_index('ix_user_ap_id', 'user')
    op.drop_column('user', 'ap_id')
    op.drop_index('ix_user_ap_profile_id', 'user')
    op.drop_column('user', 'ap_profile_id')
    op.drop_column('user', 'ap_public_url')
    op.drop_column('user', 'ap_fetched_at')
    op.drop_column('user', 'ap_followers_url')
    op.drop_column('user', 'ap_inbox_url')
    op.drop_index('ix_user_ap_domain', 'user')
    op.drop_column('user', 'ap_domain')
    op.drop_column('user', 'ap_preferred_username')
    op.drop_column('user', 'ap_manually_approves_followers')
    op.drop_column('user', 'ap_deleted_at')
    op.drop_column('user', 'private_key')
    op.drop_column('user', 'public_key')
    op.drop_index('ix_user_instance_id', 'user')
    op.drop_column('user', 'instance_id')
    
    # Remove instance columns
    op.drop_column('instance', 'post_count')
    op.drop_column('instance', 'user_count')
    op.drop_column('instance', 'nodeinfo_href')
    op.drop_column('instance', 'start_trying_again')
    op.drop_index('ix_instance_created_at', 'instance')
    op.drop_column('instance', 'created_at')
    op.drop_column('instance', 'updated_at')
    op.drop_column('instance', 'inbox')
    op.drop_column('instance', 'shared_inbox')
    op.drop_column('instance', 'outbox')
    op.drop_column('instance', 'gone_forever')
    op.drop_column('instance', 'dormant')
    op.drop_column('instance', 'last_seen')
    op.drop_column('instance', 'last_successful_send')
    op.drop_column('instance', 'failures')
    op.drop_column('instance', 'most_recent_attempt')
    
    # Remove community columns
    op.drop_column('community', 'rules_html')
    op.drop_column('community', 'description_html')
    op.drop_column('community', 'content_retention')
    op.drop_column('community', 'deleted')
    op.drop_column('community', 'deleted_by')
    op.drop_column('community', 'posting_warning')
    op.drop_column('community', 'default_layout')
    op.drop_column('community', 'private_mods')
    op.drop_column('community', 'new_mods_wanted')
    op.drop_column('community', 'show_popular')
    op.drop_column('community', 'low_quality')
    op.drop_column('community', 'restricted_to_mods')
    op.drop_column('community', 'local_only')
    op.drop_column('community', 'approval_required')
    op.drop_column('community', 'topic_id')
    op.drop_column('community', 'user_id')
    op.drop_column('community', 'instance_id')
    op.drop_column('community', 'ap_moderators_url')
    op.drop_column('community', 'ap_featured_url')
    op.drop_column('community', 'ap_deleted_at')
    op.drop_column('community', 'ap_domain')
    op.drop_column('community', 'ap_followers_url')
    op.drop_column('community', 'ap_public_url')
    op.drop_column('community', 'ap_fetched_at')
    op.drop_column('community', 'language')
    op.drop_column('community', 'updated_at')
    
    # Remove post columns
    op.drop_index('ix_post_created_at', 'post')
    op.drop_column('post', 'created_at')
    op.drop_column('post', 'updated_at')
    op.drop_index('ix_post_deleted', 'post')
    op.drop_column('post', 'deleted')
    op.drop_column('post', 'deleted_at')
    op.drop_index('ix_post_score', 'post')
    op.drop_column('post', 'score')
    op.drop_column('post', 'up_votes')
    op.drop_column('post', 'down_votes')
    op.drop_index('ix_post_ranking', 'post')
    op.drop_column('post', 'ranking')
    op.drop_index('ix_post_ap_id', 'post')
    op.drop_column('post', 'ap_id')
    op.drop_index('ix_post_ap_profile_id', 'post')
    op.drop_column('post', 'ap_profile_id')
    op.drop_column('post', 'ap_public_url')
    op.drop_column('post', 'ap_fetched_at')
    op.drop_column('post', 'ap_followers_url')
    op.drop_column('post', 'ap_inbox_url')
    op.drop_column('post', 'ap_outbox_url')
    op.drop_column('post', 'language')
    op.drop_index('ix_post_nsfw', 'post')
    op.drop_column('post', 'nsfw')
    op.drop_index('ix_post_nsfl', 'post')
    op.drop_column('post', 'nsfl')
    op.drop_column('post', 'nsfw_mask')
    op.drop_column('post', 'from_bot')
    op.drop_column('post', 'reply_count')
    op.drop_column('post', 'edited_at')
    op.drop_column('post', 'edit_reason')
    op.drop_index('ix_post_posted_at', 'post')
    op.drop_column('post', 'posted_at')
    op.drop_index('ix_post_last_active', 'post')
    op.drop_column('post', 'last_active')
    op.drop_column('post', 'microblog')
    
    # Remove post_reply columns
    op.drop_index('ix_post_reply_created_at', 'post_reply')
    op.drop_column('post_reply', 'created_at')
    op.drop_column('post_reply', 'updated_at')
    op.drop_index('ix_post_reply_deleted', 'post_reply')
    op.drop_column('post_reply', 'deleted')
    op.drop_column('post_reply', 'deleted_at')
    op.drop_index('ix_post_reply_score', 'post_reply')
    op.drop_column('post_reply', 'score')
    op.drop_column('post_reply', 'up_votes')
    op.drop_column('post_reply', 'down_votes')
    op.drop_index('ix_post_reply_ranking', 'post_reply')
    op.drop_column('post_reply', 'ranking')
    op.drop_index('ix_post_reply_ap_id', 'post_reply')
    op.drop_column('post_reply', 'ap_id')
    op.drop_index('ix_post_reply_ap_profile_id', 'post_reply')
    op.drop_column('post_reply', 'ap_profile_id')
    op.drop_column('post_reply', 'ap_public_url')
    op.drop_column('post_reply', 'ap_fetched_at')
    op.drop_column('post_reply', 'ap_followers_url')
    op.drop_column('post_reply', 'ap_inbox_url')
    op.drop_column('post_reply', 'ap_outbox_url')
    op.drop_column('post_reply', 'language')
    op.drop_index('ix_post_reply_nsfw', 'post_reply')
    op.drop_column('post_reply', 'nsfw')
    op.drop_index('ix_post_reply_nsfl', 'post_reply')
    op.drop_column('post_reply', 'nsfl')
    op.drop_column('post_reply', 'from_bot')
    op.drop_column('post_reply', 'edited_at')
    
    # Note: Not reverting FK constraints to avoid issues