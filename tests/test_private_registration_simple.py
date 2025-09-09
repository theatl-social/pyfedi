"""
Simple unit tests for private registration functionality
These tests avoid full Flask app initialization to prevent configuration issues
"""

import hmac
import ipaddress
import unittest
from unittest.mock import MagicMock, patch


class TestSecurityFunctions(unittest.TestCase):
    """Test security utility functions"""

    @patch("app.api.admin.security.get_private_registration_secret")
    def test_validate_registration_secret_success(self, mock_get_secret):
        """Test successful secret validation"""
        from app.api.admin.security import validate_registration_secret

        mock_get_secret.return_value = "test_secret_123"
        result = validate_registration_secret("test_secret_123")
        self.assertTrue(result)

    @patch("app.api.admin.security.get_private_registration_secret")
    def test_validate_registration_secret_failure(self, mock_get_secret):
        """Test failed secret validation"""
        from app.api.admin.security import validate_registration_secret

        mock_get_secret.return_value = "correct_secret"
        result = validate_registration_secret("wrong_secret")
        self.assertFalse(result)

    @patch("app.api.admin.security.get_private_registration_secret")
    def test_validate_registration_secret_empty(self, mock_get_secret):
        """Test empty secret validation"""
        from app.api.admin.security import validate_registration_secret

        mock_get_secret.return_value = ""
        result = validate_registration_secret("any_secret")
        self.assertFalse(result)

    @patch("app.api.admin.security.get_private_registration_allowed_ips")
    def test_ip_whitelist_validation_allowed(self, mock_get_ips):
        """Test IP whitelist allows valid IP"""
        from app.api.admin.security import is_ip_whitelisted

        mock_get_ips.return_value = ["192.168.1.0/24", "10.0.0.0/8"]
        result = is_ip_whitelisted("192.168.1.100")
        self.assertTrue(result)

    @patch("app.api.admin.security.get_private_registration_allowed_ips")
    def test_ip_whitelist_validation_denied(self, mock_get_ips):
        """Test IP whitelist denies invalid IP"""
        from app.api.admin.security import is_ip_whitelisted

        mock_get_ips.return_value = ["192.168.1.0/24"]
        result = is_ip_whitelisted("10.0.0.1")
        self.assertFalse(result)

    @patch("app.api.admin.security.get_private_registration_allowed_ips")
    def test_ip_whitelist_no_restrictions(self, mock_get_ips):
        """Test IP whitelist allows when no restrictions configured"""
        from app.api.admin.security import is_ip_whitelisted

        mock_get_ips.return_value = []
        result = is_ip_whitelisted("1.2.3.4")
        self.assertTrue(result)

    def test_generate_secure_password(self):
        """Test secure password generation"""
        from app.api.admin.security import generate_secure_password

        password = generate_secure_password(16)
        self.assertIsInstance(password, str)
        self.assertGreater(len(password), 10)  # URL-safe base64 is longer than input

    def test_hmac_compare_digest_works(self):
        """Test that hmac.compare_digest works as expected"""
        secret1 = "test_secret_123"
        secret2 = "test_secret_123"
        secret3 = "different_secret"

        self.assertTrue(hmac.compare_digest(secret1, secret2))
        self.assertFalse(hmac.compare_digest(secret1, secret3))


class TestPrivateRegistrationLogic(unittest.TestCase):
    """Test private registration logic functions"""

    @patch("app.api.admin.private_registration.User")
    def test_validate_user_availability_success(self, mock_user):
        """Test user availability validation when available"""
        from app.api.admin.private_registration import validate_user_availability

        # Mock that both username and email are available
        mock_user.query.filter_by.return_value.first.return_value = None

        result = validate_user_availability("newuser", "new@example.com")

        self.assertTrue(result["username_available"])
        self.assertTrue(result["email_available"])
        self.assertEqual(len(result["validation_errors"]), 0)

    @patch("app.api.admin.private_registration.User")
    @patch("app.api.admin.private_registration.generate_username_suggestions")
    def test_validate_user_availability_username_taken(
        self, mock_suggestions, mock_user
    ):
        """Test user availability validation when username is taken"""
        from app.api.admin.private_registration import validate_user_availability

        # Mock existing user for username check
        mock_existing_user = MagicMock()
        mock_user.query.filter_by.side_effect = [
            MagicMock(
                first=MagicMock(return_value=mock_existing_user)
            ),  # username taken
            MagicMock(first=MagicMock(return_value=None)),  # email available
        ]
        mock_suggestions.return_value = ["testuser1", "testuser2"]

        result = validate_user_availability("testuser", "test@example.com")

        self.assertFalse(result["username_available"])
        self.assertTrue(result["email_available"])
        self.assertIn("username", result["validation_errors"])
        self.assertEqual(result["username_suggestions"], ["testuser1", "testuser2"])

    def test_input_sanitization(self):
        """Test input sanitization"""
        from app.api.admin.security import sanitize_user_input

        dirty_data = {
            "username": '  <script>alert("xss")</script>testuser  ',
            "email": "test@example.com",
            "bio": "My bio with <b>html</b> tags",
        }

        clean_data = sanitize_user_input(dirty_data)

        self.assertNotIn("<script>", clean_data["username"])
        self.assertNotIn("<b>", clean_data["bio"])
        self.assertEqual(clean_data["email"], "test@example.com")  # Email unchanged


if __name__ == "__main__":
    unittest.main()
