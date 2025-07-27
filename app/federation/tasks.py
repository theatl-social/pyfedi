"""Task dispatch system using Redis Streams instead of Celery"""
from __future__ import annotations
import json
import logging
from typing import Dict, Any, Optional, Callable, TypeVar, ParamSpec
from datetime import datetime
from flask import current_app, has_app_context
import redis

from app.federation.types import Priority, ActivityType, get_activity_priority
from app.federation.producer import get_producer

logger = logging.getLogger(__name__)

# Type variables for better typing
P = ParamSpec('P')
R = TypeVar('R')

# Task registry
_task_registry: Dict[str, 'FederationTask'] = {}

class FederationTask:
    """Wrapper for tasks that can be dispatched to Redis Streams"""
    
    def __init__(
        self, 
        func: Callable[P, R],
        name: Optional[str] = None,
        priority: Priority = Priority.NORMAL
    ):
        self.func = func
        self.name = name or func.__name__
        self.priority = priority
        
        # Register task
        _task_registry[self.name] = self
    
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """Direct synchronous call"""
        return self.func(*args, **kwargs)
    
    async def delay(self, *args: Any, **kwargs: Any) -> str:
        """Queue task for async execution (Celery-compatible API)"""
        task_data = {
            'task': self.name,
            'args': args,
            'kwargs': kwargs,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Queue to Redis Stream
        producer = get_producer()
        msg_id = await producer.queue_activity(
            activity={
                'type': 'Task',
                'id': f'task/{self.name}/{datetime.utcnow().timestamp()}',
                'actor': 'system',
                'object': task_data
            },
            priority=self.priority
        )
        
        logger.info(f"Queued task {self.name} with id {msg_id}")
        return msg_id
    
    def apply_async(self, args=None, kwargs=None, **options) -> str:
        """Queue task with options (Celery-compatible API)"""
        # For now, just use delay - can be extended later
        return self.delay(*(args or []), **(kwargs or {}))

def task(
    name: Optional[str] = None, 
    priority: Priority = Priority.NORMAL
) -> Callable[[Callable[P, R]], FederationTask]:
    """Decorator to create a task (replaces @celery.task)"""
    def decorator(func: Callable[P, R]) -> FederationTask:
        return FederationTask(func, name=name, priority=priority)
    return decorator

def task_selector(task_key: str, send_async: bool = True, **kwargs) -> Any:
    """
    Dispatch tasks using Redis Streams instead of Celery
    
    This maintains compatibility with existing code while replacing
    the underlying implementation.
    """
    # Handle email tasks specially since they're in app.email
    if task_key == 'send_async_email':
        from app.email import send_async_email
        if not send_async:
            return send_async_email(**kwargs)
        # Queue for async
        task_data = {
            'task': task_key,
            'kwargs': kwargs,
            'timestamp': datetime.utcnow().isoformat()
        }
        # Get Redis client (synchronous for Flask compatibility)
        if has_app_context():
            redis_client = current_app.redis_client
        else:
            redis_client = redis.from_url(current_app.config.get('REDIS_URL', 'redis://localhost:6379/0'))
        
        msg_id = redis_client.xadd(
            'federation:normal',
            {
                'type': f'task.{task_key}',
                'data': json.dumps(task_data),
                'priority': Priority.NORMAL.value,
                'attempts': 0,
                'timestamp': task_data['timestamp']
            },
            maxlen=100000,
            approximate=True
        )
        return msg_id
    
    # Import tasks here to avoid circular imports
    from app.federation.tasks.follows import join_community, leave_community
    from app.federation.tasks.likes import vote_for_post, vote_for_reply
    from app.federation.tasks.notes import make_reply, edit_reply
    from app.federation.tasks.deletes import (
        delete_reply, restore_reply, delete_post, restore_post, 
        delete_community, restore_community, delete_posts_with_blocked_images
    )
    from app.federation.tasks.flags import report_reply, report_post
    from app.federation.tasks.pages import make_post, edit_post
    from app.federation.tasks.locks import lock_post, unlock_post
    from app.federation.tasks.adds import sticky_post, add_mod
    from app.federation.tasks.removes import unsticky_post, remove_mod
    from app.federation.tasks.groups import edit_community
    from app.federation.tasks.users import check_user_application
    from app.federation.tasks.blocks import (
        ban_from_community, unban_from_community, 
        ban_from_site, unban_from_site
    )
    from app.federation.tasks.activitypub import (
        process_inbox_request, process_delete_request
    )
    
    tasks = {
        'join_community': join_community,
        'leave_community': leave_community,
        'vote_for_post': vote_for_post,
        'vote_for_reply': vote_for_reply,
        'make_reply': make_reply,
        'edit_reply': edit_reply,
        'delete_reply': delete_reply,
        'restore_reply': restore_reply,
        'report_reply': report_reply,
        'make_post': make_post,
        'edit_post': edit_post,
        'delete_post': delete_post,
        'restore_post': restore_post,
        'report_post': report_post,
        'lock_post': lock_post,
        'unlock_post': unlock_post,
        'sticky_post': sticky_post,
        'unsticky_post': unsticky_post,
        'edit_community': edit_community,
        'delete_community': delete_community,
        'restore_community': restore_community,
        'delete_posts_with_blocked_images': delete_posts_with_blocked_images,
        'check_application': check_user_application,
        'ban_from_community': ban_from_community,
        'unban_from_community': unban_from_community,
        'ban_from_site': ban_from_site,
        'unban_from_site': unban_from_site,
        'add_mod': add_mod,
        'remove_mod': remove_mod,
        'process_inbox_request': process_inbox_request,
        'process_delete_request': process_delete_request,
    }
    
    if task_key not in tasks:
        raise ValueError(f"Unknown task: {task_key}")
    
    task_func = tasks[task_key]
    
    # In debug mode or when explicitly synchronous, run directly
    if current_app.debug:
        send_async = False
        logger.info(f'task_selector: debug mode, forcing sync execution for {task_key}')
    
    if not send_async:
        logger.info(f'task_selector: executing {task_key} synchronously with kwargs: {kwargs}')
        return task_func(send_async=send_async, **kwargs)
    
    # Queue for async execution
    logger.info(f'task_selector: dispatching {task_key} async with kwargs: {kwargs}')
    
    # For now, use synchronous Redis to queue (will be processed by async workers)
    # This maintains Flask compatibility
    task_data = {
        'task': task_key,
        'kwargs': {'send_async': send_async, **kwargs},
        'timestamp': datetime.utcnow().isoformat()
    }
    
    # Determine priority based on task type
    priority_map = {
        'vote_for_post': Priority.URGENT,
        'vote_for_reply': Priority.URGENT,
        'join_community': Priority.URGENT,
        'leave_community': Priority.URGENT,
        'delete_posts_with_blocked_images': Priority.BULK,
    }
    priority = priority_map.get(task_key, Priority.NORMAL)
    
    # Get Redis client (synchronous for Flask compatibility)
    if has_app_context():
        redis_client = current_app.redis_client
    else:
        redis_client = redis.from_url(current_app.config.get('REDIS_URL', 'redis://localhost:6379/0'))
    
    # Add to appropriate stream
    stream_name = f'federation:{priority.value}'
    msg_id = redis_client.xadd(
        stream_name,
        {
            'type': f'task.{task_key}',
            'data': json.dumps(task_data),
            'priority': priority.value,
            'attempts': 0,
            'timestamp': task_data['timestamp']
        },
        maxlen=100000,
        approximate=True
    )
    
    logger.info(f'task_selector: Task {task_key} queued to {stream_name} with id={msg_id}')
    return msg_id

# Export for backward compatibility
__all__ = ['task', 'task_selector', 'FederationTask']