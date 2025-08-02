"""Notification and messaging models for PeachPie"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app import db
from app.models.base import TimestampMixin, UserId, PostId, ReplyId

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.content import Post, PostReply


# Association table for many-to-many conversation members
# This is for backward compatibility with existing code
conversation_member = db.Table('conversation_member',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('conversation_id', db.Integer, db.ForeignKey('conversation.id')),
    db.PrimaryKeyConstraint('user_id', 'conversation_id'),
    extend_existing=True
)


class Notification(TimestampMixin, db.Model):
    """User notifications"""
    __tablename__ = 'notification'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Recipient
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False, index=True
    )
    
    # Notification details
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text)
    
    # Type and context
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'reply', 'mention', 'follow', etc.
    
    # Related objects (polymorphic)
    author_id: Mapped[Optional[UserId]] = mapped_column(Integer, ForeignKey('user.id'))
    post_id: Mapped[Optional[PostId]] = mapped_column(Integer, ForeignKey('post.id'))
    post_reply_id: Mapped[Optional[ReplyId]] = mapped_column(Integer, ForeignKey('post_reply.id'))
    
    # Status
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # URL for action
    url: Mapped[Optional[str]] = mapped_column(String(512))
    
    # Relationships
    user = relationship('User', foreign_keys=[user_id], back_populates='notifications')
    author = relationship('User', foreign_keys=[author_id])
    post = relationship('Post')
    post_reply = relationship('PostReply')
    
    def mark_read(self) -> None:
        """Mark notification as read"""
        self.read = True
        self.read_at = datetime.now(timezone.utc)


class NotificationSubscription(TimestampMixin, db.Model):
    """Push notification subscriptions"""
    __tablename__ = 'notification_subscription'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # User
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False, index=True
    )
    
    # Subscription details
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(256), nullable=False)
    auth: Mapped[str] = mapped_column(String(256), nullable=False)
    
    # Device info
    device_name: Mapped[Optional[str]] = mapped_column(String(256))
    
    # Status
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Relationships
    user = relationship('User', back_populates='notification_subscriptions')


class Conversation(TimestampMixin, db.Model):
    """Private conversations between users"""
    __tablename__ = 'conversation'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Participants
    user1_id: Mapped[UserId] = mapped_column(
        Integer, 
        ForeignKey('user.id', name='fk_conversation_user1_id'), 
        nullable=False, 
        index=True
    )
    user2_id: Mapped[UserId] = mapped_column(
        Integer, 
        ForeignKey('user.id', name='fk_conversation_user2_id'), 
        nullable=False, 
        index=True
    )
    
    # Status
    user1_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user2_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Last activity
    last_message_id: Mapped[Optional[int]] = mapped_column(
        Integer, 
        ForeignKey('chat_message.id', name='fk_conversation_last_message_id')
    )
    
    # Relationships
    user1 = relationship('User', foreign_keys=[user1_id])
    user2 = relationship('User', foreign_keys=[user2_id])
    messages = relationship('ChatMessage', foreign_keys='ChatMessage.conversation_id',
                          back_populates='conversation', lazy='dynamic',
                          cascade='all, delete-orphan')
    
    def get_other_user(self, user_id: int) -> Optional['User']:
        """Get the other participant in conversation"""
        if self.user1_id == user_id:
            return self.user2
        elif self.user2_id == user_id:
            return self.user1
        return None
    
    def is_participant(self, user_id: int) -> bool:
        """Check if user is participant"""
        return user_id in (self.user1_id, self.user2_id)


class ChatMessage(TimestampMixin, db.Model):
    """Messages in private conversations"""
    __tablename__ = 'chat_message'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Message details
    conversation_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey('conversation.id', name='fk_chat_message_conversation_id'), 
        nullable=False, 
        index=True
    )
    sender_id: Mapped[UserId] = mapped_column(
        Integer, 
        ForeignKey('user.id', name='fk_chat_message_sender_id'), 
        nullable=False
    )
    
    # Content
    body: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Status
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Deletion
    sender_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recipient_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relationships
    conversation = relationship('Conversation', foreign_keys=[conversation_id], back_populates='messages')
    sender = relationship('User')
    
    def mark_read(self) -> None:
        """Mark message as read"""
        self.read = True
        self.read_at = datetime.now(timezone.utc)