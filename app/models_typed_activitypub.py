"""Typed ActivityPub models for PyFedi using Python 3.13 features"""
from __future__ import annotations
from typing import Optional, Dict, Any, Literal, TYPE_CHECKING
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, Text, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app import db
from app.federation.types import ActivityId, ActorUrl, Domain

if TYPE_CHECKING:
    from app.models_typed import TypedUser, TypedCommunity, TypedInstance

# Type aliases
type LogId = int
type InstanceId = int


class TypedActivityPubLog(db.Model):
    """ActivityPub logging model with full typing"""
    __tablename__ = 'activity_pub_log'
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Activity details
    direction: Mapped[str] = mapped_column(String(3), nullable=False)  # 'in' or 'out'
    activity_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    activity_type: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    result: Mapped[Optional[str]] = mapped_column(String(10))  # 'success', 'failure', etc.
    activity_json: Mapped[Optional[str]] = mapped_column(Text)
    
    # Instance tracking
    instance_id: Mapped[Optional[InstanceId]] = mapped_column(Integer, ForeignKey('instance.id'), index=True)
    
    # Error tracking
    exception_message: Mapped[Optional[str]] = mapped_column(Text)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relationships
    instance: Mapped[Optional['TypedInstance']] = relationship('TypedInstance')
    
    def __repr__(self) -> str:
        return f'<ActivityPubLog {self.id}: {self.direction} {self.activity_type}>'


class TypedActivityPubRequestLog(db.Model):
    """ActivityPub request logging with full typing"""
    __tablename__ = 'activity_pub_request_log'
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Request details
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    headers: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    body: Mapped[Optional[str]] = mapped_column(Text)
    
    # Response details
    status_code: Mapped[Optional[int]] = mapped_column(Integer)
    response_headers: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    response_body: Mapped[Optional[str]] = mapped_column(Text)
    
    # Timing
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    def __repr__(self) -> str:
        return f'<ActivityPubRequestLog {self.id}: {self.method} {self.url}>'


class TypedCommunityJoinRequest(db.Model):
    """Pending community join request with full typing"""
    __tablename__ = 'community_join_request'
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Request details
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('user.id'), index=True, nullable=False)
    community_id: Mapped[int] = mapped_column(Integer, ForeignKey('community.id'), index=True, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user: Mapped['TypedUser'] = relationship('TypedUser')
    community: Mapped['TypedCommunity'] = relationship('TypedCommunity')
    
    def __repr__(self) -> str:
        return f'<CommunityJoinRequest user={self.user_id} community={self.community_id}>'


class TypedInstanceRole(db.Model):
    """Instance role assignment with full typing"""
    __tablename__ = 'instance_role'
    
    # Primary keys
    instance_id: Mapped[InstanceId] = mapped_column(Integer, ForeignKey('instance.id'), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('user.id'), primary_key=True)
    
    # Role
    role: Mapped[str] = mapped_column(String(50), default='admin', nullable=False)
    
    # Relationships
    user: Mapped['TypedUser'] = relationship('TypedUser', lazy='joined')
    instance: Mapped['TypedInstance'] = relationship('TypedInstance')
    
    def __repr__(self) -> str:
        return f'<InstanceRole user={self.user_id} instance={self.instance_id} role={self.role}>'


class TypedBannedInstances(db.Model):
    """Banned instances with full typing"""
    __tablename__ = 'banned_instances'
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Ban details
    domain: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(256))
    initiator: Mapped[Optional[str]] = mapped_column(String(256))
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Defederation subscription
    subscription_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('defederation_subscription.id'), index=True)
    
    @classmethod
    def is_banned(cls, domain: str) -> bool:
        """Check if a domain is banned"""
        return cls.query.filter_by(domain=domain).first() is not None
    
    def __repr__(self) -> str:
        return f'<BannedInstances {self.domain}>'


class TypedAllowedInstances(db.Model):
    """Allowed instances (allowlist mode) with full typing"""
    __tablename__ = 'allowed_instances'
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Instance details
    domain: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    @classmethod
    def is_allowed(cls, domain: str) -> bool:
        """Check if a domain is allowed"""
        return cls.query.filter_by(domain=domain).first() is not None
    
    def __repr__(self) -> str:
        return f'<AllowedInstances {self.domain}>'


class TypedActivityBatch(db.Model):
    """Batched activities for efficient sending with full typing"""
    __tablename__ = 'activity_batch'
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Batch details
    instance_id: Mapped[InstanceId] = mapped_column(Integer, ForeignKey('instance.id'), index=True, nullable=False)
    community_id: Mapped[int] = mapped_column(Integer, ForeignKey('community.id'), index=True, nullable=False)
    
    # Activity payload
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    instance: Mapped['TypedInstance'] = relationship('TypedInstance')
    community: Mapped['TypedCommunity'] = relationship('TypedCommunity')
    
    def __repr__(self) -> str:
        return f'<ActivityBatch {self.id} to {self.instance_id}>'


class TypedSendQueue(db.Model):
    """Queue for outgoing activities with full typing"""
    __tablename__ = 'send_queue'
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Activity details
    activity_id: Mapped[str] = mapped_column(String(256), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    activity_json: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_inbox: Mapped[str] = mapped_column(String(256), nullable=False)
    
    # Sender details
    private_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_id: Mapped[str] = mapped_column(String(256), nullable=False)
    
    # Status
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Indexes
    __table_args__ = (
        Index('idx_send_queue_next_attempt', 'next_attempt_at'),
    )
    
    def increment_attempts(self) -> None:
        """Increment attempts and set next attempt time"""
        self.attempts += 1
        self.last_attempt_at = datetime.utcnow()
        
        # Exponential backoff: 1min, 2min, 4min, 8min, 16min, 32min, 1hr, 2hr, 4hr, 8hr...
        backoff_minutes = min(2 ** (self.attempts - 1), 480)  # Max 8 hours
        self.next_attempt_at = datetime.utcnow() + timedelta(minutes=backoff_minutes)
    
    def __repr__(self) -> str:
        return f'<SendQueue {self.id}: {self.activity_type} to {self.recipient_inbox}>'