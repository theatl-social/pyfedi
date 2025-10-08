"""
Test that private registration properly sets up ActivityPub for new users
"""
import unittest
from unittest.mock import patch, MagicMock, call


class TestPrivateRegistrationActivityPubSetup(unittest.TestCase):
    """Test that private registration calls finalize_user_setup for ActivityPub"""

    @patch('app.api.admin.private_registration.db')
    @patch('app.api.admin.private_registration.User')
    @patch('app.api.admin.private_registration.validate_user_availability')
    @patch('app.api.admin.private_registration.log_registration_attempt')
    @patch('app.api.admin.private_registration.sanitize_user_input')
    @patch('app.utils.finalize_user_setup')
    @patch('app.api.admin.private_registration.current_app')
    def test_create_private_user_calls_finalize_user_setup(
        self, mock_app, mock_finalize, mock_sanitize, mock_log, mock_validate, mock_user_class, mock_db
    ):
        """Test that create_private_user calls finalize_user_setup when auto_activate=True"""
        from app.api.admin.private_registration import create_private_user

        # Setup mocks
        mock_sanitize.return_value = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'testpass123',
            'auto_activate': True
        }

        mock_validate.return_value = {
            'username_available': True,
            'email_available': True,
            'validation_errors': {}
        }

        # Create mock user instance
        mock_user_instance = MagicMock()
        mock_user_instance.id = 123
        mock_user_instance.user_name = 'testuser'
        mock_user_instance.email = 'test@example.com'
        mock_user_class.return_value = mock_user_instance

        # Mock logger
        mock_app.logger = MagicMock()

        # Call the function
        user_data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'testpass123',
            'auto_activate': True  # This should trigger finalize_user_setup
        }

        result = create_private_user(user_data)

        # Verify finalize_user_setup was called with the user instance
        mock_finalize.assert_called_once_with(mock_user_instance)

        # Verify result indicates success
        self.assertEqual(result['success'], True)
        self.assertEqual(result['user_id'], 123)
        self.assertEqual(result['username'], 'testuser')

    @patch('app.api.admin.private_registration.db')
    @patch('app.api.admin.private_registration.User')
    @patch('app.api.admin.private_registration.validate_user_availability')
    @patch('app.api.admin.private_registration.log_registration_attempt')
    @patch('app.api.admin.private_registration.sanitize_user_input')
    @patch('app.utils.finalize_user_setup')
    @patch('app.api.admin.private_registration.current_app')
    def test_create_private_user_skips_finalize_when_not_activated(
        self, mock_app, mock_finalize, mock_sanitize, mock_log, mock_validate, mock_user_class, mock_db
    ):
        """Test that create_private_user does NOT call finalize_user_setup when auto_activate=False"""
        from app.api.admin.private_registration import create_private_user

        # Setup mocks
        mock_sanitize.return_value = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'testpass123',
            'auto_activate': False
        }

        mock_validate.return_value = {
            'username_available': True,
            'email_available': True,
            'validation_errors': {}
        }

        # Create mock user instance
        mock_user_instance = MagicMock()
        mock_user_instance.id = 124
        mock_user_instance.user_name = 'testuser2'
        mock_user_instance.email = 'test2@example.com'
        mock_user_class.return_value = mock_user_instance

        # Mock logger
        mock_app.logger = MagicMock()

        # Call the function
        user_data = {
            'username': 'testuser2',
            'email': 'test2@example.com',
            'password': 'testpass123',
            'auto_activate': False  # This should NOT trigger finalize_user_setup
        }

        result = create_private_user(user_data)

        # Verify finalize_user_setup was NOT called
        mock_finalize.assert_not_called()

        # Verify logger message about awaiting activation
        mock_app.logger.info.assert_any_call('User 124 created but not finalized - awaiting activation')

        # Verify result indicates success
        self.assertEqual(result['success'], True)
        self.assertEqual(result['activation_required'], True)


class TestFinalizeUserSetupBehavior(unittest.TestCase):
    """Test that finalize_user_setup properly configures ActivityPub fields"""

    @patch('app.utils.plugins')
    @patch('app.utils.db')
    @patch('app.utils.current_app')
    @patch('app.utils.Notification')
    @patch('app.activitypub.signature.RsaKeys')
    def test_finalize_user_setup_sets_activitypub_fields(
        self, mock_rsa, mock_notification, mock_app, mock_db, mock_plugins
    ):
        """Test that finalize_user_setup generates keypair and sets ActivityPub URLs"""
        from app.utils import finalize_user_setup
        from app.models import utcnow

        # Setup mocks
        mock_app.config = {'SERVER_NAME': 'example.com'}
        mock_rsa.generate_keypair.return_value = ('private_key_data', 'public_key_data')
        mock_plugins.fire_hook.return_value = MagicMock()

        # Create mock user without ActivityPub setup
        mock_user = MagicMock()
        mock_user.user_name = 'testuser'
        mock_user.private_key = None
        mock_user.public_key = None
        mock_user.ap_profile_id = None
        mock_user.id = 100

        # Mock notification query
        mock_notification.query.filter_by.return_value = []

        # Call finalize_user_setup
        finalize_user_setup(mock_user)

        # Verify ActivityPub keypair was generated
        self.assertEqual(mock_user.private_key, 'private_key_data')
        self.assertEqual(mock_user.public_key, 'public_key_data')

        # Verify ActivityPub URLs were set
        self.assertEqual(mock_user.ap_profile_id, 'https://example.com/u/testuser')
        self.assertEqual(mock_user.ap_public_url, 'https://example.com/u/testuser')
        self.assertEqual(mock_user.ap_inbox_url, 'https://example.com/u/testuser/inbox')

        # Verify user was marked as verified
        self.assertTrue(mock_user.verified)

        # Verify plugin hook was fired
        mock_plugins.fire_hook.assert_called_once_with('new_user', mock_user)

        # Verify db.session.commit was called
        self.assertEqual(mock_db.session.commit.call_count, 2)

    @patch('app.utils.plugins')
    @patch('app.utils.db')
    @patch('app.utils.current_app')
    @patch('app.utils.Notification')
    def test_finalize_user_setup_preserves_existing_keys(
        self, mock_notification, mock_app, mock_db, mock_plugins
    ):
        """Test that finalize_user_setup doesn't overwrite existing keys"""
        from app.utils import finalize_user_setup

        # Setup mocks
        mock_app.config = {'SERVER_NAME': 'example.com'}
        mock_plugins.fire_hook.return_value = MagicMock()

        # Create mock user WITH existing ActivityPub setup
        mock_user = MagicMock()
        mock_user.user_name = 'testuser'
        mock_user.private_key = 'existing_private_key'
        mock_user.public_key = 'existing_public_key'
        mock_user.ap_profile_id = 'https://example.com/u/testuser'
        mock_user.id = 101

        # Mock notification query
        mock_notification.query.filter_by.return_value = []

        # Call finalize_user_setup
        finalize_user_setup(mock_user)

        # Verify existing keys were NOT overwritten
        self.assertEqual(mock_user.private_key, 'existing_private_key')
        self.assertEqual(mock_user.public_key, 'existing_public_key')
        self.assertEqual(mock_user.ap_profile_id, 'https://example.com/u/testuser')


if __name__ == '__main__':
    unittest.main()
