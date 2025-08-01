"""Federation activity producer using Redis Streams"""
from __future__ import annotations
import json
import logging
from typing import Dict, Optional, Any, Union, List
from datetime import datetime
import redis
from flask import current_app, has_app_context

from app.federation.types import (
    ActivityObject, Priority, ActivityType, HttpUrl,
    StreamMessage, validate_activity, get_activity_priority,
    ValidationError
)

logger = logging.getLogger(__name__)

class FederationProducer:
    """Producer for queueing federation activities"""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client
        self._stream_names = {
            Priority.URGENT: 'federation:urgent',
            Priority.NORMAL: 'federation:normal',
            Priority.BULK: 'federation:bulk',
            Priority.RETRY: 'federation:retry'
        }
    
    def get_redis(self) -> redis.Redis:
        """Get Redis client, using app context if available"""
        if self.redis:
            return self.redis
        
        if has_app_context():
            # Get Redis URL from config
            redis_url = current_app.config.get('REDIS_URL', 'redis://localhost:6379/0')
            return redis.from_url(redis_url, decode_responses=True)
        
        raise RuntimeError("No Redis client available")
    
    def queue_activity(
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
                'timestamp': datetime.now(timezone.utc).isoformat(),
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
            redis_client = self.get_redis()
            stream_name = self._stream_names[priority]
            
            # Add with automatic ID and max length
            msg_id = redis_client.xadd(
                stream_name,
                stream_message,
                maxlen=100000  # Keep last 100k messages
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
    
    def queue_batch(
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
        redis_client = self.get_redis()
        
        with redis_client.pipeline() as pipe:
            for activity in activities:
                try:
                    # Validate activity
                    validated_activity = validate_activity(activity)
                    
                    # Determine priority if not specified
                    if priority is None:
                        act_priority = get_activity_priority(validated_activity['type'])
                    else:
                        act_priority = priority
                    
                    # Build message
                    message_data = {
                        'activity': validated_activity,
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'attempts': 0
                    }
                    
                    if destination:
                        message_data.update({
                            'destination': destination,
                            'private_key': private_key,
                            'key_id': key_id
                        })
                    
                    stream_message = {
                        'type': 'outbox.send' if destination else f"inbox.{validated_activity['type']}",
                        'data': json.dumps(message_data),
                        'priority': act_priority.value,
                        'attempts': 0,
                        'timestamp': message_data['timestamp']
                    }
                    
                    stream_name = self._stream_names[act_priority]
                    pipe.xadd(stream_name, stream_message, maxlen=100000)
                    
                except Exception as e:
                    logger.error(f"Failed to queue activity in batch: {e}")
                    # Continue with other activities
            
            # Execute pipeline
            results = pipe.execute()
            message_ids = [msg_id for msg_id in results if msg_id]
        
        return message_ids
    
    def queue_retry(
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
            datetime.now(timezone.utc).timestamp() + retry_after
        )
        
        stream_message: StreamMessage = {
            'type': 'retry',
            'data': json.dumps(retry_data),
            'priority': Priority.RETRY.value,
            'attempts': retry_data['attempts'],
            'timestamp': datetime., timezone().isoformat()
        }
        
        redis_client = self.get_redis()
        msg_id = redis_client.xadd(
            self._stream_names[Priority.RETRY],
            stream_message,
            maxlen=10000  # Smaller limit for retry queue
        )
        
        logger.info(
            f"Queued for retry (attempt {retry_data['attempts']}): {msg_id}",
            extra={'error': error, 'retry_after': retry_after}
        )
        
        return msg_id
    
    def get_stream_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all streams"""
        redis_client = self.get_redis()
        info = {}
        
        for priority, stream_name in self._stream_names.items():
            try:
                stream_info = redis_client.xinfo_stream(stream_name)
                info[priority.value] = {
                    'length': stream_info.get('length', 0),
                    'first_entry': stream_info.get('first-entry'),
                    'last_entry': stream_info.get('last-entry'),
                    'consumer_groups': len(stream_info.get('groups', []))
                }
            except redis.ResponseError:
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

def queue_activity(
    activity: Union[Dict[str, Any], ActivityObject],
    **kwargs
) -> str:
    """Convenience function to queue an activity"""
    producer = get_producer()
    return producer.queue_activity(activity, **kwargs)


def queue_cdn_flush(url: Union[str, List[str]]) -> bool:
    """Queue CDN cache flush task (synchronous wrapper)."""
    import asyncio
    from typing import List
    
    task = {
        'type': 'flush_cdn_cache',
        'url': url
    }
    
    # Run async function in sync context
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # Queue as low priority task
    try:
        producer = get_producer()
        producer.queue_activity(
            activity={'type': 'Service', 'name': 'cdn_flush', 'object': task},
            priority=Priority.BULK
        )
        return True
    except Exception as e:
        logger.error(f"Failed to queue CDN flush: {e}")
        return False