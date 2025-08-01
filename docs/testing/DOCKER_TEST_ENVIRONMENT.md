# Docker Test Environment Guide

This document explains the PyFedi test environment setup and common issues encountered.

## Overview

PyFedi uses a Docker-based test environment to ensure consistent test execution across different development machines. The test environment includes:
- PostgreSQL 15 database
- Redis 7 for caching and queues  
- Python 3.13 application container
- Isolated test database that gets reset between runs

## Directory Structure

```
docker/test/
├── Dockerfile          # Test container definition
├── docker-compose.yml  # Test services configuration
├── test-entrypoint.sh  # Container startup script
├── test_env.py        # Test environment configuration
├── init_test_db_custom.py  # Database initialization
└── fixtures.py        # Test data fixtures
```

## Key Components

### 1. Test Database
- Separate from development database
- Uses `test-db` service name
- Automatically runs migrations on startup
- Gets populated with test fixtures

### 2. Test Configuration
The test environment uses specific configuration:
- `FLASK_ENV=testing`
- `TESTING=1`
- `SERVER_NAME=test.local`
- Signatures not required for easier testing

### 3. Service Names
Important: Test services have different names:
- Database: `test-db` (not `db`)
- Redis: `test-redis` (not `redis`)
- Runner: `test-runner`

## Common Issues and Solutions

### Issue: "could not translate host name"
**Error**: `could not translate host name "test-db" to address`

**Cause**: Running tests outside Docker container, so Docker service names don't resolve

**Solution**: Always run tests inside Docker:
```bash
docker-compose run --rm test-runner python -m pytest
```

### Issue: Permission Denied for /dev/shm
**Error**: `PermissionError: [Errno 1] Operation not permitted: '/dev/shm'`

**Cause**: Trying to create cache directory on local machine

**Solution**: Run inside Docker or adjust cache configuration

### Issue: Docker Image Not Updating
**Symptom**: Fixed code still shows old errors

**Solution**: Rebuild the test image:
```bash
cd docker/test
docker-compose build test-runner
```

### Issue: Multiple docker-compose Files
**Warning**: `Found multiple config files with supported names`

**Solution**: Use specific file:
```bash
docker-compose -f docker/test/docker-compose.yml run test-runner
```

## Running Tests

### Basic Test Execution
```bash
# Run all tests
docker-compose run --rm test-runner

# Run specific test file
docker-compose run --rm test-runner python -m pytest tests/test_file.py

# Run specific test with verbose output
docker-compose run --rm test-runner python -m pytest tests/test_file.py::test_name -xvs

# Run with coverage
docker-compose run --rm test-runner python -m pytest --cov=app --cov-report=html
```

### Test Execution Flow
1. Container starts and waits for PostgreSQL/Redis
2. Runs database migrations
3. Initializes test data (fixtures)
4. Executes pytest
5. Outputs results to `test-reports/` and `coverage-reports/`

### Debugging Tests
```bash
# Get a shell in the test container
docker-compose run --rm test-runner /bin/bash

# Check database state
docker-compose run --rm test-runner flask shell
>>> from app.models import User, Site
>>> Site.query.all()

# View logs
docker-compose logs test-db
docker-compose logs test-redis
```

## Test Data Setup

### Automatic Setup
The test environment automatically creates:
- Site with id=1 (required for g.site)
- Local instance with id=1  
- Test user with id=1
- Test community

### Manual Fixtures
Additional fixtures can be added in `conftest.py`:
```python
@pytest.fixture
def test_data(session, test_site):
    # Create test data
    return {...}
```

## Troubleshooting Workflow

1. **Check if services are running**:
   ```bash
   docker-compose ps
   ```

2. **Rebuild if model changes were made**:
   ```bash
   docker-compose build test-runner
   ```

3. **Check migration status**:
   ```bash
   docker-compose run --rm test-runner flask db current
   ```

4. **Reset test database**:
   ```bash
   docker-compose down -v
   docker-compose up -d test-db test-redis
   ```

5. **View detailed errors**:
   ```bash
   docker-compose run --rm test-runner python -m pytest -xvs --tb=short
   ```

## Performance Tips

1. **Use -x flag** to stop on first failure when debugging
2. **Run specific tests** instead of full suite during development
3. **Keep containers running** between test runs:
   ```bash
   docker-compose up -d test-db test-redis
   ```
4. **Mount source code** for faster iteration (watch mode)

## Integration with CI/CD

The same Docker setup can be used in CI/CD pipelines:
```yaml
- name: Run tests
  run: |
    docker-compose -f docker/test/docker-compose.yml build
    docker-compose -f docker/test/docker-compose.yml run test-runner
```

## Current Known Issues

1. **Slow startup**: Database migrations run every time
2. **Port conflicts**: Test database uses standard PostgreSQL port
3. **Volume persistence**: Test data persists between runs unless explicitly cleared

## Best Practices

1. **Always rebuild after model changes**
2. **Use specific test database** (never test against production data)
3. **Check migrations are up to date** before running tests
4. **Use fixtures for consistent test data**
5. **Clean up volumes** when switching branches

This test environment ensures consistent, isolated testing while closely mimicking the production environment.