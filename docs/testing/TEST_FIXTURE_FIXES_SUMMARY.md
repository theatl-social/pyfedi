# Test Fixture Fixes Summary

**Date**: 2025-08-01

## What Was Fixed

### Duplicate App Fixtures (166 ScopeMismatch Errors)
Successfully removed duplicate app() fixtures from 12 test files:
- test_api_community_subscriptions.py
- test_api_get_community.py
- test_api_get_site.py
- test_api_instance_blocks.py
- test_api_post_bookmarks.py
- test_api_post_subscriptions.py
- test_api_reply_bookmarks.py
- test_api_reply_subscriptions.py
- test_api_user_subscriptions.py
- test_activitypub_util.py

### Changes Applied
1. Removed duplicate app() fixture definitions and TestConfig classes
2. Removed imports for create_app and Config
3. Added 'session' parameter to test functions
4. Replaced all instances of 'db.session' with 'session'
5. Removed import of 'db' where present

## Current Blocker

Tests are now trying to run but fail because they cannot connect to PostgreSQL:
```
psycopg2.OperationalError: could not translate host name "test-db" to address
```

## Next Steps

To run tests locally, you need one of these options:

### Option 1: Use Docker (Recommended)
```bash
docker-compose build
docker-compose up test-runner
```

### Option 2: Set up local PostgreSQL
1. Create a test database:
```bash
createdb pyfedi_test
createuser -P pyfedi  # password: pyfedi
```

2. Run tests with DATABASE_URL:
```bash
DATABASE_URL=postgresql://pyfedi:pyfedi@localhost:5432/pyfedi_test python -m pytest tests/
```

### Option 3: Use SQLite for local testing
Modify test_env.py to use SQLite:
```python
SQLALCHEMY_DATABASE_URI = 'sqlite:///test.db'
```

## Expected Results After Database Setup

Once the database connection is resolved:
- ~166 ScopeMismatch errors should be gone ✅
- Tests should start running and reveal actual failures
- We can then focus on fixing model constructor issues and other functional problems