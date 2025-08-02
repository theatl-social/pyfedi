"""User-related models for PeachPie"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime, date, timezone
from sqlalchemy import String, Integer, Boolean, Text, DateTime, ForeignKey, Index, Date, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from sqlalchemy.ext.hybrid import hybrid_property
from flask import current_app, g
from flask_login import UserMixin, current_user
import pyotp
import jwt
from time import time
from email_validator import validate_email, EmailNotValidError
from werkzeug.security import generate_password_hash, check_password_hash

from app import db, cache
from app.models.base import TimestampMixin, ActivityPubMixin, LanguageMixin, UserId, CommunityId, InstanceId
from app.utils import markdown_to_html, html_to_text, remove_tracking_from_link, utcnow

if TYPE_CHECKING:
    from app.models.community import Community, CommunityMember, CommunityBan
    from app.models.content import Post, PostReply, PostVote, PostReplyVote
    from app.models.instance import Instance, InstanceRole
    from app.models.moderation import Report, ModLog


# Association table for read posts
read_posts = db.Table('read_posts',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), index=True),
    db.Column('read_post_id', db.Integer, db.ForeignKey('post.id'), index=True),
    db.Column('interacted_at', db.DateTime, index=True, default=utcnow),
    extend_existing=True
)


class User(UserMixin, db.Model):
    """User model with full typing support"""
    __tablename__ = 'user'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    alt_user_name: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    
    # Authentication
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    suspended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ignore_bots: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Profile
    title: Mapped[Optional[str]] = mapped_column(String(255))
    about: Mapped[Optional[str]] = mapped_column(Text)  # markdown
    about_html: Mapped[Optional[str]] = mapped_column(Text)  # rendered HTML
    avatar_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('file.id'))
    cover_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('file.id'))
    
    # Settings
    default_sort: Mapped[str] = mapped_column(String(25), default='hot', nullable=False)
    default_filter: Mapped[str] = mapped_column(String(25), default='all', nullable=False)
    theme: Mapped[str] = mapped_column(String(20), default='system', nullable=False)
    indexable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    searchable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Privacy settings
    hide_nsfw: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hide_nsfl: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hide_read_posts: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    receive_message_mode: Mapped[str] = mapped_column(String(20), default='Closed', nullable=False)
    
    # Scoring
    post_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    post_reply_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reputation: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    attitude: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    
    # Security
    password_hash: Mapped[Optional[str]] = mapped_column(String(256))
    password_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Status fields
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    ban_state: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0=not banned, 1=banned
    
    # TOTP
    totp_secret: Mapped[Optional[str]] = mapped_column(String(64))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    totp_recovery_codes: Mapped[Optional[str]] = mapped_column(Text)
    
    # ActivityPub columns (User doesn't have ap_outbox_url unlike other models)
    ap_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    ap_profile_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, unique=True)
    ap_public_url: Mapped[Optional[str]] = mapped_column(String(255))
    ap_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ap_followers_url: Mapped[Optional[str]] = mapped_column(String(255))
    ap_inbox_url: Mapped[Optional[str]] = mapped_column(String(255))
    ap_domain: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    ap_preferred_username: Mapped[Optional[str]] = mapped_column(String(255))
    ap_manually_approves_followers: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ap_deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    private_key: Mapped[Optional[str]] = mapped_column(Text)
    public_key: Mapped[Optional[str]] = mapped_column(Text)
    instance_id: Mapped[Optional[InstanceId]] = mapped_column(Integer, ForeignKey('instance.id'), index=True)
    
    
    # Bot flags
    bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Language preferences
    interface_language: Mapped[Optional[str]] = mapped_column(String(10))
    language_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('language.id'))
    
    # Role
    role_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('role.id'))
    
    # Relationships
    avatar = relationship('File', foreign_keys=[avatar_id], back_populates='avatar_users')
    cover = relationship('File', foreign_keys=[cover_id], back_populates='cover_users')
    instance = relationship('Instance', back_populates='users')
    role = relationship('Role')
    
    # Activities
    posts = relationship('Post', back_populates='author', lazy='dynamic',
                        cascade='all, delete-orphan')
    post_replies = relationship('PostReply', back_populates='author', lazy='dynamic',
                               cascade='all, delete-orphan')
    post_votes = relationship('PostVote', back_populates='user', lazy='dynamic',
                             cascade='all, delete-orphan')
    post_reply_votes = relationship('PostReplyVote', back_populates='user', lazy='dynamic',
                                   cascade='all, delete-orphan')
    
    # Communities
    community_memberships = relationship('CommunityMember', back_populates='user', lazy='dynamic',
                                       cascade='all, delete-orphan')
    community_bans = relationship('CommunityBan', foreign_keys='CommunityBan.user_id',
                                 back_populates='user', lazy='dynamic',
                                 cascade='all, delete-orphan')
    created_communities = relationship('Community', foreign_keys='Community.user_id',
                                      back_populates='creator', lazy='dynamic')
    
    # Social
    followers = relationship('UserFollower', foreign_keys='UserFollower.followed_id',
                           back_populates='followed', lazy='dynamic')
    following = relationship('UserFollower', foreign_keys='UserFollower.follower_id',
                           back_populates='follower', lazy='dynamic')
    follow_requests_sent = relationship('UserFollowRequest', foreign_keys='UserFollowRequest.follower_id',
                                      back_populates='follower', lazy='dynamic')
    follow_requests_received = relationship('UserFollowRequest', foreign_keys='UserFollowRequest.followed_id',
                                          back_populates='followed', lazy='dynamic')
    
    # Moderation
    reports_made = relationship('Report', foreign_keys='Report.reporter_id',
                              back_populates='reporter', lazy='dynamic')
    mod_actions = relationship('ModLog', foreign_keys='ModLog.user_id', back_populates='user', lazy='dynamic')
    instance_roles = relationship('InstanceRole', back_populates='user', lazy='dynamic')
    
    # Notifications
    notifications = relationship('Notification', back_populates='user', lazy='dynamic',
                               cascade='all, delete-orphan', foreign_keys='Notification.user_id')
    notification_subscriptions = relationship('NotificationSubscription', back_populates='user',
                                            lazy='dynamic', cascade='all, delete-orphan')
    
    # Other
    bookmarked_posts = relationship('PostBookmark', back_populates='user', lazy='dynamic',
                                  cascade='all, delete-orphan')
    bookmarked_replies = relationship('PostReplyBookmark', back_populates='user', lazy='dynamic',
                                    cascade='all, delete-orphan')
    user_notes = relationship('UserNote', foreign_keys='UserNote.target_id',
                            back_populates='target', lazy='dynamic')
    user_blocks = relationship('UserBlock', foreign_keys='UserBlock.blocker_id',
                             back_populates='blocker', lazy='dynamic')
    blocked_by = relationship('UserBlock', foreign_keys='UserBlock.blocked_id',
                            back_populates='blocked', lazy='dynamic')
    
    # Validations
    @validates('email')
    def validate_email_field(self, key: str, value: str) -> str:
        """Validate email format"""
        if value:
            try:
                validation = validate_email(value, check_deliverability=False)
                return validation.email
            except EmailNotValidError:
                raise ValueError('Invalid email address')
        return value
    
    @validates('user_name')
    def validate_username(self, key: str, value: str) -> str:
        """Validate username"""
        if not value or len(value) < 3:
            raise ValueError('Username must be at least 3 characters')
        if len(value) > 255:
            raise ValueError('Username too long')
        # Additional validation rules can be added here
        return value.strip()
    
    # Methods
    def get_id(self) -> str:
        """Required for Flask-Login"""
        return str(self.id)
    
    @property
    def is_authenticated(self) -> bool:
        """Required for Flask-Login"""
        return True
    
    @property
    def is_active(self) -> bool:
        """Check if user account is active"""
        return not self.banned and not self.suspended
    
    @property
    def is_anonymous(self) -> bool:
        """Required for Flask-Login"""
        return False
    
    def can_vote(self, min_reputation: float = 0.0) -> bool:
        """Check if user can vote"""
        if self.banned or self.suspended:
            return False
        return self.reputation >= min_reputation
    
    def can_create_post(self, community: 'Community') -> bool:
        """Check if user can create posts in community"""
        if self.banned or self.suspended:
            return False
        if community.restricted_to_mods:
            return self.is_moderator(community)
        if community.local_only and self.is_remote:
            return False
        return not self.is_banned_from(community)
    
    def can_create_reply(self, post: 'Post') -> bool:
        """Check if user can reply to post"""
        if self.banned or self.suspended:
            return False
        if not post.comments_enabled:
            return False
        return not self.is_banned_from(post.community)
    
    def is_moderator(self, community: 'Community') -> bool:
        """Check if user is moderator of community"""
        if self.is_admin():
            return True
        membership = self.community_memberships.filter_by(
            community_id=community.id,
            is_moderator=True
        ).first()
        return membership is not None
    
    def is_admin(self) -> bool:
        """Check if user is instance admin"""
        if current_app.config.get('ADMIN_USERS'):
            return self.user_name in current_app.config['ADMIN_USERS']
        # Check instance roles
        admin_role = self.instance_roles.filter_by(role='admin').first()
        return admin_role is not None
    
    def is_banned_from(self, community: 'Community') -> bool:
        """Check if user is banned from community"""
        ban = self.community_bans.filter_by(
            community_id=community.id,
            active=True
        ).first()
        return ban is not None
    
    def is_following(self, user: 'User') -> bool:
        """Check if following another user"""
        follow = self.following.filter_by(followed_id=user.id).first()
        return follow is not None
    
    def has_blocked(self, user: 'User') -> bool:
        """Check if this user has blocked another user"""
        block = self.user_blocks.filter_by(blocked_id=user.id).first()
        return block is not None
    
    def is_blocked_by(self, user: 'User') -> bool:
        """Check if this user is blocked by another user"""
        block = self.blocked_by.filter_by(blocker_id=user.id).first()
        return block is not None
    
    def can_message(self, recipient: 'User') -> bool:
        """Check if user can send message to recipient"""
        if self.banned or self.suspended:
            return False
        if recipient.receive_message_mode == 'Closed':
            return False
        if recipient.receive_message_mode == 'Followers':
            return recipient.is_following(self)
        return True  # 'Open' mode
    
    def generate_totp_uri(self) -> str:
        """Generate TOTP URI for QR code"""
        if not self.totp_secret:
            self.totp_secret = pyotp.random_base32()
        
        return pyotp.totp.TOTP(self.totp_secret).provisioning_uri(
            name=self.email,
            issuer_name='PeachPie'
        )
    
    def verify_totp(self, token: str) -> bool:
        """Verify TOTP token"""
        if not self.totp_enabled or not self.totp_secret:
            return False
        
        totp = pyotp.TOTP(self.totp_secret)
        return totp.verify(token, valid_window=1)
    
    def set_password(self, password: str) -> None:
        """Hash and set the user's password"""
        self.password_hash = generate_password_hash(password)
        self.password_updated_at = datetime.now(timezone.utc)
    
    def check_password(self, password: str) -> bool:
        """Check if the provided password matches the hash"""
        if not self.password_hash:
            return False
        try:
            return check_password_hash(self.password_hash, password)
        except Exception:
            return False
    
    def update_last_seen(self) -> None:
        """Update last seen timestamp"""
        self.last_seen = datetime.now(timezone.utc)
    
    def encode_jwt_token(self) -> str:
        """Generate JWT token for API authentication"""
        payload = {
            'sub': str(self.id),
            'iss': current_app.config['SERVER_NAME'],
            'iat': int(time())
        }
        return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')
    
    @property
    def is_local(self) -> bool:
        """Check if this is a local user"""
        return self.ap_id is None or self.ap_profile_id is None
    
    @property
    def is_remote(self) -> bool:
        """Check if this is a remote user"""
        return not self.is_local
    
    def __repr__(self) -> str:
        return f'<User {self.user_name}>'


class UserFollower(TimestampMixin, db.Model):
    """User follow relationships"""
    __tablename__ = 'user_follower'
    __table_args__ = {'extend_existing': True}
    
    follower_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), primary_key=True
    )
    followed_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), primary_key=True
    )
    
    # Relationships
    follower = relationship('User', foreign_keys=[follower_id], back_populates='following')
    followed = relationship('User', foreign_keys=[followed_id], back_populates='followers')


class UserFollowRequest(TimestampMixin, db.Model):
    """Pending follow requests"""
    __tablename__ = 'user_follow_request'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    follower_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False, index=True
    )
    followed_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False, index=True
    )
    
    # Relationships
    follower = relationship('User', foreign_keys=[follower_id], back_populates='follow_requests_sent')
    followed = relationship('User', foreign_keys=[followed_id], back_populates='follow_requests_received')


class UserBlock(TimestampMixin, db.Model):
    """User block relationships"""
    __tablename__ = 'user_block'
    __table_args__ = {'extend_existing': True}
    
    blocker_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), primary_key=True
    )
    blocked_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), primary_key=True
    )
    
    # Relationships
    blocker = relationship('User', foreign_keys=[blocker_id], back_populates='user_blocks')
    blocked = relationship('User', foreign_keys=[blocked_id], back_populates='blocked_by')


class UserNote(TimestampMixin, db.Model):
    """Private notes about users"""
    __tablename__ = 'user_note'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False, index=True
    )
    target_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False, index=True
    )
    note: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Relationships
    author = relationship('User', foreign_keys=[author_id])
    target = relationship('User', foreign_keys=[target_id], back_populates='user_notes')


class UserRegistration(TimestampMixin, db.Model):
    """Pending user registrations"""
    __tablename__ = 'user_registration'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    
    # Application details
    answer: Mapped[Optional[str]] = mapped_column(Text)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    denied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Verification
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_token: Mapped[Optional[str]] = mapped_column(String(256))
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Tracking
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(512))


class UserExtraField(db.Model):
    """Custom user profile fields"""
    __tablename__ = 'user_extra_field'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Relationships
    user = relationship('User')


class Passkey(TimestampMixin, db.Model):
    """WebAuthn passkeys for passwordless login"""
    __tablename__ = 'passkey'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False, index=True
    )
    
    # WebAuthn data
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    credential_id: Mapped[bytes] = mapped_column(db.LargeBinary, nullable=False, unique=True)
    public_key: Mapped[bytes] = mapped_column(db.LargeBinary, nullable=False)
    sign_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Device info
    device_type: Mapped[Optional[str]] = mapped_column(String(50))
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Relationships
    user = relationship('User')


class UserFlair(db.Model):
    """User flair/badges"""
    __tablename__ = 'user_flair'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), nullable=False, index=True
    )
    flair: Mapped[str] = mapped_column(String(256), nullable=False)
    
    # Relationships
    user = relationship('User')