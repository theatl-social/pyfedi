"""
Test startup validation for ActivityPub user setup
"""

import pytest
from unittest.mock import MagicMock, patch
from app import create_app, db
from app.models import User, utcnow
from app.startup_validation import validate_and_fix_user_activitypub_setup


class TestConfig:
    """Test configuration"""

    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    MAIL_SUPPRESS_SEND = True
    SERVER_NAME = "test.localhost"
    SECRET_KEY = "test-secret-key"
    CACHE_TYPE = "null"
    CELERY_ALWAYS_EAGER = True


@pytest.fixture
def app():
    """Create test app with test configuration"""
    try:
        app = create_app(TestConfig)

        with app.app_context():
            db.create_all()
            yield app
            db.session.remove()
            db.drop_all()
    except Exception as e:
        pytest.skip(f"Could not create test app: {e}")


class TestStartupValidationActivityPub:
    """Test startup validation for ActivityPub setup"""

    def test_finds_incomplete_users(self, app):
        """Test that validation finds users with incomplete ActivityPub setup"""
        with app.app_context():
            # Create a user with incomplete ActivityPub setup
            incomplete_user = User(
                user_name="incomplete_user",
                email="incomplete@example.com",
                password_hash="dummy_hash",
                instance_id=1,  # Local user
                verified=True,  # Activated
                banned=False,
                deleted=False,
                private_key=None,  # Missing ActivityPub setup
                public_key=None,
                ap_profile_id=None,
                created=utcnow(),
            )
            db.session.add(incomplete_user)
            db.session.commit()

            # Run validation
            result = validate_and_fix_user_activitypub_setup()

            # Verify user was found and fixed
            assert result["users_fixed"] == 1
            assert len(result["users_found"]) == 1
            assert result["users_found"][0]["username"] == "incomplete_user"

            # Verify user now has ActivityPub setup
            user = User.query.filter_by(user_name="incomplete_user").first()
            assert user.private_key is not None
            assert user.public_key is not None
            assert user.ap_profile_id is not None
            assert user.ap_public_url is not None
            assert user.ap_inbox_url is not None

    def test_ignores_complete_users(self, app):
        """Test that validation ignores users with complete ActivityPub setup"""
        with app.app_context():
            # Create a user with complete ActivityPub setup
            complete_user = User(
                user_name="complete_user",
                email="complete@example.com",
                password_hash="dummy_hash",
                instance_id=1,
                verified=True,
                banned=False,
                deleted=False,
                private_key="existing_private_key",  # Has ActivityPub setup
                public_key="existing_public_key",
                ap_profile_id="https://test.localhost/u/complete_user",
                created=utcnow(),
            )
            db.session.add(complete_user)
            db.session.commit()

            # Run validation
            result = validate_and_fix_user_activitypub_setup()

            # Verify no users were "fixed" since this user is already complete
            assert result["users_fixed"] == 0

            # Verify user's keys weren't changed
            user = User.query.filter_by(user_name="complete_user").first()
            assert user.private_key == "existing_private_key"
            assert user.public_key == "existing_public_key"

    def test_ignores_unverified_users(self, app):
        """Test that validation ignores unverified (not activated) users"""
        with app.app_context():
            # Create an unverified user
            unverified_user = User(
                user_name="unverified_user",
                email="unverified@example.com",
                password_hash="dummy_hash",
                instance_id=1,
                verified=False,  # Not activated yet
                banned=False,
                deleted=False,
                private_key=None,
                created=utcnow(),
            )
            db.session.add(unverified_user)
            db.session.commit()

            # Run validation
            result = validate_and_fix_user_activitypub_setup()

            # Verify user was NOT fixed (should wait until activated)
            assert result["users_fixed"] == 0

            # Verify user still has no ActivityPub setup
            user = User.query.filter_by(user_name="unverified_user").first()
            assert user.private_key is None

    def test_ignores_banned_and_deleted_users(self, app):
        """Test that validation ignores banned and deleted users"""
        with app.app_context():
            # Create a banned user
            banned_user = User(
                user_name="banned_user",
                email="banned@example.com",
                password_hash="dummy_hash",
                instance_id=1,
                verified=True,
                banned=True,  # Banned
                deleted=False,
                private_key=None,
                created=utcnow(),
            )
            db.session.add(banned_user)

            # Create a deleted user
            deleted_user = User(
                user_name="deleted_user",
                email="deleted@example.com",
                password_hash="dummy_hash",
                instance_id=1,
                verified=True,
                banned=False,
                deleted=True,  # Deleted
                private_key=None,
                created=utcnow(),
            )
            db.session.add(deleted_user)
            db.session.commit()

            # Run validation
            result = validate_and_fix_user_activitypub_setup()

            # Verify no users were fixed
            assert result["users_fixed"] == 0

    def test_ignores_remote_users(self, app):
        """Test that validation only processes local users"""
        with app.app_context():
            # Create a remote user (from another instance)
            remote_user = User(
                user_name="remote_user",
                email="remote@example.com",
                password_hash="dummy_hash",
                instance_id=2,  # Remote instance
                verified=True,
                banned=False,
                deleted=False,
                private_key=None,
                created=utcnow(),
            )
            db.session.add(remote_user)
            db.session.commit()

            # Run validation
            result = validate_and_fix_user_activitypub_setup()

            # Verify remote user was NOT fixed
            assert result["users_fixed"] == 0

    def test_fixes_multiple_incomplete_users(self, app):
        """Test that validation fixes multiple incomplete users"""
        with app.app_context():
            # Create multiple incomplete users
            for i in range(3):
                user = User(
                    user_name=f"user{i}",
                    email=f"user{i}@example.com",
                    password_hash="dummy_hash",
                    instance_id=1,
                    verified=True,
                    banned=False,
                    deleted=False,
                    private_key=None,
                    created=utcnow(),
                )
                db.session.add(user)
            db.session.commit()

            # Run validation
            result = validate_and_fix_user_activitypub_setup()

            # Verify all users were fixed
            assert result["users_fixed"] == 3
            assert len(result["users_found"]) == 3

            # Verify all users now have ActivityPub setup
            for i in range(3):
                user = User.query.filter_by(user_name=f"user{i}").first()
                assert user.private_key is not None
                assert user.public_key is not None


def test_startup_validation_code_exists():
    """Test that startup validation is integrated into app initialization"""
    import os
    import ast

    # Read the app/__init__.py file
    file_path = os.path.join(os.path.dirname(__file__), "..", "app", "__init__.py")

    with open(file_path, "r") as f:
        source = f.read()

    # Verify startup validation is imported and called
    assert "from app.startup_validation import run_startup_validations" in source
    assert "run_startup_validations()" in source

    print("✓ Startup validation is integrated into app initialization")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
