# PieFed Admin API Documentation

**Proprietary to PieFed** - Advanced administrative API for user management and private registration.

## Overview

The PieFed Admin API provides secure, programmatic access to administrative functions including private user registration, user management, and system monitoring. This API is designed for server-to-server communication within a VPC or trusted network environment.

### Key Features

- **Private Registration**: Create users without public registration
- **User Management**: Comprehensive user lifecycle management
- **Monitoring & Analytics**: Real-time metrics and audit trails
- **Advanced Rate Limiting**: Redis-backed sliding window rate limiting
- **OpenAPI Documentation**: Full Swagger UI integration at `/api/alpha/swagger`

## Security Model

All endpoints require authentication via the `X-PieFed-Secret` header:

```bash
curl -H "X-PieFed-Secret: your-secret-key" https://your-instance.com/api/alpha/admin/health
```

### Security Features

- **Secret-based authentication** with constant-time comparison
- **Optional IP whitelisting** for VPC deployment
- **Rate limiting** with per-operation limits
- **Comprehensive audit logging** of all actions
- **Input sanitization** to prevent XSS attacks

## Configuration

### Required Environment Variables

```bash
# Enable the admin API
PRIVATE_REGISTRATION_ENABLED=true

# Set your secret key (keep this secure!)
PRIVATE_REGISTRATION_SECRET=your-very-secure-secret-key-here
```

### Optional Configuration

```bash
# Rate limiting (default: 10/hour for registration)
PRIVATE_REGISTRATION_RATE_LIMIT=10/hour

# IP whitelist for VPC security (CIDR notation)
PRIVATE_REGISTRATION_IPS=10.0.0.0/8,192.168.1.0/24

# Redis for advanced features (recommended)
CACHE_REDIS_URL=redis://localhost:6379/0
```

## API Endpoints

### Phase 1: Private Registration (5 endpoints)

#### Create User
```http
POST /api/alpha/admin/private_register
Content-Type: application/json
X-PieFed-Secret: your-secret-key

{
  "username": "newuser",
  "email": "user@example.com",
  "display_name": "New User",
  "auto_activate": true
}
```

**Response:**
```json
{
  "success": true,
  "user_id": 123,
  "username": "newuser",
  "email": "user@example.com",
  "generated_password": "secure-random-password",
  "message": "User created successfully"
}
```

#### Validate User Availability
```http
POST /api/alpha/admin/user/validate
Content-Type: application/json
X-PieFed-Secret: your-secret-key

{
  "username": "testuser",
  "email": "test@example.com"
}
```

#### List Users
```http
GET /api/alpha/admin/users?local_only=true&page=1&limit=50
X-PieFed-Secret: your-secret-key
```

#### Look Up User
```http
GET /api/alpha/admin/user/lookup?username=testuser
X-PieFed-Secret: your-secret-key
```

#### Health Check
```http
GET /api/alpha/admin/health
X-PieFed-Secret: your-secret-key
```

### Phase 2: User Management (13 endpoints)

#### Update User Profile
```http
PUT /api/alpha/admin/user/123
Content-Type: application/json
X-PieFed-Secret: your-secret-key

{
  "display_name": "Updated Name",
  "email": "newemail@example.com",
  "bio": "Updated bio"
}
```

#### User Actions
```http
# Ban user
POST /api/alpha/admin/user/123/ban
Content-Type: application/json
X-PieFed-Secret: your-secret-key

{
  "reason": "Spam violation",
  "notify_user": false
}

# Unban user
POST /api/alpha/admin/user/123/unban
X-PieFed-Secret: your-secret-key

# Disable user
POST /api/alpha/admin/user/123/disable
Content-Type: application/json
X-PieFed-Secret: your-secret-key

{
  "reason": "Policy violation"
}

# Enable user
POST /api/alpha/admin/user/123/enable
X-PieFed-Secret: your-secret-key

# Soft delete user
DELETE /api/alpha/admin/user/123
Content-Type: application/json
X-PieFed-Secret: your-secret-key

{
  "reason": "GDPR deletion request"
}
```

#### Bulk Operations
```http
POST /api/alpha/admin/users/bulk
Content-Type: application/json
X-PieFed-Secret: your-secret-key

{
  "operation": "ban",
  "user_ids": [123, 124, 125],
  "reason": "Coordinated spam attack",
  "notify_users": false
}
```

**Response:**
```json
{
  "success": true,
  "operation": "ban",
  "total_requested": 3,
  "successful": 3,
  "failed": 0,
  "results": [
    {"user_id": 123, "success": true, "message": "User banned successfully"},
    {"user_id": 124, "success": true, "message": "User banned successfully"},
    {"user_id": 125, "success": true, "message": "User banned successfully"}
  ]
}
```

#### Statistics
```http
# User statistics
GET /api/alpha/admin/stats/users
X-PieFed-Secret: your-secret-key

# Registration analytics
GET /api/alpha/admin/stats/registrations?days=30&include_hourly=true
X-PieFed-Secret: your-secret-key
```

#### Export Users
```http
POST /api/alpha/admin/users/export
Content-Type: application/json
X-PieFed-Secret: your-secret-key

{
  "format": "csv",
  "export_fields": ["id", "username", "email", "created_at"],
  "filters": {
    "local_only": true,
    "verified": true
  }
}
```

### Phase 3: Monitoring & Operations (4 endpoints)

#### Prometheus Metrics
```http
GET /api/alpha/admin/metrics
X-PieFed-Secret: your-secret-key
```

**Prometheus Format:**
```http
GET /api/alpha/admin/metrics
Accept: text/plain
X-PieFed-Secret: your-secret-key
```

#### Comprehensive Health Check
```http
GET /api/alpha/admin/monitoring/health
X-PieFed-Secret: your-secret-key
```

**Response:**
```json
{
  "timestamp": "2025-01-02T12:00:00Z",
  "status": "healthy",
  "checks": {
    "database": {
      "status": "healthy",
      "message": "Database connection OK"
    },
    "redis": {
      "status": "healthy",
      "response_time_ms": 5,
      "message": "Redis connection OK"
    },
    "rate_limiting": {
      "status": "healthy",
      "message": "Rate limiting functional"
    }
  }
}
```

#### Rate Limit Status
```http
GET /api/alpha/admin/monitoring/rate-limits
X-PieFed-Secret: your-secret-key
```

#### Audit Trail
```http
GET /api/alpha/admin/monitoring/audit
X-PieFed-Secret: your-secret-key
```

## Rate Limiting

### Default Limits

| Operation | Default Limit | Description |
|-----------|---------------|-------------|
| Private Registration | 10/hour | Creating new users |
| User Lookup | 100/hour | Searching for users |
| User Modification | 50/hour | Updating user profiles |
| Bulk Operations | 5/hour | Mass user actions |
| Statistics | 60/hour | Analytics queries |

### Rate Limit Headers

When rate limited, responses include:

```json
{
  "success": false,
  "error": "rate_limited",
  "message": "Rate limit exceeded for private_registration",
  "details": {
    "limit": 10,
    "remaining": 0,
    "reset_time": 1704128400,
    "retry_after": 300
  }
}
```

## Error Handling

### Standard Error Format

```json
{
  "success": false,
  "error": "error_type",
  "message": "Human readable error message",
  "details": {
    "field_errors": {},
    "additional_info": {}
  }
}
```

### Common Error Types

- `invalid_secret` - Invalid authentication
- `feature_disabled` - Admin API not enabled
- `ip_unauthorized` - IP not whitelisted
- `rate_limited` - Rate limit exceeded
- `validation_failed` - Input validation error
- `user_not_found` - User doesn't exist

## Monitoring & Observability

### Metrics Collection

The API automatically collects:
- Request counts by endpoint and method
- Response times and performance metrics
- Error rates and status code distribution
- Rate limiting statistics
- Client request patterns

### Health Monitoring

Use `/api/alpha/admin/monitoring/health` for:
- Load balancer health checks
- Dependency validation (database, Redis)
- System status monitoring
- Automated alerting triggers

### Audit Trail

All administrative actions are logged with:
- Timestamp and operation details
- Client IP and user agent
- Success/failure status
- Error reasons and context

## Deployment Guide

### 1. Environment Setup

```bash
# Copy environment template
cp .env.sample .env

# Edit configuration
vim .env
```

Add admin API configuration:
```bash
PRIVATE_REGISTRATION_ENABLED=true
PRIVATE_REGISTRATION_SECRET=generate-a-secure-secret-here
```

### 2. Redis Setup (Recommended)

```bash
# Install Redis
sudo apt install redis-server

# Configure Redis URL
echo "CACHE_REDIS_URL=redis://localhost:6379/0" >> .env
```

### 3. Verify Installation

```bash
# Test health endpoint
curl -H "X-PieFed-Secret: your-secret" http://localhost:5000/api/alpha/admin/health

# Check Swagger documentation
open http://localhost:5000/api/alpha/swagger
```

## Integration Examples

### Python Integration

```python
import requests

class PieFedAdmin:
    def __init__(self, base_url, secret):
        self.base_url = base_url
        self.headers = {
            'X-PieFed-Secret': secret,
            'Content-Type': 'application/json'
        }
    
    def create_user(self, username, email, display_name=None):
        data = {
            'username': username,
            'email': email,
            'display_name': display_name or username,
            'auto_activate': True
        }
        response = requests.post(
            f"{self.base_url}/api/alpha/admin/private_register",
            json=data,
            headers=self.headers
        )
        return response.json()
    
    def ban_user(self, user_id, reason):
        data = {'reason': reason}
        response = requests.post(
            f"{self.base_url}/api/alpha/admin/user/{user_id}/ban",
            json=data,
            headers=self.headers
        )
        return response.json()

# Usage
admin = PieFedAdmin('https://your-instance.com', 'your-secret')
result = admin.create_user('newuser', 'user@example.com')
print(f"Created user {result['user_id']}")
```

### Bash/cURL Integration

```bash
#!/bin/bash

API_BASE="https://your-instance.com/api/alpha/admin"
SECRET="your-secret-key"

# Function to call admin API
call_admin_api() {
    local endpoint="$1"
    local method="${2:-GET}"
    local data="$3"
    
    if [ -n "$data" ]; then
        curl -s -X "$method" \
             -H "X-PieFed-Secret: $SECRET" \
             -H "Content-Type: application/json" \
             -d "$data" \
             "$API_BASE$endpoint"
    else
        curl -s -X "$method" \
             -H "X-PieFed-Secret: $SECRET" \
             "$API_BASE$endpoint"
    fi
}

# Create a user
create_user() {
    local username="$1"
    local email="$2"
    local data="{\"username\":\"$username\",\"email\":\"$email\",\"auto_activate\":true}"
    call_admin_api "/private_register" "POST" "$data"
}

# Usage
create_user "testuser" "test@example.com"
```

## Security Best Practices

### Secret Management

- **Never commit secrets to version control**
- Use environment variables or secret management systems
- Rotate secrets regularly
- Use different secrets for different environments

### Network Security

- Deploy within a VPC or private network
- Use IP whitelisting for additional security
- Consider TLS termination at load balancer
- Monitor for unusual request patterns

### Monitoring & Alerting

- Set up alerts for rate limit violations
- Monitor error rates and response times
- Track authentication failures
- Review audit logs regularly

## Troubleshooting

### Common Issues

**403 Forbidden - Feature Disabled**
```bash
# Check environment variable
echo $PRIVATE_REGISTRATION_ENABLED
# Should be 'true'
```

**401 Unauthorized - Invalid Secret**
```bash
# Verify secret is set correctly
echo $PRIVATE_REGISTRATION_SECRET
# Check for extra whitespace or special characters
```

**429 Too Many Requests**
```bash
# Check rate limit status
curl -H "X-PieFed-Secret: $SECRET" "$API_BASE/monitoring/rate-limits"
```

**503 Service Unavailable**
```bash
# Check health endpoint
curl -H "X-PieFed-Secret: $SECRET" "$API_BASE/monitoring/health"
```

### Debug Mode

Enable debug logging in your PieFed configuration to see detailed admin API activity:

```bash
export FLASK_ENV=development
export FLASK_DEBUG=1
```

## API Reference Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/private_register` | POST | Create user with private registration |
| `/user/validate` | POST | Check username/email availability |
| `/users` | GET | List users with filtering |
| `/user/lookup` | GET | Find specific user |
| `/health` | GET | Basic health check |
| `/user/{id}` | PUT | Update user profile |
| `/user/{id}/disable` | POST | Disable user account |
| `/user/{id}/enable` | POST | Enable user account |
| `/user/{id}/ban` | POST | Ban user account |
| `/user/{id}/unban` | POST | Unban user account |
| `/user/{id}` | DELETE | Soft delete user |
| `/users/bulk` | POST | Bulk user operations |
| `/stats/users` | GET | User statistics |
| `/stats/registrations` | GET | Registration analytics |
| `/users/export` | POST | Export user data |
| `/metrics` | GET | Prometheus metrics |
| `/monitoring/health` | GET | Comprehensive health check |
| `/monitoring/rate-limits` | GET | Rate limiting status |
| `/monitoring/audit` | GET | Audit trail |

---

**Total: 22 endpoints** providing comprehensive administrative functionality with enterprise-grade security, monitoring, and operational capabilities.

For the complete interactive API documentation, visit `/api/alpha/swagger` on your PieFed instance.