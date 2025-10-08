"""
Simple unit tests for Phase 2 user management functionality
Tests the core user management operations without full Flask app setup
"""
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import os


class TestUserManagementLogic(unittest.TestCase):
    def setUp(self):
        """Set up test Flask app context"""
        os.environ['SERVER_NAME'] = 'test.localhost'
        os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
        os.environ['CACHE_TYPE'] = 'NullCache'
        os.environ['TESTING'] = 'true'

        from app import create_app
        self.app = create_app()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        """Clean up Flask app context"""
        if hasattr(self, 'app_context'):
            self.app_context.pop()

    @patch('app.api.admin.user_management.User')
    @patch('app.api.admin.user_management.db')
    @patch('app.api.admin.user_management.current_app')
    def test_update_user_success(self, mock_app, mock_db, mock_user_class):
        """Test successful user update"""
        from app.api.admin.user_management import update_user
        
        # Mock user
        mock_user = MagicMock()
        mock_user.id = 123
        mock_user_class.query.filter_by.return_value.first.return_value = mock_user
        
        # Mock no email conflicts
        mock_user_class.query.filter.return_value.first.return_value = None
        
        update_data = {
            'display_name': 'Updated Name',
            'bio': 'New bio',
            'email': 'new@example.com'
        }
        
        result = update_user(123, update_data)
        
        self.assertTrue(result['success'])
        self.assertEqual(result['user_id'], 123)
        self.assertIn('display_name', result['updated_fields'])
        self.assertIn('bio', result['updated_fields'])
        self.assertIn('email', result['updated_fields'])

    @patch('app.api.admin.user_management.User')
    def test_update_user_not_found(self, mock_user_class):
        """Test update user when user doesn't exist"""
        from app.api.admin.user_management import update_user
        
        mock_user_class.query.filter_by.return_value.first.return_value = None
        
        with self.assertRaises(ValueError) as context:
            update_user(999, {'display_name': 'Test'})
        
        self.assertIn('not found', str(context.exception))

    @patch('app.api.admin.user_management.User')
    def test_update_user_email_conflict(self, mock_user_class):
        """Test update user with email already in use"""
        from app.api.admin.user_management import update_user
        
        # Mock existing user
        mock_user = MagicMock()
        mock_user.id = 123
        mock_user_class.query.filter_by.return_value.first.return_value = mock_user
        
        # Mock email conflict
        mock_existing = MagicMock()
        mock_user_class.query.filter.return_value.first.return_value = mock_existing
        
        with self.assertRaises(ValueError) as context:
            update_user(123, {'email': 'taken@example.com'})
        
        self.assertIn('already in use', str(context.exception))

    @patch('app.api.admin.user_management.User')
    @patch('app.api.admin.user_management.db')
    @patch('app.api.admin.user_management.utcnow')
    def test_ban_user_success(self, mock_utcnow, mock_db, mock_user_class):
        """Test successful user ban"""
        from app.api.admin.user_management import perform_user_action
        
        mock_time = datetime(2025, 1, 1, 12, 0, 0)
        mock_utcnow.return_value = mock_time
        
        # Mock user
        mock_user = MagicMock()
        mock_user.id = 123
        mock_user.banned = False
        mock_user_class.query.filter_by.return_value.first.return_value = mock_user
        
        result = perform_user_action(123, 'ban', reason='Spam')
        
        self.assertTrue(result['success'])
        self.assertEqual(result['action'], 'ban')
        self.assertEqual(result['user_id'], 123)
        self.assertTrue(mock_user.banned)

    @patch('app.api.admin.user_management.User')
    def test_ban_already_banned_user(self, mock_user_class):
        """Test banning already banned user"""
        from app.api.admin.user_management import perform_user_action
        
        # Mock already banned user
        mock_user = MagicMock()
        mock_user.id = 123
        mock_user.banned = True
        mock_user_class.query.filter_by.return_value.first.return_value = mock_user
        
        with self.assertRaises(ValueError) as context:
            perform_user_action(123, 'ban')
        
        self.assertIn('already banned', str(context.exception))

    @patch('app.api.admin.user_management.User')
    @patch('app.api.admin.user_management.db')
    @patch('app.api.admin.user_management.current_app')
    @patch('app.api.admin.user_management.utcnow')
    def test_disable_user_success(self, mock_utcnow, mock_app, mock_db, mock_user_class):
        """Test successful user disable"""
        from app.api.admin.user_management import perform_user_action
        
        mock_time = datetime(2025, 1, 1, 12, 0, 0)
        mock_utcnow.return_value = mock_time
        
        # Mock user
        mock_user = MagicMock()
        mock_user.id = 123
        mock_user.verified = True
        mock_user_class.query.filter_by.return_value.first.return_value = mock_user
        
        result = perform_user_action(123, 'disable', reason='Policy violation')
        
        self.assertTrue(result['success'])
        self.assertEqual(result['action'], 'disable')
        self.assertFalse(mock_user.verified)

    @patch('app.api.admin.user_management.User')
    @patch('app.api.admin.user_management.db')
    @patch('app.api.admin.user_management.current_app')
    @patch('app.api.admin.user_management.utcnow')
    def test_soft_delete_user(self, mock_utcnow, mock_app, mock_db, mock_user_class):
        """Test soft delete user"""
        from app.api.admin.user_management import perform_user_action
        
        mock_time = datetime(2025, 1, 1, 12, 0, 0)
        mock_utcnow.return_value = mock_time
        
        # Mock user
        mock_user = MagicMock()
        mock_user.id = 123
        mock_user.deleted = False
        mock_user_class.query.filter_by.return_value.first.return_value = mock_user
        
        result = perform_user_action(123, 'delete', reason='GDPR request')
        
        self.assertTrue(result['success'])
        self.assertEqual(result['action'], 'delete')
        self.assertTrue(mock_user.deleted)
        self.assertIn('deleted_123_', mock_user.user_name)
        self.assertIn('deleted_123@deleted.local', mock_user.email)

    def test_bulk_operations_basic(self):
        """Test basic bulk operations logic"""
        from app.api.admin.user_management import bulk_user_operations
        
        # Mock perform_user_action to succeed for all users
        with patch('app.api.admin.user_management.perform_user_action') as mock_action:
            mock_action.return_value = {
                'success': True,
                'message': 'User banned successfully'
            }
            
            result = bulk_user_operations('ban', [1, 2, 3], reason='Spam campaign')
            
            self.assertTrue(result['success'])
            self.assertEqual(result['total_requested'], 3)
            self.assertEqual(result['successful'], 3)
            self.assertEqual(result['failed'], 0)
            self.assertEqual(len(result['results']), 3)

    def test_bulk_operations_partial_failure(self):
        """Test bulk operations with some failures"""
        from app.api.admin.user_management import bulk_user_operations
        
        def mock_action_side_effect(user_id, *args, **kwargs):
            if user_id == 2:
                raise ValueError("User not found")
            return {'success': True, 'message': 'Success'}
        
        with patch('app.api.admin.user_management.perform_user_action') as mock_action:
            mock_action.side_effect = mock_action_side_effect
            
            result = bulk_user_operations('ban', [1, 2, 3])
            
            self.assertFalse(result['success'])  # False due to failures
            self.assertEqual(result['successful'], 2)
            self.assertEqual(result['failed'], 1)
            
            # Check individual results
            failed_result = next(r for r in result['results'] if r['user_id'] == 2)
            self.assertFalse(failed_result['success'])
            self.assertIn('error', failed_result)

    def test_bulk_operations_too_many_users(self):
        """Test bulk operations with too many users"""
        from app.api.admin.user_management import bulk_user_operations
        
        large_user_list = list(range(1, 102))  # 101 users
        
        with self.assertRaises(ValueError) as context:
            bulk_user_operations('ban', large_user_list)
        
        self.assertIn('more than 100', str(context.exception))


class TestUserStatistics(unittest.TestCase):
    """Test user statistics functions"""

    def setUp(self):
        """Set up test Flask app context"""
        os.environ['SERVER_NAME'] = 'test.localhost'
        os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
        os.environ['CACHE_TYPE'] = 'NullCache'
        os.environ['TESTING'] = 'true'

        from app import create_app
        self.app = create_app()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        """Clean up Flask app context"""
        if hasattr(self, 'app_context'):
            self.app_context.pop()

    @patch('app.api.admin.user_management.User')
    @patch('app.api.admin.user_management.utcnow')
    def test_get_user_statistics(self, mock_utcnow, mock_user_class):
        """Test getting user statistics"""
        from app.api.admin.user_management import get_user_statistics

        mock_time = datetime(2025, 1, 1, 12, 0, 0)
        mock_utcnow.return_value = mock_time

        # Mock database queries - need to create separate mock chains
        mock_filter_by = MagicMock()
        mock_filter_by.count.return_value = 100

        mock_filter = MagicMock()
        mock_filter.count.return_value = 25

        mock_user_class.query.filter_by.return_value = mock_filter_by
        mock_user_class.query.filter.return_value = mock_filter

        result = get_user_statistics()

        self.assertIn('total_users', result)
        self.assertIn('local_users', result)
        self.assertIn('active_24h', result)
        self.assertIn('registrations_today', result)
        self.assertIn('timestamp', result)

    @patch('app.api.admin.user_management.User')
    @patch('app.api.admin.user_management.utcnow')
    def test_get_registration_statistics(self, mock_utcnow, mock_user_class):
        """Test getting registration statistics"""
        from app.api.admin.user_management import get_registration_statistics

        mock_time = datetime(2025, 1, 1, 12, 0, 0)
        mock_utcnow.return_value = mock_time

        # Mock database query
        mock_filter = MagicMock()
        mock_filter.count.return_value = 50
        mock_user_class.query.filter.return_value = mock_filter

        result = get_registration_statistics(days=7, include_hourly=True)

        self.assertEqual(result['period_days'], 7)
        self.assertIn('total_registrations', result)
        self.assertIn('daily_breakdown', result)
        self.assertIn('hourly_breakdown', result)
        self.assertEqual(len(result['daily_breakdown']), 8)  # 7 days + today
        self.assertEqual(len(result['hourly_breakdown']), 24)  # 24 hours

    def test_export_user_data_basic(self):
        """Test basic user data export"""
        from app.api.admin.user_management import export_user_data

        # Mock the list_users function from private_registration module
        mock_users_data = [
            {'id': 1, 'username': 'user1', 'email': 'user1@test.com'},
            {'id': 2, 'username': 'user2', 'email': 'user2@test.com'}
        ]

        with patch('app.api.admin.private_registration.list_users') as mock_list:
            mock_list.return_value = {'users': mock_users_data}

            result = export_user_data(format_type='csv')

            self.assertTrue(result['success'])
            self.assertEqual(result['format'], 'csv')
            self.assertEqual(result['total_records'], 2)
            self.assertIn('download_url', result)
            self.assertIn('expires_at', result)


class TestInputValidation(unittest.TestCase):
    """Test input validation and security"""

    def setUp(self):
        """Set up test Flask app context"""
        os.environ['SERVER_NAME'] = 'test.localhost'
        os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
        os.environ['CACHE_TYPE'] = 'NullCache'
        os.environ['TESTING'] = 'true'

        from app import create_app
        self.app = create_app()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        """Clean up Flask app context"""
        if hasattr(self, 'app_context'):
            self.app_context.pop()

    def test_unknown_action_validation(self):
        """Test that unknown actions are rejected"""
        from app.api.admin.user_management import perform_user_action
        
        with patch('app.api.admin.user_management.User') as mock_user_class:
            mock_user = MagicMock()
            mock_user_class.query.filter_by.return_value.first.return_value = mock_user
            
            with self.assertRaises(ValueError) as context:
                perform_user_action(123, 'invalid_action')
            
            self.assertIn('Unknown action', str(context.exception))

    def test_bulk_operation_validation(self):
        """Test bulk operation input validation"""
        from app.api.admin.user_management import bulk_user_operations
        
        # Test empty user list
        with self.assertRaises(ValueError):
            bulk_user_operations('ban', [])
        
        # Test invalid operation
        with patch('app.api.admin.user_management.perform_user_action') as mock_action:
            mock_action.side_effect = ValueError("Unknown action: invalid")
            
            result = bulk_user_operations('invalid', [1])
            self.assertFalse(result['success'])
            self.assertEqual(result['failed'], 1)


if __name__ == '__main__':
    unittest.main()