"""
Shared pytest fixtures for all test files
"""
import pytest
import os


class TestConfig:
    """Standard test configuration"""
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_ENGINE_OPTIONS = {}  # SQLite doesn't support pool settings
    MAIL_SUPPRESS_SEND = True
    SERVER_NAME = 'test.localhost'
    SECRET_KEY = 'test-secret-key'
    PRIVATE_REGISTRATION_ENABLED = 'true'
    PRIVATE_REGISTRATION_SECRET = 'test-secret-123'
    CACHE_TYPE = 'NullCache'
    CACHE_REDIS_URL = 'memory://'
    CELERY_ALWAYS_EAGER = True
    SENTRY_DSN = ''
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    RATELIMIT_ENABLED = False
    SERVE_API_DOCS = False
    GOOGLE_OAUTH_CLIENT_ID = ''
    GOOGLE_OAUTH_CLIENT_SECRET = ''
    MASTODON_OAUTH_CLIENT_ID = ''
    MASTODON_OAUTH_CLIENT_SECRET = ''
    DISCORD_OAUTH_CLIENT_ID = ''
    DISCORD_OAUTH_CLIENT_SECRET = ''
    MAIL_SERVER = ''


@pytest.fixture
def test_app():
    """Create and configure a test application instance"""
    from app import create_app, db

    app = create_app(TestConfig)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def app(test_app):
    """Alias for test_app for compatibility"""
    return test_app


@pytest.fixture
def client(test_app):
    """Create test client"""
    return test_app.test_client()
