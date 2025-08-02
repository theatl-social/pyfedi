"""Test configuration for local testing"""
import os
import tempfile
from config import Config

class TestConfig(Config):
    TESTING = True
    SECRET_KEY = 'test-secret-key'
    
    # Use SQLite for testing
    SQLALCHEMY_DATABASE_URI = 'sqlite:///test.db'
    
    # Disable cache or use temp directory
    CACHE_TYPE = 'FileSystemCache'
    CACHE_DIR = os.path.join(tempfile.gettempdir(), 'pyfedi_cache')
    
    # Disable Redis for testing
    REDIS_URL = None
    CACHE_REDIS_URL = None
    
    # Server name
    SERVER_NAME = 'test.local'
    
    # Disable CSRF for testing
    WTF_CSRF_ENABLED = False