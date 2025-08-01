# PyFedi Testing and Fixes Plan

## Current Status (2025-01-27)

### Completed Work
1. ✅ Replaced Celery with Redis Streams
2. ✅ Migrated from aioredis to redis-py for Python 3.13 compatibility
3. ✅ Created comprehensive ActivityPub verb tests
4. ✅ Consolidated models into typed modules
5. ✅ Added type annotations to key modules:
   - auth/util.py (100%)
   - signature.py (100%)
   - community/util.py (91%)
6. ✅ Documented ActivityPub coverage (14/15 verbs implemented)
7. ✅ Fixed circular imports by moving utcnow to utils.py

### Current Blockers
1. **Circular Import Issues**
   - Many files import `utcnow` from models instead of utils
   - Need to update ~17 files to fix this
   - Event listeners in utils.py need to be moved

2. **PostgreSQL Dependencies**
   - TSVector fields commented out for testing
   - Need conditional imports based on database backend

3. **Missing Dependencies**
   - pyotp (installed but not in requirements.txt)
   - Language detection library needed

## Immediate Next Steps

### 1. Fix utcnow Imports (High Priority)
Create and run script to fix all files importing utcnow from models:
```python
# Files to fix:
app/chat/util.py
app/auth/util.py
app/auth/passkeys.py
app/auth/oauth_util.py
app/admin/routes.py
app/user/utils.py
app/user/routes.py
app/shared/auth.py
app/topic/routes.py
app/api/alpha/utils/post.py
app/dev/routes.py
app/activitypub/request_logger.py
app/activitypub/routes/api.py
app/activitypub/routes/actors.py
app/community/util.py
app/community/forms.py
app/main/routes.py
```

### 2. Run Iterative Tests
Once imports are fixed:
1. Run single test: `pytest tests/test_activitypub_verbs_comprehensive.py::TestActivityPubVerbs::test_like_activity -xvs`
2. Fix any new errors that appear
3. Gradually expand to full test suite

### 3. Database Compatibility
- Create database backend detection
- Conditionally enable TSVector fields for PostgreSQL
- Ensure SQLite compatibility for testing

### 4. Complete Type Annotations
Priority files needing annotations:
- app/activitypub/util.py (42% typed)
- app/utils.py (46% typed)

## Long-term Tasks

1. **Language Detection**
   - Install langdetect or similar
   - Implement detect_language() in LanguageMixin
   
2. **Event Listeners**
   - Move User.unread_notifications listener from utils.py
   - Create proper event registration system

3. **Requirements Update**
   - Add pyotp to requirements.txt
   - Add optional PostgreSQL dependencies
   - Document language detection options

## Testing Strategy

1. **Phase 1**: Fix all import errors
2. **Phase 2**: Run ActivityPub verb tests
3. **Phase 3**: Run model tests
4. **Phase 4**: Run integration tests
5. **Phase 5**: Full test suite

## Known Issues to Address

1. **Circular Imports**
   - models imports from utils (for functions)
   - utils imports from models (for model classes)
   - Solution: Lazy imports in utils.py

2. **Database-specific Features**
   - TSVector for PostgreSQL
   - Need fallback for SQLite

3. **Missing Move Activity**
   - Documented as intentionally not implemented
   - Complex requirements, security risks

## Success Criteria

- [ ] All tests pass
- [ ] No circular import errors
- [ ] Type coverage > 80% for core modules
- [ ] Documentation updated
- [ ] Requirements.txt complete