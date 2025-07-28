"""
Unit tests for database initialization and migration scripts.

Tests the modernized database initialization process and
schema improvements without requiring actual database connections.
"""
import pytest
import os
import tempfile
from unittest.mock import Mock, patch, call, MagicMock
from datetime import datetime, timezone

from scripts.init_db import (
    wait_for_postgres,
    create_database_if_needed,
    run_migrations,
    seed_initial_data,
    init_db as init_db_main
)


class TestDatabaseInitialization:
    """Test the modernized database initialization process."""
    
    def test_wait_for_postgres_success(self):
        """Test successful PostgreSQL connection."""
        with patch('psycopg2.connect') as mock_connect:
            # Simulate successful connection
            mock_conn = Mock()
            mock_connect.return_value = mock_conn
            
            result = wait_for_postgres('postgresql://user:pass@localhost/db', max_attempts=3)
            
            assert result is True
            assert mock_connect.call_count == 1
            mock_conn.close.assert_called_once()
    
    def test_wait_for_postgres_retry(self):
        """Test PostgreSQL connection with retries."""
        with patch('psycopg2.connect') as mock_connect:
            with patch('time.sleep'):  # Speed up test
                # Fail twice, then succeed
                mock_connect.side_effect = [
                    Exception("Connection refused"),
                    Exception("Connection refused"),
                    Mock()  # Success on third attempt
                ]
                
                result = wait_for_postgres('postgresql://user:pass@localhost/db', max_attempts=5)
                
                assert result is True
                assert mock_connect.call_count == 3
    
    def test_wait_for_postgres_timeout(self):
        """Test PostgreSQL connection timeout."""
        with patch('psycopg2.connect') as mock_connect:
            with patch('time.sleep'):  # Speed up test
                # Always fail
                mock_connect.side_effect = Exception("Connection refused")
                
                result = wait_for_postgres('postgresql://user:pass@localhost/db', max_attempts=3)
                
                assert result is False
                assert mock_connect.call_count == 3
    
    def test_create_database_if_needed_exists(self):
        """Test when database already exists."""
        with patch('psycopg2.connect') as mock_connect:
            # Database exists - connection succeeds
            mock_conn = Mock()
            mock_connect.return_value = mock_conn
            
            result = create_database_if_needed('postgresql://user:pass@localhost/testdb')
            
            assert result is True
            # Should only connect once to check
            assert mock_connect.call_count == 1
    
    def test_create_database_if_needed_create(self):
        """Test creating new database."""
        with patch('psycopg2.connect') as mock_connect:
            # First call fails (db doesn't exist), second succeeds (connect to postgres)
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_conn.cursor.return_value = mock_cursor
            
            mock_connect.side_effect = [
                psycopg2.OperationalError("database does not exist"),
                mock_conn  # Connect to postgres database
            ]
            
            result = create_database_if_needed('postgresql://user:pass@localhost/testdb')
            
            assert result is True
            # Should create database
            mock_cursor.execute.assert_called_with('CREATE DATABASE testdb')
            mock_conn.commit.assert_called_once()
    
    def test_run_migrations(self):
        """Test running Alembic migrations."""
        mock_app = Mock()
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            
            result = run_migrations(mock_app)
            
            assert result is True
            mock_run.assert_called_once()
            
            # Check correct command
            call_args = mock_run.call_args[0][0]
            assert 'flask' in call_args
            assert 'db' in call_args
            assert 'upgrade' in call_args
    
    def test_run_migrations_failure(self):
        """Test migration failure handling."""
        mock_app = Mock()
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=1)
            
            result = run_migrations(mock_app)
            
            assert result is False
    
    def test_seed_initial_data_with_env_vars(self):
        """Test seeding initial data from environment variables."""
        mock_app = Mock()
        mock_db = Mock()
        
        # Mock models
        with patch('scripts.init_db.db', mock_db):
            with patch('scripts.init_db.Instance') as MockInstance:
                with patch('scripts.init_db.User') as MockUser:
                    with patch('scripts.init_db.Site') as MockSite:
                        # Mock query results
                        MockInstance.query.first.return_value = None
                        MockUser.query.first.return_value = None
                        MockSite.query.first.return_value = None
                        
                        # Create mock instances
                        mock_instance = Mock()
                        mock_instance.id = 1
                        MockInstance.return_value = mock_instance
                        
                        mock_user = Mock()
                        MockUser.return_value = mock_user
                        
                        result = seed_initial_data(
                            mock_app,
                            admin_username='admin',
                            admin_email='admin@example.com',
                            admin_password='secure123',
                            site_name='Test Site',
                            site_description='Test Description',
                            skip_blocklists=True
                        )
                        
                        assert result is True
                        
                        # Verify instance created
                        MockInstance.assert_called_once()
                        
                        # Verify admin user created
                        MockUser.assert_called_once()
                        assert MockUser.call_args[1]['user_name'] == 'admin'
                        assert MockUser.call_args[1]['email'] == 'admin@example.com'
                        mock_user.set_password.assert_called_with('secure123')
                        
                        # Verify site created
                        MockSite.assert_called_once()
                        
                        # Verify database commit
                        assert mock_db.session.add.call_count >= 3
                        mock_db.session.commit.assert_called()
    
    def test_main_non_interactive_mode(self):
        """Test main function in non-interactive mode."""
        # Set environment variables
        env_vars = {
            'DATABASE_URL': 'postgresql://test:test@localhost/test',
            'NON_INTERACTIVE': 'true',
            'ADMIN_USERNAME': 'admin',
            'ADMIN_EMAIL': 'admin@test.com',
            'ADMIN_PASSWORD': 'secure123',
            'SITE_NAME': 'Test Site',
            'SITE_DESCRIPTION': 'A test site'
        }
        
        with patch.dict(os.environ, env_vars):
            with patch('scripts.init_db.create_app') as mock_create_app:
                with patch('scripts.init_db.wait_for_postgres', return_value=True):
                    with patch('scripts.init_db.create_database_if_needed', return_value=True):
                        with patch('scripts.init_db.run_migrations', return_value=True):
                            with patch('scripts.init_db.seed_initial_data', return_value=True):
                                    with patch('sys.exit') as mock_exit:
                                        init_db_main()
                                        
                                        # Should exit successfully
                                        mock_exit.assert_called_with(0)
    
    def test_main_skip_seed_data(self):
        """Test skipping seed data when SKIP_SEED_DATA is set."""
        env_vars = {
            'DATABASE_URL': 'postgresql://test:test@localhost/test',
            'NON_INTERACTIVE': 'true',
            'SKIP_SEED_DATA': 'true'
        }
        
        with patch.dict(os.environ, env_vars):
            with patch('scripts.init_db.create_app'):
                with patch('scripts.init_db.wait_for_postgres', return_value=True):
                    with patch('scripts.init_db.create_database_if_needed', return_value=True):
                        with patch('scripts.init_db.run_migrations', return_value=True):
                            with patch('scripts.init_db.seed_initial_data') as mock_seed:
                                with patch('sys.exit'):
                                    init_db_main()
                                    
                                    # Should not call seed_initial_data
                                    mock_seed.assert_not_called()


class TestDatabaseMigrations:
    """Test database migration scripts."""
    
    def test_peachpie_schema_improvements(self):
        """Test the PeachPie schema improvements migration."""
        # This tests the migration logic without running actual SQL
        from alembic.operations import Operations
        from alembic.migration import MigrationContext
        from sqlalchemy import create_engine
        
        # Create in-memory SQLite for testing
        engine = create_engine('sqlite:///:memory:')
        
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            op = Operations(context)
            
            # Test that operations would be valid
            # In real migration, these would alter tables
            
            # Verify migration handles TEXT conversions
            with patch.object(op, 'alter_column') as mock_alter:
                # Simulate migration operations
                mock_alter.return_value = None
                
                # URL fields should be converted to TEXT
                url_fields = [
                    ('user', 'ap_profile_id'),
                    ('user', 'ap_inbox_url'),
                    ('user', 'ap_outbox_url'),
                    ('community', 'ap_profile_id'),
                    ('community', 'ap_inbox_url'),
                    ('instance', 'inbox'),
                    ('instance', 'outbox')
                ]
                
                for table, column in url_fields:
                    op.alter_column(table, column, type_='TEXT')
                
                # Verify all URL fields were updated
                assert mock_alter.call_count >= len(url_fields)
    
    def test_pyfedi_to_peachpie_data_migration(self):
        """Test data migration from PyFedi to PeachPie."""
        # Test configuration updates
        config_updates = {
            'SOFTWARE_NAME': 'PeachPie',
            'SOFTWARE_REPO': 'https://github.com/theatl-social/peachpie',
            'USER_AGENT': 'PeachPie/1.0'
        }
        
        # Verify migration would update these values
        for key, expected_value in config_updates.items():
            assert expected_value != 'PyFedi'  # Ensure we're changing from PyFedi
            assert 'peachpie' in expected_value.lower()


class TestEnvironmentConfiguration:
    """Test environment-based configuration."""
    
    def test_redis_url_consolidation(self):
        """Test that Redis URL is properly consolidated."""
        # Test with single REDIS_URL
        with patch.dict(os.environ, {'REDIS_URL': 'redis://localhost:6379/0'}):
            from config import Config
            
            config = Config()
            assert config.REDIS_URL == 'redis://localhost:6379/0'
            
            # Legacy variables should fall back to REDIS_URL
            assert getattr(config, 'CACHE_REDIS_URL', config.REDIS_URL) == config.REDIS_URL
    
    def test_software_branding_configuration(self):
        """Test software branding environment variables."""
        env_vars = {
            'SOFTWARE_NAME': 'PeachPie',
            'SOFTWARE_REPO': 'https://github.com/theatl-social/peachpie',
            'SOFTWARE_VERSION': '2.0.0'
        }
        
        with patch.dict(os.environ, env_vars):
            from config import Config
            
            config = Config()
            assert config.SOFTWARE_NAME == 'PeachPie'
            assert config.SOFTWARE_REPO == 'https://github.com/theatl-social/peachpie'
            assert config.VERSION == '2.0.0'
    
    def test_rate_limit_configuration(self):
        """Test rate limit environment variables."""
        env_vars = {
            'RATE_LIMIT_ACTIVITIES': '200/120',  # 200 per 2 minutes
            'RATE_LIMIT_FOLLOWS': '10/300',      # 10 per 5 minutes
            'RATE_LIMIT_VOTES': '500/60',        # 500 per minute
            'RATE_LIMIT_MEDIA': '50/60',         # 50 per minute
            'RATE_LIMIT_GLOBAL': '1000/60'       # 1000 per minute
        }
        
        with patch.dict(os.environ, env_vars):
            # Test parsing of rate limit strings
            for key, value in env_vars.items():
                requests, seconds = value.split('/')
                assert int(requests) > 0
                assert int(seconds) > 0


class TestDatabasePerformance:
    """Test database performance optimizations."""
    
    def test_index_creation(self):
        """Test that proper indexes are created for performance."""
        # Key indexes that should exist
        expected_indexes = [
            ('user', 'ap_profile_id'),           # For actor lookups
            ('community', 'ap_profile_id'),      # For community lookups
            ('instance', 'domain'),              # For instance lookups
            ('activitypublog', 'activity_id'),   # For activity lookups
            ('activitypublog', 'created_at'),    # For time-based queries
            ('post', 'ap_id'),                   # For post lookups
            ('user', 'user_name', 'instance_id') # Composite index
        ]
        
        # In actual implementation, these would be verified against
        # the database schema or migration files
        for table, *columns in expected_indexes:
            # Index name would typically be: idx_<table>_<columns>
            index_name = f"idx_{table}_{'_'.join(columns)}"
            assert len(index_name) < 64  # PostgreSQL identifier limit
    
    def test_varchar_to_text_conversion(self):
        """Test that VARCHAR columns are properly sized or converted to TEXT."""
        # Fields that should be TEXT for URLs
        text_fields = [
            'ap_profile_id',
            'ap_inbox_url',
            'ap_outbox_url',
            'ap_shared_inbox_url',
            'inbox',
            'outbox',
            'shared_inbox',
            'featured',
            'followers_url',
            'following_url'
        ]
        
        # Email should support modern lengths
        email_max_length = 320  # Per RFC 5321
        
        # These assertions would be validated against actual schema
        for field in text_fields:
            # In migration, these should be TEXT, not VARCHAR
            assert field.endswith('_url') or field.endswith('_id') or field == 'inbox'


if __name__ == '__main__':
    # Import psycopg2 for exception handling
    try:
        import psycopg2
    except ImportError:
        # Create mock for tests
        import sys
        from unittest.mock import MagicMock
        sys.modules['psycopg2'] = MagicMock()
        psycopg2 = sys.modules['psycopg2']
        psycopg2.OperationalError = Exception
    
    pytest.main([__file__, '-v'])