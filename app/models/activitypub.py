"""ActivityPub and federation models for PeachPie"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, Text, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app import db
from app.models.base import TimestampMixin, InstanceId, CommunityId, UserId, PostId

if TYPE_CHECKING:
    from app.models.instance import Instance
    from app.models.community import Community
    from app.models.user import User


class ActivityPubLog(TimestampMixin, db.Model):
    """ActivityPub activity logging"""
    __tablename__ = 'activity_pub_log'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Activity details
    direction: Mapped[str] = mapped_column(String(3), nullable=False)  # 'in' or 'out'
    activity_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    activity_type: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    result: Mapped[Optional[str]] = mapped_column(String(10))  # 'success', 'failure', etc.
    activity_json: Mapped[Optional[str]] = mapped_column(Text)
    
    # Instance tracking
    instance_id: Mapped[Optional[InstanceId]] = mapped_column(
        Integer, ForeignKey('instance.id'), index=True
    )
    
    # Error tracking
    exception_message: Mapped[Optional[str]] = mapped_column(Text)
    
    # Relationships
    instance = relationship('Instance')
    
    # Indexes
    __table_args__ = (
        Index('idx_activitypub_log_lookup', 'activity_id', 'direction'),
        {'extend_existing': True}
    )


class ActivityPubRequestLog(TimestampMixin, db.Model):
    """HTTP request logging for federation debugging"""
    __tablename__ = 'activity_pub_request_log' 
    __table_args__ = {'extend_existing': True}
    
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


# CommunityJoinRequest moved to community.py to avoid duplicate definition


class ActivityBatch(TimestampMixin, db.Model):
    """Batch tracking for efficient activity delivery"""
    __tablename__ = 'activity_batch'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Batch details
    instance_id: Mapped[InstanceId] = mapped_column(
        Integer, ForeignKey('instance.id'), index=True, nullable=False
    )
    community_id: Mapped[CommunityId] = mapped_column(
        Integer, ForeignKey('community.id'), index=True, nullable=False
    )
    
    # Processing status
    sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Relationships
    instance = relationship('Instance')
    community = relationship('Community')


class SendQueue(TimestampMixin, db.Model):
    """Queue for outgoing federation activities"""
    __tablename__ = 'send_queue'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Activity details
    activity_id: Mapped[str] = mapped_column(String(256), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    activity_json: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Target
    inbox_url: Mapped[str] = mapped_column(String(512), nullable=False)
    instance_id: Mapped[InstanceId] = mapped_column(
        Integer, ForeignKey('instance.id'), nullable=False, index=True
    )
    
    # Processing
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Error tracking
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    
    # Relationships
    instance = relationship('Instance')


class APRequestBody(db.Model):
    """Stores ActivityPub request bodies for debugging"""
    __tablename__ = 'ap_request_body'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Request data
    body: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Processing status
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class APRequestStatus(db.Model):
    """Tracks ActivityPub request processing status"""
    __tablename__ = 'ap_request_status'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    
    # Status
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # 'pending', 'processing', 'completed', 'failed'
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Error info
    error_message: Mapped[Optional[str]] = mapped_column(Text)