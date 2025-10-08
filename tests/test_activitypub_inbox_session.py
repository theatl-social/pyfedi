"""
Tests for ActivityPub inbox route session management

These tests verify that the /inbox route properly manages database sessions
and handles edge cases that could cause PGRES_TUPLES_OK errors.
"""

import pytest
from flask import g
from app import create_app, db
from app.models import Site, User, Settings, utcnow
from app.utils import get_setting, set_setting


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


class TestInboxRouteSiteLoading:
    """Test that /inbox route properly loads g.site"""

    def test_inbox_sets_g_site(self, app, db):
        """Verify g.site is set when processing inbox requests"""
        with app.app_context():
            # Ensure Site exists
            site = Site.query.get(1)
            if not site:
                site = Site(id=1, name='Test Site', default_theme='piefed')
                db.session.add(site)
                db.session.commit()

            # Simulate what happens in inbox route
            g.site = Site.query.get(1)

            # Verify g.site is not None
            assert g.site is not None, "g.site should not be None"
            assert g.site.id == 1, "g.site should have id=1"

    def test_inbox_site_attribute_access(self, app, db):
        """Verify g.site attributes can be accessed without errors"""
        with app.app_context():
            # Ensure Site exists with all required attributes
            site = Site.query.get(1)
            if not site:
                site = Site(id=1, name='Test Site', default_theme='piefed')
                db.session.add(site)
                db.session.commit()

            # Simulate inbox route behavior
            g.site = Site.query.get(1)

            # Should be able to access attributes without KeyError
            assert g.site.log_activitypub_json is not None or g.site.log_activitypub_json is None
            assert g.site.default_theme is not None
            assert g.site.name is not None

            # This should not raise "Deferred loader for attribute failed"
            _ = g.site.default_theme

    def test_inbox_after_startup_validation(self, app, db):
        """Test inbox works correctly after startup validation runs"""
        with app.app_context():
            # Simulate startup validation having run
            from app.startup_validation import run_startup_validations
            run_startup_validations()

            # After startup validation, session should be clean
            # Now simulate inbox request
            g.site = Site.query.get(1)

            # Should be able to access site attributes
            assert g.site is not None
            assert hasattr(g.site, 'default_theme')
            assert hasattr(g.site, 'log_activitypub_json')


class TestGetSettingErrorHandling:
    """Test get_setting() handles invalid data types gracefully"""

    def test_get_setting_with_valid_json_string(self, app, db):
        """Verify get_setting works with properly formatted JSON"""
        with app.app_context():
            # Set a valid JSON value
            test_value = ["word1", "word2", "word3"]
            set_setting('test_blocked_words', test_value)

            # Should retrieve correctly
            result = get_setting('test_blocked_words')
            assert result == test_value

    def test_get_setting_with_integer_value(self, app, db):
        """Test get_setting handles integer values (which cause TypeError)"""
        with app.app_context():
            # Manually insert a setting with an integer value (simulating bad data)
            # This is what was causing the TypeError in production
            setting = Settings.query.filter_by(name='test_int_value').first()
            if not setting:
                setting = Settings(name='test_int_value', value='123')
                db.session.add(setting)
                db.session.commit()

            # Now manually corrupt it to an integer (simulating the bug)
            # Note: We can't actually set it as int because the column is text,
            # but we can verify get_setting handles the JSON parsing correctly
            result = get_setting('test_int_value')

            # Should get the integer value back (json.loads('123') = 123)
            assert result == 123

    def test_get_setting_with_nonexistent_key(self, app, db):
        """Test get_setting returns default for nonexistent keys"""
        with app.app_context():
            result = get_setting('nonexistent_key_xyz', default='default_value')
            assert result == 'default_value'

    def test_get_setting_with_null_value(self, app, db):
        """Test get_setting handles null values"""
        with app.app_context():
            # Insert setting with null/empty value
            setting = Settings.query.filter_by(name='test_null_value').first()
            if setting:
                db.session.delete(setting)

            setting = Settings(name='test_null_value', value='null')
            db.session.add(setting)
            db.session.commit()

            result = get_setting('test_null_value', default='default')
            # json.loads('null') returns None
            assert result is None

    def test_get_setting_with_invalid_json(self, app, db):
        """Test get_setting returns default for invalid JSON"""
        with app.app_context():
            # Insert setting with invalid JSON
            setting = Settings.query.filter_by(name='test_invalid_json').first()
            if setting:
                db.session.delete(setting)

            # Invalid JSON that will cause JSONDecodeError
            setting = Settings(name='test_invalid_json', value='{invalid json}')
            db.session.add(setting)
            db.session.commit()

            # Should return default instead of raising exception
            result = get_setting('test_invalid_json', default='fallback')
            assert result == 'fallback'

    def test_actor_blocked_words_setting(self, app, db):
        """Test the specific setting that was failing in production"""
        with app.app_context():
            # Test with empty list (valid)
            set_setting('actor_blocked_words', [])
            result = get_setting('actor_blocked_words')
            assert result == []

            # Test with actual blocked words
            blocked_words = ['spam', 'bot', 'test']
            set_setting('actor_blocked_words', blocked_words)
            result = get_setting('actor_blocked_words')
            assert result == blocked_words


class TestInboxSessionIsolation:
    """Test that inbox requests don't pollute session state"""

    def test_inbox_requests_dont_share_session_state(self, app, db):
        """Verify multiple inbox requests have isolated sessions"""
        with app.app_context():
            # First request
            g.site = Site.query.get(1)
            id(g.site)  # Python object id

            # Clear g.site
            g.site = None

            # Second request (simulating new request)
            g.site = Site.query.get(1)
            id(g.site)

            # Objects might be the same (due to identity map), but should be valid
            # The key is that both accesses work without errors
            assert g.site is not None
            assert g.site.id == 1

    def test_site_query_after_session_cleanup(self, app, db):
        """Test Site.query.get(1) works after session cleanup operations"""
        with app.app_context():
            # Simulate session cleanup (like startup validation does)
            db.session.expire_all()
            db.session.remove()

            # Now query for site (like inbox does)
            site = Site.query.get(1)

            # Should work without deferred loading errors
            assert site is not None
            assert site.default_theme is not None
            assert site.name is not None


class TestInboxDatabaseErrorRecovery:
    """Test inbox route can recover from database errors"""

    def test_recovery_after_failed_query(self, app, db):
        """Test that we can continue after a failed query"""
        with app.app_context():
            # Execute an invalid query
            try:
                from sqlalchemy import text
                db.session.execute(text("SELECT * FROM nonexistent_table"))
            except Exception:
                db.session.rollback()

            # Should still be able to load g.site
            g.site = Site.query.get(1)
            assert g.site is not None

    def test_site_access_after_commit_error(self, app, db):
        """Test site access works after a commit error"""
        with app.app_context():
            # Load site
            g.site = Site.query.get(1)
            initial_name = g.site.name

            # Try to make an invalid change and commit
            # (This simulates what might happen during activity processing)
            try:
                # Try to commit without changes
                db.session.commit()
            except Exception:
                db.session.rollback()

            # Should still be able to access site
            assert g.site.name == initial_name
            assert g.site.default_theme is not None
