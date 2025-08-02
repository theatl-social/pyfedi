"""Miscellaneous models for PeachPie"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime, date
from sqlalchemy import String, Integer, Boolean, Text, DateTime, ForeignKey, Index, Float, JSON, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app import db
from app.models.base import TimestampMixin, UserId, CommunityId

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.community import Community


class Site(db.Model):
    """Site configuration and settings"""
    __tablename__ = 'site'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns (usually only one record with id=1)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Site details
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    icon_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('file.id'))
    sidebar: Mapped[Optional[str]] = mapped_column(Text)
    legal_information: Mapped[Optional[str]] = mapped_column(Text)
    
    # Features
    enable_downvotes: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enable_gif_reply_rep_decrease: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enable_chan_image_filter: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enable_this_comment_filter: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_local_image_posts: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    remote_image_cache_days: Mapped[Optional[int]] = mapped_column(Integer, default=30)
    enable_nsfw: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enable_nsfl: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    community_creation_admin_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reports_email_admins: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    application_question: Mapped[Optional[str]] = mapped_column(Text, default='')
    
    # Registration
    registration_mode: Mapped[str] = mapped_column(String(20), default='Closed', nullable=False)  # possible values: Open, RequireApplication, Closed
    
    # Default settings
    default_theme: Mapped[Optional[str]] = mapped_column(String(20), default='')
    default_filter: Mapped[Optional[str]] = mapped_column(String(20), default='')
    
    # Cryptographic keys
    public_key: Mapped[Optional[str]] = mapped_column(Text)
    private_key: Mapped[Optional[str]] = mapped_column(Text)
    
    # Block/allow lists
    allow_or_block_list: Mapped[Optional[int]] = mapped_column(Integer)  # 0=none, 1=allowlist, 2=blocklist
    allowlist: Mapped[Optional[str]] = mapped_column(Text)
    blocklist: Mapped[Optional[str]] = mapped_column(Text)
    
    # URLs and Contact
    tos_url: Mapped[Optional[str]] = mapped_column(String(256))
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), default='')
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    last_active: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Blocked content
    blocked_phrases: Mapped[Optional[str]] = mapped_column(Text, default='')  # discard incoming content with these phrases
    auto_decline_referrers: Mapped[Optional[str]] = mapped_column(Text, default='rdrama.net\nahrefs.com\nkiwifarms.sh')  # automatically decline registration requests if the referrer is one of these
    
    # Logging
    log_activitypub_json: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # About and appearance
    about: Mapped[Optional[str]] = mapped_column(Text, default='')
    logo: Mapped[Optional[str]] = mapped_column(String(40), default='')
    logo_180: Mapped[Optional[str]] = mapped_column(String(40), default='')
    logo_152: Mapped[Optional[str]] = mapped_column(String(40), default='')
    logo_32: Mapped[Optional[str]] = mapped_column(String(40), default='')
    logo_16: Mapped[Optional[str]] = mapped_column(String(40), default='')
    show_inoculation_block: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    additional_css: Mapped[Optional[str]] = mapped_column(Text)
    additional_js: Mapped[Optional[str]] = mapped_column(Text)
    
    # Instance settings
    private_instance: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    language_id: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Relationships
    icon = relationship('File')
    
    @classmethod
    def admins(cls) -> List['User']:
        """Get all admin users"""
        from app.models.user import User
        # Role is in the same file (misc.py)
        admin_role = Role.query.filter_by(name='Admin').first()
        if admin_role:
            return User.query.filter_by(role_id=admin_role.id, deleted=False, ban_state=0).all()
        return []


class Settings(db.Model):
    """Key-value settings storage"""
    __tablename__ = 'settings'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text)
    
    # Type hint for parsing
    type: Mapped[str] = mapped_column(String(20), default='string', nullable=False)  # 'string', 'int', 'bool', 'json'
    
    def get_value(self) -> Any:
        """Get typed value"""
        if not self.value:
            return None
        
        if self.type == 'int':
            return int(self.value)
        elif self.type == 'bool':
            return self.value.lower() in ('true', '1', 'yes', 'on')
        elif self.type == 'json':
            import json
            return json.loads(self.value)
        
        return self.value


class ActivityLog(TimestampMixin, db.Model):
    """User activity logging"""
    __tablename__ = 'activity_log'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Activity details
    user_id: Mapped[Optional[UserId]] = mapped_column(Integer, ForeignKey('user.id'), index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Target (polymorphic)
    target_type: Mapped[Optional[str]] = mapped_column(String(50))
    target_id: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Request info
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(512))
    
    # Extra data
    extra_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Relationships
    user = relationship('User')


class Feed(TimestampMixin, db.Model):
    """Custom user feeds"""
    __tablename__ = 'feed'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Feed details
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Owner
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False, index=True
    )
    
    # Privacy
    private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relationships
    user = relationship('User')
    items = relationship('FeedItem', back_populates='feed', lazy='dynamic',
                        cascade='all, delete-orphan')
    members = relationship('FeedMember', back_populates='feed', lazy='dynamic',
                          cascade='all, delete-orphan')
    join_requests = relationship('FeedJoinRequest', back_populates='feed', lazy='dynamic',
                               cascade='all, delete-orphan')


class FeedItem(TimestampMixin, db.Model):
    """Communities in a feed"""
    __tablename__ = 'feed_item'
    __table_args__ = {'extend_existing': True}
    
    # Primary keys
    feed_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('feed.id'), primary_key=True
    )
    community_id: Mapped[CommunityId] = mapped_column(
        Integer, ForeignKey('community.id'), primary_key=True
    )
    
    # Relationships
    feed = relationship('Feed', back_populates='items')
    community = relationship('Community')


class FeedMember(TimestampMixin, db.Model):
    """Feed membership for private feeds"""
    __tablename__ = 'feed_member'
    __table_args__ = {'extend_existing': True}
    
    # Primary keys
    feed_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('feed.id'), primary_key=True
    )
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), primary_key=True
    )
    
    # Permissions
    can_edit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relationships
    feed = relationship('Feed', back_populates='members')
    user = relationship('User')


class FeedJoinRequest(TimestampMixin, db.Model):
    """Join requests for private feeds"""
    __tablename__ = 'feed_join_request'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    feed_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('feed.id'), nullable=False, index=True
    )
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False, index=True
    )
    
    # Relationships
    feed = relationship('Feed', back_populates='join_requests')
    user = relationship('User')


class CmsPage(TimestampMixin, db.Model):
    """Content management system pages"""
    __tablename__ = 'cms_page'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Page details
    slug: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    
    # Content
    body: Mapped[str] = mapped_column(Text, nullable=False)  # markdown
    body_html: Mapped[str] = mapped_column(Text, nullable=False)  # rendered HTML
    
    # Meta
    meta_description: Mapped[Optional[str]] = mapped_column(String(512))
    
    # Status
    published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Author
    author_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), nullable=False)
    
    # Relationships
    author = relationship('User')


class Event(TimestampMixin, db.Model):
    """Calendar events"""
    __tablename__ = 'event'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Event details
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Timing
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Location
    location: Mapped[Optional[str]] = mapped_column(String(512))
    
    # Online event
    online: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    online_url: Mapped[Optional[str]] = mapped_column(String(512))
    
    # Organizer
    user_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), nullable=False)
    community_id: Mapped[Optional[CommunityId]] = mapped_column(Integer, ForeignKey('community.id'))
    
    # Relationships
    user = relationship('User')
    community = relationship('Community')


class Interest(db.Model):
    """User interests for recommendations"""
    __tablename__ = 'interest'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Interest details
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    
    def __repr__(self) -> str:
        return f'<Interest {self.name}>'


class Role(db.Model):
    """User roles for permissions"""
    __tablename__ = 'role'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Role details
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Relationships
    permissions = relationship('RolePermission', back_populates='role', lazy='dynamic',
                             cascade='all, delete-orphan')


class RolePermission(db.Model):
    """Permission assignments to roles"""
    __tablename__ = 'role_permission'
    __table_args__ = {'extend_existing': True}
    
    # Primary keys
    role_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('role.id'), primary_key=True
    )
    permission: Mapped[str] = mapped_column(String(50), primary_key=True)
    
    # Relationships
    role = relationship('Role', back_populates='permissions')