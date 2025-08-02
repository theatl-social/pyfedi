"""
Test configuration for security tests
Provides common fixtures and test setup
"""
import pytest
from unittest.mock import Mock, patch
import tempfile
import os


# Simple mock app fixture for security tests that don't need database
@pytest.fixture
def mock_app():
    """Create mock Flask application for security unit tests"""
    mock_app = Mock()
    mock_app.config = {
        'SECRET_KEY': 'test-secret-key',
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        
        # Security settings
        'MAX_JSON_SIZE': 1000000,
        'MAX_JSON_DEPTH': 50,
        'MAX_JSON_KEYS': 1000,
        'MAX_ARRAY_LENGTH': 10000,
        
        # ActivityPub settings
        'REQUIRE_SIGNATURES': True,
        'ALLOW_UNSIGNED_ACTIVITIES': False,
        'ACTIVITYPUB_DOMAIN': 'test.instance',
        
        # URI validation
        'URI_ALLOWED_SCHEMES': {'http', 'https'},
        'URI_BLOCKED_PORTS': {22, 23, 25, 445, 3389, 6379, 11211},
        'MAX_URI_LENGTH': 2048,
        'URI_BLOCKED_HOSTS': {'localhost', '127.0.0.1', '0.0.0.0'},
        
        # Rate limiting
        'RATELIMIT_ENABLED': True,
        'RATELIMIT_STORAGE_URL': 'memory://',
        
        # Celery
        'CELERY_BROKER_URL': 'memory://',
        'CELERY_RESULT_BACKEND': 'cache+memory://',
    }
    
    # Mock common Flask attributes
    mock_app.logger = Mock()
    mock_app.test_client = Mock()
    mock_app.test_request_context = Mock()
    
    return mock_app


@pytest.fixture
def db_session():
    """Create test database session"""
    mock_session = Mock()
    mock_session.add = Mock()
    mock_session.commit = Mock()
    mock_session.rollback = Mock()
    mock_session.query = Mock()
    mock_session.execute = Mock()
    
    return mock_session


@pytest.fixture
def redis_client():
    """Create mock Redis client"""
    mock_redis = Mock()
    mock_redis.get = Mock(return_value=None)
    mock_redis.set = Mock(return_value=True)
    mock_redis.incr = Mock(return_value=1)
    mock_redis.expire = Mock(return_value=True)
    mock_redis.exists = Mock(return_value=False)
    mock_redis.delete = Mock(return_value=1)
    mock_redis.lpush = Mock(return_value=1)
    mock_redis.lrange = Mock(return_value=[])
    
    return mock_redis


@pytest.fixture
def celery_app():
    """Create mock Celery app"""
    mock_celery = Mock()
    mock_celery.task = Mock()
    mock_celery.send_task = Mock()
    
    return mock_celery


@pytest.fixture
def test_user():
    """Create test user fixture"""
    user = Mock()
    user.id = 1
    user.username = 'testuser'
    user.email = 'test@example.com'
    user.ap_profile_id = 'https://test.instance/users/testuser'
    user.public_key = '''-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0Z3VS5JJcds3xfn/yP3Z
-----END PUBLIC KEY-----'''
    user.private_key = '''-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDRndVLkkl2zfF+
-----END PRIVATE KEY-----'''
    user.instance = Mock()
    user.instance.domain = 'test.instance'
    
    return user


@pytest.fixture
def test_post():
    """Create test post fixture"""
    post = Mock()
    post.id = 123
    post.title = "Test Post"
    post.body = "This is a test post"
    post.ap_id = "https://test.instance/posts/123"
    post.author_id = 1
    post.community_id = 1
    post.created_at = Mock()
    post.updated_at = Mock()
    
    return post


@pytest.fixture
def test_community():
    """Create test community fixture"""
    community = Mock()
    community.id = 1
    community.name = "test"
    community.title = "Test Community"
    community.ap_profile_id = "https://test.instance/c/test"
    community.ap_inbox_url = "https://test.instance/c/test/inbox"
    community.ap_outbox_url = "https://test.instance/c/test/outbox"
    
    return community


@pytest.fixture
def temp_file():
    """Create temporary file for testing"""
    fd, path = tempfile.mkstemp(suffix='.py')
    os.close(fd)
    
    yield path
    
    # Cleanup
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def mock_requests():
    """Mock requests library"""
    with patch('requests.get') as mock_get:
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {}
            mock_response.text = '{}'
            
            mock_get.return_value = mock_response
            mock_post.return_value = mock_response
            
            yield {'get': mock_get, 'post': mock_post}


@pytest.fixture
def security_headers():
    """Common security headers for testing"""
    return {
        'User-Agent': 'PeachPie-Test/1.0',
        'Accept': 'application/activity+json',
        'Content-Type': 'application/activity+json',
        'Host': 'test.instance',
        'Date': 'Mon, 01 Jan 2024 00:00:00 GMT',
        'Digest': 'SHA-256=...',
        'Signature': 'keyId="https://test.instance/users/alice#main-key",algorithm="rsa-sha256",headers="(request-target) host date digest",signature="..."'
    }


@pytest.fixture
def sample_activities():
    """Sample ActivityPub activities for testing"""
    return {
        'like': {
            '@context': 'https://www.w3.org/ns/activitystreams',
            'type': 'Like',
            'id': 'https://example.com/activities/like-1',
            'actor': 'https://example.com/users/alice',
            'object': 'https://test.instance/posts/123',
            'published': '2024-01-01T00:00:00Z'
        },
        'dislike': {
            '@context': 'https://www.w3.org/ns/activitystreams',
            'type': 'Dislike',
            'id': 'https://example.com/activities/dislike-1',
            'actor': 'https://example.com/users/alice',
            'object': 'https://test.instance/posts/123',
            'published': '2024-01-01T00:00:00Z'
        },
        'create': {
            '@context': 'https://www.w3.org/ns/activitystreams',
            'type': 'Create',
            'id': 'https://example.com/activities/create-1',
            'actor': 'https://example.com/users/alice',
            'object': {
                'type': 'Note',
                'id': 'https://example.com/notes/1',
                'content': 'Hello world!',
                'attributedTo': 'https://example.com/users/alice'
            }
        },
        'undo_like': {
            '@context': 'https://www.w3.org/ns/activitystreams',
            'type': 'Undo',
            'id': 'https://example.com/activities/undo-1',
            'actor': 'https://example.com/users/alice',
            'object': {
                'type': 'Like',
                'id': 'https://example.com/activities/like-1',
                'actor': 'https://example.com/users/alice',
                'object': 'https://test.instance/posts/123'
            }
        }
    }


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "security: mark test as security-related"
    )
    config.addinivalue_line(
        "markers", "activitypub: mark test as ActivityPub-related"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow-running"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )