"""Activity handlers for different ActivityPub types"""
from __future__ import annotations
import logging
from typing import Dict, List, Tuple, Type, Optional, Any
from datetime import datetime

from app.federation.types import (
    BaseHandler, HandlerResponse, MessageId, ProcessingStatus,
    ProcessingContext, ActivityObject, ValidationError
)

logger = logging.getLogger(__name__)

# Handler registry
_handler_registry: Dict[str, Type[BaseHandler]] = {}


def register_handler(activity_type: str):
    """Decorator to register handlers"""
    def decorator(handler_class: Type[BaseHandler]) -> Type[BaseHandler]:
        _handler_registry[activity_type] = handler_class
        return handler_class
    return decorator


def get_handler_registry() -> Dict[str, Type[BaseHandler]]:
    """Get the handler registry"""
    return _handler_registry


class TaskHandler(BaseHandler[Dict[str, Any]]):
    """Handler for internal tasks (migrated from Celery)"""
    
    def can_handle(self, activity_type: str) -> bool:
        return activity_type.startswith('task.')
    
    async def handle(
        self,
        messages: List[Tuple[MessageId, Dict[str, Any]]]
    ) -> List[HandlerResponse]:
        """Handle task messages"""
        responses = []
        
        for msg_id, task_data in messages:
            try:
                task_name = task_data.get('task')
                kwargs = task_data.get('kwargs', {})
                
                # Import and execute the task
                # This maintains compatibility with existing task structure
                if task_name == 'vote_for_post':
                    from app.federation.tasks.likes import vote_for_post
                    vote_for_post(**kwargs)
                elif task_name == 'vote_for_reply':
                    from app.federation.tasks.likes import vote_for_reply
                    vote_for_reply(**kwargs)
                elif task_name == 'join_community':
                    from app.federation.tasks.follows import join_community
                    join_community(**kwargs)
                elif task_name == 'leave_community':
                    from app.federation.tasks.follows import leave_community
                    leave_community(**kwargs)
                # Add more tasks as they're migrated
                else:
                    raise ValueError(f"Unknown task: {task_name}")
                
                responses.append(HandlerResponse(
                    message_id=msg_id,
                    status=ProcessingStatus.SUCCESS,
                    processing_time=0.1  # We don't track this yet
                ))
                
            except Exception as e:
                logger.error(f"Task execution failed: {e}", exc_info=True)
                responses.append(HandlerResponse(
                    message_id=msg_id,
                    status=ProcessingStatus.FAILED,
                    error=str(e),
                    retry_after=60  # Retry after 1 minute
                ))
        
        return responses


@register_handler('inbox.Like')
@register_handler('inbox.Dislike')
class VoteHandler(BaseHandler[ActivityObject]):
    """Handler for Like/Dislike activities"""
    
    def can_handle(self, activity_type: str) -> bool:
        return activity_type in ('inbox.Like', 'inbox.Dislike')
    
    async def handle(
        self,
        messages: List[Tuple[MessageId, ActivityObject]]
    ) -> List[HandlerResponse]:
        """Process vote activities"""
        responses = []
        
        for msg_id, activity in messages:
            try:
                # Extract activity details
                actor = activity.get('actor')
                object_id = activity.get('object')
                activity_type = activity.get('type')
                
                if not actor or not object_id:
                    raise ValidationError("Missing required fields: actor or object")
                
                # Process the vote
                # TODO: Implement actual vote processing logic
                logger.info(f"Processing {activity_type} from {actor} on {object_id}")
                
                responses.append(HandlerResponse(
                    message_id=msg_id,
                    status=ProcessingStatus.SUCCESS
                ))
                
            except ValidationError as e:
                # Validation errors shouldn't be retried
                responses.append(HandlerResponse(
                    message_id=msg_id,
                    status=ProcessingStatus.FAILED,
                    error=str(e)
                ))
            except Exception as e:
                logger.error(f"Vote processing failed: {e}", exc_info=True)
                responses.append(HandlerResponse(
                    message_id=msg_id,
                    status=ProcessingStatus.FAILED,
                    error=str(e),
                    retry_after=300  # Retry after 5 minutes
                ))
        
        return responses


@register_handler('inbox.Follow')
class FollowHandler(BaseHandler[ActivityObject]):
    """Handler for Follow activities"""
    
    def can_handle(self, activity_type: str) -> bool:
        return activity_type == 'inbox.Follow'
    
    async def handle(
        self,
        messages: List[Tuple[MessageId, ActivityObject]]
    ) -> List[HandlerResponse]:
        """Process follow activities"""
        responses = []
        
        for msg_id, activity in messages:
            try:
                actor = activity.get('actor')
                object_id = activity.get('object')
                
                if not actor or not object_id:
                    raise ValidationError("Missing required fields: actor or object")
                
                # Process the follow
                logger.info(f"Processing Follow from {actor} to {object_id}")
                
                # TODO: Implement actual follow processing
                # - Verify actor signature
                # - Create/update follower relationship
                # - Send Accept activity back
                
                responses.append(HandlerResponse(
                    message_id=msg_id,
                    status=ProcessingStatus.SUCCESS
                ))
                
            except Exception as e:
                logger.error(f"Follow processing failed: {e}", exc_info=True)
                responses.append(HandlerResponse(
                    message_id=msg_id,
                    status=ProcessingStatus.FAILED,
                    error=str(e),
                    retry_after=300
                ))
        
        return responses


@register_handler('inbox.Create')
class CreateHandler(BaseHandler[ActivityObject]):
    """Handler for Create activities (posts, comments)"""
    
    def can_handle(self, activity_type: str) -> bool:
        return activity_type == 'inbox.Create'
    
    async def handle(
        self,
        messages: List[Tuple[MessageId, ActivityObject]]
    ) -> List[HandlerResponse]:
        """Process create activities"""
        responses = []
        
        for msg_id, activity in messages:
            try:
                actor = activity.get('actor')
                object_data = activity.get('object')
                
                if not actor or not object_data:
                    raise ValidationError("Missing required fields: actor or object")
                
                # Determine object type
                if isinstance(object_data, dict):
                    object_type = object_data.get('type', '').lower()
                else:
                    # Object is just an ID, we'd need to fetch it
                    object_type = 'unknown'
                
                logger.info(f"Processing Create of {object_type} from {actor}")
                
                # TODO: Implement actual create processing
                # - Verify actor signature
                # - Create post/comment in database
                # - Notify mentioned users
                # - Update community stats
                
                responses.append(HandlerResponse(
                    message_id=msg_id,
                    status=ProcessingStatus.SUCCESS
                ))
                
            except Exception as e:
                logger.error(f"Create processing failed: {e}", exc_info=True)
                responses.append(HandlerResponse(
                    message_id=msg_id,
                    status=ProcessingStatus.FAILED,
                    error=str(e),
                    retry_after=300
                ))
        
        return responses


@register_handler('outbox.send')
class OutboxHandler(BaseHandler[Dict[str, Any]]):
    """Handler for outgoing activities"""
    
    def can_handle(self, activity_type: str) -> bool:
        return activity_type == 'outbox.send'
    
    async def handle(
        self,
        messages: List[Tuple[MessageId, Dict[str, Any]]]
    ) -> List[HandlerResponse]:
        """Send outgoing activities"""
        responses = []
        
        for msg_id, outbox_data in messages:
            try:
                activity = outbox_data.get('activity')
                destination = outbox_data.get('destination')
                private_key = outbox_data.get('private_key')
                key_id = outbox_data.get('key_id')
                
                if not all([activity, destination, private_key, key_id]):
                    raise ValidationError("Missing required outbox fields")
                
                # Send the activity
                logger.info(f"Sending {activity.get('type')} to {destination}")
                
                # Use HTTP client from context
                response = await self.context.http_client.post(
                    destination,
                    json=activity,
                    headers={
                        'Content-Type': 'application/activity+json',
                        # TODO: Add HTTP signature
                    },
                    timeout=30.0
                )
                
                if response.status_code >= 200 and response.status_code < 300:
                    responses.append(HandlerResponse(
                        message_id=msg_id,
                        status=ProcessingStatus.SUCCESS
                    ))
                else:
                    # Temporary failure - retry
                    responses.append(HandlerResponse(
                        message_id=msg_id,
                        status=ProcessingStatus.FAILED,
                        error=f"HTTP {response.status_code}: {response.text[:200]}",
                        retry_after=300 if response.status_code < 500 else 3600
                    ))
                
            except httpx.TimeoutException:
                responses.append(HandlerResponse(
                    message_id=msg_id,
                    status=ProcessingStatus.FAILED,
                    error="Request timeout",
                    retry_after=600  # Retry after 10 minutes
                ))
            except Exception as e:
                logger.error(f"Outbox send failed: {e}", exc_info=True)
                responses.append(HandlerResponse(
                    message_id=msg_id,
                    status=ProcessingStatus.FAILED,
                    error=str(e),
                    retry_after=300
                ))
        
        return responses


# Register task handlers for all task types
for task_type in ['task.vote_for_post', 'task.vote_for_reply', 'task.join_community', 'task.leave_community']:
    register_handler(task_type)(TaskHandler)