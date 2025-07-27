"""Stream processor for handling federation activities"""
from __future__ import annotations
import asyncio
import json
import logging
import signal
import time
from typing import Dict, List, Tuple, Optional, Any, Set
from datetime import datetime
import aioredis
import httpx
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.federation.types import (
    StreamConfig, ProcessingContext, ProcessingMetrics, HandlerResponse,
    MessageId, ProcessingStatus, StreamMessage, Priority, ValidationError
)
from app.federation.handlers import get_handler_registry

logger = logging.getLogger(__name__)


class FederationStreamProcessor:
    """Main processor for Redis Streams"""
    
    def __init__(
        self,
        redis_url: str,
        database_url: str,
        consumer_name: str = 'worker-1',
        max_batch_size: int = 10,
        block_ms: int = 1000
    ):
        self.redis_url = redis_url
        self.database_url = database_url
        self.consumer_name = consumer_name
        self.max_batch_size = max_batch_size
        self.block_ms = block_ms
        
        # Will be initialized in start()
        self.redis: Optional[aioredis.Redis] = None
        self.http_client: Optional[httpx.AsyncClient] = None
        self.async_session_maker: Optional[sessionmaker] = None
        
        # Stream configurations
        self.stream_configs = {
            Priority.URGENT: StreamConfig(
                name='federation:urgent',
                consumer_group='federation-workers',
                batch_size=5,
                block_ms=100,  # Short block for urgent
                max_retries=5
            ),
            Priority.NORMAL: StreamConfig(
                name='federation:normal',
                consumer_group='federation-workers',
                batch_size=10,
                block_ms=1000,
                max_retries=3
            ),
            Priority.BULK: StreamConfig(
                name='federation:bulk',
                consumer_group='federation-workers',
                batch_size=20,
                block_ms=5000,
                max_retries=2
            ),
            Priority.RETRY: StreamConfig(
                name='federation:retry',
                consumer_group='federation-workers',
                batch_size=5,
                block_ms=10000,
                max_retries=1
            )
        }
        
        self.metrics = ProcessingMetrics()
        self._running = False
        self._tasks: Set[asyncio.Task] = set()
    
    async def start(self) -> None:
        """Initialize connections and start processing"""
        logger.info(f"Starting federation processor {self.consumer_name}")
        
        # Initialize Redis
        self.redis = await aioredis.from_url(
            self.redis_url,
            decode_responses=False,  # We handle decoding ourselves
            health_check_interval=30
        )
        
        # Initialize HTTP client
        self.http_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
        
        # Initialize async database
        engine = create_async_engine(
            self.database_url.replace('postgresql://', 'postgresql+asyncpg://'),
            pool_size=5,
            max_overflow=10
        )
        self.async_session_maker = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        
        # Create consumer groups
        await self._create_consumer_groups()
        
        # Start processing
        self._running = True
        await self._run()
    
    async def stop(self) -> None:
        """Gracefully stop processing"""
        logger.info("Stopping federation processor")
        self._running = False
        
        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        # Cleanup connections
        if self.redis:
            await self.redis.close()
        if self.http_client:
            await self.http_client.aclose()
    
    async def _create_consumer_groups(self) -> None:
        """Create consumer groups for all streams"""
        for config in self.stream_configs.values():
            try:
                await self.redis.xgroup_create(
                    config.name,
                    config.consumer_group,
                    id='0',
                    mkstream=True
                )
                logger.info(f"Created consumer group {config.consumer_group} for {config.name}")
            except aioredis.ResponseError as e:
                if "BUSYGROUP" in str(e):
                    # Group already exists
                    pass
                else:
                    raise
    
    async def _run(self) -> None:
        """Main processing loop"""
        # Create a task for each priority stream
        for priority, config in self.stream_configs.items():
            task = asyncio.create_task(
                self._process_stream(priority, config),
                name=f"stream-{priority.value}"
            )
            self._tasks.add(task)
        
        # Also start maintenance tasks
        self._tasks.add(asyncio.create_task(self._claim_pending_messages()))
        self._tasks.add(asyncio.create_task(self._report_metrics()))
        
        # Wait for tasks (they should run forever unless stopped)
        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            logger.info("Processing tasks cancelled")
    
    async def _process_stream(self, priority: Priority, config: StreamConfig) -> None:
        """Process a single stream"""
        logger.info(f"Starting processor for {config.name}")
        
        while self._running:
            try:
                # Read messages from stream
                messages = await self.redis.xreadgroup(
                    config.consumer_group,
                    self.consumer_name,
                    {config.name: '>'},  # Read new messages
                    count=config.batch_size,
                    block=config.block_ms
                )
                
                if messages:
                    stream_name, stream_messages = messages[0]
                    await self._handle_messages(config, stream_messages)
                    
            except Exception as e:
                logger.error(f"Error processing {config.name}: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def _handle_messages(
        self,
        config: StreamConfig,
        messages: List[Tuple[bytes, Dict[bytes, bytes]]]
    ) -> None:
        """Handle a batch of messages"""
        # Parse messages
        parsed_messages: List[Tuple[MessageId, StreamMessage]] = []
        
        for msg_id_bytes, data in messages:
            try:
                msg_id = MessageId(msg_id_bytes.decode())
                
                # Decode message data
                message_data = {}
                for k, v in data.items():
                    key = k.decode() if isinstance(k, bytes) else k
                    value = v.decode() if isinstance(v, bytes) else v
                    message_data[key] = value
                
                # Validate StreamMessage structure
                stream_message: StreamMessage = {
                    'type': message_data['type'],
                    'data': message_data['data'],
                    'priority': message_data['priority'],
                    'attempts': int(message_data['attempts']),
                    'timestamp': message_data['timestamp']
                }
                
                if 'request_id' in message_data:
                    stream_message['request_id'] = message_data['request_id']
                
                parsed_messages.append((msg_id, stream_message))
                
            except Exception as e:
                logger.error(f"Failed to parse message {msg_id_bytes}: {e}")
                # ACK the bad message so we don't get stuck
                await self.redis.xack(config.name, config.consumer_group, msg_id_bytes)
        
        if not parsed_messages:
            return
        
        # Create processing context
        async with self.async_session_maker() as session:
            context = ProcessingContext(
                stream_config=config,
                redis_client=self.redis,
                http_client=self.http_client,
                db_session=session,
                metrics=self.metrics
            )
            
            # Process messages by type
            await self._process_by_type(context, parsed_messages)
    
    async def _process_by_type(
        self,
        context: ProcessingContext,
        messages: List[Tuple[MessageId, StreamMessage]]
    ) -> None:
        """Group messages by type and process with appropriate handlers"""
        # Group by message type
        messages_by_type: Dict[str, List[Tuple[MessageId, StreamMessage]]] = {}
        
        for msg_id, message in messages:
            msg_type = message['type']
            if msg_type not in messages_by_type:
                messages_by_type[msg_type] = []
            messages_by_type[msg_type].append((msg_id, message))
        
        # Process each type
        handler_registry = get_handler_registry()
        
        for msg_type, type_messages in messages_by_type.items():
            try:
                # Get handler for this type
                handler_class = handler_registry.get(msg_type)
                if not handler_class:
                    logger.warning(f"No handler found for message type: {msg_type}")
                    # ACK these messages so we don't reprocess
                    for msg_id, _ in type_messages:
                        await self.redis.xack(
                            context.stream_config.name,
                            context.stream_config.consumer_group,
                            msg_id
                        )
                    continue
                
                # Create handler instance
                handler = handler_class(context)
                
                # Parse activity data
                parsed_activities = []
                for msg_id, message in type_messages:
                    try:
                        activity_data = json.loads(message['data'])
                        parsed_activities.append((msg_id, activity_data))
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON in message {msg_id}: {e}")
                        await self.redis.xack(
                            context.stream_config.name,
                            context.stream_config.consumer_group,
                            msg_id
                        )
                
                if parsed_activities:
                    # Process batch
                    start_time = time.time()
                    responses = await handler.handle(parsed_activities)
                    processing_time = time.time() - start_time
                    
                    # Handle responses
                    await self._handle_responses(context, responses, processing_time)
                    
            except Exception as e:
                logger.error(f"Error processing {msg_type} messages: {e}", exc_info=True)
                context.metrics.record_failure(str(e))
    
    async def _handle_responses(
        self,
        context: ProcessingContext,
        responses: List[HandlerResponse],
        processing_time: float
    ) -> None:
        """Handle responses from handlers"""
        for response in responses:
            if response.status == ProcessingStatus.SUCCESS:
                # ACK successful message
                await self.redis.xack(
                    context.stream_config.name,
                    context.stream_config.consumer_group,
                    response.message_id
                )
                context.metrics.record_success(response.processing_time or processing_time)
                
            elif response.should_retry:
                # Queue for retry
                await self._queue_retry(context, response)
                # Still ACK the original message
                await self.redis.xack(
                    context.stream_config.name,
                    context.stream_config.consumer_group,
                    response.message_id
                )
                
            else:
                # Failed permanently - move to dead letter
                logger.error(f"Message {response.message_id} failed permanently: {response.error}")
                await self._move_to_dead_letter(context, response)
                # ACK the message
                await self.redis.xack(
                    context.stream_config.name,
                    context.stream_config.consumer_group,
                    response.message_id
                )
    
    async def _queue_retry(self, context: ProcessingContext, response: HandlerResponse) -> None:
        """Queue a message for retry"""
        # This would use the producer to queue to retry stream
        logger.info(f"Queueing {response.message_id} for retry after {response.retry_after}s")
        context.metrics.record_retry()
    
    async def _move_to_dead_letter(self, context: ProcessingContext, response: HandlerResponse) -> None:
        """Move failed message to dead letter queue"""
        await self.redis.xadd(
            'federation:dead_letter',
            {
                'original_stream': context.stream_config.name,
                'message_id': response.message_id,
                'error': response.error or 'Unknown error',
                'timestamp': datetime.utcnow().isoformat()
            },
            maxlen=10000,
            approximate=True
        )
    
    async def _claim_pending_messages(self) -> None:
        """Periodically claim pending messages from dead consumers"""
        while self._running:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                for config in self.stream_configs.values():
                    # Get pending messages
                    pending = await self.redis.xpending_range(
                        config.name,
                        config.consumer_group,
                        min='-',
                        max='+',
                        count=100
                    )
                    
                    # Claim old messages
                    for msg in pending:
                        if msg['time_since_delivered'] > config.claim_min_idle_ms:
                            await self.redis.xclaim(
                                config.name,
                                config.consumer_group,
                                self.consumer_name,
                                min_idle_time=config.claim_min_idle_ms,
                                message_ids=[msg['message_id']]
                            )
                            
            except Exception as e:
                logger.error(f"Error claiming pending messages: {e}")
    
    async def _report_metrics(self) -> None:
        """Periodically report metrics"""
        while self._running:
            await asyncio.sleep(30)  # Report every 30 seconds
            
            logger.info(
                f"Metrics - Processed: {self.metrics.messages_processed}, "
                f"Failed: {self.metrics.messages_failed}, "
                f"Retried: {self.metrics.messages_retried}, "
                f"Avg time: {self.metrics.total_processing_time / max(1, self.metrics.messages_processed):.2f}s"
            )


async def run_processor(
    redis_url: str,
    database_url: str,
    consumer_name: Optional[str] = None
) -> None:
    """Run the federation processor"""
    import platform
    
    if not consumer_name:
        consumer_name = f"worker-{platform.node()}-{asyncio.current_task().get_name()}"
    
    processor = FederationStreamProcessor(
        redis_url=redis_url,
        database_url=database_url,
        consumer_name=consumer_name
    )
    
    # Handle signals
    loop = asyncio.get_event_loop()
    
    def signal_handler():
        asyncio.create_task(processor.stop())
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        await processor.start()
    except Exception as e:
        logger.error(f"Processor failed: {e}", exc_info=True)
        await processor.stop()
        raise