"""Type definitions for the federation module using Python 3.13 features"""
from __future__ import annotations
from typing import (
    Dict, List, Optional, Union, Literal, TypedDict, 
    Protocol, TypeVar, Generic, Callable, Awaitable,
    Any, cast, overload, Type, Tuple, NewType, NotRequired
)
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from abc import ABC, abstractmethod
import asyncio
from collections.abc import Mapping

# Type aliases
ActorUrl = NewType('ActorUrl', str)
ActivityId = NewType('ActivityId', str)
MessageId = NewType('MessageId', str)
Domain = NewType('Domain', str)
HttpUrl = NewType('HttpUrl', str)

# Enums
class Priority(Enum):
    """Message priority levels"""
    URGENT = "urgent"    # Votes, follows, unfollows
    NORMAL = "normal"    # Posts, comments
    BULK = "bulk"       # Announces, mass operations
    RETRY = "retry"     # Failed activities for retry

class ActivityType(Enum):
    """ActivityPub activity types"""
    LIKE = "Like"
    DISLIKE = "Dislike"
    CREATE = "Create"
    UPDATE = "Update"
    DELETE = "Delete"
    FOLLOW = "Follow"
    ACCEPT = "Accept"
    REJECT = "Reject"
    ANNOUNCE = "Announce"
    UNDO = "Undo"
    FLAG = "Flag"
    ADD = "Add"
    REMOVE = "Remove"
    BLOCK = "Block"

class ProcessingStatus(Enum):
    """Processing status for activities"""
    PENDING = auto()
    PROCESSING = auto()
    SUCCESS = auto()
    FAILED = auto()
    DEAD_LETTER = auto()
    RETRYING = auto()

# TypedDicts for JSON structures
class ActivityObject(TypedDict, total=False):
    """ActivityPub object structure with proper typing"""
    id: str
    type: str
    actor: str
    object: Union[str, 'ActivityObject', List[Union[str, 'ActivityObject']]]
    target: NotRequired[str]
    to: NotRequired[List[str]]
    cc: NotRequired[List[str]]
    audience: NotRequired[str]
    content: NotRequired[str]
    name: NotRequired[str]
    summary: NotRequired[str]
    inReplyTo: NotRequired[str]
    published: NotRequired[str]
    updated: NotRequired[str]
    url: NotRequired[str]
    attributedTo: NotRequired[str]
    tag: NotRequired[List[Dict[str, Any]]]
    attachment: NotRequired[List[Dict[str, Any]]]
    '@context': NotRequired[Union[str, List[str], Dict[str, Any]]]

class StreamMessage(TypedDict):
    """Redis Stream message structure"""
    type: str           # Message type (e.g., 'inbox.Like')
    data: str          # JSON string of the activity
    priority: str      # Priority level
    attempts: int      # Number of processing attempts
    timestamp: str     # ISO format timestamp
    request_id: NotRequired[str]  # Optional request tracking ID

class OutboxActivity(TypedDict):
    """Outgoing activity structure"""
    destination: HttpUrl
    body: ActivityObject
    private_key: str
    key_id: str
    domain: Domain
    retry_count: int
    max_retries: int
    timeout: float

# Protocols
class Signable(Protocol):
    """Protocol for objects that can be signed"""
    def to_activity_json(self) -> ActivityObject: ...
    def get_actor_url(self) -> ActorUrl: ...
    def get_private_key(self) -> str: ...
    def get_key_id(self) -> str: ...

class Processable(Protocol):
    """Protocol for objects that can be processed"""
    async def process(self) -> ProcessingStatus: ...
    def get_priority(self) -> Priority: ...
    def get_activity_type(self) -> ActivityType: ...

# Generic Types using Python 3.13 syntax
type HandlerResult = Union[ProcessingStatus, List[ProcessingStatus]]
type HandlerFunc[T] = Callable[[StreamConfig, List[Tuple[MessageId, T]]], Awaitable[HandlerResult]]
type ErrorHandler = Callable[[Exception, MessageId, Dict[str, Any]], Awaitable[None]]

# Dataclasses
@dataclass(frozen=True, slots=True)
class StreamConfig:
    """Configuration for a Redis stream"""
    name: str
    consumer_group: str
    batch_size: int = 10
    block_ms: int = 1000
    max_retries: int = 5
    claim_min_idle_ms: int = 60000
    max_length: Optional[int] = 100000  # Prevent unbounded growth
    
    def __post_init__(self) -> None:
        """Validate configuration"""
        if self.batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if self.block_ms < 0:
            raise ValueError("block_ms must be non-negative")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")

@dataclass
class ProcessingContext:
    """Context passed to handlers"""
    stream_config: StreamConfig
    redis_client: Any  # aioredis.Redis in runtime
    http_client: Any   # httpx.AsyncClient in runtime
    db_session: Any    # SQLAlchemy AsyncSession
    metrics: ProcessingMetrics
    
@dataclass
class ProcessingMetrics:
    """Metrics for monitoring processing"""
    messages_processed: int = 0
    messages_failed: int = 0
    messages_retried: int = 0
    total_processing_time: float = 0.0
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    
    def record_success(self, processing_time: float) -> None:
        """Record successful processing"""
        self.messages_processed += 1
        self.total_processing_time += processing_time
    
    def record_failure(self, error: str) -> None:
        """Record processing failure"""
        self.messages_failed += 1
        self.last_error = error
        self.last_error_time = datetime.utcnow()
    
    def record_retry(self) -> None:
        """Record retry attempt"""
        self.messages_retried += 1

@dataclass
class HandlerResponse:
    """Response from activity handlers"""
    message_id: MessageId
    status: ProcessingStatus
    error: Optional[str] = None
    retry_after: Optional[int] = None  # seconds
    processing_time: float = 0.0
    
    @property
    def should_retry(self) -> bool:
        """Check if message should be retried"""
        return self.status in (ProcessingStatus.FAILED, ProcessingStatus.RETRYING) and self.retry_after is not None

# Base classes using Python 3.13 generic syntax
class BaseHandler[T](ABC):
    """Base class for activity handlers with type parameter"""
    
    def __init__(self, context: ProcessingContext) -> None:
        self.context = context
        self._semaphore: Optional[asyncio.Semaphore] = None
    
    @abstractmethod
    async def handle(
        self, 
        messages: List[Tuple[MessageId, T]]
    ) -> List[HandlerResponse]:
        """Handle a batch of messages"""
        pass
    
    @abstractmethod
    def can_handle(self, activity_type: str) -> bool:
        """Check if this handler can process the activity type"""
        pass
    
    async def get_semaphore(self, limit: int = 10) -> asyncio.Semaphore:
        """Get or create semaphore for rate limiting"""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(limit)
        return self._semaphore

class BatchHandler[T](BaseHandler[T]):
    """Handler that processes messages in batches"""
    
    @abstractmethod
    async def process_batch(
        self,
        batch: List[Tuple[MessageId, T]]
    ) -> List[HandlerResponse]:
        """Process a batch of messages together"""
        pass
    
    async def handle(
        self, 
        messages: List[Tuple[MessageId, T]]
    ) -> List[HandlerResponse]:
        """Default implementation using process_batch"""
        return await self.process_batch(messages)

# Exception types
class FederationError(Exception):
    """Base exception for federation errors"""
    pass

class HandlerNotFoundError(FederationError):
    """Raised when no handler is found for an activity type"""
    pass

class ProcessingError(FederationError):
    """Raised when processing fails"""
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after

class ValidationError(FederationError):
    """Raised when activity validation fails"""
    pass

# Helper functions
def validate_activity(activity: dict) -> ActivityObject:
    """Validate and cast activity to proper type"""
    required_fields = ['id', 'type', 'actor']
    for field in required_fields:
        if field not in activity:
            raise ValidationError(f"Missing required field: {field}")
    
    # Validate URLs
    if 'id' in activity and not activity['id'].startswith(('http://', 'https://')):
        raise ValidationError(f"Invalid activity ID URL: {activity['id']}")
    
    return cast(ActivityObject, activity)

def get_activity_priority(activity_type: str) -> Priority:
    """Determine priority based on activity type"""
    urgent_types = {'Like', 'Dislike', 'Follow', 'Accept', 'Reject'}
    bulk_types = {'Announce', 'Delete'}
    
    if activity_type in urgent_types:
        return Priority.URGENT
    elif activity_type in bulk_types:
        return Priority.BULK
    else:
        return Priority.NORMAL