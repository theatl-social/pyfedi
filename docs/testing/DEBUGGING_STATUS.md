# PyFedi/PeachPie Debugging Status

**Last Updated**: 2025-01-31  
**Current Branch**: 20250127-testing-and-fixes

## 🔴 Current Status: Import Errors Blocking All Tests

### Primary Blocker
The codebase has widespread import errors due to the model refactoring completed on 2025-01-27. Approximately 17 files are importing `utcnow` from the old monolithic `models.py` instead of from `utils.py` where it now resides.

### Last Stopping Point
We completed the model refactoring (splitting 3390-line models.py into typed modules) but stopped before fixing the import errors across the codebase. Tests cannot run until these imports are corrected.

## 📋 Immediate Tasks Required

### 1. Fix utcnow Import Errors (CRITICAL)
The following files need their imports updated from:
```python
from app.models import utcnow
```
To:
```python
from app.utils import utcnow
```

Files requiring update:
- app/chat/util.py
- app/auth/util.py
- app/auth/passkeys.py
- app/auth/oauth_util.py
- app/admin/routes.py
- app/user/utils.py
- app/user/routes.py
- app/shared/auth.py
- app/topic/routes.py
- app/api/alpha/utils/post.py
- app/dev/routes.py
- app/activitypub/request_logger.py
- app/activitypub/routes/api.py
- app/activitypub/routes/actors.py
- app/community/util.py
- app/community/forms.py
- app/main/routes.py

### 2. Resolve Remaining Circular Imports
After fixing utcnow imports, there may be additional circular import issues between:
- models importing from utils (for helper functions)
- utils importing from models (for model classes)

Solution: Implement lazy imports in utils.py

### 3. Database Compatibility Issues
- TSVector fields are PostgreSQL-specific and were commented out
- Need conditional imports based on database backend
- Ensure SQLite compatibility for testing

## 🧪 Test Infrastructure Status

### Completed Tests
✅ **tests/test_activitypub_verbs_comprehensive.py** - Full ActivityPub verb coverage  
✅ **tests/test_redis_py_integration.py** - Redis integration tests  
✅ **tests/test_security/** - Security module tests

### Test Execution Plan
Once imports are fixed:
1. Start with single test: `pytest tests/test_activitypub_verbs_comprehensive.py::TestActivityPubVerbs::test_like_activity -xvs`
2. Fix any new errors that appear
3. Gradually expand to full test suite

## 🔧 Recent Completed Work

### Model Refactoring (2025-01-27)
- Split 3390-line models.py into 10 typed modules
- Added full type annotations to all models
- Created backward-compatible wrapper
- Moved old files to legacy/models/

### Redis Migration (2025-01-27)
- Replaced aioredis with redis-py for Python 3.13
- Upgraded to Redis 7 with Redis Functions
- Fixed async/sync call mismatches
- Implemented atomic rate limiting

### Security Fixes (2025-01-26)
- Fixed RCE via unsafe JSON deserialization
- Fixed SQL injection in 3 locations
- Fixed SSRF in media fetching
- Fixed DoS via malformed JSON
- Implemented actor creation rate limiting

## ⚠️ Known Issues

### Missing Dependencies
- pyotp (installed but not in requirements.txt)
- Language detection library needed for LanguageMixin

### Type Annotation Coverage
Files needing completion:
- app/activitypub/util.py (42% typed)
- app/utils.py (46% typed)

### ActivityPub Implementation
- 14/15 verbs implemented
- Move activity intentionally omitted (security risks)
- Vote federation has compatibility issues

## 📊 Progress Metrics

| Component | Status | Notes |
|-----------|---------|-------|
| Model Refactoring | ✅ Complete | All models typed and split |
| Redis Migration | ✅ Complete | Using redis-py v5.2.0 |
| Security Fixes | ✅ Complete | All critical vulnerabilities patched |
| Import Fixes | ❌ Blocked | ~17 files need updates |
| Test Suite | ❌ Blocked | Cannot run due to imports |
| Type Coverage | ⚠️ Partial | Core modules ~50% typed |

## 🚀 Next Steps After Import Fixes

1. Run comprehensive test suite
2. Complete type annotations for utils.py and activitypub/util.py
3. Update requirements.txt with missing dependencies
4. Document language detection implementation
5. Fix PostgreSQL-specific features for cross-database compatibility

## 📝 Testing Commands

### Docker-based Testing (Recommended)
The project includes a complete Docker test environment that creates its own test database and Redis instance:

```bash
# Run security tests (default)
./docker/test/run-tests.sh

# Run all tests
./docker/test/run-tests.sh all

# Run tests in watch mode
./docker/test/run-tests.sh watch

# Open debug shell to run specific tests
./docker/test/run-tests.sh shell

# Clean up test environment
./docker/test/run-tests.sh clean
```

### Manual Testing
If running tests manually outside Docker:

```bash
# After fixing imports, run:

# Single test
pytest tests/test_activitypub_verbs_comprehensive.py::TestActivityPubVerbs::test_like_activity -xvs

# All ActivityPub tests
pytest tests/test_activitypub_verbs_comprehensive.py -xvs

# Redis integration tests
pytest tests/test_redis_py_integration.py -xvs

# Full test suite
pytest

# Check for import errors
python -m py_compile app/**/*.py
```

### Test Infrastructure
- **Test Database**: PostgreSQL 15 (test-db container)
- **Test Redis**: Redis 7 (test-redis container)
- **Test Runner**: Isolated Python environment with all dependencies
- **Test Reports**: Generated in `docker/test/test-reports/` and `docker/test/coverage-reports/`

## 🔗 Related Documentation
- [TESTING_PLAN.md](./TESTING_PLAN.md) - Detailed testing strategy
- [CLAUDE.md](../../CLAUDE.md) - Project memory and instructions
- [TYPING_MIGRATION_PLAN.md](../development/TYPING_MIGRATION_PLAN.md) - Type annotation progress