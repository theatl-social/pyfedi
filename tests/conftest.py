"""
Global pytest configuration and fixtures
"""
import os
import sys
import pytest
from datetime import datetime

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