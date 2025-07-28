"""Base classes and mixins for PeachPie models"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, Text, DateTime, Float, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.hybrid import hybrid_property
from flask_login import UserMixin

from app import db, cache
from app.utils import LanguageTool

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.community import Community
    from app.models.instance import Instance


# Type aliases for better readability
type UserId = int
type CommunityId = int
type PostId = int
type InstanceId = int
type ReplyId = int
type DomainId = int
type ActivityId = str
type ActorUrl = str
type HttpUrl = str


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps"""
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow, 
        nullable=False,
        index=True
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        onupdate=datetime.utcnow
    )


class SoftDeleteMixin:
    """Mixin for soft deletion"""
    deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    def soft_delete(self) -> None:
        """Mark record as deleted"""
        self.deleted = True
        self.deleted_at = datetime.utcnow()
    
    def restore(self) -> None:
        """Restore soft-deleted record"""
        self.deleted = False
        self.deleted_at = None


class ScoreMixin:
    """Mixin for votable content"""
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    up_votes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    down_votes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ranking: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    
    @hybrid_property
    def controversy_rank(self) -> float:
        """Calculate controversy ranking"""
        if self.up_votes == 0 or self.down_votes == 0:
            return 0.0
        magnitude = self.up_votes + self.down_votes
        balance = abs(self.up_votes - self.down_votes) / magnitude
        return magnitude * (1 - balance)


class ActivityPubMixin:
    """Mixin for ActivityPub properties"""
    ap_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, unique=True)
    ap_profile_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, unique=True)
    ap_public_url: Mapped[Optional[str]] = mapped_column(String(255))
    ap_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ap_followers_url: Mapped[Optional[str]] = mapped_column(String(255))
    ap_inbox_url: Mapped[Optional[str]] = mapped_column(String(255))
    ap_outbox_url: Mapped[Optional[str]] = mapped_column(String(255))
    
    @property
    def is_local(self) -> bool:
        """Check if this is a local object"""
        return self.ap_id is None or self.ap_profile_id is None
    
    @property
    def is_remote(self) -> bool:
        """Check if this is a remote object"""
        return not self.is_local


class LanguageMixin:
    """Mixin for language detection"""
    language: Mapped[Optional[str]] = mapped_column(String(10))
    
    def detect_language(self, text: str) -> Optional[str]:
        """Detect language from text"""
        if not text:
            return None
        
        lang_tool = LanguageTool()
        detected = lang_tool.detect(text)
        if detected and detected.languages:
            return detected.languages[0].lang
        return None


class NSFWMixin:
    """Mixin for NSFW content"""
    nsfw: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    nsfl: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    
    @property
    def is_safe_for_work(self) -> bool:
        """Check if content is safe for work"""
        return not self.nsfw and not self.nsfl


# Custom exceptions
class PostReplyValidationError(Exception):
    """Raised when a post reply validation fails"""
    pass


class FederationError(Exception):
    """Raised when federation operations fail"""
    pass


class ModerationError(Exception):
    """Raised when moderation operations fail"""
    pass