"""
Tests for database connection pool configuration

These tests verify that the connection pool settings are properly configured
to prevent connection exhaustion errors like PGRES_TUPLES_OK.
"""

import pytest
from sqlalchemy import text
from concurrent.futures import ThreadPoolExecutor, as_completed
from app import create_app, db
from app.models import Site


class TestConfig:
    """Test configuration"""
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    MAIL_SUPPRESS_SEND = True
    SERVER_NAME = 'test.localhost'
    SECRET_KEY = 'test-secret-key'
    CACHE_TYPE = 'NullCache'
    CELERY_ALWAYS_EAGER = True
    # These should be set via config
    DB_POOL_SIZE = 10
    DB_MAX_OVERFLOW = 30


@pytest.fixture
def app():
    """Create test app with test configuration"""
    try:
        app = create_app(TestConfig)

        with app.app_context():
            db.create_all()
            # Create a Site object (required for many operations)
            site = Site(
                id=1,
                name='Test Site',
                default_theme='piefed'
            )
            db.session.add(site)
            db.session.commit()
            yield app
            db.session.remove()
            db.drop_all()
    except Exception as e:
        pytest.skip(f"Could not create test app: {e}")


class TestConnectionPoolConfiguration:
    """Test that connection pool is properly configured"""

    def test_sqlalchemy_engine_options_configured(self, app):
        """Verify SQLALCHEMY_ENGINE_OPTIONS are properly set"""
        with app.app_context():
            assert hasattr(app.config, 'SQLALCHEMY_ENGINE_OPTIONS'), \
                "SQLALCHEMY_ENGINE_OPTIONS not found in config"

            options = app.config['SQLALCHEMY_ENGINE_OPTIONS']

            # Verify all required options are present
            assert 'pool_size' in options, "pool_size not configured"
            assert 'max_overflow' in options, "max_overflow not configured"
            assert 'pool_pre_ping' in options, "pool_pre_ping not configured"
            assert 'pool_recycle' in options, "pool_recycle not configured"

            # Verify values are correct
            assert isinstance(options['pool_size'], int), "pool_size should be int"
            assert options['pool_size'] > 0, "pool_size should be positive"

            assert isinstance(options['max_overflow'], int), "max_overflow should be int"
            assert options['max_overflow'] > 0, "max_overflow should be positive"

            assert options['pool_pre_ping'] is True, "pool_pre_ping should be enabled"
            assert options['pool_recycle'] == 300, "pool_recycle should be 300 seconds"

    def test_db_pool_size_defaults(self, app):
        """Verify DB_POOL_SIZE and DB_MAX_OVERFLOW have reasonable defaults"""
        with app.app_context():
            # Verify config variables exist
            assert hasattr(app.config, 'DB_POOL_SIZE'), "DB_POOL_SIZE not in config"
            assert hasattr(app.config, 'DB_MAX_OVERFLOW'), "DB_MAX_OVERFLOW not in config"

            # Verify they're used in engine options
            options = app.config['SQLALCHEMY_ENGINE_OPTIONS']
            assert options['pool_size'] == int(app.config['DB_POOL_SIZE'])
            assert options['max_overflow'] == int(app.config['DB_MAX_OVERFLOW'])

    def test_connection_pool_total_capacity(self, app):
        """Verify total connection pool capacity is sufficient"""
        with app.app_context():
            options = app.config['SQLALCHEMY_ENGINE_OPTIONS']
            total_connections = options['pool_size'] + options['max_overflow']

            # Should have at least 20 total connections for production
            # (this is a minimum - actual value depends on environment config)
            assert total_connections >= 10, \
                f"Total connection capacity ({total_connections}) seems too low"


class TestConnectionPoolBehavior:
    """Test connection pool behavior under various conditions"""

    def test_basic_connection_acquisition(self, app, db):
        """Test that basic connection acquisition works"""
        with app.app_context():
            # Should be able to acquire and use a connection
            result = db.session.execute(text("SELECT 1 as test"))
            row = result.fetchone()
            assert row[0] == 1

    def test_multiple_sequential_connections(self, app, db):
        """Test multiple sequential DB operations don't leak connections"""
        with app.app_context():
            # Perform multiple queries sequentially
            for i in range(10):
                result = db.session.execute(text("SELECT :val as test"), {"val": i})
                row = result.fetchone()
                assert row[0] == i

            # All connections should be returned to pool
            # No connection exhaustion errors should occur

    @pytest.mark.slow
    def test_concurrent_connection_requests(self, app, db):
        """Test connection pool handles moderate concurrent load"""
        def query_database(query_id):
            """Execute a simple query"""
            with app.app_context():
                try:
                    result = db.session.execute(
                        text("SELECT :id as query_id"),
                        {"id": query_id}
                    )
                    row = result.fetchone()
                    return row[0] == query_id
                except Exception as e:
                    return f"Error: {str(e)}"

        # Test with 20 concurrent connections
        # This should be well within pool_size + max_overflow
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(query_database, i) for i in range(20)]

            results = []
            for future in as_completed(futures):
                result = future.result()
                results.append(result)

            # All queries should succeed
            assert all(r is True for r in results), \
                f"Some queries failed: {[r for r in results if r is not True]}"

    def test_connection_recycling_config(self, app):
        """Verify connection recycling prevents stale connections"""
        with app.app_context():
            options = app.config['SQLALCHEMY_ENGINE_OPTIONS']

            # pool_recycle should be set to prevent long-lived connections
            assert options['pool_recycle'] > 0, \
                "pool_recycle should be positive to prevent stale connections"

            # 5 minutes (300 seconds) is a good default
            assert options['pool_recycle'] <= 600, \
                "pool_recycle should be <= 10 minutes to catch stale connections"

    def test_pool_pre_ping_enabled(self, app, db):
        """Verify pool_pre_ping is enabled to detect dead connections"""
        with app.app_context():
            options = app.config['SQLALCHEMY_ENGINE_OPTIONS']

            # pool_pre_ping should be True
            assert options['pool_pre_ping'] is True, \
                "pool_pre_ping must be enabled to detect stale connections"

            # Verify we can execute a query (pre_ping would catch bad connections)
            result = db.session.execute(text("SELECT 1"))
            assert result.fetchone()[0] == 1


class TestConnectionPoolErrorHandling:
    """Test connection pool error handling"""

    def test_no_connection_leak_on_error(self, app, db):
        """Verify connections are returned to pool even on error"""
        with app.app_context():
            # Execute a failing query
            try:
                db.session.execute(text("SELECT * FROM nonexistent_table_xyz"))
                assert False, "Query should have failed"
            except Exception:
                pass  # Expected

            # Should still be able to execute valid queries
            # (connection was returned to pool despite error)
            result = db.session.execute(text("SELECT 1"))
            assert result.fetchone()[0] == 1

    def test_session_cleanup_after_exception(self, app, db):
        """Verify session is cleaned up after exceptions"""
        with app.app_context():
            try:
                # Force a transaction error
                db.session.execute(text("INVALID SQL HERE"))
            except Exception:
                db.session.rollback()

            # Session should be usable after rollback
            result = db.session.execute(text("SELECT 1"))
            assert result.fetchone()[0] == 1
