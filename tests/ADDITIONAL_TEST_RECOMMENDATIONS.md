# Additional Test Recommendations for ActivityPub Setup

This document outlines additional unit tests that would strengthen the test coverage for the ActivityPub user setup fix.

## Currently Implemented Tests

✅ **test_finalize_user_setup_call.py**
- Code inspection: verifies finalize_user_setup is called
- Code inspection: verifies conditional calling based on auto_activate

✅ **test_private_registration_activitypub_integration.py**
- Integration: user created with auto_activate=True gets AP setup
- Integration: user created with auto_activate=False skips AP setup
- Integration: multiple users get unique keypairs
- Integration: ActivityPub URLs use lowercase

✅ **test_startup_validation_activitypub.py**
- Startup validation finds incomplete users
- Startup validation ignores complete users
- Startup validation ignores unverified users
- Startup validation ignores banned/deleted users
- Startup validation ignores remote users
- Startup validation fixes multiple users

✅ **test_activitypub_setup_edge_cases.py** (new)
- Idempotency of finalize_user_setup
- Partial setup (has keys but missing URLs)
- Registration notification cleanup
- Plugin hook integration
- Error handling: validation continues after failures
- Error handling: database errors
- Error logging for failed users
- URL formatting with special characters
- Username case handling in URLs
- Performance: many complete users
- Result structure validation

## Additional Tests To Consider

### 1. Workflow Integration Tests

**Test: Manual Activation After Private Registration**
```python
def test_manual_activation_triggers_finalize_setup():
    """
    Test workflow:
    1. Create user with auto_activate=False
    2. Manually activate user (admin approval)
    3. Verify finalize_user_setup is called during activation
    """
```

**Test: Email Verification Flow**
```python
def test_email_verification_triggers_finalize_setup():
    """
    Test workflow:
    1. Create user requiring email verification
    2. Verify email
    3. Ensure ActivityPub setup happens at right time
    """
```

**Test: OAuth Registration Comparison**
```python
def test_oauth_and_private_registration_produce_same_setup():
    """
    Verify both OAuth and private registration workflows
    result in identical ActivityPub configuration
    """
```

### 2. Security & Validation Tests

**Test: Keypair Uniqueness Guarantee**
```python
def test_keypairs_are_cryptographically_unique():
    """
    Create 100+ users rapidly and verify:
    - All private keys are unique
    - All public keys are unique
    - Keys are properly paired (can sign/verify)
    """
```

**Test: URL Validation**
```python
def test_activitypub_urls_are_valid():
    """
    Verify generated URLs:
    - Are valid HTTPS URLs
    - Don't contain injection vulnerabilities
    - Match expected format for ActivityPub spec
    """
```

**Test: Username Edge Cases**
```python
def test_username_edge_cases():
    """
    Test usernames with:
    - Maximum length
    - Special characters (allowed ones)
    - Unicode characters
    - Leading/trailing spaces (should be trimmed)
    """
```

### 3. Database Transaction Tests

**Test: Rollback on Partial Failure**
```python
def test_transaction_rollback_on_finalize_failure():
    """
    If finalize_user_setup fails partway through:
    - Verify transaction is rolled back
    - User is left in consistent state
    - No orphaned data
    """
```

**Test: Concurrent User Creation**
```python
def test_concurrent_user_creation_safety():
    """
    Create multiple users concurrently
    Verify no race conditions in:
    - Keypair generation
    - URL assignment
    - Database commits
    """
```

### 4. Migration & Upgrade Tests

**Test: Existing Production Data**
```python
def test_startup_validation_with_production_data():
    """
    Simulate production scenario:
    - Mix of complete and incomplete users
    - Various user states (verified, banned, deleted)
    - Large number of users (performance test)
    """
```

**Test: Startup Validation Performance**
```python
def test_startup_validation_completes_quickly():
    """
    With 10,000+ users in database:
    - Validation should complete in < 30 seconds
    - Memory usage should remain reasonable
    - Should not block app startup indefinitely
    """
```

### 5. Logging & Monitoring Tests

**Test: Audit Trail**
```python
def test_finalize_user_setup_logs_all_actions():
    """
    Verify comprehensive logging:
    - User ID being processed
    - Success/failure of each step
    - Errors with full context
    - Performance metrics
    """
```

**Test: Metrics Collection**
```python
def test_startup_validation_metrics():
    """
    Verify startup validation reports:
    - Total users checked
    - Users fixed
    - Errors encountered
    - Time taken
    """
```

### 6. Admin Interface Tests

**Test: Admin Can View Incomplete Users**
```python
def test_admin_can_identify_incomplete_users():
    """
    Admin interface should show:
    - List of users without ActivityPub setup
    - Option to manually trigger finalize_user_setup
    - Status of each user's federation capability
    """
```

### 7. Federation Testing

**Test: Newly Created User Can Federate**
```python
def test_private_registration_user_can_federate():
    """
    Integration test:
    1. Create user via private registration
    2. Attempt to sign ActivityPub activity
    3. Verify signature is valid
    4. Verify remote instances can discover user
    """
```

**Test: Fixed User Can Federate**
```python
def test_fixed_user_can_federate():
    """
    Integration test:
    1. Create incomplete user (simulate old bug)
    2. Run startup validation to fix
    3. Verify user can now federate properly
    """
```

## Priority Ranking

### High Priority (Should Add)
1. ✅ Idempotency test (implemented)
2. ✅ Error handling tests (implemented)
3. Manual activation workflow test
4. Keypair uniqueness guarantee
5. Transaction rollback test

### Medium Priority (Nice to Have)
1. OAuth comparison test
2. ✅ URL validation tests (partially implemented)
3. Concurrent creation safety
4. ✅ Logging tests (partially implemented)
5. Performance benchmarks

### Low Priority (Optional)
1. Admin interface tests (if admin UI exists)
2. Full federation integration tests (may require test infrastructure)
3. Unicode username tests
4. Large-scale migration tests

## Running the Tests

```bash
# Run all ActivityPub-related tests
pytest tests/test_*activitypub*.py tests/test_finalize*.py tests/test_startup*.py -v

# Run with coverage
pytest tests/test_*activitypub*.py --cov=app.api.admin.private_registration --cov=app.startup_validation --cov=app.utils -v

# Run performance tests (when implemented)
pytest tests/test_activitypub_setup_edge_cases.py::TestStartupValidationPerformance -v
```

## Test Data Setup

For realistic testing, consider creating fixtures:
- `incomplete_user` - User without ActivityPub setup
- `complete_user` - User with full setup
- `mixed_user_dataset` - Mix of various user states
- `large_user_dataset` - 1000+ users for performance testing

## Notes

- Most integration tests require full Flask app context, which currently has environment setup issues
- Consider using factories (factory_boy) for creating test users
- Mock external dependencies (Redis, Celery) appropriately
- Use pytest-timeout for performance tests
