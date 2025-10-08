# Startup Session Cleanup Fix

## Problem Statement

After deploying the ActivityPub setup fix, the production environment experienced database session errors:

```python
KeyError: "Deferred loader for attribute 'default_theme' failed to populate correctly"
sqlalchemy.exc.ResourceClosedError: This result object does not return rows
```

These errors occurred on the first requests after app startup, affecting:
- User profile pages (`/u/username`)
- ActivityPub inbox processing (`/inbox`)
- Error page rendering (cascading failure)

## Root Cause Analysis

### What Was Happening

1. **Startup validation runs** - Our `run_startup_validations()` is called during `create_app()`
2. **Database operations performed** - `finalize_user_setup()` is called, which:
   - Loads User objects from database
   - Modifies them (adds ActivityPub keys/URLs)
   - Commits to database (twice - line 1713 and 1719 in utils.py)
3. **Objects remain in session** - After commits, User and Notification objects stay attached to SQLAlchemy session
4. **App context exits** - The `with app.app_context():` block ends
5. **Stale session persists** - SQLAlchemy session is not cleaned up
6. **First request arrives** - Gunicorn worker handles request in new context
7. **Session has stale objects** - The old User/Notification objects are still in identity map
8. **Lazy loading fails** - When code tries to access `site.default_theme`, SQLAlchemy tries to load it but the session/transaction state is corrupted

### Why This Specifically Affects Site.default_theme

The `Site` model uses deferred (lazy) loading for some attributes. When the session is in a corrupted state from startup:

```python
# This line in app/utils.py:1978
return site.default_theme if site.default_theme is not None else 'piefed'
```

Triggers SQLAlchemy to lazy-load `default_theme`, but the session/connection is in a bad state, causing the KeyError.

## The Fix

###  Session Cleanup (startup_validation.py)

Added comprehensive session cleanup in the `finally` block of `run_startup_validations()`:

```python
finally:
    try:
        # First, expire all objects to force reload on next access
        db.session.expire_all()
        # Then remove the session entirely to start fresh
        db.session.remove()
        current_app.logger.debug("Database session cleaned up after startup validation")
    except Exception as cleanup_error:
        current_app.logger.error(f"Error cleaning up database session: {cleanup_error}")
```

**What this does**:

1. **`db.session.expire_all()`** - Marks all objects in session as "stale", forcing them to be reloaded from database on next access
2. **`db.session.remove()`** - Removes the current session from the scoped session registry, ensuring next request gets a fresh session
3. **Error handling** - Catches any cleanup errors to prevent them from breaking app startup

### Why This Works

- **Breaks the connection** between startup validation objects and request-handling sessions
- **Forces fresh queries** - Any subsequent access will hit the database, not stale cached objects
- **Scoped session cleanup** - `db.session.remove()` is the proper way to clean up Flask-SQLAlchemy scoped sessions
- **Guaranteed execution** - `finally` block ensures cleanup happens even if validation errors occur

## Testing

Created comprehensive test suite in `tests/test_startup_session_cleanup.py`:

### Test Coverage

1. **`test_session_is_clean_after_startup_validation`** - Verifies session identity map is clean
2. **`test_deferred_attributes_load_after_validation`** - Tests Site.default_theme access
3. **`test_multiple_queries_after_validation`** - Multiple query types work correctly
4. **`test_session_identity_map_cleared`** - Verifies objects are properly expired
5. **`test_validation_with_no_users_to_fix`** - Cleanup works even with no fixes needed
6. **`test_validation_cleanup_handles_errors_gracefully`** - Cleanup happens even on error
7. **`test_validation_in_app_context_doesnt_pollute_next_context`** - Context isolation
8. **`test_session_cleanup_integration`** - Full end-to-end integration test

### Key Test Scenario

The integration test simulates the exact production failure:

```python
# Simulate app startup
with app.app_context():
    run_startup_validations()
    # Context exits, cleanup runs

# Simulate first request
with app.app_context():
    site = Site.query.get(1)
    theme = site.default_theme  # Should not raise KeyError
```

## Verification in Production

### Expected Log Messages

On startup, you should see:

```
[INFO] Running startup validations...
[INFO] Fixed ActivityPub setup for X user(s)  # Only if users needed fixing
[INFO] Startup validations completed
[DEBUG] Database session cleaned up after startup validation
```

### What Should NOT Happen Anymore

- ❌ `KeyError: "Deferred loader for attribute 'default_theme' failed"`
- ❌ `ResourceClosedError: This result object does not return rows`
- ❌ Cascading failures on error pages

### What SHOULD Happen

- ✅ First request after startup completes successfully
- ✅ Site attributes (default_theme, name, etc.) load correctly
- ✅ User profile pages render without errors
- ✅ ActivityPub inbox processes messages correctly

## Additional Context

### Why We Didn't See This in Testing

- **Local development** typically doesn't restart the app for every request
- **Test environment** uses in-memory SQLite which has different session behavior
- **Test fixtures** often create fresh app contexts for each test
- **Production uses Gunicorn** with worker processes that have different session lifecycle

### Related Issues This Does NOT Fix

The following database errors are separate pre-existing issues:

```python
psycopg2.DatabaseError: error with status PGRES_TUPLES_OK and no message from the libpq
```

These are **connection pool exhaustion** issues, documented in `DATABASE_CONNECTION_ISSUES.md`. They require separate fixes:
- Increasing connection pool size
- Adding connection recycling
- Celery worker session scoping

## Implementation Details

### Why expire_all() Before remove()?

1. **expire_all()** marks objects as stale but keeps them in session
2. **remove()** clears the session entirely
3. Doing both ensures:
   - Objects that might still be referenced are invalidated
   - Session registry is cleaned for next request
   - No path to access stale objects

### Alternative Approaches Considered

❌ **Just remove()** - Might leave cached attributes on objects
❌ **Just expire_all()** - Doesn't clear session registry
❌ **commit() before cleanup** - Unnecessary and could hide errors
✅ **expire_all() + remove()** - Complete cleanup, handles all cases

## Files Modified

1. **app/startup_validation.py** - Added session cleanup in finally block
2. **tests/test_startup_session_cleanup.py** - Comprehensive test suite
3. **STARTUP_SESSION_CLEANUP_FIX.md** - This documentation

## Deployment Checklist

- [x] Code change implemented
- [x] Tests written (8 test scenarios)
- [x] Lint checks passing
- [x] Documentation created
- [ ] Deployed to staging
- [ ] Verified in staging logs
- [ ] Deployed to production
- [ ] Monitor production logs for 24 hours
- [ ] Verify error rate decrease

## Rollback Plan

If this fix doesn't resolve the issue:

1. Revert commit: `git revert <commit-hash>`
2. Temporarily disable startup validation:
   ```python
   # In app/__init__.py, comment out:
   # with app.app_context():
   #     from app.startup_validation import run_startup_validations
   #     run_startup_validations()
   ```
3. Users with incomplete ActivityPub setup will need manual fixing

## Future Improvements

1. **Add metrics** - Track how many users are fixed on each startup
2. **Add timing** - Log how long validation takes
3. **Make optional** - Add environment variable to disable if needed
4. **Background job** - Move validation to Celery task for zero startup impact
5. **Admin UI** - Allow manual triggering of validation

## References

- SQLAlchemy Session Basics: https://docs.sqlalchemy.org/en/20/orm/session_basics.html
- Flask-SQLAlchemy Scoped Sessions: https://flask-sqlalchemy.palletsprojects.com/en/3.0.x/contexts/
- Original ActivityPub Fix: PR #27
