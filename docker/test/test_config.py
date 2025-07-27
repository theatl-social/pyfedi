"""
Test configuration for PyFedi
Used in Docker test environment
"""
import os

# Base configuration
TESTING = True
DEBUG = False
WTF_CSRF_ENABLED = False
FLASK_APP = 'pyfedi.py'

# Database
SQLALCHEMY_DATABASE_URI = os.environ.get(
    'DATABASE_URL',
    'postgresql://pyfedi:testpass@db:5432/pyfedi_test'
)
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Redis
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/0')

# Security settings for testing
SECRET_KEY = 'test-secret-key-not-for-production'
MEDIA_PROXY_SECRET = 'test-media-proxy-secret'

# JSON Parser limits
MAX_JSON_SIZE = 1_000_000  # 1MB
MAX_JSON_DEPTH = 50
MAX_JSON_KEYS = 1000
MAX_JSON_ARRAY_LENGTH = 10000

# Actor creation limits
ACTORS_PER_INSTANCE_HOUR = 10
ACTORS_PER_INSTANCE_DAY = 50
TOTAL_ACTORS_PER_HOUR = 100

# ActivityPub settings
REQUIRE_SIGNATURES = True
ALLOW_UNSIGNED_ACTIVITIES = False
ACTIVITYPUB_DOMAIN = 'test.instance'
SERVER_NAME = 'test.instance'

# URI validation
URI_ALLOWED_SCHEMES = {'http', 'https'}
URI_BLOCKED_PORTS = {22, 23, 25, 445, 3389, 6379, 11211}
MAX_URI_LENGTH = 2048
URI_BLOCKED_HOSTS = {'localhost', '127.0.0.1', '0.0.0.0'}
REQUIRE_HTTPS_ACTIVITYPUB = False  # Allow HTTP in tests

# Rate limiting
RATELIMIT_ENABLED = True
RATELIMIT_STORAGE_URL = REDIS_URL

# Media proxy
MAX_CONTENT_SIZE = 50 * 1024 * 1024  # 50MB
MEDIA_CACHE_DURATION = 3600

# Relay protection
MAX_ANNOUNCES_PER_OBJECT = 5
VOTE_RATE_LIMIT_PER_ACTOR = 100

# Celery (disabled for tests)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Logging
LOGGING_LEVEL = 'INFO'
LOG_TO_STDOUT = True