"""Federation activity producer using Redis Streams"""
from __future__ import annotations
import json
import logging
from typing import Dict, Optional, Any, Union
from datetime import datetime
import aioredis
from flask import current_app, has_app_context

from app.federation.types import (
    ActivityObject, Priority, ActivityType, HttpUrl,
    StreamMessage, validate_activity, get_activity_priority,
    ValidationError
)

logger = logging.getLogger(__name__)

class FederationProducer:
    """Producer for queueing federation activities"""
    
    def __init__(self, redis_client: Optional[aioredis.Redis] = None):
        self.redis = redis_client
        self._stream_names = {
            Priority.URGENT: 'federation:urgent',
            Priority.NORMAL: 'federation:normal',
            Priority.BULK: 'federation:bulk',
            Priority.RETRY: 'federation:retry'
        }
    
    async def get_redis(self) -> aioredis.Redis:
        """Get Redis client, using app context if available"""
        if self.redis:
            return self.redis
        
        if has_app_context():
            # Use async Redis from app context
            return current_app.redis_async
        
        raise RuntimeError("No Redis client available")
    
    async def queue_activity(
        self,
        activity: Union[Dict[str, Any], ActivityObject],
        priority: Optional[Priority] = None,
        destination: Optional[HttpUrl] = None,
        private_key: Optional[str] = None,
        key_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> str:
        """
        Queue an activity for processing
        
        Args:
            activity: The ActivityPub activity
            priority: Override default priority
            destination: For outgoing activities
            private_key: For signing outgoing activities
            key_id: Key ID for signing
            request_id: Optional request tracking ID
            
        Returns:
            Message ID from Redis Stream
        """
        try:
            # Validate activity
            validated_activity = validate_activity(activity)
            
            # Determine priority if not specified
            if priority is None:
                priority = get_activity_priority(validated_activity['type'])
            
            # Determine message type
            if destination:
                message_type = 'outbox.send'
            else:
                message_type = f"inbox.{validated_activity['type']}"
            
            # Build message
            message_data = {
                'activity': validated_activity,
                'timestamp': datetime.utcnow().isoformat(),
                'attempts': 0
            }
            
            # Add outbox-specific fields
            if destination:
                message_data.update({
                    'destination': destination,
                    'private_key': private_key,
                    'key_id': key_id
                })
            
            # Create stream message
            stream_message: StreamMessage = {
                'type': message_type,
                'data': json.dumps(message_data),
                'priority': priority.value,
                'attempts': 0,
                'timestamp': message_data['timestamp']
            }
            
            if request_id:
                stream_message['request_id'] = request_id
            
            # Add to appropriate stream
            redis = await self.get_redis()
            stream_name = self._stream_names[priority]
            
            # Add with automatic ID and max length
            msg_id = await redis.xadd(
                stream_name,
                stream_message,
                maxlen=100000,  # Keep last 100k messages
                approximate=True  # Allow Redis to optimize
            )
            
            logger.info(
                f"Queued {message_type} to {stream_name}: {msg_id}",
                extra={
                    'activity_id': validated_activity.get('id'),
                    'activity_type': validated_activity['type'],
                    'priority': priority.value,
                    'destination': destination
                }
            )
            
            return msg_id
            
        except ValidationError as e:
            logger.error(f"Activity validation failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to queue activity: {e}", exc_info=True)
            raise
    
    async def queue_batch(
        self,
        activities: List[Union[Dict[str, Any], ActivityObject]],
        priority: Optional[Priority] = None,
        destination: Optional[HttpUrl] = None,
        private_key: Optional[str] = None,
        key_id: Optional[str] = None
    ) -> List[str]:
        """
        Queue multiple activities efficiently
        
        Returns:
            List of message IDs
        """
        message_ids = []
        
        # Use pipeline for efficiency
        redis = await self.get_redis()
        
        for activity in activities:
            try:
                msg_id = await self.queue_activity(
                    activity=activity,
                    priority=priority,
                    destination=destination,
                    private_key=private_key,
                    key_id=key_id
                )
                message_ids.append(msg_id)
            except Exception as e:
                logger.error(f"Failed to queue activity in batch: {e}")
                # Continue with other activities
        
        return message_ids
    
    async def queue_retry(
        self,
        original_message: Dict[str, Any],
        error: str,
        retry_after: int = 60
    ) -> str:
        """
        Queue a failed activity for retry
        
        Args:
            original_message: The original message data
            error: Error that occurred
            retry_after: Seconds to wait before retry
            
        Returns:
            Message ID for retry
        """
        retry_data = original_message.copy()
        retry_data['attempts'] = retry_data.get('attempts', 0) + 1
        retry_data['last_error'] = error
        retry_data['retry_after'] = retry_after
        retry_data['retry_at'] = (
            datetime.utcnow().timestamp() + retry_after
        )
        
        stream_message: StreamMessage = {
            'type': 'retry',
            'data': json.dumps(retry_data),
            'priority': Priority.RETRY.value,
            'attempts': retry_data['attempts'],
            'timestamp': datetime.utcnow().isoformat()
        }
        
        redis = await self.get_redis()
        msg_id = await redis.xadd(
            self._stream_names[Priority.RETRY],
            stream_message,
            maxlen=10000,  # Smaller limit for retry queue
            approximate=True
        )
        
        logger.info(
            f"Queued for retry (attempt {retry_data['attempts']}): {msg_id}",
            extra={'error': error, 'retry_after': retry_after}
        )
        
        return msg_id
    
    async def get_stream_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all streams"""
        redis = await self.get_redis()
        info = {}
        
        for priority, stream_name in self._stream_names.items():
            try:
                stream_info = await redis.xinfo_stream(stream_name)
                info[priority.value] = {
                    'length': stream_info.get('length', 0),
                    'first_entry': stream_info.get('first-entry'),
                    'last_entry': stream_info.get('last-entry'),
                    'consumer_groups': stream_info.get('groups', 0)
                }
            except aioredis.ResponseError:
                # Stream doesn't exist yet
                info[priority.value] = {
                    'length': 0,
                    'exists': False
                }
        
        return info


# Singleton instance for easy access
_producer: Optional[FederationProducer] = None

def get_producer() -> FederationProducer:
    """Get the singleton producer instance"""
    global _producer
    if _producer is None:
        _producer = FederationProducer()
    return _producer

async def queue_activity(
    activity: Union[Dict[str, Any], ActivityObject],
    **kwargs
) -> str:
    """Convenience function to queue an activity"""
    producer = get_producer()
    return await producer.queue_activity(activity, **kwargs)