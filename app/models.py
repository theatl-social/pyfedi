"""
Compatibility wrapper for models

This file provides backward compatibility by importing all models from the new structure.
All models have been refactored into separate files for better organization.
"""

# Import everything from the models package
from app.models import *

# Additional imports that were in the original models.py
from datetime import datetime
from zoneinfo import ZoneInfo

def utcnow(naive=True):
    """Get current UTC time"""
    if naive:
        return datetime.now(ZoneInfo('UTC')).replace(tzinfo=None)
    return datetime.now(ZoneInfo('UTC'))

# Re-export for backward compatibility
__all__ = [
    # Base
    'TimestampMixin', 'SoftDeleteMixin', 'ScoreMixin', 'ActivityPubMixin',
    'LanguageMixin', 'NSFWMixin', 'PostReplyValidationError', 'FederationError',
    'ModerationError',
    
    # User
    'User', 'UserFollower', 'UserFollowRequest', 'UserBlock', 'UserNote',
    'UserRegistration', 'UserExtraField', 'Passkey', 'UserFlair',
    
    # Community
    'Community', 'CommunityMember', 'CommunityBan', 'CommunityJoinRequest',
    'CommunityBlock', 'CommunityWikiPage', 'CommunityWikiPageRevision',
    'CommunityFlair',
    
    # Content
    'Post', 'PostReply', 'PostVote', 'PostReplyVote', 'PostBookmark',
    'PostReplyBookmark', 'ScheduledPost', 'Topic', 'Tag', 'Poll',
    'PollChoice', 'PollChoiceVote',
    
    # Instance
    'Instance', 'InstanceRole', 'BannedInstances', 'AllowedInstances',
    'InstanceBlock', 'InstanceBan', 'Domain', 'DomainBlock',
    'DefederationSubscription', 'FederationError',
    
    # ActivityPub
    'ActivityPubLog', 'ActivityPubRequestLog', 'ActivityBatch',
    'SendQueue', 'APRequestBody', 'APRequestStatus',
    
    # Moderation
    'Report', 'ModLog', 'IpBan', 'Filter', 'BlockedImage',
    
    # Media
    'File', 'Language', 'Licence',
    
    # Notification
    'Notification', 'NotificationSubscription', 'Conversation', 'ChatMessage',
    
    # Misc
    'Site', 'Settings', 'ActivityLog', 'Feed', 'FeedItem', 'FeedMember',
    'FeedJoinRequest', 'CmsPage', 'Event', 'Interest', 'Role', 'RolePermission',
    
    # Utility function
    'utcnow'
]