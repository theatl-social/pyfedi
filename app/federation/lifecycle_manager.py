"""
Redis Data Lifecycle Manager for Federation System

This module manages the lifecycle of data in Redis to prevent unbounded memory
growth. It implements automatic expiration, data archival, and memory monitoring.

Key Features:
    - Automatic TTL management for completed tasks
    - Stream trimming based on age and size
    - Important failure archival to database before expiry
    - Memory usage monitoring and alerts
    - Configurable retention policies

Example:
    >>> from app.federation.lifecycle_manager import LifecycleManager
    >>> manager = LifecycleManager(redis_client, db_session)
    >>> await manager.start_background_tasks()
"""

from __future__ import annotations
from typing import Dict, Any, Optional, List, Tuple, Protocol, TypedDict
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import asyncio
import json
import logging

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert

from app.federation.types import StreamMessage, ProcessingStatus
from app.models import ActivityPubLog

# Type aliases
type ByteSize = int
type RetentionSeconds = int
type StreamName = str
type MessageId = str
type TaskId = str

# Constants
DEFAULT_RETENTION_POLICIES: Dict[str, RetentionSeconds] = {
    'completed_tasks': 86400,      # 24 hours
    'failed_tasks': 604800,        # 7 days
    'retry_metadata': 172800,      # 2 days
    'success_metrics': 86400,      # 24 hours
    'stream_messages': 259200,     # 3 days
    'dlq_messages': 2592000,       # 30 days
}

MEMORY_WARNING_THRESHOLD_MB = 1024  # 1GB
MEMORY_CRITICAL_THRESHOLD_MB = 2048  # 2GB


class DataCategory(Enum):
    """Categories of data stored in Redis."""
    COMPLETED_TASK = "completed_task"
    FAILED_TASK = "failed_task"
    RETRY_METADATA = "retry_metadata"
    SUCCESS_METRIC = "success_metric"
    STREAM_MESSAGE = "stream_message"
    DLQ_MESSAGE = "dlq_message"


class MemoryStatus(TypedDict):
    """Memory usage status information."""
    used_memory_mb: float
    used_memory_peak_mb: float
    used_memory_rss_mb: float
    memory_fragmentation_ratio: float
    status: Literal['healthy', 'warning', 'critical']


@dataclass
class RetentionPolicy:
    """
    Defines retention policy for a data category.
    
    Attributes:
        category: The type of data this policy applies to
        ttl_seconds: Time to live in seconds
        archive_to_db: Whether to archive to database before deletion
        trim_strategy: Strategy for trimming old data ('age' or 'size')
        max_size: Maximum number of items (for size-based trimming)
    """
    category: DataCategory
    ttl_seconds: RetentionSeconds
    archive_to_db: bool = False
    trim_strategy: Literal['age', 'size'] = 'age'
    max_size: Optional[int] = None


class ArchivalProtocol(Protocol):
    """Protocol for classes that can archive data to database."""
    
    async def archive(
        self,
        data: Dict[str, Any],
        category: DataCategory,
        session: AsyncSession
    ) -> bool:
        """Archive data to database."""
        ...


class LifecycleManager:
    """
    Manages the lifecycle of data in Redis.
    
    This class handles automatic expiration of data, archival of important
    information to the database, and monitoring of Redis memory usage.
    
    Attributes:
        redis: Redis async client
        retention_policies: Dictionary of data categories to retention policies
        cleanup_interval: Interval between cleanup runs in seconds
        archive_handler: Optional handler for archiving data to database
    """
    
    def __init__(
        self,
        redis_client: redis.Redis,
        retention_policies: Optional[Dict[DataCategory, RetentionPolicy]] = None,
        cleanup_interval: int = 3600,  # 1 hour
        archive_handler: Optional[ArchivalProtocol] = None
    ) -> None:
        """
        Initialize the LifecycleManager.
        
        Args:
            redis_client: Async Redis client instance
            retention_policies: Custom retention policies by data category
            cleanup_interval: Seconds between cleanup runs (default: 1 hour)
            archive_handler: Optional handler for archiving to database
        """
        self.redis = redis_client
        self.cleanup_interval = cleanup_interval
        self.archive_handler = archive_handler
        self.logger = logging.getLogger(__name__)
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Initialize retention policies
        self.retention_policies = self._initialize_policies(retention_policies)
    
    def _initialize_policies(
        self,
        custom_policies: Optional[Dict[DataCategory, RetentionPolicy]]
    ) -> Dict[DataCategory, RetentionPolicy]:
        """
        Initialize retention policies with defaults and custom overrides.
        
        Args:
            custom_policies: Optional custom retention policies
            
        Returns:
            Complete set of retention policies
        """
        policies = {
            DataCategory.COMPLETED_TASK: RetentionPolicy(
                category=DataCategory.COMPLETED_TASK,
                ttl_seconds=DEFAULT_RETENTION_POLICIES['completed_tasks'],
                archive_to_db=False
            ),
            DataCategory.FAILED_TASK: RetentionPolicy(
                category=DataCategory.FAILED_TASK,
                ttl_seconds=DEFAULT_RETENTION_POLICIES['failed_tasks'],
                archive_to_db=True  # Archive failures for analysis
            ),
            DataCategory.RETRY_METADATA: RetentionPolicy(
                category=DataCategory.RETRY_METADATA,
                ttl_seconds=DEFAULT_RETENTION_POLICIES['retry_metadata'],
                archive_to_db=False
            ),
            DataCategory.SUCCESS_METRIC: RetentionPolicy(
                category=DataCategory.SUCCESS_METRIC,
                ttl_seconds=DEFAULT_RETENTION_POLICIES['success_metrics'],
                archive_to_db=False
            ),
            DataCategory.STREAM_MESSAGE: RetentionPolicy(
                category=DataCategory.STREAM_MESSAGE,
                ttl_seconds=DEFAULT_RETENTION_POLICIES['stream_messages'],
                archive_to_db=False,
                trim_strategy='age'
            ),
            DataCategory.DLQ_MESSAGE: RetentionPolicy(
                category=DataCategory.DLQ_MESSAGE,
                ttl_seconds=DEFAULT_RETENTION_POLICIES['dlq_messages'],
                archive_to_db=True,  # Always archive DLQ messages
                trim_strategy='size',
                max_size=10000  # Keep max 10k messages in DLQ
            ),
        }
        
        # Apply custom policies
        if custom_policies:
            policies.update(custom_policies)
        
        return policies
    
    async def set_expiration(
        self,
        key: str,
        category: DataCategory,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Set expiration on a Redis key based on its data category.
        
        Args:
            key: Redis key to set expiration on
            category: Category of data stored in the key
            data: Optional data for keys that need it set along with expiration
            
        Example:
            >>> await manager.set_expiration(
            ...     "task:12345",
            ...     DataCategory.COMPLETED_TASK
            ... )
        """
        policy = self.retention_policies.get(category)
        if not policy:
            self.logger.warning(f"No retention policy for category {category}")
            return
        
        if data:
            # Set data with expiration
            await self.redis.setex(
                key,
                policy.ttl_seconds,
                json.dumps(data)
            )
        else:
            # Just set expiration on existing key
            await self.redis.expire(key, policy.ttl_seconds)
        
        self.logger.debug(
            f"Set {policy.ttl_seconds}s expiration on {key} (category: {category.value})"
        )
    
    async def trim_stream(
        self,
        stream_name: StreamName,
        policy: RetentionPolicy
    ) -> int:
        """
        Trim a Redis stream based on retention policy.
        
        Args:
            stream_name: Name of the Redis stream
            policy: Retention policy to apply
            
        Returns:
            Number of messages trimmed
            
        Example:
            >>> trimmed = await manager.trim_stream(
            ...     "federation:stream:normal",
            ...     policy
            ... )
            >>> print(f"Trimmed {trimmed} old messages")
        """
        trimmed_count = 0
        
        try:
            if policy.trim_strategy == 'age':
                # Trim by age
                cutoff_time = datetime.utcnow() - timedelta(seconds=policy.ttl_seconds)
                cutoff_id = f"{int(cutoff_time.timestamp() * 1000)}-0"
                
                # Get messages that will be trimmed for potential archival
                if policy.archive_to_db and self.archive_handler:
                    messages = await self.redis.xrange(
                        stream_name,
                        min='-',
                        max=cutoff_id,
                        count=100  # Process in batches
                    )
                    
                    # Archive messages before trimming
                    for msg_id, msg_data in messages:
                        await self._archive_stream_message(
                            stream_name,
                            msg_id,
                            msg_data,
                            policy.category
                        )
                
                # Perform the trim
                result = await self.redis.xtrim(stream_name, minid=cutoff_id)
                trimmed_count = result or 0
                
            elif policy.trim_strategy == 'size' and policy.max_size:
                # Trim by size (keep newest N messages)
                info = await self.redis.xinfo_stream(stream_name)
                current_size = info.get('length', 0)
                
                if current_size > policy.max_size:
                    # Archive oldest messages if needed
                    if policy.archive_to_db and self.archive_handler:
                        to_remove = current_size - policy.max_size
                        messages = await self.redis.xrange(
                            stream_name,
                            count=to_remove
                        )
                        
                        for msg_id, msg_data in messages:
                            await self._archive_stream_message(
                                stream_name,
                                msg_id,
                                msg_data,
                                policy.category
                            )
                    
                    # Trim to max size
                    result = await self.redis.xtrim(
                        stream_name,
                        maxlen=policy.max_size,
                        approximate=False
                    )
                    trimmed_count = result or 0
            
            if trimmed_count > 0:
                self.logger.info(
                    f"Trimmed {trimmed_count} messages from {stream_name} "
                    f"(strategy: {policy.trim_strategy})"
                )
                
        except Exception as e:
            self.logger.error(f"Error trimming stream {stream_name}: {e}")
        
        return trimmed_count
    
    async def _archive_stream_message(
        self,
        stream_name: StreamName,
        message_id: MessageId,
        message_data: Dict[bytes, bytes],
        category: DataCategory
    ) -> None:
        """
        Archive a stream message to database before deletion.
        
        Args:
            stream_name: Name of the stream
            message_id: Redis stream message ID
            message_data: Raw message data from Redis
            category: Data category for archival
        """
        if not self.archive_handler:
            return
        
        try:
            # Decode message data
            decoded_data = {
                k.decode('utf-8'): v.decode('utf-8')
                for k, v in message_data.items()
            }
            
            # Parse the actual message content
            if 'data' in decoded_data:
                content = json.loads(decoded_data['data'])
            else:
                content = decoded_data
            
            # Create archive record
            archive_data = {
                'stream_name': stream_name,
                'message_id': message_id,
                'content': content,
                'archived_at': datetime.utcnow().isoformat()
            }
            
            # Use a dummy session for now - in production this would be injected
            from app import db
            async with db.get_session() as session:
                await self.archive_handler.archive(
                    archive_data,
                    category,
                    session
                )
                
        except Exception as e:
            self.logger.error(
                f"Failed to archive message {message_id} from {stream_name}: {e}"
            )
    
    async def get_memory_status(self) -> MemoryStatus:
        """
        Get current Redis memory usage status.
        
        Returns:
            MemoryStatus with current memory metrics and health status
            
        Example:
            >>> status = await manager.get_memory_status()
            >>> if status['status'] == 'critical':
            ...     alert_admins("Redis memory critical!")
        """
        try:
            info = await self.redis.info('memory')
            
            used_memory = info.get('used_memory', 0)
            used_memory_mb = used_memory / (1024 * 1024)
            
            used_memory_peak = info.get('used_memory_peak', 0)
            used_memory_peak_mb = used_memory_peak / (1024 * 1024)
            
            used_memory_rss = info.get('used_memory_rss', 0)
            used_memory_rss_mb = used_memory_rss / (1024 * 1024)
            
            fragmentation_ratio = info.get('mem_fragmentation_ratio', 1.0)
            
            # Determine health status
            if used_memory_mb >= MEMORY_CRITICAL_THRESHOLD_MB:
                status = 'critical'
            elif used_memory_mb >= MEMORY_WARNING_THRESHOLD_MB:
                status = 'warning'
            else:
                status = 'healthy'
            
            return MemoryStatus(
                used_memory_mb=round(used_memory_mb, 2),
                used_memory_peak_mb=round(used_memory_peak_mb, 2),
                used_memory_rss_mb=round(used_memory_rss_mb, 2),
                memory_fragmentation_ratio=round(fragmentation_ratio, 2),
                status=status
            )
            
        except Exception as e:
            self.logger.error(f"Failed to get memory status: {e}")
            return MemoryStatus(
                used_memory_mb=0,
                used_memory_peak_mb=0,
                used_memory_rss_mb=0,
                memory_fragmentation_ratio=0,
                status='unknown'
            )
    
    async def cleanup_expired_keys(self) -> Dict[str, int]:
        """
        Clean up expired keys across all data categories.
        
        This method scans for keys that should have expired but haven't been
        removed by Redis TTL mechanism yet.
        
        Returns:
            Dictionary mapping data category to number of keys cleaned
            
        Example:
            >>> cleaned = await manager.cleanup_expired_keys()
            >>> for category, count in cleaned.items():
            ...     print(f"{category}: {count} keys cleaned")
        """
        cleanup_stats: Dict[str, int] = {}
        
        # Define key patterns for each category
        key_patterns = {
            DataCategory.COMPLETED_TASK: 'task:completed:*',
            DataCategory.FAILED_TASK: 'task:failed:*',
            DataCategory.RETRY_METADATA: 'retry:metadata:*',
            DataCategory.SUCCESS_METRIC: 'success:*',
        }
        
        for category, pattern in key_patterns.items():
            policy = self.retention_policies.get(category)
            if not policy:
                continue
            
            cleaned_count = 0
            cursor = 0
            
            # Scan for keys matching pattern
            while True:
                cursor, keys = await self.redis.scan(
                    cursor,
                    match=pattern,
                    count=100
                )
                
                for key in keys:
                    try:
                        # Check if key has TTL set
                        ttl = await self.redis.ttl(key)
                        
                        # If no TTL or expired, handle it
                        if ttl == -1:  # No expiration set
                            # Archive if needed
                            if policy.archive_to_db and self.archive_handler:
                                data = await self.redis.get(key)
                                if data:
                                    await self._archive_key_data(
                                        key.decode('utf-8'),
                                        json.loads(data),
                                        category
                                    )
                            
                            # Set expiration
                            await self.redis.expire(key, policy.ttl_seconds)
                            cleaned_count += 1
                            
                    except Exception as e:
                        self.logger.error(f"Error processing key {key}: {e}")
                
                if cursor == 0:
                    break
            
            cleanup_stats[category.value] = cleaned_count
        
        # Clean up streams
        streams = {
            'federation:stream:urgent': DataCategory.STREAM_MESSAGE,
            'federation:stream:normal': DataCategory.STREAM_MESSAGE,
            'federation:stream:bulk': DataCategory.STREAM_MESSAGE,
            'federation:stream:retry': DataCategory.STREAM_MESSAGE,
            'federation:dlq': DataCategory.DLQ_MESSAGE,
        }
        
        for stream_name, category in streams.items():
            policy = self.retention_policies.get(category)
            if policy:
                trimmed = await self.trim_stream(stream_name, policy)
                cleanup_stats[f"{category.value}:{stream_name}"] = trimmed
        
        return cleanup_stats
    
    async def _archive_key_data(
        self,
        key: str,
        data: Dict[str, Any],
        category: DataCategory
    ) -> None:
        """
        Archive key data to database before deletion.
        
        Args:
            key: Redis key
            data: Data stored in the key
            category: Data category for archival
        """
        if not self.archive_handler:
            return
        
        try:
            archive_data = {
                'redis_key': key,
                'data': data,
                'category': category.value,
                'archived_at': datetime.utcnow().isoformat()
            }
            
            from app import db
            async with db.get_session() as session:
                await self.archive_handler.archive(
                    archive_data,
                    category,
                    session
                )
                
        except Exception as e:
            self.logger.error(f"Failed to archive key {key}: {e}")
    
    async def start_background_tasks(self) -> None:
        """
        Start background cleanup tasks.
        
        This starts a periodic task that runs cleanup operations at the
        configured interval.
        
        Example:
            >>> await manager.start_background_tasks()
            >>> # Cleanup now runs automatically every hour
        """
        if self._cleanup_task and not self._cleanup_task.done():
            self.logger.warning("Background cleanup task already running")
            return
        
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        self.logger.info(
            f"Started background cleanup task (interval: {self.cleanup_interval}s)"
        )
    
    async def stop_background_tasks(self) -> None:
        """
        Stop background cleanup tasks.
        
        Example:
            >>> await manager.stop_background_tasks()
        """
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self.logger.info("Stopped background cleanup task")
    
    async def _periodic_cleanup(self) -> None:
        """
        Periodic cleanup task that runs at configured intervals.
        
        This method runs continuously, performing cleanup operations and
        monitoring memory usage.
        """
        while True:
            try:
                # Perform cleanup
                self.logger.info("Starting periodic cleanup")
                cleanup_stats = await self.cleanup_expired_keys()
                
                # Log results
                total_cleaned = sum(cleanup_stats.values())
                if total_cleaned > 0:
                    self.logger.info(
                        f"Cleaned up {total_cleaned} items: {cleanup_stats}"
                    )
                
                # Check memory status
                memory_status = await self.get_memory_status()
                if memory_status['status'] == 'warning':
                    self.logger.warning(
                        f"Redis memory usage warning: {memory_status['used_memory_mb']}MB"
                    )
                elif memory_status['status'] == 'critical':
                    self.logger.error(
                        f"Redis memory usage critical: {memory_status['used_memory_mb']}MB"
                    )
                    # Could trigger more aggressive cleanup here
                
                # Wait for next interval
                await asyncio.sleep(self.cleanup_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in periodic cleanup: {e}")
                # Continue after error
                await asyncio.sleep(60)  # Wait a minute before retrying
    
    async def force_cleanup(
        self,
        aggressive: bool = False
    ) -> Dict[str, Any]:
        """
        Force an immediate cleanup operation.
        
        Args:
            aggressive: If True, use more aggressive cleanup strategies
            
        Returns:
            Cleanup statistics and memory status
            
        Example:
            >>> # Normal cleanup
            >>> stats = await manager.force_cleanup()
            >>> 
            >>> # Aggressive cleanup when memory is critical
            >>> stats = await manager.force_cleanup(aggressive=True)
        """
        self.logger.info(f"Starting forced cleanup (aggressive={aggressive})")
        
        # Run normal cleanup
        cleanup_stats = await self.cleanup_expired_keys()
        
        if aggressive:
            # Reduce retention times temporarily
            original_policies = self.retention_policies.copy()
            
            try:
                # Halve all retention times for aggressive cleanup
                for category, policy in self.retention_policies.items():
                    policy.ttl_seconds = policy.ttl_seconds // 2
                
                # Run cleanup again with reduced retention
                aggressive_stats = await self.cleanup_expired_keys()
                
                # Merge stats
                for key, value in aggressive_stats.items():
                    cleanup_stats[f"aggressive_{key}"] = value
                    
            finally:
                # Restore original policies
                self.retention_policies = original_policies
        
        # Get final memory status
        memory_status = await self.get_memory_status()
        
        return {
            'cleanup_stats': cleanup_stats,
            'memory_status': memory_status,
            'timestamp': datetime.utcnow().isoformat()
        }