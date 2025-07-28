"""Instance and federation-related models for PeachPie"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, Text, DateTime, ForeignKey, Index, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.hybrid import hybrid_property

from app import db
from app.models.base import TimestampMixin, InstanceId, UserId, CommunityId, DomainId
from app.utils import domain_from_url

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.community import Community
    from app.models.content import Post


class Instance(TimestampMixin, db.Model):
    """Remote instance information"""
    __tablename__ = 'instance'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain: Mapped[str] = mapped_column(String(256), index=True, unique=True, nullable=False)
    
    # ActivityPub endpoints
    inbox: Mapped[Optional[str]] = mapped_column(String(256))
    shared_inbox: Mapped[Optional[str]] = mapped_column(String(256))
    outbox: Mapped[Optional[str]] = mapped_column(String(256))
    
    # Instance details
    software: Mapped[Optional[str]] = mapped_column(String(50))
    version: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Status
    online: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    gone_forever: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dormant: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Trust and reputation
    trust_level: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    
    # Nodeinfo
    nodeinfo_href: Mapped[Optional[str]] = mapped_column(String(256))
    
    # Stats
    post_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    user_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Last contact
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_successful_contact: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_failed_contact: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Failure tracking
    failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    most_recent_attempt: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Relationships
    users = relationship('User', back_populates='instance', lazy='dynamic')
    communities = relationship('Community', back_populates='instance', lazy='dynamic')
    instance_roles = relationship('InstanceRole', back_populates='instance', lazy='dynamic',
                                cascade='all, delete-orphan')
    banned_instances = relationship('BannedInstances', uselist=False, back_populates='instance')
    allowed_instances = relationship('AllowedInstances', uselist=False, back_populates='instance')
    blocks = relationship('InstanceBlock', back_populates='instance', lazy='dynamic')
    bans = relationship('InstanceBan', back_populates='instance', lazy='dynamic')
    federation_errors = relationship('FederationError', back_populates='instance', lazy='dynamic',
                                   cascade='all, delete-orphan')
    
    @hybrid_property
    def is_online(self) -> bool:
        """Check if instance is currently online"""
        return self.online and not self.gone_forever
    
    @hybrid_property
    def is_trusted(self) -> bool:
        """Check if instance is trusted"""
        return self.trust_level > 0.5
    
    def record_success(self) -> None:
        """Record successful contact"""
        self.last_seen = datetime.utcnow()
        self.last_successful_contact = datetime.utcnow()
        self.failures = 0
        self.online = True
    
    def record_failure(self) -> None:
        """Record failed contact"""
        self.last_failed_contact = datetime.utcnow()
        self.failures += 1
        self.most_recent_attempt = datetime.utcnow()
        
        # Mark offline after too many failures
        if self.failures > 10:
            self.online = False
        
        # Mark gone forever after extended failures
        if self.failures > 100:
            self.gone_forever = True
    
    def __repr__(self) -> str:
        return f'<Instance {self.domain}>'


class InstanceRole(db.Model):
    """User roles for instance administration"""
    __tablename__ = 'instance_role'
    __table_args__ = {'extend_existing': True}
    
    # Primary keys
    instance_id: Mapped[InstanceId] = mapped_column(
        Integer, ForeignKey('instance.id'), primary_key=True
    )
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), primary_key=True
    )
    
    # Role
    role: Mapped[str] = mapped_column(String(50), default='admin', nullable=False)
    
    # Relationships
    instance = relationship('Instance', back_populates='instance_roles')
    user = relationship('User', back_populates='instance_roles')


class BannedInstances(TimestampMixin, db.Model):
    """Banned instances list"""
    __tablename__ = 'banned_instances'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Ban details
    domain: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(256))
    initiator: Mapped[Optional[str]] = mapped_column(String(256))
    
    # Instance link
    instance_id: Mapped[Optional[InstanceId]] = mapped_column(
        Integer, ForeignKey('instance.id'), unique=True
    )
    
    # Relationships
    instance = relationship('Instance', back_populates='banned_instances')


class AllowedInstances(TimestampMixin, db.Model):
    """Allowed instances (for allowlist mode)"""
    __tablename__ = 'allowed_instances'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Instance details
    domain: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    
    # Instance link
    instance_id: Mapped[Optional[InstanceId]] = mapped_column(
        Integer, ForeignKey('instance.id'), unique=True
    )
    
    # Relationships
    instance = relationship('Instance', back_populates='allowed_instances')


class InstanceBlock(TimestampMixin, db.Model):
    """User blocks of instances"""
    __tablename__ = 'instance_block'
    __table_args__ = {'extend_existing': True}
    
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), primary_key=True
    )
    instance_id: Mapped[InstanceId] = mapped_column(
        Integer, ForeignKey('instance.id'), primary_key=True
    )
    
    # Relationships
    user = relationship('User')
    instance = relationship('Instance', back_populates='blocks')


class InstanceBan(TimestampMixin, db.Model):
    """Instance-wide user bans"""
    __tablename__ = 'instance_ban'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False, index=True
    )
    instance_id: Mapped[InstanceId] = mapped_column(
        Integer, ForeignKey('instance.id'), nullable=False, index=True
    )
    
    # Relationships
    user = relationship('User')
    instance = relationship('Instance', back_populates='bans')


class Domain(db.Model):
    """Domain tracking for link posts"""
    __tablename__ = 'domain'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    name: Mapped[str] = mapped_column(String(256), index=True, unique=True, nullable=False)
    banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relationships
    posts = relationship('Post', back_populates='domain', lazy='dynamic')
    blocks = relationship('DomainBlock', back_populates='domain', lazy='dynamic',
                        cascade='all, delete-orphan')


class DomainBlock(TimestampMixin, db.Model):
    """User blocks of domains"""
    __tablename__ = 'domain_block'
    __table_args__ = {'extend_existing': True}
    
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), primary_key=True
    )
    domain_id: Mapped[DomainId] = mapped_column(
        Integer, ForeignKey('domain.id'), primary_key=True
    )
    
    # Relationships
    user = relationship('User')
    domain = relationship('Domain', back_populates='blocks')


class DefederationSubscription(TimestampMixin, db.Model):
    """Defederation subscription lists"""
    __tablename__ = 'defederation_subscription'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Subscription details
    node_id: Mapped[Optional[int]] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Tracking
    last_update: Mapped[Optional[datetime]] = mapped_column(DateTime)


class FederationError(TimestampMixin, db.Model):
    """Federation error tracking"""
    __tablename__ = 'federation_error'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    instance_id: Mapped[InstanceId] = mapped_column(
        Integer, ForeignKey('instance.id'), nullable=False, index=True
    )
    
    # Error details
    error_type: Mapped[str] = mapped_column(String(50), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Activity context
    activity_id: Mapped[Optional[str]] = mapped_column(String(256))
    activity_type: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Response details
    status_code: Mapped[Optional[int]] = mapped_column(Integer)
    response_body: Mapped[Optional[str]] = mapped_column(Text)
    
    # Tracking
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relationships
    instance = relationship('Instance', back_populates='federation_errors')