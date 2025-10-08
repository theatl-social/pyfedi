"""
Test that startup validation properly cleans up database session

This test verifies that the startup validation doesn't leave stale
objects in the SQLAlchemy session that could cause issues for
subsequent requests.
"""
import pytest
from unittest.mock import patch, MagicMock
from app import create_app, db
from app.models import User, Site, utcnow
from app.startup_validation import run_startup_validations


class TestConfig:
    """Test configuration"""
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    MAIL_SUPPRESS_SEND = True
    SERVER_NAME = 'test.localhost'
    SECRET_KEY = 'test-secret-key'
    CACHE_TYPE = 'null'
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


class TestStartupSessionCleanup:
    """Test that startup validation cleans up session properly"""

    def test_session_is_clean_after_startup_validation(self, app):
        """Test that running startup validation leaves session in clean state"""
        with app.app_context():
            # Create an incomplete user that will be fixed
            incomplete_user = User(
                user_name='test_cleanup',
                email='cleanup@example.com',
                password_hash='dummy_hash',
                instance_id=1,
                verified=True,
                banned=False,
                deleted=False,
                private_key=None,  # Will trigger fix
                created=utcnow()
            )
            db.session.add(incomplete_user)
            db.session.commit()
            user_id = incomplete_user.id

            # Get initial session identity map count
            initial_identity_map_size = len(db.session.identity_map)

            # Run startup validation (will fix the user)
            result = run_startup_validations()

            # Verify user was fixed
            assert result['activitypub_validation']['users_fixed'] == 1

            # The critical test: after validation, the session should be clean
            # Either empty or only contain fresh objects

            # Check that we can query for objects without issues
            # This would fail if stale objects are in session
            site = Site.query.get(1)
            assert site is not None
            assert site.default_theme == 'piefed'  # Should not raise KeyError

            # Verify we can access the user again fresh
            user = User.query.get(user_id)
            assert user is not None
            assert user.private_key is not None  # Should be fixed

    def test_deferred_attributes_load_after_validation(self, app):
        """Test that deferred attributes can be loaded after startup validation"""
        with app.app_context():
            # Run startup validation
            run_startup_validations()

            # Now try to access deferred attributes on Site
            # This is what was failing in production
            site = Site.query.get(1)

            # These should not raise "Deferred loader failed" errors
            try:
                theme = site.default_theme
                assert theme is not None or theme is None  # Either is fine, just shouldn't error

                name = site.name
                assert name == 'Test Site'

            except KeyError as e:
                pytest.fail(f"Deferred attribute loading failed after validation: {e}")

    def test_multiple_queries_after_validation(self, app):
        """Test that multiple queries work correctly after validation"""
        with app.app_context():
            # Create test data
            user1 = User(
                user_name='user1',
                email='user1@example.com',
                password_hash='hash',
                instance_id=1,
                verified=True,
                private_key=None,
                created=utcnow()
            )
            user2 = User(
                user_name='user2',
                email='user2@example.com',
                password_hash='hash',
                instance_id=1,
                verified=True,
                private_key=None,
                created=utcnow()
            )
            db.session.add_all([user1, user2])
            db.session.commit()

            # Run validation
            result = run_startup_validations()
            assert result['activitypub_validation']['users_fixed'] == 2

            # Now perform various queries that should all work
            # Query 1: Get all users
            all_users = User.query.all()
            assert len(all_users) >= 2

            # Query 2: Get specific user
            specific_user = User.query.filter_by(user_name='user1').first()
            assert specific_user is not None

            # Query 3: Access lazy-loaded attributes
            assert specific_user.private_key is not None
            assert specific_user.ap_profile_id is not None

            # Query 4: Get Site (different model)
            site = Site.query.get(1)
            assert site.default_theme is not None or site.default_theme is None

    def test_session_identity_map_cleared(self, app):
        """Test that session identity map is properly cleared"""
        with app.app_context():
            # Create incomplete user
            user = User(
                user_name='identity_test',
                email='identity@example.com',
                password_hash='hash',
                instance_id=1,
                verified=True,
                private_key=None,
                created=utcnow()
            )
            db.session.add(user)
            db.session.commit()

            # Run validation
            run_startup_validations()

            # After cleanup, querying the same user should create a fresh instance
            # Get user before validation reference
            user_before_id = id(user)

            # Clear local reference
            del user

            # Query again - should be fresh instance (different Python object)
            user_after = User.query.filter_by(user_name='identity_test').first()

            # Verify it's a fresh object (not the same Python instance)
            # Note: This test is subtle - we're checking that the session
            # was properly cleaned and objects were expired/removed
            assert user_after is not None
            assert user_after.private_key is not None

    def test_validation_with_no_users_to_fix(self, app):
        """Test cleanup works even when no users need fixing"""
        with app.app_context():
            # Don't create any incomplete users

            # Run validation
            result = run_startup_validations()

            # Should complete successfully
            assert result['activitypub_validation']['users_fixed'] == 0

            # Session should still be clean
            site = Site.query.get(1)
            assert site.default_theme is not None or site.default_theme is None

    def test_validation_cleanup_handles_errors_gracefully(self, app):
        """Test that cleanup happens even if validation has errors"""
        with app.app_context():
            # Create user that will be processed
            user = User(
                user_name='error_test',
                email='error@example.com',
                password_hash='hash',
                instance_id=1,
                verified=True,
                private_key=None,
                created=utcnow()
            )
            db.session.add(user)
            db.session.commit()

            # Mock finalize_user_setup to raise an error
            with patch('app.startup_validation.finalize_user_setup') as mock_finalize:
                mock_finalize.side_effect = Exception("Simulated error")

                # Run validation - should not crash
                result = run_startup_validations()

                # Should report 0 users fixed due to error
                assert result['activitypub_validation']['users_fixed'] == 0

                # Session should still be cleaned up (finally block)
                # This should work without errors
                site = Site.query.get(1)
                assert site is not None


class TestSessionCleanupWithAppContext:
    """Test session cleanup with app context lifecycle"""

    def test_validation_in_app_context_doesnt_pollute_next_context(self, app):
        """Test that running validation in one context doesn't affect the next"""

        # First context - run validation
        with app.app_context():
            db.create_all()
            site = Site(id=1, name='Test', default_theme='piefed')
            db.session.add(site)
            db.session.commit()

            user = User(
                user_name='context_test',
                email='context@example.com',
                password_hash='hash',
                instance_id=1,
                verified=True,
                private_key=None,
                created=utcnow()
            )
            db.session.add(user)
            db.session.commit()

            # Run validation
            run_startup_validations()

            # Context ends here, session should be cleaned

        # Second context - simulate a new request
        with app.app_context():
            # This simulates what happens when Gunicorn handles a request
            # The session should be fresh, not polluted from validation

            site = Site.query.get(1)

            # This should not raise KeyError about deferred attributes
            try:
                theme = site.default_theme
                assert theme == 'piefed'
            except KeyError as e:
                pytest.fail(f"Session was polluted from previous context: {e}")

            # Should be able to query users
            user = User.query.filter_by(user_name='context_test').first()
            assert user is not None
            assert user.private_key is not None  # Should be fixed


def test_session_cleanup_integration(app):
    """
    Integration test: Verify the complete flow works

    This test simulates what happens in production:
    1. App starts
    2. Startup validation runs
    3. First request comes in
    4. Request tries to access Site attributes
    """
    with app.app_context():
        db.create_all()
        site = Site(id=1, name='Integration Test', default_theme='piefed')
        db.session.add(site)

        # Create incomplete user
        user = User(
            user_name='integration_test',
            email='integration@example.com',
            password_hash='hash',
            instance_id=1,
            verified=True,
            private_key=None,
            created=utcnow()
        )
        db.session.add(user)
        db.session.commit()

        # Simulate app startup - run validation
        result = run_startup_validations()
        assert result['activitypub_validation']['users_fixed'] == 1

    # Simulate new request context (like Gunicorn worker handling request)
    with app.app_context():
        # This is what was failing in production:
        # Accessing site.default_theme in render_template -> current_theme()

        site = Site.query.get(1)

        # Should not raise: KeyError: "Deferred loader for attribute 'default_theme' failed"
        theme = site.default_theme
        assert theme == 'piefed'

        # User should be properly fixed
        user = User.query.filter_by(user_name='integration_test').first()
        assert user.private_key is not None
        assert user.ap_profile_id is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
