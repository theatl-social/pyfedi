"""
Global pytest configuration and fixtures
"""
import os
import sys
import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Add the test environment configuration to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../docker/test'))

# Import the test configuration
try:
    from test_env import TestConfig
except ImportError:
    # Fallback if running outside Docker
    from config import Config as TestConfig

# Import Flask app and database
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from app.models import User, Instance, Community, Post


@pytest.fixture(scope='session')
def app():
    """Create application for testing"""
    app = create_app(TestConfig)
    
    with app.app_context():
        yield app


@pytest.fixture(scope='session')
def _db(app):
    """Create database for testing"""
    db.create_all()
    yield db
    db.drop_all()


@pytest.fixture(scope='function')
def session(_db):
    """Create a database session for testing"""
    connection = _db.engine.connect()
    transaction = connection.begin()
    
    # Configure session to use the transaction
    _db.session.configure(bind=connection)
    
    yield _db.session
    
    # Rollback the transaction
    _db.session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(app):
    """Create a test client"""
    return app.test_client()


@pytest.fixture
def test_instance(session):
    """Create a test instance"""
    instance = Instance(
        domain='test.instance',
        software='pyfedi',
        created_at=datetime.utcnow()
    )
    session.add(instance)
    session.commit()
    return instance


@pytest.fixture
def test_user(session, test_instance):
    """Create a test user"""
    user = User(
        username='testuser',
        email='test@example.com',
        ap_profile_id='https://test.instance/u/testuser',
        instance_id=test_instance.id,
        public_key='-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----',
        private_key='-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----',
        created_at=datetime.utcnow()
    )
    session.add(user)
    session.commit()
    return user


@pytest.fixture
def admin_user(session, test_instance):
    """Create an admin user"""
    user = User(
        username='admin',
        email='admin@example.com',
        ap_profile_id='https://test.instance/u/admin',
        instance_id=test_instance.id,
        is_site_admin=True,
        public_key='-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----',
        private_key='-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----',
        created_at=datetime.utcnow()
    )
    session.add(user)
    session.commit()
    return user


@pytest.fixture
def test_community(session, test_instance):
    """Create a test community"""
    community = Community(
        name='testcommunity',
        title='Test Community',
        ap_profile_id='https://test.instance/c/testcommunity',
        ap_inbox_url='https://test.instance/c/testcommunity/inbox',
        ap_outbox_url='https://test.instance/c/testcommunity/outbox',
        created_at=datetime.utcnow()
    )
    session.add(community)
    session.commit()
    return community


@pytest.fixture
def auth_headers():
    """Generate authentication headers for testing"""
    return {
        'Authorization': 'Bearer test-token',
        'Content-Type': 'application/json'
    }


# Ensure proper cleanup after each test
@pytest.fixture(autouse=True)
def cleanup(session):
    """Clean up after each test"""
    yield
    # The session fixture will handle rollback


# Add async fixtures for Redis and other async components
@pytest.fixture(scope='session')
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def async_session():
    """Create an async database session for tests."""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    
    async with engine.begin() as conn:
        # Create tables if needed
        pass
    
    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        yield session
    
    await engine.dispose()


@pytest_asyncio.fixture
async def redis_client():
    """Create a mock Redis client for testing."""
    mock_redis = AsyncMock(spec=redis.Redis)
    
    # Mock common Redis operations
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)
    mock_redis.exists = AsyncMock(return_value=0)
    mock_redis.expire = AsyncMock(return_value=True)
    mock_redis.ttl = AsyncMock(return_value=-1)
    
    # Mock stream operations
    mock_redis.xadd = AsyncMock(return_value=b'1234567890-0')
    mock_redis.xread = AsyncMock(return_value=[])
    mock_redis.xreadgroup = AsyncMock(return_value=[])
    mock_redis.xgroup_create = AsyncMock(return_value=True)
    mock_redis.xack = AsyncMock(return_value=1)
    mock_redis.xdel = AsyncMock(return_value=1)
    
    # Mock sorted set operations
    mock_redis.zadd = AsyncMock(return_value=1)
    mock_redis.zcard = AsyncMock(return_value=0)
    mock_redis.zrange = AsyncMock(return_value=[])
    mock_redis.zremrangebyscore = AsyncMock(return_value=0)
    
    # Mock hash operations
    mock_redis.hset = AsyncMock(return_value=1)
    mock_redis.hget = AsyncMock(return_value=None)
    mock_redis.hgetall = AsyncMock(return_value={})
    mock_redis.hdel = AsyncMock(return_value=1)
    
    # Mock pipeline
    mock_pipeline = AsyncMock()
    mock_pipeline.execute = AsyncMock(return_value=[])
    mock_redis.pipeline = Mock(return_value=mock_pipeline)
    
    # Mock scan
    mock_redis.scan = AsyncMock(return_value=(0, []))
    
    yield mock_redis


@pytest.fixture
def mock_httpx():
    """Mock httpx for external requests."""
    with patch('httpx.AsyncClient') as mock:
        client = AsyncMock()
        mock.return_value = client
        
        # Mock response
        response = AsyncMock()
        response.status_code = 200
        response.json = AsyncMock(return_value={})
        response.text = 'OK'
        response.headers = {}
        
        client.get = AsyncMock(return_value=response)
        client.post = AsyncMock(return_value=response)
        client.request = AsyncMock(return_value=response)
        
        yield client


# ActivityPub test data
@pytest.fixture
def ap_actor_data():
    """Sample ActivityPub actor data."""
    return {
        '@context': 'https://www.w3.org/ns/activitystreams',
        'id': 'https://test.instance/u/testuser',
        'type': 'Person',
        'preferredUsername': 'testuser',
        'inbox': 'https://test.instance/u/testuser/inbox',
        'outbox': 'https://test.instance/u/testuser/outbox',
        'publicKey': {
            'id': 'https://test.instance/u/testuser#main-key',
            'owner': 'https://test.instance/u/testuser',
            'publicKeyPem': '-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----'
        }
    }


@pytest.fixture
def ap_create_activity():
    """Sample ActivityPub Create activity."""
    return {
        '@context': 'https://www.w3.org/ns/activitystreams',
        'id': 'https://test.instance/activities/1',
        'type': 'Create',
        'actor': 'https://test.instance/u/testuser',
        'object': {
            'id': 'https://test.instance/posts/1',
            'type': 'Note',
            'content': 'Test post content',
            'attributedTo': 'https://test.instance/u/testuser',
            'to': ['https://www.w3.org/ns/activitystreams#Public'],
            'published': '2024-01-01T00:00:00Z'
        },
        'published': '2024-01-01T00:00:00Z'
    }