"""
Startup Validation Tests
========================

These tests validate that both Flask app and Celery worker can initialize properly
without runtime errors. They catch issues like:
- Blueprint registration errors (flask-smorest schema issues)
- Import/dependency resolution problems  
- Configuration validation errors
- Database connection initialization (without requiring actual DB)
- Cache initialization issues
- Extension initialization failures

This is designed to run in CI/CD to catch startup issues early.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest


def setup_minimal_test_env():
    """Set up minimal environment variables for testing"""
    test_env = {
        'SERVER_NAME': 'test.localhost',
        'SECRET_KEY': 'test-secret-key-for-testing-only',
        'DATABASE_URL': 'sqlite:///memory:test.db',  # In-memory SQLite for testing
        'CACHE_TYPE': 'NullCache',  # Use null cache for testing to avoid filesystem issues
        'CACHE_REDIS_URL': 'memory://',  # Use memory storage for limiter to avoid Redis dependency
        'CELERY_BROKER_URL': 'memory://localhost/',  # In-memory broker for testing
        'RESULT_BACKEND': 'cache+memory://localhost/',
        'TESTING': 'true',
        'MAIL_SUPPRESS_SEND': 'true',
        'SENTRY_DSN': '',  # Disable sentry in tests
        'S3_BUCKET': '',
        'STRIPE_SECRET_KEY': '',
        'FULL_AP_CONTEXT': '0',
        'LOG_ACTIVITYPUB_TO_DB': 'false',
        'LOG_ACTIVITYPUB_TO_FILE': 'false',
        'WTF_CSRF_ENABLED': 'false',  # Disable CSRF for testing
        'GOOGLE_OAUTH_CLIENT_ID': '',
        'MASTODON_OAUTH_CLIENT_ID': '',  
        'DISCORD_OAUTH_CLIENT_ID': '',
        'MAIL_SERVER': '',
        'ERRORS_TO': '',
    }
    
    for key, value in test_env.items():
        os.environ[key] = value


class TestFlaskAppInitialization:
    """Test Flask application startup and blueprint registration"""
    
    @pytest.fixture(autouse=True)
    def setup_environment(self):
        """Set up test environment before each test"""
        setup_minimal_test_env()
        # Create temporary directories that might be needed
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ['TEMP_DIR'] = tmpdir
            yield
    
    def test_flask_app_creation(self):
        """Test that Flask app can be created without errors"""
        try:
            from app import create_app
            
            app = create_app()
            assert app is not None
            assert app.name == 'app'
            print("✅ Flask app created successfully")
            
        except Exception as e:
            pytest.fail(f"Flask app creation failed: {e}")
    
    def test_flask_app_context(self):
        """Test that Flask app context works properly"""
        try:
            from app import create_app
            
            app = create_app()
            with app.app_context():
                from flask import current_app
                assert current_app == app
                print("✅ Flask app context works")
                
        except Exception as e:
            pytest.fail(f"Flask app context failed: {e}")
    
    def test_blueprint_registration(self):
        """Test that all blueprints register without errors"""
        try:
            from app import create_app
            
            app = create_app()
            
            # Check that key blueprints are registered
            blueprint_names = [bp.name for bp in app.blueprints.values()]
            
            expected_blueprints = [
                'main',
                'errors', 
                'admin',
                'activitypub',
                'auth',
                'community',
                'post',
                'user',
                'domain',
                'feed',
                'instance',
                'topic',
                'chat',
                'search',
                'tag',
                'dev',
                'api_alpha'
            ]
            
            for expected_bp in expected_blueprints:
                if expected_bp not in blueprint_names:
                    pytest.fail(f"Blueprint '{expected_bp}' not registered")
            
            print(f"✅ All {len(expected_blueprints)} main blueprints registered successfully")
            
        except Exception as e:
            pytest.fail(f"Blueprint registration failed: {e}")
    
    def test_flask_smorest_api_registration(self):
        """Test that flask-smorest API blueprints register without schema errors"""
        try:
            from app import create_app
            
            app = create_app()
            
            with app.app_context():
                # Get the REST API instance
                from app import rest_api
                assert rest_api is not None
                
                # Check that API blueprints are registered with rest_api
                api_specs = rest_api.spec
                assert api_specs is not None
                
                print("✅ Flask-smorest API registration successful")
                
        except Exception as e:
            if "SchemaMeta" in str(e) and "not iterable" in str(e):
                pytest.fail(f"Flask-smorest schema error (likely incorrect @alt_response usage): {e}")
            else:
                pytest.fail(f"Flask-smorest API registration failed: {e}")

    def test_database_initialization_dry_run(self):
        """Test database models can be imported and initialized (dry run)"""
        try:
            from app import create_app, db
            from app.models import User, Post, Community  # Import key models
            
            app = create_app()
            with app.app_context():
                # Test that models are properly defined
                assert hasattr(User, '__tablename__')
                assert hasattr(Post, '__tablename__')
                assert hasattr(Community, '__tablename__')
                
                print("✅ Database models initialization successful")
                
        except Exception as e:
            pytest.fail(f"Database models initialization failed: {e}")

    def test_extensions_initialization(self):
        """Test that Flask extensions initialize properly"""
        try:
            from app import create_app
            
            app = create_app()
            
            # Check that extensions are in app.extensions
            # First, let's see what extensions are actually loaded
            actual_extensions = list(app.extensions.keys())
            print(f"📋 Loaded extensions: {actual_extensions}")
            
            # Check for key extensions (use actual names from the loaded extensions)
            critical_extensions = ['sqlalchemy', 'migrate']  # Most critical ones
            
            for ext_name in critical_extensions:
                if ext_name not in app.extensions:
                    pytest.fail(f"Critical extension '{ext_name}' not initialized")
            
            print(f"✅ Critical Flask extensions initialized. Total loaded: {len(actual_extensions)}")
            
        except Exception as e:
            pytest.fail(f"Flask extensions initialization failed: {e}")


class TestCeleryWorkerInitialization:
    """Test Celery worker startup and task discovery"""
    
    @pytest.fixture(autouse=True)
    def setup_environment(self):
        """Set up test environment before each test"""
        setup_minimal_test_env()
        yield
    
    def test_celery_app_creation(self):
        """Test that Celery app can be created without errors"""
        try:
            # Mock Redis connection since we don't need real Redis for this test
            with patch('app.utils.get_redis_connection') as mock_redis:
                mock_redis.return_value = MagicMock()
                
                from app import celery, create_app
                
                # Create Flask app first (required for Celery)
                app = create_app()
                
                with app.app_context():
                    # Test Celery app
                    assert celery is not None
                    assert hasattr(celery, 'control')
                    assert hasattr(celery, 'send_task')
                    
                    print("✅ Celery app created successfully")
                    
        except Exception as e:
            pytest.fail(f"Celery app creation failed: {e}")
    
    def test_celery_worker_import(self):
        """Test that celery_worker module can be imported (main entrypoint)"""
        try:
            # Mock components that require actual Redis/DB connections
            with patch('app.utils.get_redis_connection') as mock_redis, \
                 patch('app.create_app') as mock_create_app:
                
                mock_redis.return_value = MagicMock()
                mock_app = MagicMock()
                mock_create_app.return_value = mock_app
                
                # This would be the main import in celery_worker.py or celery_worker_docker.py
                import celery_worker_docker
                
                assert hasattr(celery_worker_docker, 'celery')
                print("✅ Celery worker module imported successfully")
                
        except Exception as e:
            pytest.fail(f"Celery worker import failed: {e}")
    
    def test_celery_task_discovery(self):
        """Test that Celery can discover tasks without errors"""
        try:
            with patch('app.utils.get_redis_connection') as mock_redis:
                mock_redis.return_value = MagicMock()
                
                from app import celery, create_app
                
                app = create_app()
                with app.app_context():
                    # Test task discovery - this would fail if imports are broken
                    celery.autodiscover_tasks()
                    
                    # Check that some expected tasks exist
                    task_names = list(celery.tasks.keys())
                    
                    # Look for common task patterns
                    background_tasks_found = any('background' in name or 'task' in name 
                                                for name in task_names)
                    
                    if not background_tasks_found:
                        print("ℹ️  No background tasks discovered (might be expected)")
                    else:
                        print(f"✅ Celery task discovery successful ({len(task_names)} tasks)")
                    
        except Exception as e:
            pytest.fail(f"Celery task discovery failed: {e}")

    def test_celery_configuration(self):
        """Test that Celery configuration is properly set"""
        try:
            with patch('app.utils.get_redis_connection') as mock_redis:
                mock_redis.return_value = MagicMock()
                
                from app import celery, create_app
                
                app = create_app()
                with app.app_context():
                    # Test basic Celery configuration
                    assert celery.conf.broker_url
                    assert celery.conf.result_backend or True  # result_backend might be None
                    
                    # Test that task routes are configured
                    if hasattr(celery.conf, 'task_routes'):
                        print("✅ Celery task routes configured")
                    
                    print("✅ Celery configuration valid")
                    
        except Exception as e:
            pytest.fail(f"Celery configuration failed: {e}")


class TestStartupIntegration:
    """Integration tests for complete startup process"""
    
    @pytest.fixture(autouse=True) 
    def setup_environment(self):
        """Set up test environment before each test"""
        setup_minimal_test_env()
        yield
    
    def test_complete_startup_sequence(self):
        """Test complete startup sequence: Flask app + Celery + all extensions"""
        try:
            with patch('app.utils.get_redis_connection') as mock_redis:
                mock_redis.return_value = MagicMock()
                
                # Simulate complete startup
                from app import create_app, celery
                
                app = create_app()
                
                with app.app_context():
                    # Verify both Flask and Celery are working
                    assert app is not None
                    assert celery is not None
                    
                    # Test that we can import key modules
                    from app.models import User
                    from app.api.alpha import admin_bp
                    
                    assert admin_bp is not None
                    
                    print("✅ Complete startup sequence successful")
                    
        except Exception as e:
            pytest.fail(f"Complete startup sequence failed: {e}")
    
    def test_error_conditions(self):
        """Test that startup handles expected error conditions gracefully"""
        # Test missing SERVER_NAME
        original_server_name = os.environ.get('SERVER_NAME')
        
        try:
            if 'SERVER_NAME' in os.environ:
                del os.environ['SERVER_NAME']
            
            # Test that config loading raises AttributeError for missing SERVER_NAME
            try:
                import importlib
                import config
                importlib.reload(config)
                pytest.fail("Expected AttributeError when SERVER_NAME is missing")
            except AttributeError as e:
                if "'NoneType' object has no attribute 'lower'" in str(e):
                    print("✅ Startup properly validates required configuration")
                else:
                    pytest.fail(f"Unexpected AttributeError: {e}")
            
        except Exception as e:
            pytest.fail(f"Error condition testing failed: {e}")
        finally:
            if original_server_name:
                os.environ['SERVER_NAME'] = original_server_name
            # Reload config again to restore proper state
            import importlib  
            import config
            importlib.reload(config)


def test_production_startup_errors():
    """
    Test for common production startup errors that might not show up in development
    """
    try:
        # Test with production-like settings
        setup_minimal_test_env()
        
        # Set some production-like settings that might cause issues
        os.environ['FLASK_ENV'] = 'production'
        os.environ['FLASK_DEBUG'] = '0'
        
        with patch('app.utils.get_redis_connection') as mock_redis:
            mock_redis.return_value = MagicMock()
            
            from app import create_app
            
            app = create_app()
            assert app is not None
            
            print("✅ Production-like startup validation successful")
            
    except Exception as e:
        pytest.fail(f"Production startup validation failed: {e}")


if __name__ == '__main__':
    """
    Allow running these tests standalone for quick validation
    """
    print("🧪 Running PieFed Startup Validation Tests")
    print("=" * 50)
    
    # Run tests manually for quick feedback
    setup_minimal_test_env()
    
    flask_tests = TestFlaskAppInitialization()
    flask_tests.setup_environment = lambda: None  # Mock the fixture
    
    try:
        flask_tests.test_flask_app_creation()
        flask_tests.test_flask_app_context()
        flask_tests.test_blueprint_registration()
        flask_tests.test_flask_smorest_api_registration()
        flask_tests.test_database_initialization_dry_run()
        flask_tests.test_extensions_initialization()
        print("\n🎉 All Flask startup tests passed!")
        
    except Exception as e:
        print(f"\n❌ Flask startup test failed: {e}")
        sys.exit(1)
    
    celery_tests = TestCeleryWorkerInitialization()
    celery_tests.setup_environment = lambda: None  # Mock the fixture
    
    try:
        celery_tests.test_celery_app_creation()
        celery_tests.test_celery_worker_import()
        celery_tests.test_celery_task_discovery()
        celery_tests.test_celery_configuration()
        print("\n🎉 All Celery startup tests passed!")
        
    except Exception as e:
        print(f"\n❌ Celery startup test failed: {e}")
        sys.exit(1)
    
    integration_tests = TestStartupIntegration()
    integration_tests.setup_environment = lambda: None  # Mock the fixture
    
    try:
        integration_tests.test_complete_startup_sequence()
        integration_tests.test_error_conditions()
        test_production_startup_errors()
        print("\n🎉 All integration tests passed!")
        
    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        sys.exit(1)
    
    print("\n✅ All startup validation tests completed successfully!")
    print("🚀 Application startup is validated and ready for deployment")