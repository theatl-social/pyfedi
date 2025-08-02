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
    
    yield app


@pytest.fixture(scope='session')
def _db(app):
    """Create database for testing"""
    with app.app_context():
        db.create_all()
        
        # Create Site(id=1) immediately after database creation
        from app.models import Site, Role, RolePermission
        from app.activitypub.signature import generate_rsa_keypair
        
        # Create roles first
        roles_data = [
            ('Anonymous user', 0, []),
            ('Authenticated user', 1, []),
            ('Staff', 2, [
                'approve registrations',
                'ban users',
                'administer all communities',
                'administer all users'
            ]),
            ('Admin', 3, [
                'approve registrations',
                'change user roles',
                'ban users',
                'manage users',
                'change instance settings',
                'administer all communities',
                'administer all users',
                'edit cms pages'
            ])
        ]
        
        for name, weight, permissions in roles_data:
            role = Role.query.filter_by(name=name).first()
            if not role:
                role = Role(name=name, weight=weight)
                for perm in permissions:
                    role.permissions.append(RolePermission(permission=perm))
                db.session.add(role)
        
        db.session.commit()
        
        site = Site.query.get(1)
        if not site:
            site = Site(
                id=1,
                name='Test Site',
                description='Test site for PyFedi',
                registration_mode='Open',
                enable_downvotes=True,
                enable_nsfw=False,
                enable_nsfl=False,
                community_creation_admin_only=False,
                reports_email_admins=True,
                application_question='',
                default_theme='',
                default_filter='',
                allow_or_block_list=0,
                log_activitypub_json=False,
                # Additional fields with defaults
                enable_gif_reply_rep_decrease=False,
                enable_chan_image_filter=False,
                enable_this_comment_filter=False,
                allow_local_image_posts=True,
                remote_image_cache_days=30,
                # Logo fields - empty strings as defaults
                logo='',
                logo_180='',
                logo_152='',
                logo_32='',
                logo_16='',
                # Other fields
                contact_email='',
                show_inoculation_block=True,
                private_instance=False
            )
            private_key, public_key = generate_rsa_keypair()
            site.private_key = private_key
            site.public_key = public_key
            db.session.add(site)
            db.session.commit()
        
        yield db
        db.session.remove()
        # Drop all tables with CASCADE to handle all dependencies
        with db.engine.begin() as conn:
            # Get all table names
            inspector = db.inspect(conn)
            tables = inspector.get_table_names()
            # Drop each table with CASCADE, quote table names to handle reserved words
            for table in tables:
                conn.execute(db.text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))


@pytest.fixture(scope='function')
def session(app, _db):
    """Create a clean database session for each test"""
    with app.app_context():
        # Start a transaction
        connection = _db.engine.connect()
        transaction = connection.begin()
        
        # Configure the session to use this connection
        _db.session.configure(bind=connection)
        
        # Begin a nested transaction (savepoint)
        nested = connection.begin_nested()
        
        # If a test fails, rollback to the savepoint
        @db.event.listens_for(_db.session, "after_transaction_end")
        def restart_savepoint(session, transaction):
            if transaction.nested and not transaction._parent.nested:
                # Ensure we're still connected
                if connection.closed:
                    return
                nested = connection.begin_nested()
        
        yield _db.session
        
        # Cleanup
        _db.session.close()
        if not connection.closed:
            transaction.rollback()
        connection.close()
        
        # Remove the event listener
        db.event.remove(_db.session, "after_transaction_end", restart_savepoint)


# Alias for backward compatibility - many tests use db_session
@pytest.fixture(scope='function')
def db_session(session):
    """Alias for session fixture for backward compatibility"""
    return session


@pytest.fixture
def client(app):
    """Create a test client"""
    return app.test_client()


@pytest.fixture
def test_site(session):
    """Create or get the test site and set g.site"""
    from flask import g
    from app.models import Site
    
    # Site should already exist from _db fixture
    site = Site.query.get(1)
    if not site:
        # Fallback creation if needed
        from app.activitypub.signature import generate_rsa_keypair
        site = Site(
            id=1,
            name='Test Site',
            description='Test site for PyFedi',
            registration_mode='Open',
            enable_downvotes=True,
            enable_nsfw=False,
            enable_nsfl=False,
            community_creation_admin_only=False,
            reports_email_admins=True,
            application_question='',
            default_theme='',
            default_filter='',
            allow_or_block_list=0,
            log_activitypub_json=False,
            enable_gif_reply_rep_decrease=False,
            enable_chan_image_filter=False,
            enable_this_comment_filter=False,
            allow_local_image_posts=True,
            remote_image_cache_days=30,
            logo='',
            contact_email='',
            show_inoculation_block=True,
            private_instance=False
        )
        private_key, public_key = generate_rsa_keypair()
        site.private_key = private_key
        site.public_key = public_key
        session.add(site)
        session.commit()
    
    # Set g.site for this test
    g.site = site
    return site


@pytest.fixture
def test_data(session, test_site):
    """Create basic test data that many tests expect"""
    from app.models import User, Instance, Community
    from app.activitypub.signature import generate_rsa_keypair
    
    # Create local instance (id=1)
    local_instance = Instance.query.get(1)
    if not local_instance:
        local_instance = Instance(
            id=1,
            domain='test.local',
            software='pyfedi',
            version='1.0.0'
        )
        session.add(local_instance)
    
    # Create test user with id=1 (many tests expect this)
    user1 = User.query.get(1)
    if not user1:
        user1 = User(
            id=1,
            user_name='testuser1',
            email='test1@example.com',
            ap_profile_id='https://test.local/u/testuser1',
            instance_id=1,
            verified=True
        )
        private_key, public_key = generate_rsa_keypair()
        user1.private_key = private_key
        user1.public_key = public_key
        user1.set_password('password123')
        session.add(user1)
    
    # Create a test community
    community = Community.query.filter_by(name='testcommunity').first()
    if not community:
        community = Community(
            name='testcommunity',
            title='Test Community',
            description='A test community',
            ap_profile_id='https://test.local/c/testcommunity',
            instance_id=1,
            user_id=1  # creator
        )
        private_key, public_key = generate_rsa_keypair()
        community.private_key = private_key
        community.public_key = public_key
        session.add(community)
    
    session.commit()
    
    return {
        'site': test_site,
        'instance': local_instance,
        'user1': user1,
        'community': community
    }


@pytest.fixture
def test_instance(session):
    """Create a test instance"""
    instance = Instance(
        domain='test.instance',
        software='pyfedi'
    )
    session.add(instance)
    session.commit()
    return instance


@pytest.fixture
def test_user(session, test_instance):
    """Create a test user"""
    user = User(
        user_name='testuser',
        email='test@example.com',
        ap_profile_id='https://test.instance/u/testuser',
        instance_id=test_instance.id,
        public_key='-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----',
        private_key='-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----',
        verified=True
    )
    session.add(user)
    session.commit()
    return user


@pytest.fixture
def admin_user(session, test_instance):
    """Create an admin user"""
    user = User(
        user_name='admin',
        email='admin@example.com',
        ap_profile_id='https://test.instance/u/admin',
        instance_id=test_instance.id,
        public_key='-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----',
        private_key='-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----',
        verified=True
    )
    # Note: Admin status is typically set through instance roles or config, not a field
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
        ap_outbox_url='https://test.instance/c/testcommunity/outbox'
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


# Set up g.site automatically for all tests
@pytest.fixture(autouse=True)
def setup_g_site(app, _db):
    """Automatically set g.site for all tests"""
    with app.app_context():
        from flask import g
        from app.models import Site
        
        # Get the site created in _db fixture
        site = Site.query.get(1)
        if site:
            g.site = site
        
        yield
        
        # Clean up g.site after test
        if hasattr(g, 'site'):
            delattr(g, 'site')


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