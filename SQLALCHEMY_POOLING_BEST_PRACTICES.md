# SQLAlchemy Connection Pooling Best Practices for Gunicorn + Flask

**Date:** 2025-10-17
**Context:** Investigating proper connection pool configuration for PieFed production deployment

---

## Executive Summary

**You DON'T need PgBouncer for typical Flask + Gunicorn deployments.** SQLAlchemy's QueuePool is the standard, recommended solution when properly configured. The key is understanding the math and configuring pool_size correctly.

**The real issue in production:** We're using QueuePool (correct) but WITHOUT proper thread safety (incorrect). We need to either:
1. **Use QueuePool properly** with correct pool_size calculations (RECOMMENDED)
2. Use NullPool (only if using PgBouncer or very low traffic)

---

## Best Practice: QueuePool with Proper Sizing

### The Standard Pattern

**QueuePool is thread-safe** when used with Flask-SQLAlchemy's scoped_session (which PieFed already uses). The protocol corruption we're seeing is NOT because QueuePool is inherently thread-unsafe.

### Connection Pool Math

```python
# Formula for pool_size per worker:
pool_size = min(threads_per_worker, 10)

# Formula for total PostgreSQL connections:
total_connections = (workers × pool_size) + max_overflow

# For PieFed production example (8 core machine):
workers = max(2, 8 // 2) = 4
threads = min(16, 8 * 2) = 16

# Recommended configuration:
pool_size = 10           # Per worker
max_overflow = 10        # Additional connections under burst load
total = (4 × 10) + 10 = 50 connections maximum
```

### Why This Works

1. **Each worker process has its own pool** - pools are NOT shared across processes
2. **Flask-SQLAlchemy uses scoped_session** - each thread gets its own session
3. **QueuePool has internal locking** - multiple threads can safely check out different connections
4. **Pool size should match concurrency** - one connection per concurrent thread is optimal

---

## When to Use Each Pool Type

### QueuePool (Default - RECOMMENDED for most cases)

**Use when:**
- Running production Flask app with Gunicorn
- Direct connection to PostgreSQL (no PgBouncer)
- Moderate to high traffic
- Want optimal performance

**Configuration:**
```python
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_size': 10,           # Base connections per worker
    'max_overflow': 10,        # Additional under load
    'pool_pre_ping': True,     # Verify connection before use
    'pool_recycle': 3600,      # Recycle every hour
}
```

**Pros:**
- ✅ Connection reuse (faster)
- ✅ Lower PostgreSQL connection overhead
- ✅ Thread-safe with scoped_session
- ✅ Industry standard pattern

**Cons:**
- ❌ Requires proper configuration
- ❌ Can exhaust PostgreSQL max_connections if misconfigured

### NullPool (NO connection pooling)

**Use when:**
- Using PgBouncer or other external connection pooler
- Very low traffic (< 10 req/min)
- Development/testing environments
- Troubleshooting connection issues

**Configuration:**
```python
from sqlalchemy.pool import NullPool

SQLALCHEMY_ENGINE_OPTIONS = {
    'poolclass': NullPool,
    'pool_pre_ping': True,  # Still good practice
}
```

**Pros:**
- ✅ Simple (no pool state to manage)
- ✅ Never exhausts connections (closes immediately)
- ✅ Good for debugging

**Cons:**
- ❌ New TCP connection per request (slower)
- ❌ Higher database server load
- ❌ Higher latency (+1-3ms per request)
- ❌ NOT recommended for production without PgBouncer

---

## What's Actually Wrong in Production

Looking at the PGRES_TUPLES_OK errors, the issue is NOT that QueuePool is thread-unsafe. The issue is likely one of these:

### Hypothesis 1: post_fork not running properly ⚠️

If the `post_fork` hook isn't properly disposing the pool, child workers inherit parent's connection file descriptors:

```python
# Parent process (before fork)
Parent: Connection FD #5 → PostgreSQL socket

# After fork (without proper dispose)
Worker 1: Connection FD #5 → Same PostgreSQL socket ❌
Worker 2: Connection FD #5 → Same PostgreSQL socket ❌
Worker 3: Connection FD #5 → Same PostgreSQL socket ❌
```

**Result:** Multiple processes use same socket → protocol corruption

**Solution:** Ensure `post_fork` runs and disposes properly:
```python
def post_fork(server, worker):
    from app import db
    db.engine.dispose(close=False)  # ✅ Currently in production
```

### Hypothesis 2: Session not properly scoped 🔍

If sessions are being shared across threads (not using Flask-SQLAlchemy's scoped_session properly):

```python
# BAD - Global session shared across threads
session = Session(bind=engine)

# GOOD - Flask-SQLAlchemy pattern (what PieFed uses)
db.session  # Automatically scoped to current thread
```

**Verification needed:** Check if any code uses raw SQLAlchemy Session() instead of `db.session`

### Hypothesis 3: Connection checkout/return race condition 🔍

Rare edge case where QueuePool's internal state gets corrupted under high concurrency.

**Solution:** Enable pool debugging:
```python
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_size': 10,
    'echo_pool': True,  # Log all pool checkouts/returns
}
```

---

## Recommended Fix (No PgBouncer Needed)

### Step 1: Keep QueuePool, Fix Configuration

```python
# config.py
Config.SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_size': 10,              # 10 connections per worker
    'max_overflow': 20,           # Up to 30 total per worker under load
    'pool_pre_ping': True,        # Already enabled ✅
    'pool_recycle': 3600,         # Already enabled ✅
    'pool_timeout': 30,           # Wait max 30s for connection
    'echo_pool': 'debug',         # Log pool activity (temporary, for debugging)
}
```

### Step 2: Verify post_fork Hook

Ensure production gunicorn.conf.py has:
```python
def post_fork(server, worker):
    from app import db
    db.engine.dispose(close=False)
    server.log.info(f"Worker {worker.pid}: Disposed inherited pool")
```

### Step 3: Add Engine Recreation in post_worker_init

This is the key fix - recreate the engine AFTER worker initialization:

```python
def post_worker_init(worker):
    from app import db
    from sqlalchemy import create_engine

    # Dispose any inherited pool
    db.engine.dispose()

    # Recreate engine with fresh pool
    # This ensures each worker's pool is created AFTER fork, not inherited
    db.engine = create_engine(
        db.engine.url,
        **db.engine.options  # Preserve config (QueuePool, pool_size, etc.)
    )

    worker.log.info(f"Worker {worker.pid}: Recreated engine with fresh pool")
```

**Why this works:**
- Each worker creates its own pool AFTER forking
- No shared file descriptors from parent
- QueuePool remains (good for performance)
- Thread-safe via scoped_session

### Step 4: Calculate Max Connections Needed

```python
# Production example
workers = 4
pool_size = 10
max_overflow = 20

max_connections_needed = workers × (pool_size + max_overflow)
                       = 4 × (10 + 20)
                       = 120 connections

# PostgreSQL default max_connections = 100
# Action: Increase PostgreSQL max_connections to 150 (with buffer)
```

---

## When You WOULD Need PgBouncer

### Scenarios Where PgBouncer Makes Sense

1. **Very high connection count** (> 200 connections)
   - PostgreSQL performance degrades with many connections
   - PgBouncer maintains pool of ~20-50 PostgreSQL connections
   - Thousands of application connections → small PostgreSQL pool

2. **Multiple application servers**
   - 5 app servers × 4 workers × 30 connections = 600 connections
   - PgBouncer centralizes pooling across all app servers

3. **Connection limit constraints**
   - Shared PostgreSQL server with strict connection limits
   - Other applications need connections too

4. **Transaction pooling needed**
   - Very short-lived connections
   - Microservices architecture

### PgBouncer Configuration Pattern

If using PgBouncer:
```python
# Application config.py
SQLALCHEMY_ENGINE_OPTIONS = {
    'poolclass': NullPool,  # ✅ No pooling in app (PgBouncer pools)
    'pool_pre_ping': False, # ✅ PgBouncer handles health checks
}

# PgBouncer config
[databases]
pyfedi = host=localhost port=5432 dbname=pyfedi

[pgbouncer]
pool_mode = transaction    # Or session mode
max_client_conn = 1000     # App can have many connections
default_pool_size = 25     # But only 25 to PostgreSQL
```

---

## PieFed Production Recommendation

### Current State
- ✅ Using QueuePool (correct)
- ✅ pool_pre_ping enabled (correct)
- ✅ post_fork hook disposes pool (correct)
- ❌ Missing post_worker_init (NEEDS FIX)
- ❌ Possibly inheriting parent pool (causing errors)

### Recommended Action

**DO NOT add PgBouncer yet.** First:

1. **Add post_worker_init hook** to recreate engine after fork
2. **Keep QueuePool** (it's thread-safe with scoped_session)
3. **Increase PostgreSQL max_connections** to 150-200
4. **Monitor connection usage** for 7 days
5. **Only add PgBouncer if** connection count becomes problematic

### Expected Outcome

With proper post_worker_init hook:
- ✅ PGRES_TUPLES_OK errors should stop (no shared FDs)
- ✅ Performance remains good (QueuePool still used)
- ✅ No PgBouncer complexity needed
- ✅ Standard Flask + Gunicorn + SQLAlchemy pattern

---

## Testing Plan

### Test 1: Verify Current Connections
```sql
-- Check current PostgreSQL connections
SELECT count(*), state FROM pg_stat_activity
WHERE datname = 'pyfedi'
GROUP BY state;

-- Check max_connections setting
SHOW max_connections;
```

### Test 2: Load Test with QueuePool
```bash
# Simulate production load
ab -n 10000 -c 50 https://production.example.com/

# Monitor connections during test
watch -n 1 "psql -c \"SELECT count(*) FROM pg_stat_activity WHERE datname='pyfedi'\""
```

### Test 3: Verify No Shared File Descriptors
```bash
# After deployment, check each worker's connections
for pid in $(pgrep -f "gunicorn.*worker"); do
    echo "Worker $pid:"
    lsof -p $pid | grep postgres
done

# Should see DIFFERENT socket FDs per worker (not same FD number)
```

---

## Conclusion

**PgBouncer is NOT required for typical Flask + Gunicorn + PostgreSQL deployments.**

The standard pattern is:
1. QueuePool in SQLAlchemy ✅
2. Proper post_fork hook ✅ (already have)
3. Proper post_worker_init hook ❌ (NEED TO ADD)
4. Flask-SQLAlchemy's scoped_session ✅ (already have)
5. Sufficient PostgreSQL max_connections ❓ (need to verify)

**Next step:** Implement post_worker_init with QueuePool (not NullPool) to recreate engine properly after fork.

---

## References

- SQLAlchemy Pooling: https://docs.sqlalchemy.org/en/20/core/pooling.html
- Flask-SQLAlchemy: https://flask-sqlalchemy.palletsprojects.com/
- Gunicorn Design: https://docs.gunicorn.org/en/stable/design.html
- PostgreSQL Connection Limits: https://www.postgresql.org/docs/current/runtime-config-connection.html
- Thread-local session: https://docs.sqlalchemy.org/en/20/orm/contextual.html
