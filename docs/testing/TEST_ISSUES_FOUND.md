# Test Suite Issues Found

**Date**: 2025-08-01  
**Current Status**: 39 failed, 55 passed, 217 errors

## Issues Resolved ✅

1. **SQLAlchemy Relationship Errors** - FIXED
   - User.notifications missing foreign_keys
   - Duplicate CommunityJoinRequest class
   - Report back_populates mismatches
   - PostReply self-referential relationships

## Remaining Issues 🔴

### 1. Test Fixture Scope Mismatch
**Error**: `ScopeMismatch: You tried to access the function scoped fixture app with a session scoped request object`

**Affected Tests**: Most API and ActivityPub tests

**Root Cause**: 
- `app` fixture in conftest.py is session-scoped
- Many tests expect function-scoped fixtures
- Database fixture `_db` depends on session-scoped app

**Potential Solutions**:
1. Change app fixture to function scope (may slow tests)
2. Create separate function-scoped app fixture for tests that need it
3. Update tests to use session scope properly

### 2. Model Constructor Argument Mismatch
**Error**: `TypeError: 'user' is an invalid keyword argument for Post`

**Location**: `tests/test_activitypub_verbs_comprehensive.py:65`

**Issue**: Test uses `Post(user=self.user)` but Post expects `author`

**Other potential mismatches**:
- Tests may be using old model signatures
- Need to audit all test model creations

### 3. Database Connection Issues
Some tests show PostgreSQL connection errors, suggesting test database isn't properly initialized in some cases.

## Test Categories Status

| Category | Status | Issue |
|----------|--------|-------|
| Unit tests (no DB) | ✅ Working | Tests like allowlist_html pass |
| Database tests | ❌ Scope errors | Fixture scope mismatches |
| API tests | ❌ Scope errors | Can't access app fixture |
| ActivityPub tests | ❌ Multiple | Scope + model mismatches |
| Security tests | ❌ Import errors | Missing modules/functions |

## Recommended Fix Order

1. **Fix fixture scoping** - This blocks most tests
2. **Update test model usage** - Use correct constructor arguments
3. **Fix security test imports** - Resolve missing modules
4. **Address functional test failures** - Once tests can run

## Quick Fixes to Try

### For Scope Issues
```python
# In conftest.py, try changing:
@pytest.fixture(scope='session')
def app():

# To:
@pytest.fixture(scope='function')
def app():
```

### For Model Issues
```python
# In tests, change:
Post(user=self.user, ...)

# To:
Post(author=self.user, ...)
# Or use user_id directly:
Post(user_id=self.user.id, ...)
```

## Next Steps

1. Decide on fixture scoping strategy
2. Create migration script for test updates if needed
3. Run focused test groups to isolate issues