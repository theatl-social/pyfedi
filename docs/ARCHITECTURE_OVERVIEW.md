# PeachPie Architecture Overview

## Current State (2025-01-27)

PeachPie is a modern ActivityPub implementation that evolved from PyFedi/PieFed, featuring:
- Python 3.13 with comprehensive type annotations
- Redis Streams replacing Celery for async task processing
- Enhanced security with circuit breakers and rate limiting
- Modular architecture for better maintainability

## Core Components

### 1. Web Application Layer
- **Framework**: Flask with Python 3.13
- **Type Safety**: Full typing using Python 3.13 features
- **Structure**: Modular blueprints for different concerns
  - `/app/activitypub/routes/` - ActivityPub endpoints (41 routes)
  - `/app/admin/` - Administration interface
  - `/app/community/` - Community management
  - `/app/user/` - User functionality

### 2. Federation Layer
- **Protocol**: ActivityPub with Lemmy/Mastodon compatibility
- **Processing**: Redis Streams for async message handling
- **Directory**: `/app/federation/`
  - `processor.py` - Main stream processor
  - `handlers.py` - Activity type handlers
  - `health_monitor.py` - Instance health tracking
  - `rate_limiter.py` - Per-destination rate limiting
  - `retry_manager.py` - Exponential backoff retries
  - `lifecycle_manager.py` - Data TTL management

### 3. Data Layer
- **Database**: PostgreSQL with SQLAlchemy 2.0
- **Cache**: Redis for caching and streams
- **Models**: Typed models in `/app/models_typed*.py`
- **Schema**: Improved with proper URL field lengths and indexes

### 4. Security Features
- **Authentication**: HTTP Signatures for ActivityPub
- **Protection**: SSRF, SQL injection, actor spam prevention
- **Monitoring**: Circuit breakers for failed instances
- **Rate Limiting**: Per-destination and global limits

## Key Improvements from PyFedi

### 1. Redis Streams Architecture
Replaced Celery with Redis Streams for better control and monitoring:
```
Priority Queues:
- federation:stream:critical (immediate delivery)
- federation:stream:high (user actions)
- federation:stream:medium (general federation)
- federation:stream:low (background tasks)
```

### 2. Type Safety
All models and federation code fully typed:
- `TypedUser`, `TypedCommunity`, `TypedPost` models
- Type-safe ActivityPub objects
- Comprehensive type hints throughout

### 3. Health Monitoring
Circuit breaker pattern for instance health:
- Tracks success/failure rates
- Automatic circuit opening on failures
- Half-open state for recovery testing
- Admin dashboard for monitoring

### 4. Modular Design
ActivityPub routes split into logical modules:
- `actors.py` - Actor/profile endpoints
- `communities.py` - Community endpoints
- `posts.py` - Post and comment endpoints
- `activities.py` - Activity endpoints
- `collections.py` - Collection endpoints
- `misc.py` - WebFinger, NodeInfo, etc.

## Configuration

### Environment Variables
```env
# Core Configuration
SERVER_NAME=your-domain.com
SECRET_KEY=<random-32-chars>
DATABASE_URL=postgresql://...
REDIS_URL=redis://localhost:6379/0

# Software Identity
SOFTWARE_NAME=PeachPie
SOFTWARE_REPO=https://github.com/theatl-social/peachpie
SOFTWARE_VERSION=1.0.1

# Federation Tuning
CIRCUIT_FAILURE_THRESHOLD=5
CIRCUIT_SUCCESS_THRESHOLD=3
CIRCUIT_RECOVERY_TIMEOUT=300
RATE_LIMIT_PER_DESTINATION=100
RATE_LIMIT_WINDOW=60
```

## Data Flow

### Incoming Federation
1. Request arrives at `/inbox` endpoint
2. Signature verification
3. Activity validation
4. Queued to Redis Stream by priority
5. Processor handles activity
6. Updates local database
7. Sends any necessary responses

### Outgoing Federation
1. User action triggers federation
2. Activity created and signed
3. Health check on destination instance
4. Rate limit check
5. Queued to Redis Stream
6. Processor delivers activity
7. Records success/failure metrics

## Monitoring

### Available Dashboards
1. **Federation Monitor** (`/monitoring/`)
   - Stream queue lengths
   - Processing rates
   - Error tracking
   - Worker health

2. **Instance Health** (`/admin/health/instances`)
   - Health status by instance
   - Circuit breaker states
   - Success rates and response times
   - Manual reset options

3. **Task Status API** (`/api/v1/monitoring/tasks`)
   - Real-time task metrics
   - Stream statistics
   - Worker status

## Testing Strategy

### Unit Tests
- Isolated component testing
- Mocked dependencies
- Type checking validation
- No database/Redis required

### Integration Tests
- Redis Streams workflows
- Federation scenarios
- Health monitoring
- Rate limiting

### Performance Tests
- Load testing with concurrent workers
- Stream throughput benchmarks
- Database query optimization

## Migration Path

From PyFedi/PieFed:
1. Backup existing database
2. Set environment variables
3. Run migration: `flask db upgrade`
4. Update systemd services
5. Monitor health dashboard

## Future Enhancements

### Planned Features
1. **Task Scheduling** - Cron-like scheduled tasks
2. **Enhanced Analytics** - Federation statistics
3. **Plugin System** - Extensible architecture
4. **GraphQL API** - Modern API alongside REST

### Performance Optimizations
1. **Connection Pooling** - Reuse HTTP connections
2. **Batch Processing** - Group similar activities
3. **Caching Strategy** - Intelligent cache warming
4. **Query Optimization** - Database performance tuning