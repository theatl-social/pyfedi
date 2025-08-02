"""Community-related models for PeachPie"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, Text, DateTime, ForeignKey, Index, Float, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from sqlalchemy.ext.hybrid import hybrid_property

from app import db, cache
from app.models.base import (
    TimestampMixin, ActivityPubMixin, LanguageMixin, NSFWMixin,
    UserId, CommunityId, PostId, InstanceId
)
from app.utils import markdown_to_html, html_to_text

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.content import Post, Topic
    from app.models.instance import Instance
    from app.models.moderation import Report


class Community(TimestampMixin, ActivityPubMixin, LanguageMixin, NSFWMixin, db.Model):
    """Community model with full typing support"""
    __tablename__ = 'community'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Description
    description: Mapped[Optional[str]] = mapped_column(Text)  # markdown
    description_html: Mapped[Optional[str]] = mapped_column(Text)  # rendered HTML
    
    # Rules and guidelines
    rules: Mapped[Optional[str]] = mapped_column(Text)  # markdown
    rules_html: Mapped[Optional[str]] = mapped_column(Text)  # rendered HTML
    
    # Visual elements
    icon_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('file.id'))
    image_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('file.id'))
    
    # Stats
    post_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    post_reply_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    subscriptions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    
    # Settings
    banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    private_mods: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    new_mods_wanted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    show_popular: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    show_all: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    searchable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    low_quality: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    content_retention: Mapped[int] = mapped_column(Integer, default=-1, nullable=False)
    
    # Access control
    restricted_to_mods: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    local_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Moderation
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    topic_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('topic.id'))
    default_layout: Mapped[Optional[str]] = mapped_column(String(15))
    
    # Deletion
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_by: Mapped[Optional[UserId]] = mapped_column(Integer, ForeignKey('user.id'))
    
    # Creator and instance
    user_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), nullable=False)
    instance_id: Mapped[Optional[InstanceId]] = mapped_column(Integer, ForeignKey('instance.id'), index=True)
    
    # Posting settings
    posting_warning: Mapped[Optional[str]] = mapped_column(Text)
    
    # ActivityPub extras
    ap_moderators_url: Mapped[Optional[str]] = mapped_column(String(255))
    ap_featured_url: Mapped[Optional[str]] = mapped_column(String(255))
    ap_deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ap_domain: Mapped[Optional[str]] = mapped_column(String(255))
    private_key: Mapped[Optional[str]] = mapped_column(Text)
    public_key: Mapped[Optional[str]] = mapped_column(Text)
    
    # Search vector (PostgreSQL specific)
    # TODO: Enable search_vector when using PostgreSQL
    # from sqlalchemy_utils.types import TSVectorType
    # search_vector = mapped_column(TSVectorType('name', 'title', 'description'))
    
    # Relationships
    icon = relationship('File', foreign_keys=[icon_id])
    image = relationship('File', foreign_keys=[image_id])
    topic = relationship('Topic', back_populates='communities')
    creator = relationship('User', foreign_keys=[user_id], back_populates='created_communities')
    instance = relationship('Instance', back_populates='communities')
    
    posts = relationship('Post', back_populates='community', lazy='dynamic',
                        cascade='all, delete-orphan')
    members = relationship('CommunityMember', back_populates='community', lazy='dynamic',
                          cascade='all, delete-orphan')
    banned_users = relationship('CommunityBan', back_populates='community', lazy='dynamic',
                               cascade='all, delete-orphan')
    join_requests = relationship('CommunityJoinRequest', back_populates='community', lazy='dynamic',
                               cascade='all, delete-orphan')
    wiki_pages = relationship('CommunityWikiPage', back_populates='community', lazy='dynamic',
                            cascade='all, delete-orphan')
    
    # Indexes
    __table_args__ = (
        Index('idx_community_name_instance', 'name', 'instance_id'),
        Index('idx_community_activity', 'post_count', 'subscriptions_count'),
        {'extend_existing': True}
    )
    
    @validates('name')
    def validate_name(self, key: str, value: str) -> str:
        """Validate community name"""
        if not value or len(value) < 3:
            raise ValueError('Community name must be at least 3 characters')
        if len(value) > 255:
            raise ValueError('Community name too long')
        # Only allow alphanumeric and underscores
        if not value.replace('_', '').isalnum():
            raise ValueError('Community name can only contain letters, numbers, and underscores')
        return value.lower()
    
    @hybrid_property
    def display_name(self) -> str:
        """Get display name with instance"""
        if self.is_local:
            return f"!{self.name}"
        return f"!{self.name}@{self.ap_domain}"
    
    @hybrid_property
    def is_active(self) -> bool:
        """Check if community is active"""
        return not self.deleted
    
    def can_be_posted_to(self) -> bool:
        """Check if community accepts new posts"""
        if self.deleted:
            return False
        if self.restricted_to_mods:
            return False  # Will be checked per-user
        return True
    
    def is_moderator(self, user: 'User') -> bool:
        """Check if user is moderator"""
        if user.is_admin():
            return True
        membership = self.members.filter_by(
            user_id=user.id,
            is_moderator=True
        ).first()
        return membership is not None
    
    def is_member(self, user: 'User') -> bool:
        """Check if user is member"""
        membership = self.members.filter_by(user_id=user.id).first()
        return membership is not None
    
    def is_banned(self, user: 'User') -> bool:
        """Check if user is banned"""
        ban = self.banned_users.filter_by(
            user_id=user.id,
            active=True
        ).first()
        return ban is not None
    
    def __repr__(self) -> str:
        return f'<Community {self.name}>'


class CommunityMember(TimestampMixin, db.Model):
    """Community membership with roles"""
    __tablename__ = 'community_member'
    __table_args__ = (
        UniqueConstraint('community_id', 'user_id'),
        {'extend_existing': True}
    )
    
    # Primary keys
    community_id: Mapped[CommunityId] = mapped_column(
        Integer, ForeignKey('community.id'), primary_key=True
    )
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), primary_key=True
    )
    
    # Roles
    is_moderator: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Notifications
    notify_new_posts: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notify_new_replies: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relationships
    community = relationship('Community', back_populates='members')
    user = relationship('User', back_populates='community_memberships')


class CommunityBan(TimestampMixin, db.Model):
    """Community bans"""
    __tablename__ = 'community_ban'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    community_id: Mapped[CommunityId] = mapped_column(
        Integer, ForeignKey('community.id'), nullable=False, index=True
    )
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False, index=True
    )
    banned_by_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False
    )
    
    # Ban details
    reason: Mapped[Optional[str]] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ban_until: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Relationships
    community = relationship('Community', back_populates='banned_users')
    user = relationship('User', foreign_keys=[user_id], back_populates='community_bans')
    banned_by = relationship('User', foreign_keys=[banned_by_id])
    
    @property
    def is_expired(self) -> bool:
        """Check if ban has expired"""
        if not self.ban_until:
            return False
        return datetime.now(timezone.utc) > self.ban_until


class CommunityJoinRequest(TimestampMixin, db.Model):
    """Pending community join requests"""
    __tablename__ = 'community_join_request'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    community_id: Mapped[CommunityId] = mapped_column(
        Integer, ForeignKey('community.id'), nullable=False, index=True
    )
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False, index=True
    )
    
    # Relationships
    community = relationship('Community', back_populates='join_requests')
    user = relationship('User')


class CommunityBlock(TimestampMixin, db.Model):
    """User blocks of communities"""
    __tablename__ = 'community_block'
    __table_args__ = {'extend_existing': True}
    
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), primary_key=True
    )
    community_id: Mapped[CommunityId] = mapped_column(
        Integer, ForeignKey('community.id'), primary_key=True
    )
    
    # Relationships
    user = relationship('User')
    community = relationship('Community')


class CommunityWikiPage(TimestampMixin, db.Model):
    """Community wiki pages"""
    __tablename__ = 'community_wiki_page'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    community_id: Mapped[CommunityId] = mapped_column(
        Integer, ForeignKey('community.id'), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Permissions
    restricted_to_mods: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relationships
    community = relationship('Community', back_populates='wiki_pages')
    revisions = relationship('CommunityWikiPageRevision', back_populates='page', lazy='dynamic',
                           cascade='all, delete-orphan', order_by='desc(CommunityWikiPageRevision.created_at)')
    
    @property
    def current_revision(self) -> Optional['CommunityWikiPageRevision']:
        """Get current revision"""
        return self.revisions.first()
    
    @property
    def body(self) -> Optional[str]:
        """Get current body text"""
        revision = self.current_revision
        return revision.body if revision else None
    
    @property
    def body_html(self) -> Optional[str]:
        """Get current body HTML"""
        revision = self.current_revision
        return revision.body_html if revision else None


class CommunityWikiPageRevision(TimestampMixin, db.Model):
    """Wiki page revision history"""
    __tablename__ = 'community_wiki_page_revision'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    page_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('community_wiki_page.id'), nullable=False, index=True
    )
    author_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False
    )
    
    # Content
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)  # markdown
    body_html: Mapped[str] = mapped_column(Text, nullable=False)  # rendered HTML
    
    # Edit summary
    summary: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Relationships
    page = relationship('CommunityWikiPage', back_populates='revisions')
    author = relationship('User')


class CommunityFlair(db.Model):
    """Community-specific user flair"""
    __tablename__ = 'community_flair'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    community_id: Mapped[CommunityId] = mapped_column(
        Integer, ForeignKey('community.id'), nullable=False, index=True
    )
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False, index=True
    )
    flair: Mapped[str] = mapped_column(String(256), nullable=False)
    
    # Relationships
    community = relationship('Community')
    user = relationship('User')