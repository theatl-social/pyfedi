# Database Connection Issues Analysis

## Issue Summary

Production environment experiencing recurring database connection errors that are **NOT related** to the ActivityPub setup fix:

```
psycopg2.DatabaseError: error with status PGRES_TUPLES_OK and no message from the libpq
sqlalchemy.exc.ResourceClosedError: This result object does not return rows
```

## Root Causes

### 1. Connection Pool Exhaustion
Multiple Gunicorn workers + Celery workers competing for limited database connections.

**Current Settings** (from config.py):
```python
DB_POOL_SIZE = 10  # May be insufficient
DB_MAX_OVERFLOW = 30  # May be insufficient
```

### 2. Stale/Broken Connections
Connections being reused after they've timed out or been closed by PostgreSQL.

**Evidence**:
- Errors happening during high-concurrency ActivityPub inbox processing
- "PGRES_TUPLES_OK with no message" indicates PostgreSQL returned success but connection is broken
- Deferred attribute loading failures indicate session corruption

### 3. Transaction Management Issues
Transactions not being properly committed/rolled back, leaving sessions in bad states.

## Errors Observed

### Error Type 1: Connection Closed During Query
```python
sqlalchemy.exc.ResourceClosedError: This result object does not return rows.
It has been closed automatically.
```

**Occurs in**:
- `get_setting('actor_blocked_words')` - app/utils.py:181
- `Site.query.get(1)` - app/activitypub/routes.py:558

### Error Type 2: Deferred Attribute Loading Failure
```python
KeyError: "Deferred loader for attribute 'default_theme' failed to populate correctly"
```

**Occurs in**:
- `current_theme()` when accessing `site.default_theme` - app/utils.py:1978
- Any lazy-loaded Site model attributes

### Error Type 3: PostgreSQL Protocol Error
```python
psycopg2.DatabaseError: error with status PGRES_TUPLES_OK and no message from the libpq
```

**Occurs in**:
- Various queries during ActivityPub processing
- Both Flask and Celery workers affected

## Impact

- **High**: Affects ActivityPub federation (inbox processing failures)
- **High**: Affects user profile pages
- **Medium**: Error pages also fail (cascading failure)
- **Pattern**: Happens under load, especially with concurrent ActivityPub requests

## Recommended Fixes

### Priority 1: Increase Connection Pool (Quick Win)

**File**: `config.py`

```python
# Increase pool size for production
DB_POOL_SIZE = int(os.environ.get('DB_POOL_SIZE') or 20)  # Was 10
DB_MAX_OVERFLOW = int(os.environ.get('DB_MAX_OVERFLOW') or 60)  # Was 30

# Add connection health checks
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_pre_ping': True,  # Test connections before using
    'pool_recycle': 3600,   # Recycle connections after 1 hour
    'pool_timeout': 30,     # Wait up to 30s for connection
    'max_overflow': 60,     # Allow up to 60 overflow connections
}
```

### Priority 2: Add Session Scoping for Celery

**File**: `celery_worker_docker.py` or task decorator

```python
from celery.signals import task_prerun, task_postrun

@task_prerun.connect
def celery_task_prerun(*args, **kwargs):
    """Ensure fresh database session for each Celery task"""
    db.session.remove()

@task_postrun.connect
def celery_task_postrun(*args, **kwargs):
    """Clean up database session after Celery task"""
    db.session.remove()
```

### Priority 3: Add Connection Retry Logic

**File**: `app/utils.py` - Wrap critical queries

```python
from sqlalchemy.exc import OperationalError
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(OperationalError)
)
@cache.memoize(timeout=300)
def get_setting(name, default=None):
    """Get setting with retry logic for connection failures"""
    try:
        setting = db.session.query(Settings).filter_by(name=name).first()
        # ... rest of function
    except OperationalError:
        db.session.rollback()
        raise
```

### Priority 4: Optimize Site Model Loading

**File**: `app/models.py` - Site model

Consider eager loading commonly-used attributes:

```python
# Instead of lazy loading everything, eager load critical fields
@property
def get_with_defaults(cls):
    return db.session.query(cls).options(
        joinedload('*')  # Eager load all attributes
    ).get(1)
```

### Priority 5: Add Database Connection Monitoring

**File**: `app/__init__.py` - Add health check endpoint

```python
@app.route('/health/db')
def db_health():
    """Check database connection health"""
    try:
        db.session.execute('SELECT 1')
        return {'status': 'healthy', 'db': 'connected'}, 200
    except Exception as e:
        return {'status': 'unhealthy', 'error': str(e)}, 503
```

## Environment Variables to Add

```bash
# Docker compose or .env
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=60
SQLALCHEMY_POOL_PRE_PING=1
SQLALCHEMY_POOL_RECYCLE=3600
```

## Testing the Fix

1. **Monitor connection pool usage**:
```python
from sqlalchemy import event
from sqlalchemy.pool import Pool

@event.listens_for(Pool, "connect")
def receive_connect(dbapi_conn, connection_record):
    app.logger.info("Database connection created")

@event.listens_for(Pool, "checkout")
def receive_checkout(dbapi_conn, connection_record, connection_proxy):
    app.logger.info("Database connection checked out from pool")
```

2. **Load test** - Simulate concurrent ActivityPub requests
3. **Monitor logs** - Check for reduction in connection errors
4. **Metrics** - Track connection pool saturation

## Why This Isn't Related to ActivityPub Fix

1. **Timing**: Errors occur during runtime request processing, not startup
2. **Location**: Errors in `/inbox` endpoint and user profile pages, not in startup validation
3. **Pattern**: Connection pool exhaustion pattern, not data corruption
4. **Scope**: Affects both old and new code paths

## Status

- ✅ **Fixed**: Startup validation session cleanup (prevents one source of stale sessions)
- ⚠️ **Pending**: Connection pool configuration (needs environment variables)
- ⚠️ **Pending**: Celery session scoping (needs worker configuration)
- ⚠️ **Recommended**: Connection retry logic (improves resilience)

## Next Steps

1. Apply Priority 1 fix (connection pool increase) - **Quick win, low risk**
2. Deploy and monitor for 24 hours
3. If issues persist, apply Priority 2 (Celery session scoping)
4. Consider Priority 3-5 for long-term stability

## References

- SQLAlchemy Pool Configuration: https://docs.sqlalchemy.org/en/20/core/pooling.html
- Psycopg2 Connection Issues: https://www.psycopg.org/docs/faq.html
- Flask-SQLAlchemy Scoped Sessions: https://flask-sqlalchemy.palletsprojects.com/en/3.0.x/contexts/
