# PyFedi Docker Test Environment

This directory contains a complete Docker-based testing environment for PyFedi, with a focus on security testing.

## Quick Start

```bash
# Run security tests (default)
./docker/test/run-tests.sh

# Run all tests
./docker/test/run-tests.sh all

# Run tests in watch mode
./docker/test/run-tests.sh watch

# Open debug shell
./docker/test/run-tests.sh shell

# Clean up
./docker/test/run-tests.sh clean
```

## Architecture

The test environment consists of three containers:

1. **test-db**: PostgreSQL 15 database for tests
2. **test-redis**: Redis 7 for caching/queuing tests  
3. **test-runner**: Python environment with all dependencies

## Test Types

### Security Tests
Tests all security modules including:
- JSON parser (DoS protection)
- Signature validator (auth bypass prevention)
- URI validator (SSRF protection)
- Actor limits (rate limiting)
- Relay protection (vote amplification prevention)
- Media proxy (SSRF prevention)
- Permission validator (privilege escalation prevention)
- Error handler (information disclosure prevention)

### Linting
```bash
./docker/test/run-tests.sh lint
```
Runs:
- flake8 (style checking)
- black (code formatting)
- isort (import sorting)
- mypy (type checking)

### Security Scanning
```bash
./docker/test/run-tests.sh scan
```
Runs:
- bandit (security linting)
- safety (dependency vulnerabilities)
- SQL injection audit

## Test Reports

Test outputs are saved to:
- `docker/test/coverage-reports/` - HTML coverage reports
- `docker/test/test-reports/` - JUnit XML, security scan results

## Environment Variables

Configuration is in `docker/test/.env.test`. Key settings:
- `TESTING=1` - Enables test mode
- `REQUIRE_SIGNATURES=true` - Enforces signature validation
- `MAX_JSON_SIZE=1000000` - 1MB JSON limit
- `ACTORS_PER_INSTANCE_HOUR=10` - Rate limiting

## Writing New Tests

1. Add test files to `tests/test_security/`
2. Follow naming convention: `test_*.py`
3. Use fixtures from `conftest.py`
4. Run in watch mode for development

Example test:
```python
def test_new_security_feature():
    # Arrange
    validator = NewValidator()
    
    # Act
    result = validator.validate(malicious_input)
    
    # Assert
    assert result is False
```

## CI/CD Integration

For GitHub Actions:
```yaml
- name: Run Security Tests
  run: |
    docker-compose -f docker/test/docker-compose.yml up --build --abort-on-container-exit test-runner
    docker-compose -f docker/test/docker-compose.yml down -v
```

## Troubleshooting

### Tests won't start
- Check Docker is running: `docker ps`
- Check ports 5432 and 6379 are free
- Run `./docker/test/run-tests.sh clean` and retry

### Import errors
- Ensure all dependencies are in `requirements.txt`
- Rebuild: `docker-compose -f docker/test/docker-compose.yml build --no-cache`

### Debugging failures
```bash
# Open shell in test container
./docker/test/run-tests.sh shell

# Run specific test
pytest tests/test_security/test_json_validator.py -v

# Check database
psql $DATABASE_URL
```

## Performance

- First run: ~2-3 minutes (building images)
- Subsequent runs: ~30 seconds (using cache)
- Watch mode: Near instant feedback

## Security

This is a **test environment only**. It uses:
- Weak passwords (testpass)
- Insecure secrets (test-secret-key)
- Permissive settings

Never use these settings in production!