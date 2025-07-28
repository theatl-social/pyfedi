"""PeachPie models package

This package contains all database models for PeachPie, organized into logical modules:
- base.py: Base classes, mixins, and exceptions
- user.py: User and authentication related models
- community.py: Community and membership models
- content.py: Posts, replies, votes, and content models
- instance.py: Instance and federation models
- activitypub.py: ActivityPub specific models
- moderation.py: Moderation and reporting models
- media.py: File and media management models
- notification.py: Notifications and messaging models
- misc.py: Site settings and miscellaneous models
"""

# Import all models to ensure they're registered with SQLAlchemy
from app.models.base import (
    TimestampMixin, SoftDeleteMixin, ScoreMixin, ActivityPubMixin,
    LanguageMixin, NSFWMixin, PostReplyValidationError, FederationError,
    ModerationError
)

from app.models.user import (
    User, UserFollower, UserFollowRequest, UserBlock, UserNote,
    UserRegistration, UserExtraField, Passkey, UserFlair
)

from app.models.community import (
    Community, CommunityMember, CommunityBan, CommunityJoinRequest,
    CommunityBlock, CommunityWikiPage, CommunityWikiPageRevision,
    CommunityFlair
)

from app.models.content import (
    Post, PostReply, PostVote, PostReplyVote, PostBookmark,
    PostReplyBookmark, ScheduledPost, Topic, Tag, Poll,
    PollChoice, PollChoiceVote
)

from app.models.instance import (
    Instance, InstanceRole, BannedInstances, AllowedInstances,
    InstanceBlock, InstanceBan, Domain, DomainBlock,
    DefederationSubscription, FederationError
)

from app.models.activitypub import (
    ActivityPubLog, ActivityPubRequestLog, CommunityJoinRequest as APCommunityJoinRequest,
    ActivityBatch, SendQueue, APRequestBody, APRequestStatus
)

from app.models.moderation import (
    Report, ModLog, IpBan, Filter, BlockedImage
)

from app.models.media import (
    File, Language, Licence
)

from app.models.notification import (
    Notification, NotificationSubscription, Conversation, ChatMessage
)

from app.models.misc import (
    Site, Settings, ActivityLog, Feed, FeedItem, FeedMember,
    FeedJoinRequest, CmsPage, Event, Interest, Role, RolePermission
)

# For backward compatibility and convenience, expose commonly used models at package level
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
    'FeedJoinRequest', 'CmsPage', 'Event', 'Interest', 'Role', 'RolePermission'
]

# Import search functionality if using PostgreSQL
try:
    from sqlalchemy_searchable import make_searchable
    from app import db
    make_searchable(db.metadata)
except ImportError:
    pass