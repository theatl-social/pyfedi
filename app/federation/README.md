# Federation Module

This module handles all federation-related functionality for PyFedi, implementing the ActivityPub protocol with a custom Redis Streams-based message queue system.

## Architecture Overview

```
federation/
├── producer.py          # Enqueues activities to Redis Streams
├── processor.py         # Consumes and processes activities
├── handlers.py          # Activity-specific handling logic
├── retry_manager.py     # Exponential backoff retry system
├── lifecycle_manager.py # Redis memory and data lifecycle
├── archival_handler.py  # Database archival for important data
├── types.py            # Type definitions and data structures
└── tasks/              # Activity handlers organized by type
```

## Components

### Producer (`producer.py`)
- Enqueues ActivityPub activities to appropriate Redis streams
- Handles priority routing (urgent, normal, bulk)
- Validates activities before queueing
- Supports batch operations

### Processor (`processor.py`)
- Main processing engine for consuming activities
- Implements consumer groups for scalability
- Handles concurrent processing with configurable workers
- Integrates retry and lifecycle management

### Retry Manager (`retry_manager.py`)
- Implements exponential backoff with jitter
- Per-activity-type retry policies
- Automatic promotion to Dead Letter Queue
- Configurable maximum retry duration (default: 2 days)

### Lifecycle Manager (`lifecycle_manager.py`)
- Manages Redis memory usage
- Automatic TTL on completed tasks
- Stream trimming based on age/size
- Archives important data to database before expiry

### Handlers (`handlers.py`, `tasks/`)
- Modular handlers for each ActivityPub activity type
- Full typing support
- Async-ready architecture
- Extensible handler registry

## Usage

### Starting the Processor

```python
from app.federation.processor import FederationStreamProcessor

processor = FederationStreamProcessor(
    redis_url="redis://localhost:6379",
    database_url="postgresql://user:pass@localhost/db"
)

await processor.start()
```

### Queueing an Activity

```python
from app.federation.producer import get_producer

producer = get_producer()
await producer.queue_activity(
    activity={"type": "Create", "object": {...}},
    destination="https://remote.instance/inbox",
    private_key=private_key,
    key_id=key_id
)
```

## Configuration

### Environment Variables

- `REDIS_URL`: Redis connection string
- `MAX_RETRY_DURATION`: Maximum retry duration in seconds (default: 172800)
- `TASK_TTL`: TTL for completed tasks in seconds (default: 86400)
- `MAX_BATCH_SIZE`: Messages per processing batch (default: 10)

### Retry Policies

Configured in `retry_manager.py`:
- Create/Update: 10 retries, 2.0x backoff
- Delete: 8 retries, 1.5x backoff
- Like: 5 retries, 1.5x backoff
- Follow: 8 retries, 2.0x backoff

## Monitoring

### Check Queue Status
```python
stats = await producer.get_queue_stats()
```

### View Retry Statistics
```python
retry_stats = await retry_manager.get_retry_stats()
```

### Memory Status
```python
memory = await lifecycle_manager.get_memory_status()
```

## Error Handling

1. **Transient Failures**: Automatic retry with exponential backoff
2. **Permanent Failures**: Move to Dead Letter Queue
3. **Memory Pressure**: Automatic cleanup and archival
4. **Instance Issues**: Circuit breaker pattern (planned)

## Future Enhancements

- [ ] Circuit breaker for failing instances
- [ ] Rate limiting per destination
- [ ] Web monitoring dashboard
- [ ] Scheduled task support
- [ ] Prometheus metrics export