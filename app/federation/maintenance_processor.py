"""
Maintenance task processor for scheduled maintenance activities.

This module handles scheduled maintenance tasks such as:
- Cleaning up old activities
- Archiving federation logs
- Updating instance statistics
- Purging expired data
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
import redis.asyncio as redis
from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActivityPubLog, Instance, User, Post, PostReply
from app.utils import utcnow

logger = logging.getLogger(__name__)


class MaintenanceProcessor:
    """
    Processor for scheduled maintenance tasks.
    
    This class listens to the maintenance task stream and executes
    various maintenance operations based on the task type.
    """
    
    def __init__(
        self,
        redis_client: redis.Redis,
        async_session_maker,
        stream_name: str = "stream:maintenance:tasks"
    ):
        """
        Initialize the maintenance processor.
        
        Args:
            redis_client: Redis client for stream operations
            async_session_maker: SQLAlchemy async session factory
            stream_name: Name of the Redis stream to listen to
        """
        self.redis = redis_client
        self.async_session_maker = async_session_maker
        self.stream_name = stream_name
        self.consumer_group = "maintenance-group"
        self.consumer_name = "maintenance-worker-1"
        self._running = False
    
    async def start(self) -> None:
        """Start the maintenance processor"""
        logger.info("Starting maintenance processor")
        
        # Create consumer group
        try:
            await self.redis.xgroup_create(
                self.stream_name,
                self.consumer_group,
                id='0'
            )
        except redis.ResponseError:
            # Group already exists
            pass
        
        self._running = True
        await self._process_loop()
    
    async def stop(self) -> None:
        """Stop the maintenance processor"""
        logger.info("Stopping maintenance processor")
        self._running = False
    
    async def _process_loop(self) -> None:
        """Main processing loop"""
        while self._running:
            try:
                # Read from stream
                messages = await self.redis.xreadgroup(
                    self.consumer_group,
                    self.consumer_name,
                    {self.stream_name: '>'},
                    count=1,
                    block=5000  # 5 second timeout
                )
                
                if messages:
                    for stream, stream_messages in messages:
                        for message_id, data in stream_messages:
                            await self._process_message(message_id, data)
                
            except Exception as e:
                logger.error(f"Error in maintenance processor loop: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    async def _process_message(self, message_id: str, data: Dict[str, Any]) -> None:
        """Process a single maintenance message"""
        try:
            task_name = data.get('task_name', 'unknown')
            payload = data.get('payload', {})
            
            logger.info(f"Processing maintenance task: {task_name}")
            
            # Route to appropriate handler
            handlers = {
                'cleanup_old_activities': self._cleanup_old_activities,
                'archive_federation_logs': self._archive_federation_logs,
                'update_instance_stats': self._update_instance_stats,
                'cleanup_orphaned_data': self._cleanup_orphaned_data,
                'purge_deleted_content': self._purge_deleted_content,
                'vacuum_database': self._vacuum_database,
            }
            
            handler = handlers.get(task_name)
            if handler:
                await handler(payload)
                logger.info(f"Completed maintenance task: {task_name}")
            else:
                logger.warning(f"Unknown maintenance task: {task_name}")
            
            # Acknowledge message
            await self.redis.xack(self.stream_name, self.consumer_group, message_id)
            
        except Exception as e:
            logger.error(f"Error processing maintenance task: {e}", exc_info=True)
            # Message will be redelivered on failure
    
    async def _cleanup_old_activities(self, payload: Dict[str, Any]) -> None:
        """Clean up old activity logs"""
        days_to_keep = payload.get('days_to_keep', 30)
        batch_size = payload.get('batch_size', 1000)
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
        
        async with self.async_session_maker() as session:
            # Count records to delete
            count_query = select(func.count(ActivityPubLog.id)).where(
                ActivityPubLog.timestamp < cutoff_date
            )
            total_count = await session.scalar(count_query)
            
            logger.info(f"Found {total_count} activity logs older than {days_to_keep} days")
            
            if total_count == 0:
                return
            
            # Delete in batches
            deleted_total = 0
            while deleted_total < total_count:
                # Get batch of IDs to delete
                id_query = select(ActivityPubLog.id).where(
                    ActivityPubLog.timestamp < cutoff_date
                ).limit(batch_size)
                
                result = await session.execute(id_query)
                ids_to_delete = [row[0] for row in result]
                
                if not ids_to_delete:
                    break
                
                # Delete batch
                delete_query = delete(ActivityPubLog).where(
                    ActivityPubLog.id.in_(ids_to_delete)
                )
                await session.execute(delete_query)
                await session.commit()
                
                deleted_total += len(ids_to_delete)
                logger.info(f"Deleted {deleted_total}/{total_count} old activity logs")
                
                # Small delay to avoid overloading
                await asyncio.sleep(0.1)
    
    async def _archive_federation_logs(self, payload: Dict[str, Any]) -> None:
        """Archive old federation logs to external storage"""
        # This would typically involve:
        # 1. Query old logs
        # 2. Export to S3/external storage
        # 3. Delete from database
        logger.info("Federation log archival not yet implemented")
    
    async def _update_instance_stats(self, payload: Dict[str, Any]) -> None:
        """Update instance statistics"""
        async with self.async_session_maker() as session:
            # Get all active instances
            instances_query = select(Instance).where(
                Instance.active == True
            )
            result = await session.execute(instances_query)
            instances = result.scalars().all()
            
            for instance in instances:
                try:
                    # Update user count
                    user_count_query = select(func.count(User.id)).where(
                        User.instance_id == instance.id,
                        User.active == True
                    )
                    instance.user_count = await session.scalar(user_count_query) or 0
                    
                    # Update post count
                    post_count_query = select(func.count(Post.id)).where(
                        Post.instance_id == instance.id,
                        Post.deleted == False
                    )
                    instance.post_count = await session.scalar(post_count_query) or 0
                    
                    # Update last active
                    last_activity_query = select(func.max(Post.created_at)).where(
                        Post.instance_id == instance.id
                    )
                    last_activity = await session.scalar(last_activity_query)
                    if last_activity:
                        instance.last_active = last_activity
                    
                    logger.info(
                        f"Updated stats for {instance.domain}: "
                        f"users={instance.user_count}, posts={instance.post_count}"
                    )
                    
                except Exception as e:
                    logger.error(f"Error updating stats for {instance.domain}: {e}")
            
            await session.commit()
    
    async def _cleanup_orphaned_data(self, payload: Dict[str, Any]) -> None:
        """Clean up orphaned data (posts without users, etc.)"""
        async with self.async_session_maker() as session:
            # Find orphaned posts (where user has been deleted)
            orphaned_posts_query = select(Post).where(
                Post.user_id.notin_(
                    select(User.id)
                )
            )
            result = await session.execute(orphaned_posts_query)
            orphaned_posts = result.scalars().all()
            
            if orphaned_posts:
                logger.info(f"Found {len(orphaned_posts)} orphaned posts")
                for post in orphaned_posts:
                    post.deleted = True
                    post.deleted_at = utcnow()
                
                await session.commit()
            
            # Similarly for comments
            orphaned_comments_query = select(Comment).where(
                Comment.user_id.notin_(
                    select(User.id)
                )
            )
            result = await session.execute(orphaned_comments_query)
            orphaned_comments = result.scalars().all()
            
            if orphaned_comments:
                logger.info(f"Found {len(orphaned_comments)} orphaned comments")
                for comment in orphaned_comments:
                    comment.deleted = True
                    comment.deleted_at = utcnow()
                
                await session.commit()
    
    async def _purge_deleted_content(self, payload: Dict[str, Any]) -> None:
        """Permanently remove soft-deleted content after retention period"""
        days_to_retain = payload.get('days_to_retain', 90)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_retain)
        
        async with self.async_session_maker() as session:
            # Delete old soft-deleted posts
            delete_posts_query = delete(Post).where(
                Post.deleted == True,
                Post.deleted_at < cutoff_date
            )
            result = await session.execute(delete_posts_query)
            posts_deleted = result.rowcount
            
            # Delete old soft-deleted comments
            delete_comments_query = delete(Comment).where(
                Comment.deleted == True,
                Comment.deleted_at < cutoff_date
            )
            result = await session.execute(delete_comments_query)
            comments_deleted = result.rowcount
            
            await session.commit()
            
            logger.info(
                f"Purged {posts_deleted} posts and {comments_deleted} comments "
                f"deleted more than {days_to_retain} days ago"
            )
    
    async def _vacuum_database(self, payload: Dict[str, Any]) -> None:
        """Run VACUUM on PostgreSQL to reclaim space"""
        # Note: VACUUM cannot run inside a transaction
        logger.info("Database VACUUM should be run separately from application")
        # This could trigger an external process or scheduled job