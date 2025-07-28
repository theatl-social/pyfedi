"""Media and file management models for PeachPie"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app import db
from app.models.base import TimestampMixin, UserId

if TYPE_CHECKING:
    from app.models.user import User


class File(TimestampMixin, db.Model):
    """File storage and management"""
    __tablename__ = 'file'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # File details
    file_name: Mapped[str] = mapped_column(String(256), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    
    # Storage backend
    source: Mapped[str] = mapped_column(String(10), default='local', nullable=False)  # 'local', 's3', etc.
    source_url: Mapped[Optional[str]] = mapped_column(String(512))
    
    # Metadata
    alt_text: Mapped[Optional[str]] = mapped_column(String(256))
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Thumbnail
    thumbnail_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('file.id'))
    
    # Categorization
    file_type: Mapped[Optional[str]] = mapped_column(String(50))  # 'image', 'video', 'document', etc.
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Size
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Relationships
    thumbnail = relationship('File', remote_side=[id])
    
    # Back references from other models
    avatar_users = relationship('User', foreign_keys='User.avatar_id', back_populates='avatar')
    cover_users = relationship('User', foreign_keys='User.cover_id', back_populates='cover')
    
    def is_image(self) -> bool:
        """Check if file is an image"""
        if self.mime_type:
            return self.mime_type.startswith('image/')
        return self.file_type == 'image'
    
    def is_video(self) -> bool:
        """Check if file is a video"""
        if self.mime_type:
            return self.mime_type.startswith('video/')
        return self.file_type == 'video'
    
    @property
    def url(self) -> str:
        """Get URL for accessing file"""
        if self.source == 's3' and self.source_url:
            return self.source_url
        # For local files, construct URL
        return f'/media/{self.file_path}'
    
    def __repr__(self) -> str:
        return f'<File {self.id}: {self.file_name}>'


class Language(db.Model):
    """Supported languages"""
    __tablename__ = 'language'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Language details
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)  # e.g., 'en', 'es', 'fr'
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., 'English', 'Spanish', 'French'
    
    # Display
    native_name: Mapped[Optional[str]] = mapped_column(String(50))  # e.g., 'Español', 'Français'
    
    # Status
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    def __repr__(self) -> str:
        return f'<Language {self.code}: {self.name}>'


class Licence(db.Model):
    """Content licenses"""
    __tablename__ = 'licence'
    __table_args__ = {'extend_existing': True}
    
    # Primary columns
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # License details
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(512))
    
    def __repr__(self) -> str:
        return f'<Licence {self.name}>'