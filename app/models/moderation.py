"""Moderation and reporting models for PeachPie"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app import db
from app.models.base import TimestampMixin, UserId, CommunityId, PostId, ReplyId

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.community import Community
    from app.models.content import Post, PostReply


class Report(TimestampMixin, db.Model):
    """User reports of content or users"""
    __tablename__ = 'report'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Reporter
    reporter_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False, index=True
    )
    
    # What is being reported (polymorphic)
    suspect_user_id: Mapped[Optional[UserId]] = mapped_column(Integer, ForeignKey('user.id'), index=True)
    suspect_post_id: Mapped[Optional[PostId]] = mapped_column(Integer, ForeignKey('post.id'), index=True)
    suspect_post_reply_id: Mapped[Optional[ReplyId]] = mapped_column(Integer, ForeignKey('post_reply.id'), index=True)
    suspect_community_id: Mapped[Optional[CommunityId]] = mapped_column(Integer, ForeignKey('community.id'), index=True)
    
    # Report details
    reason: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Status
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0=open, 1=in progress, 2=resolved, 3=rejected
    
    # Resolution
    resolved_by_id: Mapped[Optional[UserId]] = mapped_column(Integer, ForeignKey('user.id'))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # Relationships
    reporter = relationship('User', foreign_keys=[reporter_id], back_populates='reports_made')
    suspect_user = relationship('User', foreign_keys=[suspect_user_id])
    suspect_post = relationship('Post', back_populates='reports')
    suspect_post_reply = relationship('PostReply', back_populates='reports')
    suspect_community = relationship('Community')
    resolved_by = relationship('User', foreign_keys=[resolved_by_id])
    
    @property
    def is_open(self) -> bool:
        """Check if report is still open"""
        return self.status == 0
    
    @property
    def suspect_type(self) -> str:
        """Get type of suspect"""
        if self.suspect_user_id:
            return 'user'
        elif self.suspect_post_id:
            return 'post'
        elif self.suspect_post_reply_id:
            return 'post_reply'
        elif self.suspect_community_id:
            return 'community'
        return 'unknown'


class ModLog(TimestampMixin, db.Model):
    """Moderation action log"""
    __tablename__ = 'mod_log'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Who performed the action
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False, index=True
    )
    
    # What action was taken
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # 'ban_user', 'remove_post', etc.
    
    # Target (polymorphic)
    target_user_id: Mapped[Optional[UserId]] = mapped_column(Integer, ForeignKey('user.id'))
    target_post_id: Mapped[Optional[PostId]] = mapped_column(Integer, ForeignKey('post.id'))
    target_post_reply_id: Mapped[Optional[ReplyId]] = mapped_column(Integer, ForeignKey('post_reply.id'))
    target_community_id: Mapped[Optional[CommunityId]] = mapped_column(Integer, ForeignKey('community.id'))
    
    # Context
    community_id: Mapped[Optional[CommunityId]] = mapped_column(Integer, ForeignKey('community.id'), index=True)
    
    # Details
    reason: Mapped[Optional[str]] = mapped_column(Text)
    note: Mapped[Optional[str]] = mapped_column(Text)
    
    # Relationships
    user = relationship('User', foreign_keys=[user_id], back_populates='mod_actions')
    target_user = relationship('User', foreign_keys=[target_user_id])
    target_post = relationship('Post')
    target_post_reply = relationship('PostReply')
    target_community = relationship('Community', foreign_keys=[target_community_id])
    community = relationship('Community', foreign_keys=[community_id])


class IpBan(TimestampMixin, db.Model):
    """IP address bans"""
    __tablename__ = 'ip_ban'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Ban details
    ip_address: Mapped[str] = mapped_column(String(45), index=True, nullable=False)  # Supports IPv6
    reason: Mapped[Optional[str]] = mapped_column(String(256))
    
    # Who banned
    banned_by_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), nullable=False)
    
    # Duration
    permanent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ban_until: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Relationships
    banned_by = relationship('User')
    
    @property
    def is_active(self) -> bool:
        """Check if ban is currently active"""
        if self.permanent:
            return True
        if self.ban_until:
            return datetime.utcnow() < self.ban_until
        return True


class Filter(TimestampMixin, db.Model):
    """User content filters"""
    __tablename__ = 'filter'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Filter ownership
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False, index=True
    )
    
    # Filter settings
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    filter_text: Mapped[str] = mapped_column(Text, nullable=False)
    
    # What to filter
    filter_posts: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    filter_replies: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # How to filter
    hide: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Scope
    community_id: Mapped[Optional[CommunityId]] = mapped_column(Integer, ForeignKey('community.id'))
    
    # Active status
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Relationships
    user = relationship('User')
    community = relationship('Community')


class BlockedImage(TimestampMixin, db.Model):
    """Blocked images by hash"""
    __tablename__ = 'blocked_image'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Image identification
    hash: Mapped[str] = mapped_column(String(128), index=True, unique=True, nullable=False)
    
    # Blocking details
    reason: Mapped[Optional[str]] = mapped_column(String(256))
    blocked_by_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), nullable=False)
    
    # Severity
    severity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1=spam, 2=nsfw, 3=illegal
    
    # Relationships
    blocked_by = relationship('User')