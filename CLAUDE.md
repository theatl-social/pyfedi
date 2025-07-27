# PyFedi/PeachPie Development Memory

## Important Directives
- **NEVER DELETE FILES** - Always move files to `/legacy` folder with annotation in README.md
- **MAINTAIN PYFEDI COMPATIBILITY** - PeachPie must appear as PyFedi to external servers

## Current Status (2025-01-27)

### Branch: 20250127-integrate-security-fixes
Completed integration of critical security fixes into main codebase.

### Completed Security Work
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

### Important Implementation Details

#### Redis Configuration
- PyFedi uses `CACHE_REDIS_URL` for main app
- Security modules look for `REDIS_URL` (not set by default)
- Need to add: `REDIS_URL=redis://redis:6379/2`

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
5. Add REDIS_URL to production environment

### Testing Commands
```bash
# Rebuild Docker after changes
docker-compose build

# Check Python syntax
python -m py_compile app/**/*.py

# Run security tests
docker-compose up test-runner
```

### User Preferences
- Wants autonomous implementation after analysis
- Prefers date-prefixed branch names (YYYYMMDD-description)  
- Expects detailed technical information with code references
- Direct feedback style: "Do better and be more careful"
- Wants to see plans before implementation
- Aligned with Lemmy's strict security model

### Files Created This Session
- SECURITY_LEARNINGS.md - Mistakes and lessons from integration
- ACTIVITYPUB_PROTOCOL_MISMATCHES.md - Detailed protocol compatibility issues
- Multiple security modules in app/security/
- Test files in tests/test_security/

Remember: Security modules without integration provide ZERO protection!