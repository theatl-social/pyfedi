# PeachPie Testing Guide

## Overview

PeachPie includes a comprehensive test suite covering all refactored components. The tests are designed to run without requiring actual external services or federation partners, making them fast and reliable.

## Test Categories

### 1. Unit Tests

#### Federation Components (`test_federation_components.py`)
- **Instance Health Monitor**: Circuit breaker pattern, success/failure tracking
- **Rate Limiter**: Per-destination limits, adaptive rate adjustment, burst allowance
- **Task Scheduler**: Cron/interval/one-time scheduling, task execution
- **Maintenance Processor**: Cleanup tasks, statistics updates

#### ActivityPub Routes (`test_activitypub_routes.py`)
- All 41 ActivityPub endpoints
- Actor endpoints (users, communities, server)
- Inbox/Outbox handling
- Collections (followers, following, liked)
- Object retrieval (posts, comments)
- Content negotiation

#### Database Management (`test_database_management.py`)
- Non-interactive initialization
- PostgreSQL connection handling
- Migration execution
- Schema improvements
- Environment configuration

#### Security Mitigations (`test_security_mitigations.py`)
- SQL injection prevention
- SSRF protection
- Authentication bypass prevention
- Rate limiting enforcement
- Safe JSON parsing
- HTML/XSS sanitization

### 2. Integration Tests

#### Redis Streams (`test_redis_streams.py`)
- Stream processing workflow
- Message retry logic
- Dead Letter Queue
- Performance benchmarks

#### Security Integration (`test_security/`)
- End-to-end security scenarios
- Federation security
- API security

## Running Tests

### Quick Start

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_federation_components.py

# Run specific test
pytest tests/test_federation_components.py::TestInstanceHealthMonitor::test_circuit_breaker_logic

# Run with verbose output
pytest -xvs
```

### Comprehensive Test Suite

Use the test runner for complete analysis:

```bash
# Basic run
python tests/run_comprehensive_tests.py

# With coverage report
python tests/run_comprehensive_tests.py --coverage

# With performance benchmarks
python tests/run_comprehensive_tests.py --performance

# All options
python tests/run_comprehensive_tests.py --coverage --performance
```

### Docker Testing

```bash
# Run tests in Docker
docker-compose run --rm app pytest

# With specific test file
docker-compose run --rm app pytest tests/test_activitypub_routes.py
```

## Test Configuration

### Environment Variables

Tests use these environment variables (set automatically by test runner):

```bash
FLASK_ENV=testing
DATABASE_URL=sqlite:///:memory:
REDIS_URL=redis://localhost:6379/15
SECRET_KEY=test-secret-key
SERVER_NAME=test.instance
SOFTWARE_NAME=PeachPie
NON_INTERACTIVE=true
```

### Fixtures

Key fixtures available in `conftest.py`:

- `app`: Flask application configured for testing
- `client`: Flask test client
- `session`: Database session with automatic rollback
- `redis_client`: Mocked Redis client
- `async_session`: Async database session
- `test_user`, `test_community`, `test_post`: Sample data
- `ap_actor_data`, `ap_create_activity`: ActivityPub test data
- `mock_httpx`: Mocked HTTP client

## Writing Tests

### Unit Test Example

```python
class TestNewFeature:
    """Test the new feature."""
    
    def test_feature_initialization(self):
        """Test feature initializes correctly."""
        feature = NewFeature(param="value")
        assert feature.param == "value"
    
    @pytest.mark.asyncio
    async def test_async_operation(self, redis_client):
        """Test async operation."""
        feature = NewFeature(redis_client)
        result = await feature.async_method()
        assert result is not None
```

### Mocking External Services

```python
def test_external_api_call(self, mock_httpx):
    """Test calling external API."""
    # Setup mock response
    mock_httpx.get.return_value.json.return_value = {"status": "ok"}
    
    # Test the call
    result = fetch_external_data("https://api.example.com")
    
    # Verify
    assert result["status"] == "ok"
    mock_httpx.get.assert_called_with("https://api.example.com")
```

### Testing Security

```python
def test_sql_injection_prevention(self):
    """Test SQL injection is prevented."""
    dangerous_input = "'; DROP TABLE users; --"
    
    # Should safely handle dangerous input
    result = User.query.filter_by(username=dangerous_input).first()
    
    # Query should not execute malicious SQL
    assert result is None
    # Database should still be intact
    assert User.query.count() >= 0
```

## Coverage Goals

Target coverage percentages:

- **Overall**: 80%+ coverage
- **Critical paths**: 95%+ (federation, security)
- **New code**: 90%+ for all new features

View coverage report:
```bash
# Generate HTML report
pytest --cov=app --cov-report=html

# Open report
open htmlcov/index.html
```

## Performance Testing

### Redis Streams Benchmark

The test suite includes performance benchmarks:

```python
def test_redis_streams_performance():
    """Test Redis Streams can handle high throughput."""
    # Queues 1000 tasks and measures time
    # Should complete in under 1 second
```

### Load Testing

For load testing federation endpoints:

```bash
# Use locust for load testing
locust -f tests/load/federation_load_test.py
```

## Continuous Integration

### GitHub Actions

Tests run automatically on:
- Pull requests
- Pushes to main branch
- Nightly scheduled runs

### Pre-commit Hooks

Install pre-commit hooks to run tests locally:

```bash
pre-commit install
```

## Debugging Failed Tests

### Verbose Output

```bash
# Show all output
pytest -xvs tests/test_file.py

# Stop on first failure
pytest -x

# Show local variables on failure
pytest -l
```

### Interactive Debugging

```python
# Add breakpoint in test
import pdb; pdb.set_trace()

# Or use pytest's built-in
pytest --pdb
```

### Check Test Logs

```bash
# Federation logs
tail -f logs/federation.log

# Application logs
tail -f logs/app.log
```

## Common Issues

### Redis Connection

If tests fail with Redis errors:
```bash
# Start Redis
redis-server

# Or with Docker
docker run -d -p 6379:6379 redis:7
```

### Database Issues

For database-related failures:
```bash
# Reset test database
flask db upgrade

# Or use in-memory SQLite
export DATABASE_URL=sqlite:///:memory:
```

### Async Test Issues

For async test problems:
```python
# Ensure proper async fixtures
@pytest.mark.asyncio
async def test_async():
    # test code
```

## Test Maintenance

### Adding New Tests

1. Create test file following naming convention: `test_<feature>.py`
2. Add test class for organization
3. Use descriptive test names
4. Add docstrings explaining what's tested
5. Update test runner if new category

### Updating Fixtures

When adding new fixtures:
1. Add to `conftest.py` for shared fixtures
2. Document fixture purpose
3. Ensure proper cleanup
4. Consider scope (function, class, module, session)

### Test Data

- Use factories for complex test data
- Keep test data minimal but realistic
- Clean up after tests
- Don't rely on database state

## Best Practices

1. **Fast Tests**: Keep unit tests under 100ms each
2. **Independent**: Tests shouldn't depend on each other
3. **Deterministic**: Same result every time
4. **Clear Names**: Test name should explain what's tested
5. **Single Responsibility**: Test one thing per test
6. **Use Fixtures**: Don't repeat setup code
7. **Mock External**: Mock all external dependencies
8. **Assert Specific**: Make specific assertions
9. **Clean Up**: Always clean up resources
10. **Document Why**: Explain complex test scenarios