"""
Test environment configuration
This file sets up the proper configuration class for testing
"""
import os

class TestConfig:
    """Test configuration for PyFedi"""
    # Base settings
    TESTING = True
    DEBUG = False
    WTF_CSRF_ENABLED = False
    WTF_CSRF_TIME_LIMIT = None
    FLASK_DEBUG = False
    
    # Basic required settings
    SERVER_NAME = os.environ.get('SERVER_NAME', 'test.local')
    SECRET_KEY = os.environ.get('SECRET_KEY', 'test-secret-key-not-for-production')
    SOFTWARE_NAME = 'PeachPie'
    VERSION = '0.1.0-test'
    SOFTWARE_REPO = 'https://github.com/pyfedi/pyfedi'
    
    # Database settings
    DB_POOL_SIZE = 5
    DB_MAX_OVERFLOW = 10
    
    # Override database URL for tests
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql://pyfedi:pyfedi@localhost:5432/pyfedi_test'
    )
    
    # Redis configuration
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    CACHE_REDIS_URL = os.environ.get('REDIS_URL', 'redis://test-redis:6379/1')
    CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://test-redis:6379/0')
    RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://test-redis:6379/0')
    
    # Override server name for tests
    SERVER_NAME = os.environ.get('SERVER_NAME', 'test.instance')
    
    # Security settings for testing
    SECRET_KEY = os.environ.get('SECRET_KEY', 'test-secret-key-not-for-production')
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
    
    # URI validation
    URI_ALLOWED_SCHEMES = {'http', 'https'}
    URI_BLOCKED_PORTS = {22, 23, 25, 445, 3389, 6379, 11211}
    MAX_URI_LENGTH = 2048
    URI_BLOCKED_HOSTS = {'localhost', '127.0.0.1', '0.0.0.0'}
    REQUIRE_HTTPS_ACTIVITYPUB = False  # Allow HTTP in tests
    
    # Rate limiting
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/1')
    
    # Media proxy
    MAX_CONTENT_SIZE = 50 * 1024 * 1024  # 50MB
    MEDIA_CACHE_DURATION = 3600
    
    # Relay protection
    MAX_ANNOUNCES_PER_OBJECT = 5
    VOTE_RATE_LIMIT_PER_ACTOR = 100
    
    # Celery (run synchronously for tests)
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
    
    # Logging
    LOGGING_LEVEL = 'INFO'
    LOG_TO_STDOUT = True
    
    # Required config attributes
    LANGUAGES = ['en']
    BOOTSTRAP_SERVE_LOCAL = True
    FULL_AP_CONTEXT = False
    CACHE_TYPE = 'RedisCache'
    CACHE_DIR = '/tmp/piefed'
    CACHE_DEFAULT_TIMEOUT = 300
    CACHE_THRESHOLD = 1000
    CACHE_KEY_PREFIX = 'pyfedi_test'
    HTTP_PROTOCOL = 'http'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    
    # Mail settings (disabled for tests)
    MAIL_SERVER = None
    MAIL_PORT = 25
    MAIL_USE_TLS = False
    MAIL_USERNAME = None
    MAIL_PASSWORD = None
    MAIL_FROM = 'noreply@test.local'
    ERRORS_TO = ''
    BOUNCE_ADDRESS = ''
    BOUNCE_HOST = ''
    BOUNCE_USERNAME = ''
    BOUNCE_PASSWORD = ''
    
    # AWS/S3 settings (disabled for tests)
    AWS_REGION = None
    S3_BUCKET = None
    S3_ENDPOINT = None
    S3_PUBLIC_URL = None
    S3_ACCESS_KEY = None
    S3_ACCESS_SECRET = None
    S3_REGION = None
    
    # Other settings
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    ENABLE_ALPHA_API = 'true'
    CORS_ALLOW_ORIGIN = '*'
    NOTIF_SERVER = None
    FLAG_THROWAWAY_EMAILS = 0
    IMAGE_HASHING_ENDPOINT = None
    PAGE_LENGTH = 20
    KEEP_LOCAL_VOTE_DATA_TIME = 6
    KEEP_REMOTE_VOTE_DATA_TIME = 3
    FEP_AWESOME = False
    COUNTRY_SOURCE_HEADER = None
    CLOUDFLARE_API_TOKEN = None
    CLOUDFLARE_ZONE_ID = None
    IPINFO_TOKEN = None
    STRIPE_SECRET_KEY = None
    STRIPE_PUBLISHABLE_KEY = None
    STRIPE_MONTHLY_SMALL = None
    STRIPE_MONTHLY_BIG = None
    STRIPE_MONTHLY_SMALL_TEXT = None
    STRIPE_MONTHLY_BIG_TEXT = None
    WEBHOOK_SIGNING_SECRET = None
    SERVE_API_DOCS = False
    
    # Disable email during tests
    MAIL_SERVER = None
    
    # Disable some features for tests
    SENTRY_DSN = None
    IPINFO_TOKEN = None
    GOOGLE_OAUTH_CLIENT_ID = None
    MASTODON_OAUTH_CLIENT_ID = None
    DISCORD_OAUTH_CLIENT_ID = None