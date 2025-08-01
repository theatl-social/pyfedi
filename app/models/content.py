"""Content models (posts, replies, votes) for PeachPie"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, Text, DateTime, ForeignKey, Index, Float, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy_searchable import make_searchable
# from sqlalchemy_utils.types import TSVectorType  # TODO: Enable for PostgreSQL

from app import db, cache
from app.models.base import (
    TimestampMixin, SoftDeleteMixin, ScoreMixin, ActivityPubMixin, 
    LanguageMixin, NSFWMixin, PostReplyValidationError,
    UserId, CommunityId, PostId, ReplyId, DomainId
)
from app.utils import markdown_to_html, html_to_text, domain_from_url

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.community import Community
    from app.models.instance import Domain
    from app.models.media import File


# Association tables
post_tag = db.Table('post_tag',
    db.Column('post_id', db.Integer, db.ForeignKey('post.id')),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id')),
    db.PrimaryKeyConstraint('post_id', 'tag_id'),
    extend_existing=True
)

post_flair = db.Table('post_flair',
    db.Column('post_id', db.Integer, db.ForeignKey('post.id')),
    db.Column('flair_id', db.Integer, db.ForeignKey('community_flair.id')),
    db.PrimaryKeyConstraint('post_id', 'flair_id'),
    extend_existing=True
)

# Community language association table
community_language = db.Table('community_language',
    db.Column('community_id', db.Integer, db.ForeignKey('community.id')),
    db.Column('language_id', db.Integer, db.ForeignKey('language.id')),
    db.PrimaryKeyConstraint('community_id', 'language_id'),
    extend_existing=True
)


class Post(TimestampMixin, SoftDeleteMixin, ScoreMixin, ActivityPubMixin, 
           LanguageMixin, NSFWMixin, db.Model):
    """Post model with full typing support"""
    __tablename__ = 'post'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Content
    body: Mapped[Optional[str]] = mapped_column(Text)  # markdown
    body_html: Mapped[Optional[str]] = mapped_column(Text)  # rendered HTML
    
    # Type and media
    type: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1=text, 2=link, 3=image, 4=video, 5=poll
    url: Mapped[Optional[str]] = mapped_column(String(2048))
    domain_id: Mapped[Optional[DomainId]] = mapped_column(Integer, ForeignKey('domain.id'), index=True)
    image_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('file.id'))
    
    # Authorship
    user_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), nullable=False, index=True)
    community_id: Mapped[CommunityId] = mapped_column(Integer, ForeignKey('community.id'), nullable=False, index=True)
    
    # Settings
    comments_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sticky: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    nsfw_mask: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    from_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Stats
    reply_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Edit tracking
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    edit_reason: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Federation
    posted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    last_active: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False, index=True)
    
    # Microblog support
    microblog: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Search vector
    # TODO: Enable search_vector when using PostgreSQL
    # search_vector = mapped_column(TSVectorType('title', 'body'))
    
    # Relationships
    author = relationship('User', back_populates='posts')
    community = relationship('Community', back_populates='posts')
    domain = relationship('Domain', back_populates='posts')
    image = relationship('File', foreign_keys=[image_id])
    
    replies = relationship('PostReply', back_populates='post', lazy='dynamic',
                          cascade='all, delete-orphan')
    votes = relationship('PostVote', back_populates='post', lazy='dynamic',
                        cascade='all, delete-orphan')
    bookmarks = relationship('PostBookmark', back_populates='post', lazy='dynamic',
                           cascade='all, delete-orphan')
    reports = relationship('Report', back_populates='suspect_post', lazy='dynamic',
                         cascade='all, delete-orphan')
    
    # Indexes
    __table_args__ = (
        Index('idx_post_hot', 'community_id', 'deleted', 'sticky', 'ranking'),
        Index('idx_post_new', 'community_id', 'deleted', 'posted_at'),
        Index('idx_post_active', 'community_id', 'deleted', 'last_active'),
        {'extend_existing': True}
    )
    
    @validates('url')
    def validate_url(self, key: str, value: Optional[str]) -> Optional[str]:
        """Validate and normalize URL"""
        if not value:
            return value
        
        # Extract domain
        domain = domain_from_url(value)
        if domain:
            # Find or create domain record
            domain_obj = Domain.query.filter_by(name=domain).first()
            if not domain_obj:
                domain_obj = Domain(name=domain)
                db.session.add(domain_obj)
                db.session.flush()
            self.domain_id = domain_obj.id
        
        return value
    
    @hybrid_property
    def is_pinned(self) -> bool:
        """Check if post is pinned (sticky)"""
        return self.sticky
    
    @hybrid_property
    def is_locked(self) -> bool:
        """Check if post is locked (comments disabled)"""
        return not self.comments_enabled
    
    def can_edit(self, user: 'User') -> bool:
        """Check if user can edit post"""
        if user.id == self.user_id:
            return True
        if user.is_moderator(self.community):
            return True
        return False
    
    def can_delete(self, user: 'User') -> bool:
        """Check if user can delete post"""
        return self.can_edit(user)
    
    def update_reply_count(self) -> None:
        """Update reply count"""
        self.reply_count = self.replies.filter_by(deleted=False).count()
    
    def update_last_active(self) -> None:
        """Update last active timestamp"""
        latest_reply = self.replies.filter_by(deleted=False).order_by(
            PostReply.created_at.desc()
        ).first()
        
        if latest_reply:
            self.last_active = latest_reply.created_at
        else:
            self.last_active = self.posted_at
    
    def __repr__(self) -> str:
        return f'<Post {self.id}: {self.title[:50]}>'


class PostReply(TimestampMixin, SoftDeleteMixin, ScoreMixin, ActivityPubMixin,
                LanguageMixin, NSFWMixin, db.Model):
    """Post reply model with full typing support"""
    __tablename__ = 'post_reply'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Content
    body: Mapped[str] = mapped_column(Text, nullable=False)  # markdown
    body_html: Mapped[str] = mapped_column(Text, nullable=False)  # rendered HTML
    
    # Hierarchy
    post_id: Mapped[PostId] = mapped_column(Integer, ForeignKey('post.id'), nullable=False, index=True)
    parent_id: Mapped[Optional[ReplyId]] = mapped_column(Integer, ForeignKey('post_reply.id'), index=True)
    root_id: Mapped[Optional[ReplyId]] = mapped_column(Integer, ForeignKey('post_reply.id'), index=True)
    depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Authorship
    user_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), nullable=False, index=True)
    
    # Edit tracking
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # From bot
    from_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Search vector
    # TODO: Enable search_vector when using PostgreSQL
    # search_vector = mapped_column(TSVectorType('body'))
    
    # Relationships
    post = relationship('Post', back_populates='replies')
    author = relationship('User', back_populates='post_replies')
    parent = relationship('PostReply', foreign_keys=[parent_id], remote_side=[id], backref='children')
    root = relationship('PostReply', foreign_keys=[root_id], remote_side=[id])
    
    votes = relationship('PostReplyVote', back_populates='post_reply', lazy='dynamic',
                        cascade='all, delete-orphan')
    bookmarks = relationship('PostReplyBookmark', back_populates='post_reply', lazy='dynamic',
                           cascade='all, delete-orphan')
    reports = relationship('Report', back_populates='suspect_post_reply', lazy='dynamic',
                         cascade='all, delete-orphan')
    
    @property
    def community(self):
        """Get community through post relationship"""
        return self.post.community if self.post else None
    
    @validates('parent_id')
    def validate_parent(self, key: str, value: Optional[int]) -> Optional[int]:
        """Validate parent reply"""
        if value:
            parent = PostReply.query.get(value)
            if not parent:
                raise PostReplyValidationError('Parent reply not found')
            if parent.post_id != self.post_id:
                raise PostReplyValidationError('Parent reply must be from same post')
            
            # Set depth and root
            self.depth = parent.depth + 1
            self.root_id = parent.root_id or parent.id
        
        return value
    
    def can_edit(self, user: 'User') -> bool:
        """Check if user can edit reply"""
        if user.id == self.user_id:
            return True
        if user.is_moderator(self.post.community):
            return True
        return False
    
    def can_delete(self, user: 'User') -> bool:
        """Check if user can delete reply"""
        return self.can_edit(user)
    
    def __repr__(self) -> str:
        return f'<PostReply {self.id} to Post {self.post_id}>'


class PostVote(TimestampMixin, db.Model):
    """Post votes"""
    __tablename__ = 'post_vote'
    __table_args__ = (
        UniqueConstraint('user_id', 'post_id'),
        {'extend_existing': True}
    )
    
    # Primary keys
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), primary_key=True
    )
    post_id: Mapped[PostId] = mapped_column(
        Integer, ForeignKey('post.id'), primary_key=True
    )
    
    # Vote
    effect: Mapped[int] = mapped_column(Integer, nullable=False)  # 1=upvote, -1=downvote
    
    # Relationships
    user = relationship('User', back_populates='post_votes')
    post = relationship('Post', back_populates='votes')


class PostReplyVote(TimestampMixin, db.Model):
    """Post reply votes"""
    __tablename__ = 'post_reply_vote'
    __table_args__ = (
        UniqueConstraint('user_id', 'post_reply_id'),
        {'extend_existing': True}
    )
    
    # Primary keys
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), primary_key=True
    )
    post_reply_id: Mapped[ReplyId] = mapped_column(
        Integer, ForeignKey('post_reply.id'), primary_key=True
    )
    
    # Vote
    effect: Mapped[int] = mapped_column(Integer, nullable=False)  # 1=upvote, -1=downvote
    
    # Relationships
    user = relationship('User', back_populates='post_reply_votes')
    post_reply = relationship('PostReply', back_populates='votes')


class PostBookmark(TimestampMixin, db.Model):
    """Post bookmarks"""
    __tablename__ = 'post_bookmark'
    __table_args__ = {'extend_existing': True}
    
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), primary_key=True
    )
    post_id: Mapped[PostId] = mapped_column(
        Integer, ForeignKey('post.id'), primary_key=True
    )
    
    # Relationships
    user = relationship('User', back_populates='bookmarked_posts')
    post = relationship('Post', back_populates='bookmarks')


class PostReplyBookmark(TimestampMixin, db.Model):
    """Post reply bookmarks"""
    __tablename__ = 'post_reply_bookmark'
    __table_args__ = {'extend_existing': True}
    
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), primary_key=True
    )
    post_reply_id: Mapped[ReplyId] = mapped_column(
        Integer, ForeignKey('post_reply.id'), primary_key=True
    )
    
    # Relationships
    user = relationship('User', back_populates='bookmarked_replies')
    post_reply = relationship('PostReply', back_populates='bookmarks')


class ScheduledPost(TimestampMixin, db.Model):
    """Scheduled posts"""
    __tablename__ = 'scheduled_post'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Post data
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text)
    url: Mapped[Optional[str]] = mapped_column(String(2048))
    
    # Settings
    type: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    nsfw: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    nsfl: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Scheduling
    user_id: Mapped[UserId] = mapped_column(Integer, ForeignKey('user.id'), nullable=False)
    community_id: Mapped[CommunityId] = mapped_column(Integer, ForeignKey('community.id'), nullable=False)
    schedule_for: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    posted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relationships
    user = relationship('User')
    community = relationship('Community')


class Topic(db.Model):
    """Post topics/categories"""
    __tablename__ = 'topic'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    machine_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    
    # Relationships
    communities = relationship('Community', back_populates='topic', lazy='dynamic')


class Tag(db.Model):
    """Content tags"""
    __tablename__ = 'tag'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    name: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    post_id: Mapped[Optional[PostId]] = mapped_column(Integer, ForeignKey('post.id'), index=True)
    community_id: Mapped[Optional[CommunityId]] = mapped_column(Integer, ForeignKey('community.id'), index=True)
    
    # Relationships
    post = relationship('Post')
    community = relationship('Community')


class Poll(TimestampMixin, db.Model):
    """Polls attached to posts"""
    __tablename__ = 'poll'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[PostId] = mapped_column(Integer, ForeignKey('post.id'), nullable=False, unique=True)
    
    # Settings
    end_poll: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    multiple_choice: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hide_results: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relationships
    post = relationship('Post')
    choices = relationship('PollChoice', back_populates='poll', lazy='dynamic',
                         cascade='all, delete-orphan')


class PollChoice(db.Model):
    """Poll choices"""
    __tablename__ = 'poll_choice'
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    poll_id: Mapped[int] = mapped_column(Integer, ForeignKey('poll.id'), nullable=False)
    
    choice_text: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Relationships
    poll = relationship('Poll', back_populates='choices')
    votes = relationship('PollChoiceVote', back_populates='choice', lazy='dynamic',
                        cascade='all, delete-orphan')


class PollChoiceVote(TimestampMixin, db.Model):
    """Poll votes"""
    __tablename__ = 'poll_choice_vote'
    __table_args__ = {'extend_existing': True}
    
    user_id: Mapped[UserId] = mapped_column(
        Integer, ForeignKey('user.id'), primary_key=True
    )
    choice_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('poll_choice.id'), primary_key=True
    )
    
    # Relationships
    user = relationship('User')
    choice = relationship('PollChoice', back_populates='votes')