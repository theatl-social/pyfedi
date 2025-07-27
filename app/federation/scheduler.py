"""
Task scheduler for Redis Streams-based federation system.

This module provides cron-like scheduling capabilities for recurring and one-time
tasks in the PeachPie federation system. It integrates with Redis Streams for
task execution and supports various scheduling patterns.

Features:
    - Cron expression support (e.g., "0 0 * * *" for daily at midnight)
    - One-time scheduled tasks
    - Interval-based scheduling (e.g., every 5 minutes)
    - Task persistence in Redis
    - Integration with existing stream processors
    - Admin interface for managing scheduled tasks
    - Timezone support

Example:
    >>> scheduler = TaskScheduler(redis_url="redis://localhost")
    >>> await scheduler.schedule_task(
    ...     name="cleanup_old_activities",
    ...     task_type="maintenance",
    ...     schedule="0 2 * * *",  # Daily at 2 AM
    ...     payload={"days_to_keep": 30}
    ... )
"""
from __future__ import annotations
import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple, Literal
from dataclasses import dataclass, asdict
from enum import Enum
import redis.asyncio as redis
from croniter import croniter
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


class ScheduleType(str, Enum):
    """Types of schedules supported"""
    CRON = "cron"
    INTERVAL = "interval"
    ONE_TIME = "one_time"


class TaskStatus(str, Enum):
    """Status of scheduled tasks"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ScheduledTask:
    """Represents a scheduled task"""
    id: str
    name: str
    task_type: str
    schedule_type: ScheduleType
    schedule: str  # Cron expression or interval
    payload: Dict[str, Any]
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    timezone: str = "UTC"
    max_retries: int = 3
    enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Redis storage"""
        data = asdict(self)
        # Convert datetime objects to ISO format
        for field in ['created_at', 'updated_at', 'last_run', 'next_run']:
            if data.get(field):
                data[field] = data[field].isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ScheduledTask:
        """Create from dictionary retrieved from Redis"""
        # Convert ISO strings back to datetime objects
        for field in ['created_at', 'updated_at', 'last_run', 'next_run']:
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field])
        # Convert string enums
        data['schedule_type'] = ScheduleType(data['schedule_type'])
        data['status'] = TaskStatus(data['status'])
        return cls(**data)


class TaskScheduler:
    """
    Main task scheduler for Redis Streams federation.
    
    This class manages scheduled tasks, determines when they should run,
    and publishes them to appropriate Redis Streams for processing.
    
    Attributes:
        redis_url: Redis connection URL
        task_key_prefix: Redis key prefix for scheduled tasks
        check_interval: How often to check for tasks to run (seconds)
    """
    
    def __init__(
        self,
        redis_url: str,
        task_key_prefix: str = "scheduler:task:",
        check_interval: int = 60  # Check every minute
    ) -> None:
        """
        Initialize the task scheduler.
        
        Args:
            redis_url: Redis connection URL
            task_key_prefix: Prefix for task keys in Redis
            check_interval: Interval between schedule checks
        """
        self.redis_url = redis_url
        self.task_key_prefix = task_key_prefix
        self.check_interval = check_interval
        self.redis: Optional[redis.Redis] = None
        self._running = False
        self._check_task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the scheduler"""
        logger.info("Starting task scheduler")
        self.redis = await redis.from_url(self.redis_url, decode_responses=True)
        self._running = True
        self._check_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Task scheduler started")
    
    async def stop(self) -> None:
        """Stop the scheduler"""
        logger.info("Stopping task scheduler")
        self._running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        if self.redis:
            await self.redis.close()
        logger.info("Task scheduler stopped")
    
    async def schedule_task(
        self,
        name: str,
        task_type: str,
        schedule: str,
        payload: Dict[str, Any],
        schedule_type: ScheduleType = ScheduleType.CRON,
        timezone: str = "UTC",
        max_retries: int = 3,
        enabled: bool = True
    ) -> ScheduledTask:
        """
        Schedule a new task.
        
        Args:
            name: Human-readable task name
            task_type: Type of task (e.g., 'maintenance', 'federation')
            schedule: Cron expression or interval specification
            payload: Task data to pass to processor
            schedule_type: Type of schedule (cron, interval, one_time)
            timezone: Timezone for cron schedules
            max_retries: Maximum retry attempts
            enabled: Whether task is enabled
            
        Returns:
            Created ScheduledTask instance
        """
        task = ScheduledTask(
            id=str(uuid.uuid4()),
            name=name,
            task_type=task_type,
            schedule_type=schedule_type,
            schedule=schedule,
            payload=payload,
            status=TaskStatus.ACTIVE if enabled else TaskStatus.PAUSED,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            timezone=timezone,
            max_retries=max_retries,
            enabled=enabled
        )
        
        # Calculate next run time
        task.next_run = self._calculate_next_run(task)
        
        # Store in Redis
        await self._save_task(task)
        
        logger.info(f"Scheduled task: {name} ({task.id})")
        return task
    
    async def update_task(
        self,
        task_id: str,
        **updates: Any
    ) -> Optional[ScheduledTask]:
        """Update an existing scheduled task"""
        task = await self.get_task(task_id)
        if not task:
            return None
        
        # Update fields
        for field, value in updates.items():
            if hasattr(task, field):
                setattr(task, field, value)
        
        task.updated_at = datetime.now(timezone.utc)
        
        # Recalculate next run if schedule changed
        if 'schedule' in updates or 'schedule_type' in updates:
            task.next_run = self._calculate_next_run(task)
        
        await self._save_task(task)
        return task
    
    async def delete_task(self, task_id: str) -> bool:
        """Delete a scheduled task"""
        key = f"{self.task_key_prefix}{task_id}"
        result = await self.redis.delete(key)
        return result > 0
    
    async def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Get a scheduled task by ID"""
        key = f"{self.task_key_prefix}{task_id}"
        data = await self.redis.get(key)
        if not data:
            return None
        return ScheduledTask.from_dict(json.loads(data))
    
    async def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        task_type: Optional[str] = None
    ) -> List[ScheduledTask]:
        """List all scheduled tasks with optional filtering"""
        tasks = []
        
        # Scan for all task keys
        cursor = 0
        pattern = f"{self.task_key_prefix}*"
        
        while True:
            cursor, keys = await self.redis.scan(
                cursor, match=pattern, count=100
            )
            
            if keys:
                # Get all task data
                pipeline = self.redis.pipeline()
                for key in keys:
                    pipeline.get(key)
                results = await pipeline.execute()
                
                for data in results:
                    if data:
                        task = ScheduledTask.from_dict(json.loads(data))
                        
                        # Apply filters
                        if status and task.status != status:
                            continue
                        if task_type and task.task_type != task_type:
                            continue
                        
                        tasks.append(task)
            
            if cursor == 0:
                break
        
        # Sort by next run time
        tasks.sort(key=lambda t: t.next_run or datetime.max.replace(tzinfo=timezone.utc))
        return tasks
    
    async def pause_task(self, task_id: str) -> bool:
        """Pause a scheduled task"""
        task = await self.get_task(task_id)
        if not task:
            return False
        
        task.status = TaskStatus.PAUSED
        task.enabled = False
        task.updated_at = datetime.now(timezone.utc)
        
        await self._save_task(task)
        return True
    
    async def resume_task(self, task_id: str) -> bool:
        """Resume a paused task"""
        task = await self.get_task(task_id)
        if not task:
            return False
        
        task.status = TaskStatus.ACTIVE
        task.enabled = True
        task.updated_at = datetime.now(timezone.utc)
        task.next_run = self._calculate_next_run(task)
        
        await self._save_task(task)
        return True
    
    async def _scheduler_loop(self) -> None:
        """Main scheduler loop that checks for tasks to run"""
        while self._running:
            try:
                await self._check_and_run_tasks()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(self.check_interval)
    
    async def _check_and_run_tasks(self) -> None:
        """Check for tasks that need to run and execute them"""
        now = datetime.now(timezone.utc)
        tasks = await self.list_tasks(status=TaskStatus.ACTIVE)
        
        for task in tasks:
            if not task.next_run:
                continue
                
            # Ensure next_run is timezone-aware
            if task.next_run.tzinfo is None:
                task.next_run = task.next_run.replace(tzinfo=timezone.utc)
            
            if task.next_run <= now:
                await self._execute_task(task)
    
    async def _execute_task(self, task: ScheduledTask) -> None:
        """Execute a scheduled task"""
        logger.info(f"Executing scheduled task: {task.name} ({task.id})")
        
        try:
            # Prepare task message
            message = {
                "scheduled_task_id": task.id,
                "task_name": task.name,
                "task_type": task.task_type,
                "payload": task.payload,
                "scheduled_at": task.next_run.isoformat() if task.next_run else None,
                "executed_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Determine which stream to publish to based on task type
            stream_name = self._get_stream_for_task_type(task.task_type)
            
            # Add to Redis Stream
            await self.redis.xadd(
                stream_name,
                message,
                maxlen=10000  # Keep last 10k messages
            )
            
            # Update task record
            task.last_run = datetime.now(timezone.utc)
            task.run_count += 1
            
            # Calculate next run
            if task.schedule_type == ScheduleType.ONE_TIME:
                task.status = TaskStatus.COMPLETED
                task.enabled = False
                task.next_run = None
            else:
                task.next_run = self._calculate_next_run(task)
            
            await self._save_task(task)
            logger.info(f"Successfully executed task: {task.name}")
            
        except Exception as e:
            logger.error(f"Error executing task {task.name}: {e}", exc_info=True)
            task.error_count += 1
            task.last_error = str(e)
            
            # Disable task if too many errors
            if task.error_count >= task.max_retries:
                task.status = TaskStatus.FAILED
                task.enabled = False
                logger.error(f"Task {task.name} disabled after {task.error_count} errors")
            
            await self._save_task(task)
    
    def _calculate_next_run(self, task: ScheduledTask) -> Optional[datetime]:
        """Calculate the next run time for a task"""
        if not task.enabled or task.status != TaskStatus.ACTIVE:
            return None
        
        now = datetime.now(timezone.utc)
        
        if task.schedule_type == ScheduleType.CRON:
            # Parse cron expression with timezone
            tz = ZoneInfo(task.timezone)
            local_now = now.astimezone(tz)
            cron = croniter(task.schedule, local_now)
            next_local = cron.get_next(datetime)
            return next_local.astimezone(timezone.utc)
            
        elif task.schedule_type == ScheduleType.INTERVAL:
            # Parse interval (e.g., "5m", "1h", "1d")
            interval = self._parse_interval(task.schedule)
            if task.last_run:
                return task.last_run + interval
            else:
                return now + interval
                
        elif task.schedule_type == ScheduleType.ONE_TIME:
            # For one-time tasks, schedule is ISO datetime
            scheduled_time = datetime.fromisoformat(task.schedule)
            if scheduled_time.tzinfo is None:
                scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
            return scheduled_time if scheduled_time > now else None
        
        return None
    
    def _parse_interval(self, interval_str: str) -> timedelta:
        """Parse interval string like '5m', '1h', '1d' into timedelta"""
        units = {
            's': 'seconds',
            'm': 'minutes',
            'h': 'hours',
            'd': 'days',
            'w': 'weeks'
        }
        
        # Extract number and unit
        import re
        match = re.match(r'^(\d+)([smhdw])$', interval_str)
        if not match:
            raise ValueError(f"Invalid interval format: {interval_str}")
        
        amount = int(match.group(1))
        unit = units.get(match.group(2))
        
        if not unit:
            raise ValueError(f"Unknown interval unit: {match.group(2)}")
        
        return timedelta(**{unit: amount})
    
    def _get_stream_for_task_type(self, task_type: str) -> str:
        """Determine which Redis Stream to publish task to"""
        # Map task types to streams
        stream_mapping = {
            "maintenance": "stream:maintenance:tasks",
            "federation": "stream:federation:tasks",
            "cleanup": "stream:cleanup:tasks",
            "analytics": "stream:analytics:tasks",
            "notification": "stream:notification:tasks"
        }
        
        return stream_mapping.get(task_type, "stream:scheduled:tasks")
    
    async def _save_task(self, task: ScheduledTask) -> None:
        """Save task to Redis"""
        key = f"{self.task_key_prefix}{task.id}"
        await self.redis.set(key, json.dumps(task.to_dict()))
    
    # Admin interface methods
    async def get_scheduler_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics for admin dashboard"""
        tasks = await self.list_tasks()
        
        stats = {
            "total_tasks": len(tasks),
            "active_tasks": sum(1 for t in tasks if t.status == TaskStatus.ACTIVE),
            "paused_tasks": sum(1 for t in tasks if t.status == TaskStatus.PAUSED),
            "failed_tasks": sum(1 for t in tasks if t.status == TaskStatus.FAILED),
            "completed_tasks": sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
            "tasks_by_type": {},
            "upcoming_tasks": [],
            "recent_executions": []
        }
        
        # Count by type
        for task in tasks:
            stats["tasks_by_type"][task.task_type] = \
                stats["tasks_by_type"].get(task.task_type, 0) + 1
        
        # Get upcoming tasks (next 10)
        active_tasks = [t for t in tasks if t.status == TaskStatus.ACTIVE and t.next_run]
        active_tasks.sort(key=lambda t: t.next_run)
        stats["upcoming_tasks"] = [
            {
                "id": t.id,
                "name": t.name,
                "type": t.task_type,
                "next_run": t.next_run.isoformat() if t.next_run else None
            }
            for t in active_tasks[:10]
        ]
        
        # Get recent executions
        executed_tasks = [t for t in tasks if t.last_run]
        executed_tasks.sort(key=lambda t: t.last_run, reverse=True)
        stats["recent_executions"] = [
            {
                "id": t.id,
                "name": t.name,
                "type": t.task_type,
                "last_run": t.last_run.isoformat() if t.last_run else None,
                "status": t.status.value,
                "run_count": t.run_count
            }
            for t in executed_tasks[:10]
        ]
        
        return stats