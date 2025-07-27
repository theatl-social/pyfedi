"""Typed relationship and voting models for PyFedi using Python 3.13 features"""
from __future__ import annotations
from typing import Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, Float, Text, DateTime, ForeignKey, Index, JSON, desc
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app import db
from app.constants import NOTIF_DEFAULT

if TYPE_CHECKING:
    from app.models_typed import TypedUser, TypedCommunity, TypedPost, TypedPostReply

# Type aliases
type UserId = int
type CommunityId = int
type PostId = int
type PostReplyId = int
type NotificationId = int


class TypedCommunityMember(db.Model):
    """Community membership model with full typing"""
    __tablename__ = 'community_member'
    
    # Primary keys
    user_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), primary_key=True)
    community_id: Mapped[CommunityId] = mapped_column(Integer, ForeignKey('community.id'), primary_key=True)
    
    # Membership status
    is_moderator: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    
    # Notifications
    notify_new_posts: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Metadata
    joined_via_feed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user: Mapped['TypedUser'] = relationship('TypedUser', backref='memberships')
    community: Mapped['TypedCommunity'] = relationship('TypedCommunity', backref='memberships')
    
    def __repr__(self) -> str:
        return f'<CommunityMember user={self.user_id} community={self.community_id}>'


class TypedPostVote(db.Model):
    """Post vote model with full typing"""
    __tablename__ = 'post_vote'
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), index=True, nullable=False)
    author_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), index=True, nullable=False)
    post_id: Mapped[PostId] = mapped_column(Integer, ForeignKey('post.id'), index=True, nullable=False)
    
    # Vote details
    effect: Mapped[float] = mapped_column(Float, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    post: Mapped['TypedPost'] = relationship('TypedPost', foreign_keys=[post_id])
    user: Mapped['TypedUser'] = relationship('TypedUser', foreign_keys=[user_id])
    author: Mapped['TypedUser'] = relationship('TypedUser', foreign_keys=[author_id])
    
    # Indexes
    __table_args__ = (
        Index('ix_post_vote_user_id_id_desc', 'user_id', desc('id')),
        Index('ix_post_vote_post_created', 'post_id', 'created_at'),
        Index('ix_post_vote_created', 'created_at')
    )
    
    @property
    def is_upvote(self) -> bool:
        """Check if this is an upvote"""
        return self.effect > 0
    
    @property
    def is_downvote(self) -> bool:
        """Check if this is a downvote"""
        return self.effect < 0


class TypedPostReplyVote(db.Model):
    """Post reply vote model with full typing"""
    __tablename__ = 'post_reply_vote'
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), index=True, nullable=False)
    author_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), index=True, nullable=False)
    post_reply_id: Mapped[PostReplyId] = mapped_column(Integer, ForeignKey('post_reply.id'), index=True, nullable=False)
    
    # Vote details
    effect: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    post_reply: Mapped['TypedPostReply'] = relationship('TypedPostReply', foreign_keys=[post_reply_id])
    user: Mapped['TypedUser'] = relationship('TypedUser', foreign_keys=[user_id])
    author: Mapped['TypedUser'] = relationship('TypedUser', foreign_keys=[author_id])
    
    # Indexes
    __table_args__ = (
        Index('ix_post_reply_vote_user_id_id_desc', 'user_id', desc('id')),
        Index('ix_post_reply_vote_reply_created', 'post_reply_id', 'created_at'),
        Index('ix_post_reply_vote_created', 'created_at')
    )
    
    @property
    def is_upvote(self) -> bool:
        """Check if this is an upvote"""
        return self.effect > 0
    
    @property
    def is_downvote(self) -> bool:
        """Check if this is a downvote"""
        return self.effect < 0


class TypedNotification(db.Model):
    """Notification model with full typing"""
    __tablename__ = 'notification'
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Notification content
    title: Mapped[Optional[str]] = mapped_column(String(150))
    url: Mapped[Optional[str]] = mapped_column(String(512))
    
    # Status
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # User relationships
    user_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), index=True, nullable=False)
    author_id: Mapped[Optional[UserId]] = mapped_column(Integer, ForeignKey('user.id'))
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Notification type
    notif_type: Mapped[int] = mapped_column(Integer, default=NOTIF_DEFAULT, index=True, nullable=False)
    subtype: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    
    # Additional data
    targets: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Relationships
    user: Mapped['TypedUser'] = relationship('TypedUser', foreign_keys=[user_id], backref='notifications')
    author: Mapped[Optional['TypedUser']] = relationship('TypedUser', foreign_keys=[author_id])
    
    def mark_read(self) -> None:
        """Mark notification as read"""
        self.read = True
        # Also decrement user's unread count
        if self.user:
            self.user.unread_notifications = max(0, self.user.unread_notifications - 1)
    
    def __repr__(self) -> str:
        return f'<Notification {self.id}: {self.title}>'


class TypedUserBlock(db.Model):
    """User block relationship with full typing"""
    __tablename__ = 'user_block'
    
    # Primary keys
    blocker_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), primary_key=True)
    blocked_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), primary_key=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    blocker: Mapped['TypedUser'] = relationship('TypedUser', foreign_keys=[blocker_id])
    blocked: Mapped['TypedUser'] = relationship('TypedUser', foreign_keys=[blocked_id])
    
    def __repr__(self) -> str:
        return f'<UserBlock {self.blocker_id} blocks {self.blocked_id}>'


class TypedInstanceBlock(db.Model):
    """Instance block by user with full typing"""
    __tablename__ = 'instance_block'
    
    # Primary keys
    user_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), primary_key=True)
    instance_id: Mapped[int] = mapped_column(Integer, ForeignKey('instance.id'), primary_key=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user: Mapped['TypedUser'] = relationship('TypedUser')
    instance: Mapped['TypedInstance'] = relationship('TypedInstance')
    
    def __repr__(self) -> str:
        return f'<InstanceBlock user={self.user_id} blocks instance={self.instance_id}>'


class TypedCommunityBan(db.Model):
    """Community ban with full typing"""
    __tablename__ = 'community_ban'
    
    # Primary keys
    user_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), primary_key=True)
    community_id: Mapped[CommunityId] = mapped_column(Integer, ForeignKey('community.id'), primary_key=True)
    
    # Ban details
    banned_by: Mapped[Optional[UserId]] = mapped_column(Integer, ForeignKey('user.id'))
    reason: Mapped[Optional[str]] = mapped_column(String(256))
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    banned_until: Mapped[Optional[datetime]] = mapped_column(DateTime)  # None = permanent
    
    # Relationships
    user: Mapped['TypedUser'] = relationship('TypedUser', foreign_keys=[user_id])
    community: Mapped['TypedCommunity'] = relationship('TypedCommunity')
    banner: Mapped[Optional['TypedUser']] = relationship('TypedUser', foreign_keys=[banned_by])
    
    @property
    def is_active(self) -> bool:
        """Check if ban is currently active"""
        if self.banned_until is None:
            return True  # Permanent ban
        return datetime.utcnow() < self.banned_until
    
    def __repr__(self) -> str:
        return f'<CommunityBan user={self.user_id} community={self.community_id}>'