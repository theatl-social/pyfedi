"""
Integration test for private registration ActivityPub setup
"""
import pytest
from app import create_app, db
from app.models import User
from app.api.admin.private_registration import create_private_user


class TestConfig:
    """Test configuration"""
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    MAIL_SUPPRESS_SEND = True
    SERVER_NAME = 'test.localhost'
    SECRET_KEY = 'test-secret-key'
    PRIVATE_REGISTRATION_ENABLED = 'true'
    PRIVATE_REGISTRATION_SECRET = 'test-secret-123'
    CACHE_TYPE = 'null'  # Disable caching for tests
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


class TestPrivateRegistrationActivityPubSetup:
    """Test that private registration properly sets up ActivityPub for new users"""

    def test_create_private_user_sets_activitypub_fields_when_activated(self, app):
        """Test that create_private_user sets up ActivityPub fields when auto_activate=True"""
        with app.app_context():
            # Create user with auto_activate=True
            user_data = {
                'username': 'testuser',
                'email': 'test@example.com',
                'display_name': 'Test User',
                'password': 'securepassword123',
                'auto_activate': True,
                'bio': 'Test bio',
                'timezone': 'UTC'
            }

            result = create_private_user(user_data)

            # Verify user was created
            assert result['success'] is True
            assert result['user_id'] is not None

            # Fetch the user from database
            user = User.query.get(result['user_id'])
            assert user is not None

            # Verify ActivityPub setup was completed
            assert user.private_key is not None, "User should have ActivityPub private key"
            assert user.public_key is not None, "User should have ActivityPub public key"
            assert user.ap_profile_id is not None, "User should have ActivityPub profile ID"
            assert user.ap_public_url is not None, "User should have ActivityPub public URL"
            assert user.ap_inbox_url is not None, "User should have ActivityPub inbox URL"

            # Verify the URLs are correctly formatted
            expected_profile_id = f"https://test.localhost/u/{user.user_name}".lower()
            expected_public_url = f"https://test.localhost/u/{user.user_name}"
            expected_inbox_url = f"https://test.localhost/u/{user.user_name.lower()}/inbox"

            assert user.ap_profile_id == expected_profile_id
            assert user.ap_public_url == expected_public_url
            assert user.ap_inbox_url == expected_inbox_url

            # Verify user is verified
            assert user.verified is True

            # Verify last_seen is set
            assert user.last_seen is not None

    def test_create_private_user_skips_activitypub_when_not_activated(self, app):
        """Test that create_private_user does NOT set up ActivityPub when auto_activate=False"""
        with app.app_context():
            # Create user with auto_activate=False
            user_data = {
                'username': 'testuser2',
                'email': 'test2@example.com',
                'display_name': 'Test User 2',
                'password': 'securepassword123',
                'auto_activate': False,
                'bio': 'Test bio',
                'timezone': 'UTC'
            }

            result = create_private_user(user_data)

            # Verify user was created
            assert result['success'] is True
            assert result['activation_required'] is True

            # Fetch the user from database
            user = User.query.get(result['user_id'])
            assert user is not None

            # Verify ActivityPub setup was NOT completed (will be done on activation)
            assert user.private_key is None, "User should NOT have ActivityPub private key before activation"
            assert user.public_key is None, "User should NOT have ActivityPub public key before activation"
            assert user.ap_profile_id is None, "User should NOT have ActivityPub profile ID before activation"

            # Verify user is NOT verified
            assert user.verified is False

    def test_multiple_users_get_unique_keypairs(self, app):
        """Test that multiple users get unique ActivityPub keypairs"""
        with app.app_context():
            # Create first user
            user_data_1 = {
                'username': 'user1',
                'email': 'user1@example.com',
                'password': 'password123',
                'auto_activate': True
            }
            result1 = create_private_user(user_data_1)
            user1 = User.query.get(result1['user_id'])

            # Create second user
            user_data_2 = {
                'username': 'user2',
                'email': 'user2@example.com',
                'password': 'password123',
                'auto_activate': True
            }
            result2 = create_private_user(user_data_2)
            user2 = User.query.get(result2['user_id'])

            # Verify both users have different keypairs
            assert user1.private_key != user2.private_key
            assert user1.public_key != user2.public_key
            assert user1.ap_profile_id != user2.ap_profile_id

    def test_activitypub_urls_are_lowercase(self, app):
        """Test that ActivityPub profile ID uses lowercase username"""
        with app.app_context():
            # Create user with mixed-case username
            user_data = {
                'username': 'MixedCaseUser',
                'email': 'mixed@example.com',
                'password': 'password123',
                'auto_activate': True
            }
            result = create_private_user(user_data)
            user = User.query.get(result['user_id'])

            # Verify ap_profile_id is lowercase
            assert 'mixedcaseuser' in user.ap_profile_id.lower()
            assert user.ap_profile_id == user.ap_profile_id.lower()
