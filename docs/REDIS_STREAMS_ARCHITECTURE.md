# Redis Streams Federation Architecture

## Overview

PyFedi has migrated from Celery to a custom Redis Streams-based message queue system for handling ActivityPub federation. This new architecture provides better performance, reliability, and debuggability while reducing complexity.

## Architecture Components

### 1. Redis Streams
- **Purpose**: Message queuing and persistence
- **Streams**:
  - `federation:stream:urgent` - High priority activities (Likes, Follows)
  - `federation:stream:normal` - Standard activities (Create, Update)
  - `federation:stream:bulk` - Low priority bulk operations
  - `federation:stream:retry` - Messages scheduled for retry
  - `federation:dlq` - Dead Letter Queue for failed messages

### 2. Federation Producer
- **Location**: `app/federation/producer.py`
- **Purpose**: Enqueue activities to appropriate streams
- **Features**:
  - Priority-based routing
  - Batch operations support
  - Message validation
  - Automatic stream selection

### 3. Stream Processor
- **Location**: `app/federation/processor.py`
- **Purpose**: Consume and process messages from streams
- **Features**:
  - Concurrent processing with configurable workers
  - Consumer groups for scalability
  - Automatic message acknowledgment
  - Metrics collection

### 4. Retry Manager
- **Location**: `app/federation/retry_manager.py`
- **Purpose**: Handle failed message retries with exponential backoff
- **Features**:
  - Per-activity-type retry policies
  - Exponential backoff with jitter
  - Maximum retry duration (default: 2 days)
  - Automatic DLQ promotion

### 5. Lifecycle Manager
- **Location**: `app/federation/lifecycle_manager.py`
- **Purpose**: Manage Redis memory and data retention
- **Features**:
  - Automatic TTL on completed tasks
  - Stream trimming by age/size
  - Memory monitoring
  - Database archival for important data

## Message Flow

```mermaid
graph TD
    A[ActivityPub Activity] --> B[Federation Producer]
    B --> C{Priority Router}
    C -->|Urgent| D[Urgent Stream]
    C -->|Normal| E[Normal Stream]
    C -->|Bulk| F[Bulk Stream]
    
    D --> G[Stream Processor]
    E --> G
    F --> G
    
    G --> H{Processing Result}
    H -->|Success| I[Mark Complete + TTL]
    H -->|Retry| J[Retry Manager]
    H -->|Permanent Failure| K[Dead Letter Queue]
    
    J --> L{Retry Decision}
    L -->|Schedule| M[Retry Stream]
    L -->|Max Retries| K
    
    M --> G
    K --> N[Database Archive]
```

## Configuration

### Environment Variables

```bash
# Redis connection
REDIS_URL=redis://localhost:6379/0

# Retry configuration
MAX_RETRY_DURATION=172800  # 2 days in seconds
TASK_TTL=86400            # 24 hours in seconds

# Processing configuration
MAX_BATCH_SIZE=10         # Messages per batch
WORKER_COUNT=4            # Concurrent workers
```

### Retry Policies

Retry policies are configured per activity type in `retry_manager.py`:

```python
{
    'Create': {'max_retries': 10, 'backoff_factor': 2.0, 'max_delay': 3600, 'initial_delay': 60},
    'Update': {'max_retries': 10, 'backoff_factor': 2.0, 'max_delay': 3600, 'initial_delay': 60},
    'Delete': {'max_retries': 8, 'backoff_factor': 1.5, 'max_delay': 1800, 'initial_delay': 30},
    'Follow': {'max_retries': 8, 'backoff_factor': 2.0, 'max_delay': 1800, 'initial_delay': 60},
    'Like': {'max_retries': 5, 'backoff_factor': 1.5, 'max_delay': 600, 'initial_delay': 30},
}
```

### Data Retention

Retention policies in `lifecycle_manager.py`:

```python
{
    'completed_tasks': 86400,   # 24 hours
    'failed_tasks': 604800,     # 7 days
    'retry_metadata': 172800,   # 2 days
    'stream_messages': 259200,  # 3 days
    'dlq_messages': 2592000,    # 30 days
}
```

## Operations

### Starting the Processor

```python
from app.federation.processor import FederationStreamProcessor

processor = FederationStreamProcessor(
    redis_url="redis://localhost:6379",
    database_url="postgresql://user:pass@localhost/db",
    consumer_name="worker-1"
)

await processor.start()
```

### Monitoring

#### Check Queue Depths
```python
from app.federation.producer import get_producer

producer = get_producer()
stats = await producer.get_queue_stats()
print(f"Urgent queue: {stats['urgent']} messages")
```

#### Get Retry Statistics
```python
from app.federation.retry_manager import RetryManager

retry_manager = RetryManager(redis_client)
stats = await retry_manager.get_retry_stats()
print(f"Active retries: {stats['active_retries']}")
print(f"DLQ size: {stats['dlq_size']}")
```

#### Memory Status
```python
from app.federation.lifecycle_manager import LifecycleManager

lifecycle_manager = LifecycleManager(redis_client)
status = await lifecycle_manager.get_memory_status()
if status['status'] == 'critical':
    await lifecycle_manager.force_cleanup(aggressive=True)
```

### Manual Operations

#### Retry a Failed Message
```python
# Move message from DLQ back to retry queue
message = await redis.xrange('federation:dlq', count=1)
if message:
    msg_id, data = message[0]
    # Parse and re-queue the message
    await producer.queue_activity(...)
```

#### Force Cleanup
```python
# Run aggressive cleanup during memory pressure
stats = await lifecycle_manager.force_cleanup(aggressive=True)
print(f"Cleaned {sum(stats['cleanup_stats'].values())} items")
```

## Error Handling

### Retry Flow

1. **First Failure**: Message enters retry system
2. **Exponential Backoff**: Delay increases with each retry
3. **Jitter**: Random variation prevents thundering herd
4. **Max Retries**: After limit, moves to DLQ
5. **Archival**: DLQ messages archived to database

### Dead Letter Queue

Messages in the DLQ contain:
- Original message content
- Error history
- Retry metadata
- Processing context

Access DLQ messages:
```python
# Read from DLQ
dlq_messages = await redis.xrange('federation:dlq', '-', '+', count=10)

# Get archived failures from database
from app.federation.archival_handler import DatabaseArchivalHandler
handler = DatabaseArchivalHandler()
stats = await handler.get_archived_stats(session, days=7)
```

## Performance Tuning

### Redis Memory

Monitor memory usage:
```bash
redis-cli info memory
```

Adjust retention if needed:
```python
# Reduce retention during high load
lifecycle_manager.retention_policies[DataCategory.COMPLETED_TASK].ttl_seconds = 43200  # 12 hours
```

### Processing Throughput

Increase concurrent processing:
```python
processor = FederationStreamProcessor(
    max_batch_size=20,  # More messages per batch
    worker_count=8      # More concurrent workers
)
```

### Network Optimization

Batch operations for same destination:
```python
activities = [activity1, activity2, activity3]
await producer.queue_batch(activities, destination="https://example.com")
```

## Troubleshooting

### Common Issues

1. **High Memory Usage**
   - Check: `await lifecycle_manager.get_memory_status()`
   - Fix: `await lifecycle_manager.force_cleanup(aggressive=True)`

2. **Messages Stuck in Retry**
   - Check: `await retry_manager.get_retry_stats()`
   - Fix: Investigate specific instance issues

3. **Slow Processing**
   - Check: Stream processor metrics
   - Fix: Increase worker count or batch size

### Debug Mode

Enable detailed logging:
```python
import logging
logging.getLogger('app.federation').setLevel(logging.DEBUG)
```

### Health Checks

```python
async def health_check():
    # Check Redis connection
    await redis.ping()
    
    # Check queue depths
    stats = await producer.get_queue_stats()
    if any(count > 10000 for count in stats.values()):
        return "WARNING: High queue depth"
    
    # Check memory
    memory = await lifecycle_manager.get_memory_status()
    if memory['status'] != 'healthy':
        return f"WARNING: Memory {memory['status']}"
    
    return "OK"
```

## Migration from Celery

### Key Differences

1. **No Celery Workers**: Processing happens in the main application
2. **Native Async**: All operations are async/await
3. **Priority Queues**: Built-in priority handling
4. **Better Visibility**: Direct Redis access for debugging

### Migration Checklist

- [x] Remove Celery dependencies
- [x] Update Docker configuration
- [x] Migrate task definitions to handlers
- [x] Update monitoring dashboards
- [x] Test retry mechanisms
- [x] Verify memory management

## Future Enhancements

1. **Circuit Breaker**: Auto-disable failing instances
2. **Rate Limiting**: Per-destination throttling
3. **Web Dashboard**: Real-time monitoring UI
4. **Scheduled Tasks**: Cron-like scheduling
5. **Metrics Export**: Prometheus integration