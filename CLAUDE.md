# PyFedi/PeachPie Development Memory

## Important Directives
- **NEVER DELETE FILES** - Always move files to `/legacy` folder with annotation in README.md
- **MAINTAIN PYFEDI COMPATIBILITY** - PeachPie must appear as PyFedi to external servers
- **ALL PYTHON FILES MUST BE TYPED** - Use Python 3.13 type annotations everywhere

## Development Guidelines

### When Refactoring Large Files
1. **Always double-check completeness** - When splitting large files into smaller modules, verify all functionality is preserved
2. **Count and compare** - Use grep/awk to count classes, functions, etc. before and after refactoring
3. **Test imports** - Ensure all imports still work with the new structure
4. **Maintain backward compatibility** - Create wrapper modules when needed
5. **Document the changes** - Leave clear documentation about what was moved where

### File Size Guidelines
- Keep Python files under 750-1000 lines
- Split by logical functionality
- Use packages (folders with __init__.py) for related modules
- All Python files must have type annotations

## Current Status (2025-01-28)

### Branch: 20250127-testing-and-fixes
Working on test infrastructure and fixing issues.

### Completed Work
1. **Redis Migration**
   - ✅ Replaced aioredis with redis-py for Python 3.13 compatibility
   - ✅ Upgraded to Redis 7 in Docker configurations
   - ✅ Implemented Redis 7 Functions for atomic operations
   - ✅ Fixed all async/sync Redis call mismatches

2. **Model Refactoring**
   - ✅ Split 3390-line models.py into logical modules
   - ✅ Added full type annotations to all models
   - ✅ Created backward-compatible wrapper
   - ✅ Moved old files to legacy/models/

3. **Test Infrastructure**
   - ✅ Created comprehensive ActivityPub verb tests
   - ✅ Added Redis integration tests
   - ⚠️  Tests failing due to import issues - need to fix

### Redis 7 Features Implemented
- **Redis Functions** for atomic rate limiting
- **Pipeline operations** for batch processing
- **Improved Streams** performance
- **Connection pooling** with proper configuration

### Key Technical Details

#### Redis Configuration
- Single `REDIS_URL` environment variable
- `redis-py` library (v5.2.0) for all operations
- `redis.asyncio` for async processors
- Redis 7 (`redis:7-bookworm`) in Docker

#### Model Structure
```
app/models/
├── __init__.py      # Exports all models
├── base.py          # Mixins and base classes
├── user.py          # User-related models
├── community.py     # Community models
├── content.py       # Posts, replies, votes
├── instance.py      # Federation models
├── activitypub.py   # ActivityPub specific
├── moderation.py    # Reports, bans, filters
├── media.py         # Files, languages
├── notification.py  # Notifications, messages
└── misc.py          # Settings, feeds, etc.
```

### Previous Work (2025-01-27)

#### Completed Security Work
1. **Critical Vulnerabilities Fixed**
   - ✅ RCE via unsafe JSON deserialization - SafeJSONParser integrated
   - ✅ SQL injection in 3 locations - Fixed with parameterized queries
   - ⚠️  Authentication bypass - Reverted to original (broke federation)

2. **High Vulnerabilities Fixed**
   - ✅ SSRF in media fetching - URIValidator integrated
   - ✅ DoS via malformed JSON - SafeJSONParser limits
   - ✅ Actor creation spam - ActorCreationLimiter integrated  
   - ❌ Vote relay attacks - RelayProtection created but not integrated

### Key Lessons Learned
1. **CRITICAL**: Always integrate security modules into main code - I initially created modules without integration
2. **API Mismatches**: Check actual function signatures - many integration failures from wrong assumptions
3. **Docker Testing**: Must rebuild containers after changes - wasted time debugging old code
4. **Federation Balance**: Strict security can break federation - had to revert signature validation
5. **Model Refactoring**: Always verify completeness when splitting large files

### Important Implementation Details

#### API Patterns
- `URIValidator.validate()` - Raises ValueError, doesn't return result object
- `SafeJSONParser()` - No constructor params, reads from Flask config
- `ActorCreationLimiter.can_create_actor()` - Returns (allowed, reason) tuple
- Always use try/except for validators that raise exceptions

#### F-String Gotcha
Cannot use backslashes in f-string expressions:
```python
# Bad
f"%{search.replace('%', '\\%')}"

# Good  
escaped = search.replace('%', '\\%')
f"%{escaped}%"
```

### Current Vote Federation Issues
1. **audience field** - PyFedi adds non-standard field to votes
2. **Announce wrapping** - Votes wrapped in Announce confuse other implementations
3. **No suspense queue** - Votes for unknown posts are dropped
4. **Signature fallbacks** - Accepting unsigned activities for compatibility

### Next Critical Tasks
1. Fix authentication bypass while maintaining federation
2. Remove 'audience' field from votes
3. Stop Announce-wrapping votes
4. Implement suspense queue for out-of-order activities
5. Fix test import issues from model refactoring

### Testing Commands
```bash
# Rebuild Docker after changes
docker-compose build

# Check Python syntax
python -m py_compile app/**/*.py

# Run security tests
docker-compose up test-runner

# Run specific tests
python -m pytest tests/test_redis_py_integration.py -xvs
```

### User Preferences
- Wants autonomous implementation after analysis
- Prefers date-prefixed branch names (YYYYMMDD-description)  
- Expects detailed technical information with code references
- Direct feedback style: "Do better and be more careful"
- Wants to see plans before implementation
- Aligned with Lemmy's strict security model
- Expects verification of completeness when refactoring

### Files Created/Modified
- REDIS_MIGRATION_SUMMARY.md - Redis migration details
- app/models/* - Fully typed, modular model structure
- app/federation/redis_functions.py - Redis 7 optimizations
- tests/test_activitypub_verbs_comprehensive.py - Complete verb coverage
- tests/test_redis_py_integration.py - Redis integration tests
- Multiple security modules in app/security/
- Test files in tests/test_security/

Remember: 
- Security modules without integration provide ZERO protection!
- Always verify completeness when refactoring large files!
- All Python code must have type annotations!