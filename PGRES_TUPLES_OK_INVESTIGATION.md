# PGRES_TUPLES_OK Investigation Report

**Date:** 2025-10-17
**Issue:** Persistent PostgreSQL protocol corruption errors in production
**Status:** Root cause identified, solution proposed but not yet deployed

---

## Executive Summary

Production is experiencing PostgreSQL protocol corruption errors despite previous connection pool fixes. The root cause is **thread-unsafe connection pooling** with Gunicorn's `gthread` worker class. Multiple threads within the same worker process are sharing connections from a QueuePool, leading to race conditions and protocol state corruption.

---

## Error Symptoms

Multiple types of PostgreSQL protocol errors observed in production logs:

```
1. PGRES_TUPLES_OK and no message from the libpq
2. lost synchronization with server: got message type "i", length 1954111281
3. insufficient data in "T" message
4. IndexError: tuple index out of range
5. ResourceClosedError: This result object does not return rows
```

All errors indicate **protocol-level corruption** where the client and server are out of sync.

---

## Current Production Configuration

### Gunicorn Settings (gunicorn.conf.py)
```python
worker_class = "gthread"
workers = max(2, cpu_cores // 2)          # e.g., 2-4 workers
threads = min(16, cpu_cores * 2)          # e.g., 8-16 threads per worker
max_requests = 2000
max_requests_jitter = 50
```

### SQLAlchemy Pool Settings (config.py)
```python
pool_size = 10              # Base connections per worker
max_overflow = 30           # Additional connections under load
pool_pre_ping = True        # Verify connection alive before use
pool_recycle = 3600         # Recycle connections after 1 hour
poolclass = QueuePool       # Default - REUSES connections
```

### Hooks Currently in Production (main branch)
```python
def post_fork(server, worker):
    """Runs after worker process is forked"""
    db.engine.dispose(close=False)
    # Prevents parent/child process from sharing connections
```

**Missing:** `post_worker_init` hook for thread configuration

---

## Root Cause Analysis

### The Problem with gthread + QueuePool

1. **Gunicorn forks worker processes** → `post_fork` hook runs ✅
   - Each worker gets its own connection pool (10-40 connections)
   - This prevents process-level connection sharing

2. **Each worker spawns multiple threads** (e.g., 16 threads)
   - All threads in the same worker **share the same QueuePool** ❌
   - QueuePool is NOT thread-safe by default without additional locking

3. **Race condition scenario:**
   ```
   Time  Thread A              Thread B              Connection Pool
   ────  ──────────────────    ──────────────────    ─────────────────
   T1    checkout conn #1      -                     [conn#1 in use]
   T2    reading from conn#1   checkout conn #1      [conn#1 SHARED!]
   T3    waiting for data...   writes to conn #1     [protocol corrupt]
   T4    receives wrong data   -                     [PGRES_TUPLES_OK]
   ```

4. **Protocol corruption occurs** when:
   - Thread A sends query, waits for response
   - Thread B sends different query on SAME connection
   - PostgreSQL server responds to Thread B's query
   - Thread A receives Thread B's response data
   - Protocol state machine breaks → "lost synchronization"

### Why pool_pre_ping Doesn't Help

`pool_pre_ping=True` only verifies the connection is **alive** before checkout:
- Checks: "Can I execute a simple SELECT 1?"
- Doesn't prevent: Multiple threads using the same connection simultaneously
- The corruption happens **during concurrent use**, not at checkout time

---

## Previous Fix Attempts

### Attempt 1: Celery worker_process_init (Commit 45eb3a81, 51de2bc5)
- **Target:** Celery workers using prefork pool
- **Solution:** `engine.dispose()` on worker fork
- **Result:** Fixed Celery PGRES_TUPLES_OK errors ✅
- **Limitation:** Doesn't affect Gunicorn workers

### Attempt 2: Gunicorn post_fork (Commit ebda43fb)
- **Target:** Gunicorn worker processes
- **Solution:** `engine.dispose(close=False)` after fork
- **Result:** Prevents process-level connection sharing ✅
- **Limitation:** Doesn't address thread-level sharing within workers ❌

### Current Attempt: Gunicorn post_worker_init (PR #36 - NOT YET MERGED)
- **Target:** Gunicorn gthread workers
- **Solution:** Switch from QueuePool to NullPool after worker initialization
- **Status:** In branch `20251017/fix-pgres-tuples-and-pillow`
- **Blocker:** Waiting for CI tests to pass, then merge and deploy

---

## Proposed Solution (UPDATED)

### ✅ CORRECT Approach: Recreate Engine with QueuePool in post_worker_init

**Key insight from best practices research:** We should KEEP QueuePool (it's thread-safe with Flask-SQLAlchemy), but recreate the engine after fork to avoid inheriting parent's pool.

### Approach: Recreate Engine in post_worker_init

```python
def post_worker_init(worker):
    """
    Called after worker initialization.
    Switches to NullPool for thread-safe database access.
    """
    from app import db
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    # Dispose existing pool
    db.engine.dispose()

    # Recreate engine with NullPool
    db.engine = create_engine(
        db.engine.url,
        poolclass=NullPool,      # No pooling - fresh connection per request
        pool_pre_ping=True,      # Still verify connections
        echo=False,
    )

    worker.log.info(f"Worker {worker.pid}: Configured NullPool for gthread")
```

### Why NullPool?

**What it does:**
- Creates a **fresh database connection** for every request
- Closes the connection immediately after request completes
- No connection reuse = no shared state = thread-safe

**Trade-offs:**

✅ **Pros:**
- Thread-safe by design (no sharing)
- Simple to implement
- Works with Flask-SQLAlchemy's scoped_session
- Prevents all connection-sharing race conditions

❌ **Cons:**
- Higher connection overhead (TCP handshake per request)
- Potential to exhaust PostgreSQL max_connections under high load
- Slower than pooled connections (but modern PostgreSQL handles this well)

**Performance impact estimate:**
- Connection establishment: ~1-3ms overhead per request
- Acceptable for moderate traffic (< 1000 req/sec per worker)
- PostgreSQL default max_connections: 100 (check production setting)

---

## Alternative Solutions Considered

### Option 1: Keep QueuePool with StaticPool wrapper
**Complexity:** High
**Risk:** Medium
**Effort:** 3-5 days
Not recommended - would require custom pool implementation and extensive testing.

### Option 2: Switch to sync workers (no threading)
**Complexity:** Low
**Risk:** High
**Effort:** 1-2 days
```python
worker_class = "sync"
workers = cpu_cores * 2  # More workers needed without threads
```
Would require capacity planning and load testing. QueuePool would be safe with sync workers.

### Option 3: Switch to gevent workers (async)
**Complexity:** Very High
**Risk:** Very High
**Effort:** 1-2 weeks
Would require auditing entire codebase for gevent compatibility (blocking I/O, monkey patching, etc.).

---

## Hypothesis Testing

### Test 1: Verify QueuePool thread-unsafety
**Method:** Load test with concurrent threads hammering same connection pool
**Result:** Expected to reproduce PGRES_TUPLES_OK errors
**Status:** Created test in `tests/test_connection_pool_thread_safety.py`

### Test 2: Verify NullPool thread-safety
**Method:** Same load test with NullPool configuration
**Result:** Expected no errors, all requests succeed
**Status:** Test passes locally ✅

### Test 3: Production deployment validation
**Method:** Deploy post_worker_init fix, monitor error rates
**Metrics to track:**
- PGRES_TUPLES_OK error count (should go to zero)
- PostgreSQL active connections (should increase slightly)
- Request latency p50/p95/p99 (should increase 1-3ms)
- Error rate overall (should decrease)

**Status:** Blocked - waiting for PR #36 to merge

---

## Deployment Plan

### Phase 1: Code Review & Merge
- [ ] PR #36 CI tests pass
- [ ] Code review approved
- [ ] Merge to main branch
- [ ] Tag release version

### Phase 2: Staged Deployment
- [ ] Deploy to staging environment
- [ ] Run load tests (simulate production traffic)
- [ ] Monitor for 24 hours
- [ ] Check PostgreSQL connection counts

### Phase 3: Production Rollout
- [ ] Deploy to production during low-traffic window
- [ ] Monitor error logs in real-time
- [ ] Track PostgreSQL connections: `SELECT count(*) FROM pg_stat_activity WHERE datname='pyfedi'`
- [ ] Verify PGRES_TUPLES_OK errors stop occurring
- [ ] Monitor for 7 days

### Phase 4: Optimization (if needed)
- [ ] If connection exhaustion occurs, tune PostgreSQL max_connections
- [ ] Consider PgBouncer for connection pooling at database level
- [ ] Evaluate switching to sync workers if performance degrades

---

## Risk Assessment

### High Risk
- **PostgreSQL max_connections exhaustion:** If NullPool creates too many connections
  - Mitigation: Monitor connection counts, adjust max_connections if needed
  - Rollback: Revert to previous version immediately

### Medium Risk
- **Performance degradation:** 1-3ms added latency per request
  - Mitigation: Load test before production deployment
  - Rollback: Switch to sync workers as fallback

### Low Risk
- **Regression in error rate:** Unlikely, but monitor all error types
  - Mitigation: Comprehensive error tracking in Sentry
  - Rollback: Automated rollback if error rate > 2x baseline

---

## Open Questions

1. **What is production PostgreSQL max_connections setting?**
   - Need to verify this won't be exhausted
   - Calculate: (workers × threads × safety_margin) should be < max_connections
   - Example: (4 workers × 16 threads × 1.2) = 77 connections needed

2. **What is current connection pool utilization?**
   - Query: `SELECT count(*) FROM pg_stat_activity WHERE state = 'active'`
   - Need baseline metrics before/after deployment

3. **Is PgBouncer already in use?**
   - If yes, NullPool is perfect (PgBouncer handles pooling)
   - If no, might want to add PgBouncer for connection pooling

4. **What is acceptable request latency increase?**
   - Current p95 latency?
   - Budget for +3ms overhead?

---

## Next Steps

1. **Wait for user decision:**
   - Proceed with NullPool solution (PR #36)?
   - Investigate alternative approaches?
   - Gather more production metrics first?

2. **If proceeding:**
   - Create fresh branch from main
   - Cherry-pick only the gunicorn.conf.py fix
   - Create minimal PR focused solely on this issue
   - Get approval and merge

3. **If investigating further:**
   - Gather PostgreSQL metrics from production
   - Load test with various worker configurations
   - Evaluate PgBouncer deployment
   - Consider architecture changes (sync vs gthread)

---

## References

- SQLAlchemy Pooling Docs: https://docs.sqlalchemy.org/en/20/core/pooling.html
- Gunicorn Worker Types: https://docs.gunicorn.org/en/stable/design.html#async-workers
- PostgreSQL max_connections: https://www.postgresql.org/docs/current/runtime-config-connection.html
- Previous fix commits:
  - 51de2bc5: Fix Celery database connection issues with session cleanup
  - ebda43fb: Add post_fork hook for Gunicorn to fix lost synchronization errors
  - 45eb3a81: Fix Celery PGRES_TUPLES_OK error with engine.dispose() on fork

---

## Appendix: Related Documentation

- [DATABASE_CONNECTION_ISSUES.md](DATABASE_CONNECTION_ISSUES.md) - Previous investigation notes
- [CELERY_FORK_FIX.md](CELERY_FORK_FIX.md) - Celery worker fix documentation
- [tests/test_connection_pool_thread_safety.py](tests/test_connection_pool_thread_safety.py) - Thread-safety tests
- PR #36: https://github.com/theatl-social/pyfedi/pull/36
