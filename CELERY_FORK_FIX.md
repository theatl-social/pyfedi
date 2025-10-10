# Celery Fork Connection Pool Fix

## Problem Summary

**Error:** `psycopg2.DatabaseError: error with status PGRES_TUPLES_OK and no message from the libpq`

**Root Cause:** When Celery forks worker processes, the SQLAlchemy Engine and its connection pool are inherited from the parent process. These connections are file descriptors pointing to TCP sockets that should NOT be shared across processes.

## What Was Happening

1. Parent process creates SQLAlchemy Engine with connection pool
2. Celery forks child worker processes
3. Child processes inherit the Engine and connection pool (file descriptors)
4. Multiple processes access the same PostgreSQL connections
5. Protocol state corruption occurs:
   - PostgreSQL returns `PGRES_TUPLES_OK` (success status)
   - But libpq can't read the data because another process consumed it
   - Connection is in inconsistent state

## The Fix

Added `worker_process_init` signal handler to dispose of inherited connection pool:

```python
from celery.signals import worker_process_init

@worker_process_init.connect
def init_celery_worker(**kwargs):
    """
    Called once when each Celery worker process starts (after fork).
    Disposes of the connection pool inherited from the parent process.
    """
    db.engine.dispose(close=False)
```

### Why `close=False`?

- `close=True` (default) would close the connections
- Since the parent process still needs its connections, we use `close=False`
- This marks the connections as **invalid** in the child process without touching the parent's connections
- Child process will create fresh connections when needed

## Files Modified

1. `celery_worker_docker.py` - Added `worker_process_init` signal
2. `celery_worker.default.py` - Added `worker_process_init` signal
3. `DATABASE_CONNECTION_ISSUES.md` - Updated documentation

## Why Previous Fix Was Incomplete

Previous commit `51de2bc5` added:
- ✅ `task_prerun` → Clears session before each task
- ✅ `task_postrun` → Clears session after each task

This helped but didn't fix the root cause:
- Session cleanup happens **per-task**
- Connection pool is **per-worker-process**
- Corrupted connections remained in the pool between tasks

## Expected Results

After deploying this fix:
- ✅ No more `PGRES_TUPLES_OK` errors
- ✅ Each worker process has its own connection pool
- ✅ No protocol state corruption from shared connections
- ✅ Stable Celery task execution

## Monitoring

After deployment, monitor for:
1. Reduction in `PGRES_TUPLES_OK` errors (should go to zero)
2. Connection pool checkout messages showing different PIDs
3. Overall Celery task success rate improvement

If errors persist, consider:
- Increasing connection pool size (DB_POOL_SIZE, DB_MAX_OVERFLOW)
- Checking PostgreSQL server-side connection limits

## References

- [SQLAlchemy: Using Connection Pools with Multiprocessing](https://docs.sqlalchemy.org/en/20/core/pooling.html#using-connection-pools-with-multiprocessing-or-os-fork)
- [Celery Signals Documentation](https://docs.celeryproject.org/en/stable/userguide/signals.html#worker-process-init)
- [Apache Superset PR #13350](https://github.com/apache/superset/pull/13350) - Similar fix
- Stack Overflow discussions about PGRES_TUPLES_OK errors

## Technical Deep Dive

### Why File Descriptors Can't Be Shared

PostgreSQL connections are TCP sockets represented as file descriptors:
- OS allows file descriptors to work across process boundaries
- But each process has independent Python interpreter state
- Concurrent access to the same socket causes:
  - Race conditions reading/writing data
  - Protocol state machines getting out of sync
  - Silent data corruption

### The Three-Layer Fix

| Layer | Fix | Purpose |
|-------|-----|---------|
| Worker Process | `worker_process_init` + `engine.dispose(close=False)` | Prevent fork-inherited pool reuse |
| Task Start | `task_prerun` + `db.session.remove()` | Clean session state before task |
| Task End | `task_postrun` + `db.session.remove()` | Clean session state after task |

All three layers work together to ensure database connection integrity.
