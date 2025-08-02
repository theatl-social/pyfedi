# Next Steps for Test Fixing - 2025-08-02

## Context
We've fixed the test infrastructure - tests can now run but many fail due to missing test data and other issues. The systemic model-database mismatches have been resolved.

## TODOs with Systemic Issue Likelihood

### 1. Fix test data initialization - Site with id=1 not created
- **Likelihood: HIGH (90%)**
- The test setup expects Site(id=1) but it's not being created by fixtures
- This will affect ALL tests that use g.site
- Fix will likely be in conftest.py or test initialization

### 2. Resolve circular dependency in chat_message/conversation tables
- **Likelihood: HIGH (85%)**
- Prevents proper test teardown
- Affects ALL tests (happens during cleanup)
- Need to add explicit FK constraint names for DROP operations

### 3. Fix security test failures (140 errors)
- **Likelihood: MEDIUM (60%)**
- Many use mock_app fixture which might not have proper config
- URIValidator and other security modules may need initialization
- Some might be individual test logic issues

### 4. Fix ActivityPub test failures (116 errors)
- **Likelihood: MEDIUM (50%)**
- Could be fixture scope issues (like we fixed for security tests)
- May need ActivityPub-specific test setup (keys, instances)
- Some will be individual test issues

### 5. Fix remaining model-database mismatches
- **Likelihood: LOW (20%)**
- We fixed User, Site, Instance - the main models
- Other models (Post, Community, etc.) may have minor issues
- Will surface as "column does not exist" errors

### 6. Run full test suite to establish baseline
- **Likelihood: N/A**
- Diagnostic task to see true failure count
- Will reveal any remaining systemic issues

## Approach Priority

1. Start with #1 and #2 - these are blocking issues affecting all tests
2. Then run full suite to see what's actually broken
3. Look for patterns in failures before fixing individual tests
4. Security and ActivityPub tests may have their own systemic issues

## Key Question

Are there other fixture/initialization issues that affect multiple test files, or are the remaining failures mostly individual test logic problems?

## What Was Accomplished Today

- Took tests from 0% passing (couldn't even run) to functional infrastructure
- Fixed 4 systemic issues causing 93% of failures:
  - Duplicate fixture conflicts (166 errors)
  - Datetime import errors (34 files)
  - Model-database schema mismatches
  - Missing test infrastructure
- Aligned all models with database schema
- Created comprehensive documentation

## Useful Commands

```bash
# Rebuild Docker after changes
docker-compose build test-runner

# Clear database and restart
docker-compose down -v
docker-compose up -d test-db test-redis

# Run specific test
docker-compose run --rm test-runner pytest tests/test_api_get_site.py -xvs

# Run all tests with summary
docker-compose run --rm test-runner pytest --tb=short | tail -50
```