"""
Database Archival Handler for Redis Lifecycle Manager

This module provides database archival functionality for important data
before it expires from Redis. It ensures critical information like failures
and DLQ messages are preserved for analysis and debugging.

Example:
    >>> from app.federation.archival_handler import DatabaseArchivalHandler
    >>> handler = DatabaseArchivalHandler()
    >>> await handler.archive(data, DataCategory.FAILED_TASK, session)
"""

from __future__ import annotations
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, and_, func

from app.federation.lifecycle_manager import DataCategory
from app.models import Instance, ActivityPubLog

# Type aliases
type ArchiveId = int
type JsonData = Dict[str, Any]


class ArchivedActivity(ActivityPubLog):
    """
    Extended model for archived activities with additional metadata.
    
    This uses the existing ActivityPubLog table but adds semantic meaning
    for archived/failed activities.
    """
    
    @classmethod
    async def create_from_archive(
        cls,
        data: JsonData,
        category: DataCategory,
        session: AsyncSession
    ) -> ArchivedActivity:
        """
        Create an archived activity record from Redis data.
        
        Args:
            data: Data to archive
            category: Category of the archived data
            session: Database session
            
        Returns:
            Created ArchivedActivity instance
        """
        # Extract activity information
        activity_data = data.get('content', data.get('message', {}))
        if isinstance(activity_data, str):
            try:
                activity_data = json.loads(activity_data)
            except json.JSONDecodeError:
                activity_data = {'raw': activity_data}
        
        # Determine activity details
        activity_type = activity_data.get('activity', {}).get('type', 'Unknown')
        activity_id = activity_data.get('activity', {}).get('id', data.get('redis_key', 'unknown'))
        
        # Map category to result
        result_map = {
            DataCategory.FAILED_TASK: 'failure',
            DataCategory.DLQ_MESSAGE: 'dlq',
            DataCategory.COMPLETED_TASK: 'success',
        }
        result = result_map.get(category, 'archived')
        
        # Extract destination for instance lookup
        destination = activity_data.get('destination', '')
        instance_id = None
        if destination:
            from urllib.parse import urlparse
            domain = urlparse(destination).netloc
            if domain:
                instance = await session.execute(
                    select(Instance).where(Instance.domain == domain)
                )
                instance_obj = instance.scalar_one_or_none()
                if instance_obj:
                    instance_id = instance_obj.id
        
        # Create the archived record
        archived = cls(
            direction='out',  # Most archived activities are outgoing
            activity_type=activity_type,
            activity_id=activity_id[:100],  # Limit length
            activity_json=json.dumps(activity_data),
            result=result,
            exception_message=data.get('reason', '') or data.get('exception_history', [''])[-1:][0] if data.get('exception_history') else '',
            instance_id=instance_id,
            created_at=datetime.utcnow()
        )
        
        session.add(archived)
        return archived


class DatabaseArchivalHandler:
    """
    Handles archiving of Redis data to the database.
    
    This class implements the ArchivalProtocol and provides methods to
    archive different types of data from Redis to permanent database storage.
    """
    
    def __init__(self) -> None:
        """Initialize the DatabaseArchivalHandler."""
        self.logger = logging.getLogger(__name__)
    
    async def archive(
        self,
        data: JsonData,
        category: DataCategory,
        session: AsyncSession
    ) -> bool:
        """
        Archive data to the database based on its category.
        
        Args:
            data: Data to archive
            category: Category of data being archived
            session: Database session to use
            
        Returns:
            True if archival was successful, False otherwise
            
        Example:
            >>> success = await handler.archive(
            ...     {'message': {...}, 'reason': 'max_retries'},
            ...     DataCategory.DLQ_MESSAGE,
            ...     session
            ... )
        """
        try:
            if category in [DataCategory.FAILED_TASK, DataCategory.DLQ_MESSAGE]:
                # Archive as ActivityPubLog entry
                await ArchivedActivity.create_from_archive(data, category, session)
                await session.commit()
                
                self.logger.info(
                    f"Archived {category.value} to database: "
                    f"{data.get('redis_key', data.get('message_id', 'unknown'))}"
                )
                return True
                
            elif category == DataCategory.STREAM_MESSAGE:
                # For stream messages, only archive if they're important failures
                content = data.get('content', {})
                if content.get('status') == 'failed':
                    await ArchivedActivity.create_from_archive(data, category, session)
                    await session.commit()
                    return True
                    
            # Other categories don't need archival
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to archive {category.value}: {e}")
            await session.rollback()
            return False
    
    async def get_archived_stats(
        self,
        session: AsyncSession,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get statistics about archived activities.
        
        Args:
            session: Database session
            days: Number of days to look back
            
        Returns:
            Dictionary containing archive statistics
            
        Example:
            >>> stats = await handler.get_archived_stats(session, days=30)
            >>> print(f"Total archived: {stats['total_count']}")
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        # Get counts by result type
        result = await session.execute(
            select(
                TypedActivityPubLog.result,
                func.count(TypedActivityPubLog.id).label('count')
            )
            .where(TypedActivityPubLog.created_at >= cutoff)
            .where(TypedActivityPubLog.result.in_(['failure', 'dlq', 'archived']))
            .group_by(TypedActivityPubLog.result)
        )
        
        counts_by_result = {row.result: row.count for row in result}
        
        # Get counts by activity type
        result = await session.execute(
            select(
                TypedActivityPubLog.activity_type,
                func.count(TypedActivityPubLog.id).label('count')
            )
            .where(TypedActivityPubLog.created_at >= cutoff)
            .where(TypedActivityPubLog.result.in_(['failure', 'dlq', 'archived']))
            .group_by(TypedActivityPubLog.activity_type)
        )
        
        counts_by_type = {row.activity_type: row.count for row in result}
        
        # Get most common failure reasons
        result = await session.execute(
            select(
                TypedActivityPubLog.exception_message,
                func.count(TypedActivityPubLog.id).label('count')
            )
            .where(TypedActivityPubLog.created_at >= cutoff)
            .where(TypedActivityPubLog.result == 'failure')
            .where(TypedActivityPubLog.exception_message.isnot(None))
            .group_by(TypedActivityPubLog.exception_message)
            .order_by(func.count(TypedActivityPubLog.id).desc())
            .limit(10)
        )
        
        top_failures = [
            {'reason': row.exception_message[:100], 'count': row.count}
            for row in result
        ]
        
        return {
            'total_count': sum(counts_by_result.values()),
            'counts_by_result': counts_by_result,
            'counts_by_type': counts_by_type,
            'top_failure_reasons': top_failures,
            'date_range': {
                'from': cutoff.isoformat(),
                'to': datetime.utcnow().isoformat()
            }
        }
    
    async def cleanup_old_archives(
        self,
        session: AsyncSession,
        days_to_keep: int = 90
    ) -> int:
        """
        Clean up archived records older than specified days.
        
        Args:
            session: Database session
            days_to_keep: Number of days of archives to keep
            
        Returns:
            Number of records deleted
            
        Example:
            >>> deleted = await handler.cleanup_old_archives(session, 180)
            >>> print(f"Deleted {deleted} old archive records")
        """
        cutoff = datetime.utcnow() - timedelta(days=days_to_keep)
        
        # Delete old archived records
        result = await session.execute(
            select(TypedActivityPubLog)
            .where(TypedActivityPubLog.created_at < cutoff)
            .where(TypedActivityPubLog.result.in_(['failure', 'dlq', 'archived']))
        )
        
        records = result.scalars().all()
        count = len(records)
        
        for record in records:
            session.delete(record)
        
        await session.commit()
        
        if count > 0:
            self.logger.info(f"Deleted {count} archived records older than {days_to_keep} days")
        
        return count