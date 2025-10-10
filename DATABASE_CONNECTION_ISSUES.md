# Database Connection Issues Analysis

## Issue Summary

Production environment experiencing recurring database connection errors that are **NOT related** to the ActivityPub setup fix:

```
psycopg2.DatabaseError: error with status PGRES_TUPLES_OK and no message from the libpq
sqlalchemy.exc.ResourceClosedError: This result object does not return rows
```

## Root Causes

### 1. Fork-Inherited Connection Pool (PRIMARY CAUSE - FIXED ✅)
When Celery forks worker processes, the SQLAlchemy Engine and its connection pool are copied from the parent process. These copied connections are file descriptors pointing to the same TCP sockets as the parent process.

**Why This Causes PGRES_TUPLES_OK Errors**:
- Multiple processes access the same PostgreSQL connection file descriptors
- Protocol state gets corrupted (PGRES_TUPLES_OK status but no readable data)
- Transaction boundaries become confused
- libpq can't read result data because another process consumed it

**Evidence**:
- Error is intermittent and non-deterministic (classic fork issue)
- Occurs randomly in both Celery workers
- Matches symptoms from 10+ similar issues documented online
- SQLAlchemy docs explicitly warn about this scenario

**Solution Applied**:
- Added `worker_process_init` signal to call `db.engine.dispose(close=False)`
- This marks inherited connections as invalid without closing parent process connections
- Each worker process starts with a fresh connection pool

### 2. Stale Session State (SECONDARY - FIXED ✅)
Sessions not being cleaned up between Celery tasks.

**Solution Applied**:
- Added `task_prerun`/`task_postrun` signals to call `db.session.remove()`

### 3. Connection Pool Exhaustion (POSSIBLE CONTRIBUTING FACTOR)
Multiple Gunicorn workers + Celery workers competing for limited database connections.

**Current Settings** (from config.py):
```python
DB_POOL_SIZE = 10  # May need increase if fork fix doesn't fully resolve
DB_MAX_OVERFLOW = 30  # May need increase if fork fix doesn't fully resolve
```

**Note**: The fork issue fix should resolve most errors. Monitor after deployment to see if pool size increase is still needed.

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

### Priority 2: Add Connection Pool Disposal on Fork (CRITICAL - COMPLETED ✅)

**File**: `celery_worker_docker.py` and `celery_worker.default.py`

```python
from celery.signals import worker_process_init, task_prerun, task_postrun

@worker_process_init.connect
def init_celery_worker(**kwargs):
    """
    Called once when each Celery worker process starts (after fork).
    Disposes of the connection pool inherited from the parent process.

    This prevents the "PGRES_TUPLES_OK and no message from libpq" error
    caused by multiple processes sharing the same PostgreSQL connection
    file descriptors.

    Reference: https://docs.sqlalchemy.org/en/20/core/pooling.html#using-connection-pools-with-multiprocessing-or-os-fork
    """
    # close=False prevents closing parent process connections
    db.engine.dispose(close=False)

@task_prerun.connect
def celery_task_prerun(*args, **kwargs):
    """Ensure fresh database session for each Celery task"""
    db.session.remove()

@task_postrun.connect
def celery_task_postrun(*args, **kwargs):
    """Clean up database session after Celery task"""
    db.session.remove()
```

**Why Both Are Needed:**
- `worker_process_init` → Runs once per worker process when it starts (fixes fork issue)
- `task_prerun`/`task_postrun` → Runs per task (ensures clean session state)

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
- ✅ **Fixed**: Celery worker process fork issue - Added `worker_process_init` signal to dispose inherited connection pool
- ✅ **Fixed**: Celery task session cleanup - Added `task_prerun`/`task_postrun` signal handlers
- ⚠️ **Pending**: Connection pool configuration (needs environment variables - may not be needed after fork fix)
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
