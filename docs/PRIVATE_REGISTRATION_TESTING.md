# Private Registration API Testing Guide

This guide covers comprehensive testing of the private registration API endpoints both locally and in CI/CD environments.

## Overview

The private registration testing suite provides comprehensive coverage of:

- **HTTP Endpoint Testing** - Full request/response validation
- **Authentication & Authorization** - Secret validation, IP restrictions  
- **Configuration Testing** - Environment variables vs database settings
- **Security Testing** - Rate limiting, attack scenarios, concurrent access
- **Performance Testing** - Response time benchmarks
- **Integration Testing** - End-to-end workflow validation

## Quick Start

### Prerequisites

```bash
# Ensure virtual environment is activated
source .venv/bin/activate

# Install test dependencies (if not already installed)
uv pip install pytest pytest-cov pytest-html pytest-benchmark
```

### Basic Local Testing

```bash
# Run all private registration tests
./scripts/test-private-registration.sh --local

# Run with verbose output
./scripts/test-private-registration.sh --local --verbose

# Run specific configuration scenario
./scripts/test-private-registration.sh --local --config env-only
```

## Test Suite Structure

### 1. Core Endpoint Tests (`test_private_registration_endpoints.py`)

**Endpoints Covered:**
- `/api/alpha/admin/health` - Health check with private registration status
- `/api/alpha/admin/private_register` - Main user registration endpoint  
- `/api/alpha/admin/user/validate` - Username/email validation

**Test Categories:**
- ✅ Success scenarios with valid authentication
- ✅ Authentication failures (invalid/missing secrets)
- ✅ Feature toggle testing (enabled/disabled states)
- ✅ Input validation (malformed data, missing fields)
- ✅ Duplicate user handling
- ✅ Environment variable configuration

### 2. Security Tests (`test_private_registration_security.py`)

**Security Features:**
- ✅ Rate limiting enforcement per IP
- ✅ IP whitelist validation (CIDR ranges, exact matches)
- ✅ Concurrent request handling  
- ✅ Brute force protection
- ✅ Malicious payload handling
- ✅ Header injection protection

### 3. Legacy Unit Tests

**Existing Tests:**
- `test_private_registration.py` - Comprehensive Flask app tests
- `test_private_registration_simple.py` - Isolated unit tests

## Configuration Scenarios

The test suite supports multiple configuration scenarios to validate different deployment environments:

### Default Configuration
```bash
export PRIVATE_REGISTRATION_ENABLED=true
export PRIVATE_REGISTRATION_SECRET="your-secret-here"
export PRIVATE_REGISTRATION_ALLOWED_IPS="127.0.0.1,10.0.0.0/8"
```

### Environment-Only Configuration
Tests that settings are read from environment variables instead of database.

### Mixed Configuration  
Tests behavior when some settings come from environment, others from database.

## Local Testing Commands

### Run All Test Scenarios
```bash
# Test all configuration scenarios
./scripts/test-private-registration.sh --all

# Equivalent to running:
./scripts/test-private-registration.sh --config default
./scripts/test-private-registration.sh --config env-only  
./scripts/test-private-registration.sh --config mixed
```

### Run Specific Test Categories

```bash
# Run only endpoint integration tests
python -m pytest tests/test_private_registration_endpoints.py -v

# Run only security tests
python -m pytest tests/test_private_registration_security.py -v

# Run specific test class
python -m pytest tests/test_private_registration_endpoints.py::TestPrivateRegistrationHealthEndpoint -v

# Run with coverage
python -m pytest tests/test_private_registration_endpoints.py --cov=app.api.admin --cov-report=html
```

### Manual Testing with curl

The test script includes automated curl testing, but you can also test manually:

```bash
# Start development server
export PRIVATE_REGISTRATION_ENABLED=true
export PRIVATE_REGISTRATION_SECRET="test-secret-123"
export SERVER_NAME=localhost
flask run

# Test health endpoint
curl -H "X-PieFed-Secret: test-secret-123" \
     -H "X-Forwarded-For: 127.0.0.1" \
     http://localhost:5000/api/alpha/admin/health

# Test user validation
curl -X POST \
     -H "X-PieFed-Secret: test-secret-123" \
     -H "Content-Type: application/json" \
     -H "X-Forwarded-For: 127.0.0.1" \
     -d '{"username":"testuser","email":"test@example.com"}' \
     http://localhost:5000/api/alpha/admin/user/validate

# Test user registration
curl -X POST \
     -H "X-PieFed-Secret: test-secret-123" \
     -H "Content-Type: application/json" \
     -H "X-Forwarded-For: 127.0.0.1" \
     -d '{
       "username":"testuser",
       "email":"test@example.com", 
       "display_name":"Test User",
       "auto_activate":true
     }' \
     http://localhost:5000/api/alpha/admin/private_register
```

## CI/CD Testing

### GitHub Actions Workflow

The CI/CD workflow (`.github/workflows/private-registration-tests.yml`) includes:

1. **Matrix Testing** - Tests across multiple configuration scenarios
2. **Security Testing** - Rate limiting, IP restrictions, attack scenarios
3. **Performance Testing** - Response time benchmarks
4. **E2E Testing** - Full integration testing with real HTTP requests
5. **Test Reporting** - Comprehensive results and coverage reports

### Running CI Tests Locally

```bash
# Simulate CI environment
./scripts/test-private-registration.sh --ci --config all --verbose

# Run with coverage (like CI)
python -m pytest tests/test_private_registration_endpoints.py \
  --cov=app.api.admin \
  --cov-report=xml:coverage.xml \
  --junit-xml=test-results.xml
```

## Test Data and Fixtures

### Environment Variables for Testing
```bash
# Required for all tests
export SERVER_NAME=localhost
export PRIVATE_REGISTRATION_ENABLED=true
export PRIVATE_REGISTRATION_SECRET=test-secret-123

# Optional security settings
export PRIVATE_REGISTRATION_ALLOWED_IPS="127.0.0.1,10.0.0.0/8"
export PRIVATE_REGISTRATION_RATE_LIMIT="5"

# Test database
export DATABASE_URL="sqlite:///test_private_reg.db"
```

### Test User Data Examples

```json
{
  "username": "testuser123",
  "email": "testuser123@example.com",
  "display_name": "Test User 123",
  "password": "SecurePassword123!",
  "auto_activate": true,
  "send_welcome_email": false,
  "bio": "Test user created via private registration API",
  "timezone": "America/New_York"
}
```

## Troubleshooting

### Common Issues

**ModuleNotFoundError: No module named 'app'**
```bash
# Ensure PYTHONPATH is set
export PYTHONPATH=$PWD
```

**AttributeError: 'NoneType' object has no attribute 'lower'**
```bash
# Ensure SERVER_NAME is set
export SERVER_NAME=localhost
```

**Authentication failures**
```bash
# Check secret configuration
echo $PRIVATE_REGISTRATION_SECRET

# Verify feature is enabled
echo $PRIVATE_REGISTRATION_ENABLED
```

**Database errors**
```bash
# Reset test database
rm -f test_private_reg.db
flask init-db
```

### Debug Mode

```bash
# Run with maximum verbosity
./scripts/test-private-registration.sh --local --verbose --no-cleanup

# Run specific failing test
python -m pytest tests/test_private_registration_endpoints.py::test_health_check_success -v -s

# Enable Flask debug mode  
export FLASK_DEBUG=1
flask run
```

## Performance Benchmarking

### Basic Performance Test

```bash
# Run with timing
python -m pytest tests/test_private_registration_endpoints.py --benchmark-only

# Custom performance test
python -c "
import time
import requests

start = time.time()
for i in range(100):
    # Test health endpoint performance
    pass
end = time.time()
print(f'Average response time: {(end-start)/100:.3f}s')
"
```

### Expected Performance Metrics

- **Health Endpoint**: < 100ms response time
- **User Validation**: < 200ms response time  
- **User Registration**: < 500ms response time
- **Rate Limiting**: < 50ms additional overhead

## Security Testing

### Attack Simulation

The security test suite includes:

- **Brute Force Protection** - Multiple invalid secret attempts
- **Rate Limiting** - Exceeding request limits per IP
- **IP Spoofing** - Testing with unauthorized IP addresses
- **Payload Injection** - SQL injection, XSS attempts
- **Concurrent Access** - Race conditions, duplicate registrations

### Manual Security Testing

```bash
# Test rate limiting
for i in {1..10}; do
  curl -X POST -H "X-PieFed-Secret: test-secret" \
       -H "Content-Type: application/json" \
       -d "{\"username\":\"rate$i\",\"email\":\"rate$i@example.com\"}" \
       http://localhost:5000/api/alpha/admin/private_register
done

# Test IP restrictions
curl -X POST -H "X-PieFed-Secret: test-secret" \
     -H "X-Forwarded-For: 192.168.1.100" \
     -H "Content-Type: application/json" \
     -d '{"username":"blocked","email":"blocked@example.com"}' \
     http://localhost:5000/api/alpha/admin/private_register
```

## Test Maintenance

### Adding New Tests

1. **Endpoint Tests**: Add to `test_private_registration_endpoints.py`
2. **Security Tests**: Add to `test_private_registration_security.py`  
3. **Update CI/CD**: Modify `.github/workflows/private-registration-tests.yml` if needed
4. **Documentation**: Update this guide

### Test Data Cleanup

```bash
# Cleanup test artifacts
./scripts/test-private-registration.sh --local --cleanup

# Manual cleanup
rm -f test_private_reg.db
rm -rf test-results/
rm -f coverage*.xml
```

## Integration with Main Test Suite

```bash
# Run private registration tests as part of full test suite
python -m pytest tests/ -k "private_registration" -v

# Include in CI/CD pipeline
# Tests automatically run on PR changes to:
# - app/api/admin/**
# - app/utils.py  
# - tests/test_private_registration*
```

## Best Practices

1. **Environment Isolation** - Use separate test database and configuration
2. **Deterministic Testing** - Use fixed test data and secrets
3. **Comprehensive Coverage** - Test success, failure, and edge cases
4. **Performance Monitoring** - Track response times and resource usage
5. **Security Focus** - Regularly test attack scenarios
6. **Documentation** - Keep test documentation up to date

## Support

For issues with the private registration testing suite:

1. Check this documentation for troubleshooting steps
2. Review test output for specific error messages  
3. Verify environment configuration
4. Run tests in isolation to identify issues
5. Check CI/CD workflow logs for detailed information