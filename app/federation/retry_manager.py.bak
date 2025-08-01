"""
Retry Manager for Redis Streams Federation System

This module implements a sophisticated retry mechanism with exponential backoff,
configurable retry policies, and automatic failure handling for ActivityPub
federation activities.

Features:
    - Exponential backoff with jitter to prevent thundering herd
    - Per-activity-type retry policies
    - Configurable maximum retry duration (default 2 days)
    - Automatic promotion to Dead Letter Queue after max retries
    - Redis TTL management for completed tasks
    - Comprehensive metrics and logging

Example:
    >>> from app.federation.retry_manager import RetryManager
    >>> manager = RetryManager(redis_client)
    >>> await manager.schedule_retry(message, exception)
"""

from __future__ import annotations
from typing import Dict, Any, Optional, TypedDict, Final, Literal, Protocol
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import asyncio
import random
import json
from enum import Enum
import logging

import redis.asyncio as redis
from flask import current_app

from app.federation.types import (
    StreamMessage, Priority, ProcessingStatus, ActivityObject,
    ActivityId, HttpUrl, ActorUrl
)

# Type aliases
type RetryCount = int
type BackoffSeconds = float
type RetryPolicyName = str
type ExceptionMessage = str

# Constants
DEFAULT_MAX_RETRY_DURATION: Final[int] = 172800  # 2 days in seconds
DEFAULT_TASK_TTL: Final[int] = 86400  # 24 hours in seconds
DEFAULT_BACKOFF_FACTOR: Final[float] = 2.0
DEFAULT_MAX_RETRIES: Final[int] = 10
JITTER_FACTOR: Final[float] = 0.1  # 10% jitter


class RetryPolicy(TypedDict):
    """
    Configuration for retry behavior per activity type.
    
    Attributes:
        max_retries: Maximum number of retry attempts
        backoff_factor: Multiplier for exponential backoff (e.g., 2.0)
        max_delay: Maximum delay between retries in seconds
        initial_delay: Initial retry delay in seconds
    """
    max_retries: int
    backoff_factor: float
    max_delay: int
    initial_delay: int


@dataclass
class RetryMetadata:
    """
    Metadata tracked for each retry attempt.
    
    Attributes:
        attempt_count: Current retry attempt number
        first_attempt_at: Timestamp of the first attempt
        last_attempt_at: Timestamp of the most recent attempt
        next_attempt_at: Scheduled time for next retry
        exception_history: List of exceptions from each attempt
        backoff_seconds: Current backoff delay in seconds
    """
    attempt_count: int = 0
    first_attempt_at: Optional[datetime] = None
    last_attempt_at: Optional[datetime] = None
    next_attempt_at: Optional[datetime] = None
    exception_history: list[ExceptionMessage] = field(default_factory=list)
    backoff_seconds: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert retry metadata to dictionary for Redis storage."""
        return {
            'attempt_count': self.attempt_count,
            'first_attempt_at': self.first_attempt_at.isoformat() if self.first_attempt_at else None,
            'last_attempt_at': self.last_attempt_at.isoformat() if self.last_attempt_at else None,
            'next_attempt_at': self.next_attempt_at.isoformat() if self.next_attempt_at else None,
            'exception_history': self.exception_history,
            'backoff_seconds': self.backoff_seconds
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RetryMetadata:
        """Create RetryMetadata from dictionary retrieved from Redis."""
        return cls(
            attempt_count=data.get('attempt_count', 0),
            first_attempt_at=datetime.fromisoformat(data['first_attempt_at']) if data.get('first_attempt_at') else None,
            last_attempt_at=datetime.fromisoformat(data['last_attempt_at']) if data.get('last_attempt_at') else None,
            next_attempt_at=datetime.fromisoformat(data['next_attempt_at']) if data.get('next_attempt_at') else None,
            exception_history=data.get('exception_history', []),
            backoff_seconds=data.get('backoff_seconds', 0.0)
        )


class RetryStatus(Enum):
    """Status of a retry operation."""
    SCHEDULED = "scheduled"
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"
    MAX_DURATION_EXCEEDED = "max_duration_exceeded"
    SUCCESS = "success"
    DLQ = "dlq"


class RetryManager:
    """
    Manages retry logic for failed federation activities.
    
    This class handles the scheduling of retries with exponential backoff,
    tracks retry metadata, and manages the lifecycle of messages in Redis.
    
    Attributes:
        redis: Redis async client instance
        retry_policies: Dictionary of activity type to retry policy
        max_retry_duration: Maximum time to retry before giving up (seconds)
        task_ttl: Time to live for completed tasks in Redis (seconds)
    """
    
    def __init__(
        self,
        redis_client: redis.Redis,
        retry_policies: Optional[Dict[str, RetryPolicy]] = None,
        max_retry_duration: int = DEFAULT_MAX_RETRY_DURATION,
        task_ttl: int = DEFAULT_TASK_TTL
    ) -> None:
        """
        Initialize the RetryManager.
        
        Args:
            redis_client: Async Redis client instance
            retry_policies: Custom retry policies by activity type
            max_retry_duration: Maximum duration to retry (seconds)
            task_ttl: TTL for completed tasks in Redis (seconds)
        """
        self.redis = redis_client
        self.max_retry_duration = max_retry_duration
        self.task_ttl = task_ttl
        self.logger = logging.getLogger(__name__)
        
        # Default retry policies
        self.retry_policies: Dict[str, RetryPolicy] = {
            'Create': {'max_retries': 10, 'backoff_factor': 2.0, 'max_delay': 3600, 'initial_delay': 60},
            'Update': {'max_retries': 10, 'backoff_factor': 2.0, 'max_delay': 3600, 'initial_delay': 60},
            'Delete': {'max_retries': 8, 'backoff_factor': 1.5, 'max_delay': 1800, 'initial_delay': 30},
            'Follow': {'max_retries': 8, 'backoff_factor': 2.0, 'max_delay': 1800, 'initial_delay': 60},
            'Accept': {'max_retries': 5, 'backoff_factor': 1.5, 'max_delay': 900, 'initial_delay': 30},
            'Reject': {'max_retries': 5, 'backoff_factor': 1.5, 'max_delay': 900, 'initial_delay': 30},
            'Like': {'max_retries': 5, 'backoff_factor': 1.5, 'max_delay': 600, 'initial_delay': 30},
            'Announce': {'max_retries': 6, 'backoff_factor': 2.0, 'max_delay': 1200, 'initial_delay': 45},
            'Undo': {'max_retries': 7, 'backoff_factor': 1.8, 'max_delay': 1800, 'initial_delay': 45},
        }
        
        # Override with custom policies
        if retry_policies:
            self.retry_policies.update(retry_policies)
    
    def _get_retry_policy(self, activity_type: str) -> RetryPolicy:
        """
        Get retry policy for an activity type.
        
        Args:
            activity_type: The type of ActivityPub activity
            
        Returns:
            RetryPolicy configuration for the activity type
        """
        return self.retry_policies.get(
            activity_type,
            {
                'max_retries': DEFAULT_MAX_RETRIES,
                'backoff_factor': DEFAULT_BACKOFF_FACTOR,
                'max_delay': 3600,
                'initial_delay': 60
            }
        )
    
    def _calculate_backoff(
        self,
        attempt: int,
        policy: RetryPolicy,
        add_jitter: bool = True
    ) -> BackoffSeconds:
        """
        Calculate exponential backoff with optional jitter.
        
        Args:
            attempt: Current attempt number (1-based)
            policy: Retry policy to use
            add_jitter: Whether to add random jitter to prevent thundering herd
            
        Returns:
            Backoff duration in seconds
        """
        # Calculate base exponential backoff
        base_delay = policy['initial_delay'] * (policy['backoff_factor'] ** (attempt - 1))
        
        # Cap at maximum delay
        delay = min(base_delay, policy['max_delay'])
        
        # Add jitter to prevent thundering herd
        if add_jitter:
            jitter_range = delay * JITTER_FACTOR
            jitter = random.uniform(-jitter_range, jitter_range)
            delay += jitter
        
        return max(delay, 1.0)  # Ensure at least 1 second delay
    
    async def schedule_retry(
        self,
        message: StreamMessage,
        exception: Exception,
        override_policy: Optional[RetryPolicy] = None
    ) -> RetryStatus:
        """
        Schedule a retry for a failed message.
        
        This method determines if a message should be retried based on the
        retry policy and current retry metadata. If eligible, it schedules
        the message for retry with appropriate backoff.
        
        Args:
            message: The message that failed processing
            exception: The exception that caused the failure
            override_policy: Optional policy to override default behavior
            
        Returns:
            RetryStatus indicating the outcome of the scheduling attempt
            
        Example:
            >>> status = await retry_manager.schedule_retry(
            ...     message=failed_message,
            ...     exception=processing_error
            ... )
            >>> if status == RetryStatus.DLQ:
            ...     print("Message sent to dead letter queue")
        """
        activity_type = message.activity.get('type', 'Unknown')
        policy = override_policy or self._get_retry_policy(activity_type)
        
        # Get or create retry metadata
        metadata_key = f"retry:metadata:{message.id}"
        metadata_json = await self.redis.get(metadata_key)
        
        if metadata_json:
            metadata = RetryMetadata.from_dict(json.loads(metadata_json))
        else:
            metadata = RetryMetadata(
                first_attempt_at=datetime.now(timezone.utc),
                attempt_count=0
            )
        
        # Update metadata for this attempt
        metadata.attempt_count += 1
        metadata.last_attempt_at = datetime.now(timezone.utc)
        metadata.exception_history.append(str(exception)[-200:])  # Limit exception string length
        
        # Check if we've exceeded retry limits
        if metadata.attempt_count > policy['max_retries']:
            self.logger.warning(
                f"Message {message.id} exceeded max retries ({policy['max_retries']})"
            )
            await self._send_to_dlq(message, metadata, "max_retries_exceeded")
            return RetryStatus.MAX_RETRIES_EXCEEDED
        
        # Check if we've exceeded max retry duration
        if metadata.first_attempt_at:
            elapsed = (datetime.now(timezone.utc) - metadata.first_attempt_at).total_seconds()
            if elapsed > self.max_retry_duration:
                self.logger.warning(
                    f"Message {message.id} exceeded max retry duration ({self.max_retry_duration}s)"
                )
                await self._send_to_dlq(message, metadata, "max_duration_exceeded")
                return RetryStatus.MAX_DURATION_EXCEEDED
        
        # Calculate next retry time
        backoff_seconds = self._calculate_backoff(metadata.attempt_count, policy)
        metadata.backoff_seconds = backoff_seconds
        metadata.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
        
        # Save updated metadata
        await self.redis.setex(
            metadata_key,
            self.max_retry_duration,  # TTL matches max retry duration
            json.dumps(metadata.to_dict())
        )
        
        # Create retry message
        retry_message = StreamMessage(
            id=f"{message.id}:retry:{metadata.attempt_count}",
            activity=message.activity,
            destination=message.destination,
            priority=Priority.RETRY,
            status=ProcessingStatus.PENDING,
            created_at=message.created_at,
            metadata={
                **message.metadata,
                'retry_count': metadata.attempt_count,
                'original_id': message.id,
                'next_attempt_at': metadata.next_attempt_at.isoformat()
            }
        )
        
        # Schedule the retry
        retry_stream = f"federation:stream:retry:{int(backoff_seconds)}"
        await self.redis.xadd(
            retry_stream,
            {'data': json.dumps(retry_message.to_dict())}
        )
        
        self.logger.info(
            f"Scheduled retry for {message.id} in {backoff_seconds:.1f}s "
            f"(attempt {metadata.attempt_count}/{policy['max_retries']})"
        )
        
        return RetryStatus.SCHEDULED
    
    async def _send_to_dlq(
        self,
        message: StreamMessage,
        metadata: RetryMetadata,
        reason: str
    ) -> None:
        """
        Send a message to the Dead Letter Queue.
        
        Args:
            message: The message that failed all retries
            metadata: Retry metadata for the message
            reason: Reason for sending to DLQ
        """
        dlq_message = {
            'message': message.to_dict(),
            'metadata': metadata.to_dict(),
            'reason': reason,
            'dlq_timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        await self.redis.xadd(
            'federation:dlq',
            {'data': json.dumps(dlq_message)}
        )
        
        # Clean up retry metadata
        await self.redis.delete(f"retry:metadata:{message.id}")
    
    async def mark_success(
        self,
        message_id: str,
        processing_time_ms: Optional[float] = None
    ) -> None:
        """
        Mark a message as successfully processed.
        
        This method updates success metrics and sets a TTL on the message
        data to automatically clean up after the configured period.
        
        Args:
            message_id: ID of the successfully processed message
            processing_time_ms: Optional processing time in milliseconds
        """
        # Record success metrics
        success_key = f"success:{message_id}"
        success_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'processing_time_ms': processing_time_ms or 0
        }
        
        # Set with TTL for automatic cleanup
        await self.redis.setex(
            success_key,
            self.task_ttl,
            json.dumps(success_data)
        )
        
        # Clean up retry metadata if it exists
        await self.redis.delete(f"retry:metadata:{message_id}")
        
        # Update success counter
        await self.redis.hincrby('federation:stats', 'success_count', 1)
        
        self.logger.debug(f"Marked message {message_id} as successful")
    
    async def get_retry_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive retry statistics.
        
        Returns:
            Dictionary containing retry statistics including:
            - Total retry count
            - Retries by activity type
            - Average retry count
            - DLQ size
            
        Example:
            >>> stats = await retry_manager.get_retry_stats()
            >>> print(f"Total retries: {stats['total_retries']}")
            >>> print(f"DLQ size: {stats['dlq_size']}")
        """
        # Get retry metadata keys
        retry_keys = []
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(
                cursor,
                match='retry:metadata:*',
                count=100
            )
            retry_keys.extend(keys)
            if cursor == 0:
                break
        
        # Aggregate statistics
        total_retries = 0
        retries_by_type: Dict[str, int] = {}
        retry_counts: list[int] = []
        
        for key in retry_keys:
            metadata_json = await self.redis.get(key)
            if metadata_json:
                metadata = RetryMetadata.from_dict(json.loads(metadata_json))
                total_retries += metadata.attempt_count
                retry_counts.append(metadata.attempt_count)
        
        # Get DLQ size
        dlq_info = await self.redis.xinfo_stream('federation:dlq')
        dlq_size = dlq_info.get('length', 0)
        
        # Get success/failure counts
        stats = await self.redis.hgetall('federation:stats')
        
        return {
            'total_retries': total_retries,
            'active_retries': len(retry_keys),
            'average_retry_count': sum(retry_counts) / len(retry_counts) if retry_counts else 0,
            'max_retry_count': max(retry_counts) if retry_counts else 0,
            'dlq_size': dlq_size,
            'success_count': int(stats.get(b'success_count', 0)),
            'failure_count': int(stats.get(b'failure_count', 0)),
            'retries_by_type': retries_by_type
        }
    
    async def cleanup_expired_data(self) -> int:
        """
        Clean up expired retry metadata and old stream messages.
        
        This method should be called periodically to clean up data that
        Redis TTL hasn't removed yet, such as old stream messages.
        
        Returns:
            Number of items cleaned up
            
        Example:
            >>> cleaned = await retry_manager.cleanup_expired_data()
            >>> print(f"Cleaned up {cleaned} expired items")
        """
        cleaned_count = 0
        
        # Clean up old retry metadata
        retry_keys = []
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(
                cursor,
                match='retry:metadata:*',
                count=100
            )
            retry_keys.extend(keys)
            if cursor == 0:
                break
        
        for key in retry_keys:
            metadata_json = await self.redis.get(key)
            if metadata_json:
                metadata = RetryMetadata.from_dict(json.loads(metadata_json))
                if metadata.first_attempt_at:
                    age = (datetime.now(timezone.utc) - metadata.first_attempt_at).total_seconds()
                    if age > self.max_retry_duration:
                        await self.redis.delete(key)
                        cleaned_count += 1
        
        # Trim old stream messages
        streams = [
            'federation:stream:urgent',
            'federation:stream:normal',
            'federation:stream:bulk',
            'federation:stream:retry'
        ]
        
        cutoff_time = datetime., timezone() - timedelta(seconds=self.task_ttl)
        cutoff_id = f"{int(cutoff_time.timestamp() * 1000)}-0"
        
        for stream in streams:
            try:
                result = await self.redis.xtrim(stream, minid=cutoff_id)
                if result:
                    cleaned_count += result
            except Exception as e:
                self.logger.error(f"Error trimming stream {stream}: {e}")
        
        self.logger.info(f"Cleaned up {cleaned_count} expired items")
        return cleaned_count