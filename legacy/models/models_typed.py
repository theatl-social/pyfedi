"""Typed models for PyFedi using Python 3.13 features and SQLAlchemy 2.0"""
from __future__ import annotations
from typing import Optional, List, TYPE_CHECKING, Literal, Union
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, Text, DateTime, ForeignKey, Index, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy_searchable import TSVectorType
from flask import current_app
from flask_login import UserMixin

from app import db
from app.federation.types import ActorUrl, Domain
from app.constants import POST_STATUS_PUBLISHED

if TYPE_CHECKING:
    from app.models import Community, Post, PostReply, File

# Type aliases for clarity
type UserId = int
type CommunityId = int
type PostId = int
type InstanceId = int

class TypedUser(UserMixin, db.Model):
    """User model with full typing support"""
    __tablename__ = 'user'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    alt_user_name: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    title: Mapped[Optional[str]] = mapped_column(String(256))
    
    # Authentication
    password_hash: Mapped[Optional[str]] = mapped_column(String(128))
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_token: Mapped[Optional[str]] = mapped_column(String(16), index=True)
    
    # Status flags
    banned: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    banned_until: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ban_posts: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ban_comments: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_by: Mapped[Optional[UserId]] = mapped_column(Integer, index=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_token: Mapped[Optional[str]] = mapped_column(String(16), index=True)
    
    # Profile information
    about: Mapped[Optional[str]] = mapped_column(Text)  # markdown
    about_html: Mapped[Optional[str]] = mapped_column(Text)  # html
    keywords: Mapped[Optional[str]] = mapped_column(String(256))
    matrix_user_id: Mapped[Optional[str]] = mapped_column(String(256))
    
    # Preferences
    hide_nsfw: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    hide_nsfl: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    newsletter: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_unread: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_unread_sent: Mapped[Optional[bool]] = mapped_column(Boolean)
    receive_message_mode: Mapped[str] = mapped_column(String(20), default='Closed', nullable=False)
    timezone: Mapped[Optional[str]] = mapped_column(String(30))
    searchable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    indexable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    suppress_crossposts: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    vote_privately: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ignore_bots: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Timestamps
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    last_active: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # ActivityPub fields
    ap_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True)  # ActorUrl
    ap_domain: Mapped[Optional[str]] = mapped_column(String(255), index=True)  # Domain
    ap_public_url: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    ap_profile_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True)
    ap_inbox_url: Mapped[Optional[str]] = mapped_column(String(255))
    ap_outbox_url: Mapped[Optional[str]] = mapped_column(String(255))
    ap_followers_url: Mapped[Optional[str]] = mapped_column(String(255))
    ap_preferred_username: Mapped[Optional[str]] = mapped_column(String(255))
    ap_manually_approves_followers: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ap_discoverable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ap_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ap_deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Cryptography
    public_key: Mapped[Optional[str]] = mapped_column(Text)
    private_key: Mapped[Optional[str]] = mapped_column(Text)
    
    # Media
    avatar_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('file.id'), index=True)
    cover_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('file.id'), index=True)
    
    # Instance
    instance_id: Mapped[Optional[InstanceId]] = mapped_column(Integer, ForeignKey('instance.id'), index=True)
    
    # Bot detection
    bot: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    bot_override: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    
    # Scoring and Statistics
    reputation: Mapped[float] = mapped_column(db.Float, default=0.0, nullable=False)
    attitude: Mapped[Optional[float]] = mapped_column(db.Float)  # (upvotes - downvotes) / (upvotes + downvotes)
    post_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    post_reply_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Payment/Subscription
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(50))
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Email bounces
    bounces: Mapped[int] = mapped_column(db.SmallInteger, default=0, nullable=False)
    
    # IP tracking
    ip_address: Mapped[Optional[str]] = mapped_column(String(50))
    ip_address_country: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Notifications
    unread_notifications: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Language preferences
    language: Mapped[Optional[str]] = mapped_column(String(10))
    interface_language: Mapped[Optional[str]] = mapped_column(String(10))
    languages: Mapped[Optional[List[str]]] = mapped_column(MutableList.as_mutable(ARRAY(db.String(10))))
    
    # Profile settings
    referrer: Mapped[Optional[str]] = mapped_column(String(256))
    theme: Mapped[Optional[str]] = mapped_column(String(20))
    email_visible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Content filters
    filters: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    keyword_filter_phrase: Mapped[Optional[str]] = mapped_column(Text)
    keyword_filter_replace: Mapped[Optional[str]] = mapped_column(Text)
    keyword_filter_hide: Mapped[Optional[str]] = mapped_column(Text)
    
    # Other preferences
    default_sort: Mapped[Optional[str]] = mapped_column(String(25))
    default_filter: Mapped[Optional[str]] = mapped_column(String(25))
    markdown_editor: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_post_length: Mapped[int] = mapped_column(Integer, default=10000, nullable=False)
    max_post_reply_length: Mapped[int] = mapped_column(Integer, default=5000, nullable=False)
    
    # Additional security/privacy
    last_active: Mapped[Optional[datetime]] = mapped_column(DateTime)
    password_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Relationships with proper typing
    instance: Mapped[Optional['Instance']] = relationship('Instance', back_populates='users')
    avatar: Mapped[Optional['File']] = relationship('File', foreign_keys=[avatar_id])
    cover: Mapped[Optional['File']] = relationship('File', foreign_keys=[cover_id])
    
    # Collections
    posts: Mapped[List['Post']] = relationship('Post', back_populates='author', lazy='dynamic')
    post_replies: Mapped[List['PostReply']] = relationship('PostReply', back_populates='author', lazy='dynamic')
    communities: Mapped[List['Community']] = relationship(
        'Community',
        secondary='community_member',
        back_populates='members',
        lazy='dynamic'
    )
    
    # Indexes
    __table_args__ = (
        Index('idx_user_instance_ap', 'instance_id', 'ap_id'),
        Index('idx_user_reputation', 'reputation'),
        Index('idx_user_created', 'created'),
    )
    
    def __repr__(self) -> str:
        return f'<User {self.user_name}>'
    
    # Type-safe properties
    @property
    def is_local(self) -> bool:
        """Check if user is local (not federated)"""
        return self.ap_id is None
    
    @property
    def is_remote(self) -> bool:
        """Check if user is remote (federated)"""
        return self.ap_id is not None
    
    @property
    def is_banned(self) -> bool:
        """Check if user is currently banned"""
        if not self.banned:
            return False
        if self.banned_until is None:
            return True  # Permanent ban
        return datetime.utcnow() < self.banned_until
    
    @property
    def display_name(self) -> str:
        """Get display name (title or username)"""
        return self.title or self.user_name
    
    @property
    def link(self) -> str:
        """Get local link for user"""
        return self.user_name if self.is_local else f"{self.user_name}@{self.ap_domain}"
    
    def public_url(self) -> str:
        """Get public ActivityPub URL"""
        if self.ap_public_url:
            return self.ap_public_url
        elif self.ap_id:
            return self.ap_id
        else:
            return f"https://{current_app.config['SERVER_NAME']}/u/{self.user_name}"
    
    def get_inbox_url(self) -> str:
        """Get inbox URL for ActivityPub"""
        if self.ap_inbox_url:
            return self.ap_inbox_url
        elif self.is_local:
            return f"https://{current_app.config['SERVER_NAME']}/u/{self.user_name}/inbox"
        else:
            raise ValueError("Remote user missing inbox URL")
    
    # Type-safe methods
    def has_blocked_user(self, user_id: UserId) -> bool:
        """Check if this user has blocked another user"""
        from app.models import UserBlock
        return db.session.query(
            UserBlock.query.filter_by(
                blocker_id=self.id,
                blocked_id=user_id
            ).exists()
        ).scalar()
    
    def has_blocked_instance(self, instance_id: InstanceId) -> bool:
        """Check if this user has blocked an instance"""
        from app.models import InstanceBlock
        return db.session.query(
            InstanceBlock.query.filter_by(
                user_id=self.id,
                instance_id=instance_id
            ).exists()
        ).scalar()
    
    def is_subscribed_to(self, community_id: CommunityId) -> bool:
        """Check if user is subscribed to a community"""
        from app.models import CommunityMember
        return db.session.query(
            CommunityMember.query.filter_by(
                user_id=self.id,
                community_id=community_id
            ).exists()
        ).scalar()
    
    def get_subscription_type(self, community_id: CommunityId) -> Optional[int]:
        """Get user's subscription type for a community"""
        from app.models import CommunityMember
        member = CommunityMember.query.filter_by(
            user_id=self.id,
            community_id=community_id
        ).first()
        return member.is_moderator if member else None
    
    def can_post_in(self, community: 'Community') -> bool:
        """Check if user can post in a community"""
        if self.banned or self.ban_posts:
            return False
        
        if community.restricted_to_mods:
            return self.is_moderator_of(community.id)
        
        return True
    
    def can_comment_in(self, community: 'Community') -> bool:
        """Check if user can comment in a community"""
        if self.banned or self.ban_comments:
            return False
        
        return True
    
    def is_moderator_of(self, community_id: CommunityId) -> bool:
        """Check if user is a moderator of a community"""
        from app.models import CommunityMember
        member = CommunityMember.query.filter_by(
            user_id=self.id,
            community_id=community_id,
            is_moderator=True
        ).first()
        return member is not None
    
    def is_admin(self) -> bool:
        """Check if user is an admin"""
        from app.models import Role
        return self.has_role('Admin')
    
    def has_role(self, role_name: str) -> bool:
        """Check if user has a specific role"""
        # Implementation depends on role system
        return False  # Placeholder


class TypedCommunity(db.Model):
    """Community model with full typing support"""
    __tablename__ = 'community'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Description
    description: Mapped[Optional[str]] = mapped_column(Text)  # markdown
    description_html: Mapped[Optional[str]] = mapped_column(Text)  # html
    rules: Mapped[Optional[str]] = mapped_column(Text)  # markdown
    rules_html: Mapped[Optional[str]] = mapped_column(Text)  # html
    
    # Media
    icon_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('file.id'))
    image_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('file.id'))
    
    # Settings
    nsfw: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    nsfl: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    local_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    restricted_to_mods: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    new_mods_wanted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    private_mods: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # ActivityPub fields
    ap_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True)
    ap_domain: Mapped[Optional[Domain]] = mapped_column(String(255), index=True)
    ap_public_url: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    ap_followers_url: Mapped[Optional[str]] = mapped_column(String(255))
    ap_inbox_url: Mapped[Optional[str]] = mapped_column(String(255))
    ap_moderators_url: Mapped[Optional[str]] = mapped_column(String(255))
    ap_featured_url: Mapped[Optional[str]] = mapped_column(String(255))
    ap_outbox_url: Mapped[Optional[str]] = mapped_column(String(255))
    ap_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ap_deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Cryptography
    public_key: Mapped[Optional[str]] = mapped_column(Text)
    private_key: Mapped[Optional[str]] = mapped_column(Text)
    
    # Instance
    instance_id: Mapped[Optional[InstanceId]] = mapped_column(Integer, ForeignKey('instance.id'), index=True)
    
    # Status
    banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    searchable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_active: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Statistics
    post_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    post_reply_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    subscriptions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Relationships
    instance: Mapped[Optional['Instance']] = relationship('Instance', back_populates='communities')
    icon: Mapped[Optional['File']] = relationship('File', foreign_keys=[icon_id])
    image: Mapped[Optional['File']] = relationship('File', foreign_keys=[image_id])
    posts: Mapped[List['Post']] = relationship('Post', back_populates='community', lazy='dynamic')
    members: Mapped[List['TypedUser']] = relationship(
        'TypedUser',
        secondary='community_member',
        back_populates='communities',
        lazy='dynamic'
    )
    
    @property
    def is_local(self) -> bool:
        """Check if community is local"""
        return self.ap_id is None
    
    @property
    def is_remote(self) -> bool:
        """Check if community is remote"""
        return self.ap_id is not None
    
    def public_url(self) -> str:
        """Get public ActivityPub URL"""
        if self.ap_public_url:
            return self.ap_public_url
        elif self.ap_id:
            return self.ap_id
        else:
            return f"https://{current_app.config['SERVER_NAME']}/c/{self.name}"
    
    def get_inbox_url(self) -> str:
        """Get inbox URL for ActivityPub"""
        if self.ap_inbox_url:
            return self.ap_inbox_url
        elif self.is_local:
            return f"https://{current_app.config['SERVER_NAME']}/c/{self.name}/inbox"
        else:
            raise ValueError("Remote community missing inbox URL")
    
    def following_instances(self) -> List['Instance']:
        """Get instances that follow this community"""
        # Implementation needed
        return []


class TypedPost(db.Model):
    """Post model with full typing support"""
    __tablename__ = 'post'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Content
    body: Mapped[Optional[str]] = mapped_column(Text)  # markdown
    body_html: Mapped[Optional[str]] = mapped_column(Text)  # html
    type: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1=link, 2=image, 3=article, 4=video, 5=poll
    
    # URLs
    url: Mapped[Optional[str]] = mapped_column(String(1024))
    domain: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    image_path: Mapped[Optional[str]] = mapped_column(String(255))
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Status
    status: Mapped[int] = mapped_column(Integer, default=POST_STATUS_PUBLISHED, nullable=False)
    nsfw: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    nsfl: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sticky: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    comments_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_by: Mapped[Optional[UserId]] = mapped_column(Integer)
    
    # Relationships
    user_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), index=True, nullable=False)
    community_id: Mapped[CommunityId] = mapped_column(Integer, ForeignKey('community.id'), index=True, nullable=False)
    instance_id: Mapped[Optional[InstanceId]] = mapped_column(Integer, ForeignKey('instance.id'), index=True)
    
    # Voting
    score: Mapped[float] = mapped_column(db.Float, default=0.0, nullable=False, index=True)
    up_votes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    down_votes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ranking: Mapped[float] = mapped_column(db.Float, default=0.0, nullable=False, index=True)
    hot_rank: Mapped[float] = mapped_column(db.Float, default=0.0, nullable=False, index=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    last_active: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # ActivityPub
    ap_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True)
    ap_create_id: Mapped[Optional[str]] = mapped_column(String(255))
    ap_announce_id: Mapped[Optional[str]] = mapped_column(String(255))
    ap_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ap_deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Metrics
    reply_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Language
    language: Mapped[Optional[str]] = mapped_column(String(10))
    
    # Search
    search_vector: Mapped[Optional[str]] = mapped_column(TSVectorType('title', 'body'))
    
    # Relationships
    author: Mapped['TypedUser'] = relationship('TypedUser', back_populates='posts')
    community: Mapped['TypedCommunity'] = relationship('TypedCommunity', back_populates='posts')
    instance: Mapped[Optional['Instance']] = relationship('Instance', back_populates='posts')
    replies: Mapped[List['TypedPostReply']] = relationship('TypedPostReply', back_populates='post', lazy='dynamic')
    
    # Indexes
    __table_args__ = (
        Index('idx_post_community_sticky_score', 'community_id', 'sticky', 'score'),
        Index('idx_post_posted_at', 'posted_at'),
        Index('idx_post_hot_rank', 'hot_rank'),
    )
    
    @property
    def is_local(self) -> bool:
        """Check if post is local"""
        return self.ap_id is None
    
    @property
    def is_remote(self) -> bool:
        """Check if post is remote"""
        return self.ap_id is not None
    
    def public_url(self) -> str:
        """Get public URL for post"""
        if self.ap_id:
            return self.ap_id
        else:
            return f"https://{current_app.config['SERVER_NAME']}/post/{self.id}"
    
    def can_edit(self, user: 'TypedUser') -> bool:
        """Check if user can edit this post"""
        if user.is_anonymous:
            return False
        return (self.user_id == user.id or 
                user.is_moderator_of(self.community_id) or 
                user.is_admin())
    
    def can_delete(self, user: 'TypedUser') -> bool:
        """Check if user can delete this post"""
        return self.can_edit(user)


class TypedPostReply(db.Model):
    """Post reply model with full typing support"""
    __tablename__ = 'post_reply'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Content
    body: Mapped[str] = mapped_column(Text, nullable=False)  # markdown
    body_html: Mapped[str] = mapped_column(Text, nullable=False)  # html
    
    # Status
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_by: Mapped[Optional[UserId]] = mapped_column(Integer)
    
    # Relationships
    user_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), index=True, nullable=False)
    post_id: Mapped[PostId] = mapped_column(Integer, ForeignKey('post.id'), index=True, nullable=False)
    community_id: Mapped[CommunityId] = mapped_column(Integer, ForeignKey('community.id'), index=True, nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('post_reply.id'), index=True)
    instance_id: Mapped[Optional[InstanceId]] = mapped_column(Integer, ForeignKey('instance.id'), index=True)
    
    # Voting
    score: Mapped[float] = mapped_column(db.Float, default=0.0, nullable=False)
    up_votes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    down_votes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ranking: Mapped[float] = mapped_column(db.Float, default=0.0, nullable=False)
    hot_rank: Mapped[float] = mapped_column(db.Float, default=0.0, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # ActivityPub
    ap_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True)
    ap_create_id: Mapped[Optional[str]] = mapped_column(String(255))
    ap_announce_id: Mapped[Optional[str]] = mapped_column(String(255))
    ap_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ap_deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Metrics
    depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    child_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Search
    search_vector: Mapped[Optional[str]] = mapped_column(TSVectorType('body'))
    
    # Relationships
    author: Mapped['TypedUser'] = relationship('TypedUser', back_populates='post_replies')
    post: Mapped['TypedPost'] = relationship('TypedPost', back_populates='replies')
    parent: Mapped[Optional['TypedPostReply']] = relationship('TypedPostReply', remote_side=[id])
    children: Mapped[List['TypedPostReply']] = relationship(
        'TypedPostReply',
        backref=relationship('TypedPostReply', remote_side=[parent_id]),
        cascade='all, delete-orphan'
    )
    instance: Mapped[Optional['Instance']] = relationship('Instance', back_populates='post_replies')
    
    # Indexes
    __table_args__ = (
        Index('idx_post_reply_post_created', 'post_id', 'created_at'),
        Index('idx_post_reply_parent', 'parent_id'),
    )
    
    @property
    def is_local(self) -> bool:
        """Check if reply is local"""
        return self.ap_id is None
    
    @property
    def is_remote(self) -> bool:
        """Check if reply is remote"""
        return self.ap_id is not None
    
    def public_url(self) -> str:
        """Get public URL for reply"""
        if self.ap_id:
            return self.ap_id
        else:
            return f"https://{current_app.config['SERVER_NAME']}/comment/{self.id}"
    
    def can_edit(self, user: 'TypedUser') -> bool:
        """Check if user can edit this reply"""
        if user.is_anonymous:
            return False
        return (self.user_id == user.id or 
                user.is_moderator_of(self.community_id) or 
                user.is_admin())
    
    def can_delete(self, user: 'TypedUser') -> bool:
        """Check if user can delete this reply"""
        return self.can_edit(user)


class TypedInstance(db.Model):
    """Instance model with full typing support"""
    __tablename__ = 'instance'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain: Mapped[str] = mapped_column(String(256), index=True, unique=True, nullable=False)
    
    # ActivityPub endpoints
    inbox: Mapped[Optional[str]] = mapped_column(String(256))
    shared_inbox: Mapped[Optional[str]] = mapped_column(String(256))
    outbox: Mapped[Optional[str]] = mapped_column(String(256))
    
    # Instance metadata
    software: Mapped[Optional[str]] = mapped_column(String(50))
    version: Mapped[Optional[str]] = mapped_column(String(50))
    nodeinfo_href: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Voting configuration
    vote_weight: Mapped[float] = mapped_column(db.Float, default=1.0, nullable=False)
    
    # Health tracking
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_successful_send: Mapped[Optional[datetime]] = mapped_column(DateTime)
    failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    most_recent_attempt: Mapped[Optional[datetime]] = mapped_column(DateTime)
    dormant: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    start_trying_again: Mapped[Optional[datetime]] = mapped_column(DateTime)
    gone_forever: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Network info
    ip_address: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Trust and warnings
    trusted: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    posting_warning: Mapped[Optional[str]] = mapped_column(String(512))
    
    # Relationships
    posts: Mapped[List['TypedPost']] = relationship('TypedPost', back_populates='instance', lazy='dynamic')
    post_replies: Mapped[List['TypedPostReply']] = relationship('TypedPostReply', back_populates='instance', lazy='dynamic')
    communities: Mapped[List['TypedCommunity']] = relationship('TypedCommunity', back_populates='instance', lazy='dynamic')
    users: Mapped[List['TypedUser']] = relationship('TypedUser', back_populates='instance', lazy='dynamic')
    
    def online(self) -> bool:
        """Check if instance is considered online"""
        return not (self.dormant or self.gone_forever)
    
    def user_is_admin(self, user_id: UserId) -> bool:
        """Check if user is admin of this instance"""
        from app.models import InstanceRole
        role = InstanceRole.query.filter_by(instance_id=self.id, user_id=user_id).first()
        return role and role.role == 'admin'
    
    def votes_are_public(self) -> bool:
        """Check if this instance makes votes public"""
        if self.trusted is True:
            return False
        software_lower = self.software.lower() if self.software else ''
        return software_lower in ['lemmy', 'mbin', 'kbin', 'guppe groups']
    
    def update_dormant_gone(self) -> None:
        """Update dormant and gone_forever status based on failures"""
        if self.failures > 7 and self.dormant:
            self.gone_forever = True
        elif self.failures > 2 and not self.dormant:
            self.dormant = True
    
    @classmethod
    def weight(cls, domain: str) -> float:
        """Get vote weight for a domain"""
        if domain:
            instance = cls.query.filter_by(domain=domain).first()
            if instance:
                return instance.vote_weight
        return 1.0
    
    def __repr__(self) -> str:
        return f'<Instance {self.domain}>'