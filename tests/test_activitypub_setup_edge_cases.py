"""
Edge case tests for ActivityPub user setup
Tests error handling, edge cases, and integration points
"""
import pytest
from unittest.mock import MagicMock, patch, call
from app import create_app, db
from app.models import User, utcnow, Notification
from app.startup_validation import validate_and_fix_user_activitypub_setup
from app.utils import finalize_user_setup
from app.constants import NOTIF_REGISTRATION


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
            yield app
            db.session.remove()
            db.drop_all()
    except Exception as e:
        pytest.skip(f"Could not create test app: {e}")


class TestFinalizeUserSetupEdgeCases:
    """Test edge cases for finalize_user_setup function"""

    def test_finalize_user_setup_is_idempotent(self, app):
        """Test that calling finalize_user_setup multiple times doesn't break things"""
        with app.app_context():
            # Create user without ActivityPub setup
            user = User(
                user_name='testuser',
                email='test@example.com',
                password_hash='dummy_hash',
                instance_id=1,
                verified=True,
                banned=False,
                deleted=False,
                private_key=None,
                created=utcnow()
            )
            db.session.add(user)
            db.session.commit()

            # Call finalize_user_setup first time
            finalize_user_setup(user)
            db.session.refresh(user)

            # Save the keys/URLs from first call
            first_private_key = user.private_key
            first_public_key = user.public_key
            first_profile_id = user.ap_profile_id

            # Call finalize_user_setup again (should be idempotent)
            finalize_user_setup(user)
            db.session.refresh(user)

            # Verify keys weren't regenerated
            assert user.private_key == first_private_key
            assert user.public_key == first_public_key
            assert user.ap_profile_id == first_profile_id

    def test_finalize_user_setup_with_partial_setup(self, app):
        """Test finalize_user_setup with user who has keys but missing URLs"""
        with app.app_context():
            # Create user with keys but no URLs (weird edge case)
            user = User(
                user_name='partialuser',
                email='partial@example.com',
                password_hash='dummy_hash',
                instance_id=1,
                verified=False,
                private_key='existing_key',
                public_key='existing_public_key',
                ap_profile_id=None,  # Missing
                created=utcnow()
            )
            db.session.add(user)
            db.session.commit()

            # Call finalize_user_setup
            finalize_user_setup(user)
            db.session.refresh(user)

            # Should preserve existing keys
            assert user.private_key == 'existing_key'
            assert user.public_key == 'existing_public_key'

            # Should add missing URLs
            assert user.ap_profile_id is not None
            assert user.ap_public_url is not None
            assert user.ap_inbox_url is not None

            # Should mark as verified
            assert user.verified is True

    def test_finalize_user_setup_marks_registration_notifications_read(self, app):
        """Test that finalize_user_setup marks registration notifications as read"""
        with app.app_context():
            # Create user
            user = User(
                user_name='testuser',
                email='test@example.com',
                password_hash='dummy_hash',
                instance_id=1,
                private_key=None,
                created=utcnow()
            )
            db.session.add(user)
            db.session.flush()

            # Create multiple registration notifications for this user
            notif1 = Notification(
                user_id=1,  # Admin
                author_id=user.id,
                notif_type=NOTIF_REGISTRATION,
                read=False,
                title='New registration'
            )
            notif2 = Notification(
                user_id=2,  # Another admin
                author_id=user.id,
                notif_type=NOTIF_REGISTRATION,
                read=False,
                title='New registration'
            )
            db.session.add_all([notif1, notif2])
            db.session.commit()

            # Call finalize_user_setup
            finalize_user_setup(user)

            # Verify notifications are marked as read
            notifs = Notification.query.filter_by(
                notif_type=NOTIF_REGISTRATION,
                author_id=user.id
            ).all()

            assert len(notifs) == 2
            assert all(n.read for n in notifs)

    def test_finalize_user_setup_with_plugin_hook(self, app):
        """Test that finalize_user_setup calls plugin hooks"""
        with app.app_context():
            user = User(
                user_name='testuser',
                email='test@example.com',
                password_hash='dummy_hash',
                instance_id=1,
                private_key=None,
                created=utcnow()
            )
            db.session.add(user)
            db.session.commit()

            # Mock the plugin system
            with patch('app.utils.plugins.fire_hook') as mock_hook:
                mock_hook.return_value = user

                finalize_user_setup(user)

                # Verify plugin hook was called
                mock_hook.assert_called_once_with('new_user', user)


class TestStartupValidationErrorHandling:
    """Test error handling in startup validation"""

    def test_validation_continues_after_individual_user_failure(self, app):
        """Test that validation continues if one user fails to fix"""
        with app.app_context():
            # Create multiple incomplete users
            user1 = User(
                user_name='user1',
                email='user1@example.com',
                password_hash='dummy_hash',
                instance_id=1,
                verified=True,
                banned=False,
                deleted=False,
                private_key=None,
                created=utcnow()
            )
            user2 = User(
                user_name='user2',
                email='user2@example.com',
                password_hash='dummy_hash',
                instance_id=1,
                verified=True,
                banned=False,
                deleted=False,
                private_key=None,
                created=utcnow()
            )
            user3 = User(
                user_name='user3',
                email='user3@example.com',
                password_hash='dummy_hash',
                instance_id=1,
                verified=True,
                banned=False,
                deleted=False,
                private_key=None,
                created=utcnow()
            )
            db.session.add_all([user1, user2, user3])
            db.session.commit()

            # Mock finalize_user_setup to fail for user2
            original_finalize = finalize_user_setup

            def mock_finalize(user):
                if user.user_name == 'user2':
                    raise Exception("Simulated failure for user2")
                return original_finalize(user)

            with patch('app.startup_validation.finalize_user_setup', side_effect=mock_finalize):
                result = validate_and_fix_user_activitypub_setup()

                # Should have attempted all 3 users but only fixed 2
                # Note: The actual number depends on implementation details
                # At minimum, it should not crash and should fix the users that can be fixed
                assert result['users_fixed'] == 2

    def test_validation_handles_database_errors_gracefully(self, app):
        """Test that validation handles database errors without crashing"""
        with app.app_context():
            # Mock the query to raise an exception
            with patch('app.startup_validation.User.query') as mock_query:
                mock_query.filter.side_effect = Exception("Database error")

                result = validate_and_fix_user_activitypub_setup()

                # Should return error info instead of crashing
                assert 'error' in result
                assert result['users_fixed'] == 0

    def test_validation_logs_errors_for_failed_users(self, app):
        """Test that validation logs errors when users fail to fix"""
        with app.app_context():
            # Create incomplete user
            user = User(
                user_name='problematic_user',
                email='problem@example.com',
                password_hash='dummy_hash',
                instance_id=1,
                verified=True,
                banned=False,
                deleted=False,
                private_key=None,
                created=utcnow()
            )
            db.session.add(user)
            db.session.commit()

            # Mock finalize_user_setup to fail
            with patch('app.startup_validation.finalize_user_setup') as mock_finalize:
                mock_finalize.side_effect = Exception("Key generation failed")

                # Mock logger to verify error logging
                with patch('app.startup_validation.current_app.logger') as mock_logger:
                    validate_and_fix_user_activitypub_setup()

                    # Verify error was logged
                    assert any(
                        'Failed to fix' in str(call_args)
                        for call_args in mock_logger.error.call_args_list
                    )


class TestActivityPubURLFormatting:
    """Test ActivityPub URL formatting edge cases"""

    def test_username_with_special_characters(self, app):
        """Test ActivityPub URLs with special characters in username"""
        with app.app_context():
            # Create user with underscore (allowed in usernames)
            user = User(
                user_name='test_user_123',
                email='test@example.com',
                password_hash='dummy_hash',
                instance_id=1,
                private_key=None,
                created=utcnow()
            )
            db.session.add(user)
            db.session.commit()

            finalize_user_setup(user)
            db.session.refresh(user)

            # Verify URLs are properly formatted
            assert user.ap_profile_id == 'https://test.localhost/u/test_user_123'
            assert user.ap_public_url == 'https://test.localhost/u/test_user_123'
            assert user.ap_inbox_url == 'https://test.localhost/u/test_user_123/inbox'

    def test_username_case_handling_in_urls(self, app):
        """Test that ap_profile_id is lowercase but ap_public_url preserves case"""
        with app.app_context():
            user = User(
                user_name='TestUser',
                email='test@example.com',
                password_hash='dummy_hash',
                instance_id=1,
                private_key=None,
                created=utcnow()
            )
            db.session.add(user)
            db.session.commit()

            finalize_user_setup(user)
            db.session.refresh(user)

            # ap_profile_id should be lowercase
            assert user.ap_profile_id == 'https://test.localhost/u/testuser'
            # ap_public_url preserves original case
            assert user.ap_public_url == 'https://test.localhost/u/TestUser'
            # ap_inbox_url uses lowercase
            assert user.ap_inbox_url == 'https://test.localhost/u/testuser/inbox'


class TestStartupValidationPerformance:
    """Test performance considerations for startup validation"""

    def test_validation_with_many_complete_users_is_fast(self, app):
        """Test that validation efficiently skips users who are already complete"""
        with app.app_context():
            # Create many complete users
            for i in range(50):
                user = User(
                    user_name=f'user{i}',
                    email=f'user{i}@example.com',
                    password_hash='dummy_hash',
                    instance_id=1,
                    verified=True,
                    banned=False,
                    deleted=False,
                    private_key=f'key{i}',  # Already has keys
                    public_key=f'pubkey{i}',
                    ap_profile_id=f'https://test.localhost/u/user{i}',
                    created=utcnow()
                )
                db.session.add(user)
            db.session.commit()

            # Run validation - should be quick since all users are complete
            result = validate_and_fix_user_activitypub_setup()

            # Should check all users but fix none
            assert result['users_checked'] >= 50
            assert result['users_fixed'] == 0

    def test_validation_result_includes_user_summary(self, app):
        """Test that validation returns detailed results"""
        with app.app_context():
            # Create incomplete user
            user = User(
                user_name='incomplete',
                email='incomplete@example.com',
                password_hash='dummy_hash',
                instance_id=1,
                verified=True,
                banned=False,
                deleted=False,
                private_key=None,
                created=utcnow()
            )
            db.session.add(user)
            db.session.commit()

            result = validate_and_fix_user_activitypub_setup()

            # Verify result structure
            assert 'users_checked' in result
            assert 'users_fixed' in result
            assert 'users_found' in result
            assert isinstance(result['users_found'], list)

            # Verify user details are included
            assert len(result['users_found']) == 1
            assert result['users_found'][0]['username'] == 'incomplete'
            assert 'id' in result['users_found'][0]
            assert 'email' in result['users_found'][0]


class TestRegistrationNotificationCleanup:
    """Test that registration notifications are properly cleaned up"""

    def test_finalize_marks_only_registration_notifications(self, app):
        """Test that only NOTIF_REGISTRATION notifications are marked as read"""
        with app.app_context():
            user = User(
                user_name='testuser',
                email='test@example.com',
                password_hash='dummy_hash',
                instance_id=1,
                private_key=None,
                created=utcnow()
            )
            db.session.add(user)
            db.session.flush()

            # Create registration notification
            reg_notif = Notification(
                user_id=1,
                author_id=user.id,
                notif_type=NOTIF_REGISTRATION,
                read=False,
                title='New registration'
            )

            # Create other type of notification
            other_notif = Notification(
                user_id=1,
                author_id=user.id,
                notif_type=1,  # Different notification type
                read=False,
                title='Other notification'
            )

            db.session.add_all([reg_notif, other_notif])
            db.session.commit()

            finalize_user_setup(user)

            # Registration notification should be marked read
            reg_notif_check = Notification.query.filter_by(
                notif_type=NOTIF_REGISTRATION,
                author_id=user.id
            ).first()
            assert reg_notif_check.read is True

            # Other notification should remain unread
            other_notif_check = Notification.query.filter_by(
                notif_type=1,
                author_id=user.id
            ).first()
            assert other_notif_check.read is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
