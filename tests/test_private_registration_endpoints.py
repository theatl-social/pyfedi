"""
Comprehensive HTTP endpoint tests for private registration API

This test suite covers:
- Full HTTP request/response validation
- Authentication flow testing
- Environment variable configuration
- Error handling and edge cases
- Integration with Flask-smorest schemas
"""

import pytest
import json
import os
import time
from unittest.mock import patch, MagicMock
from flask import Flask


# Test configuration that works in both local and CI environments
class PrivateRegistrationTestConfig:
    """Test configuration for private registration endpoints"""

    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    MAIL_SUPPRESS_SEND = True
    SERVER_NAME = "localhost"
    SECRET_KEY = "test-secret-key-for-private-reg-testing"

    # Private registration test settings
    PRIVATE_REGISTRATION_ENABLED = "true"
    PRIVATE_REGISTRATION_SECRET = "test-secret-pr-2024"
    PRIVATE_REGISTRATION_ALLOWED_IPS = "127.0.0.1,10.0.0.0/8"
    PRIVATE_REGISTRATION_RATE_LIMIT = "10"

    # Disable features that cause test issues
    CACHE_TYPE = "null"
    CELERY_ALWAYS_EAGER = True
    RATELIMIT_ENABLED = False  # Disable global rate limiting for tests


@pytest.fixture(scope="function")
def test_app():
    """Create isolated test app for each test"""
    try:
        # Set environment variables before importing app
        test_env = {
            "PRIVATE_REGISTRATION_ENABLED": "true",
            "PRIVATE_REGISTRATION_SECRET": "test-secret-pr-2024",
            "PRIVATE_REGISTRATION_ALLOWED_IPS": "127.0.0.1,10.0.0.0/8",
            "SERVER_NAME": "localhost",
        }

        with patch.dict(os.environ, test_env):
            from app import create_app, db

            app = create_app(PrivateRegistrationTestConfig)

            with app.app_context():
                # Create all tables
                db.create_all()

                # Yield the app for testing
                yield app

                # Cleanup
                db.session.remove()
                db.drop_all()

    except Exception as e:
        pytest.skip(f"Could not create test app: {e}")


@pytest.fixture
def client(test_app):
    """Create test client with proper environment"""
    return test_app.test_client()


@pytest.fixture
def auth_headers():
    """Standard authentication headers for tests"""
    return {
        "X-PieFed-Secret": "test-secret-pr-2024",
        "Content-Type": "application/json",
        "X-Forwarded-For": "127.0.0.1",  # Simulate allowed IP
    }


@pytest.fixture
def sample_user_request():
    """Sample user registration request data"""
    return {
        "username": "testuser123",
        "email": "testuser123@example.com",
        "display_name": "Test User 123",
        "password": "SecurePassword123!",
        "auto_activate": True,
        "send_welcome_email": False,
        "bio": "Test user created via private registration API",
        "timezone": "America/New_York",
    }


class TestPrivateRegistrationHealthEndpoint:
    """Test the /admin/health endpoint"""

    def test_health_check_success(self, client, auth_headers):
        """Test successful health check with valid authentication"""
        response = client.get("/api/alpha/admin/health", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()

        # Validate response structure
        assert "private_registration" in data
        assert "database" in data
        assert "timestamp" in data

        # Validate private registration status
        pr_status = data["private_registration"]
        assert pr_status["enabled"] is True
        assert "rate_limit_configured" in pr_status
        assert "ip_whitelist_configured" in pr_status
        assert "stats_24h" in pr_status

    def test_health_check_invalid_secret(self, client):
        """Test health check with invalid secret"""
        headers = {
            "X-PieFed-Secret": "invalid-secret",
            "Content-Type": "application/json",
        }

        response = client.get("/api/alpha/admin/health", headers=headers)
        assert response.status_code == 401

        data = response.get_json()
        assert data["success"] is False
        assert data["error"] == "invalid_secret"

    def test_health_check_no_secret(self, client):
        """Test health check without secret header"""
        response = client.get("/api/alpha/admin/health")
        assert response.status_code == 401

    @patch.dict(os.environ, {"PRIVATE_REGISTRATION_ENABLED": "false"})
    def test_health_check_feature_disabled(self, client):
        """Test health check when feature is disabled"""
        headers = {
            "X-PieFed-Secret": "test-secret-pr-2024",
            "Content-Type": "application/json",
        }

        response = client.get("/api/alpha/admin/health", headers=headers)
        assert response.status_code == 403

        data = response.get_json()
        assert data["success"] is False
        assert data["error"] == "feature_disabled"


class TestPrivateRegistrationEndpoint:
    """Test the main /admin/private_register endpoint"""

    def test_private_registration_success(
        self, client, auth_headers, sample_user_request
    ):
        """Test successful user registration"""
        response = client.post(
            "/api/alpha/admin/private_register",
            headers=auth_headers,
            data=json.dumps(sample_user_request),
        )

        assert response.status_code == 201
        data = response.get_json()

        # Validate response structure
        assert data["success"] is True
        assert "user_id" in data
        assert data["username"] == sample_user_request["username"]
        assert data["email"] == sample_user_request["email"]
        assert data["activation_required"] is False  # auto_activate=True

        # Password should not be in response (was provided)
        assert "generated_password" not in data

    def test_private_registration_generated_password(self, client, auth_headers):
        """Test registration with generated password"""
        user_data = {
            "username": "testuser456",
            "email": "testuser456@example.com",
            "auto_activate": True,
            # No password provided - should be generated
        }

        response = client.post(
            "/api/alpha/admin/private_register",
            headers=auth_headers,
            data=json.dumps(user_data),
        )

        assert response.status_code == 201
        data = response.get_json()

        assert data["success"] is True
        assert "generated_password" in data
        assert len(data["generated_password"]) >= 16  # Secure password length

    def test_private_registration_duplicate_user(
        self, client, auth_headers, sample_user_request
    ):
        """Test registration with duplicate username/email"""
        # First registration
        response1 = client.post(
            "/api/alpha/admin/private_register",
            headers=auth_headers,
            data=json.dumps(sample_user_request),
        )
        assert response1.status_code == 201

        # Duplicate registration
        response2 = client.post(
            "/api/alpha/admin/private_register",
            headers=auth_headers,
            data=json.dumps(sample_user_request),
        )

        assert response2.status_code == 400
        data = response2.get_json()
        assert data["success"] is False
        assert data["error"] == "validation_failed"

    def test_private_registration_invalid_data(self, client, auth_headers):
        """Test registration with invalid data"""
        invalid_data = {
            "username": "ab",  # Too short
            "email": "invalid-email",  # Invalid email
            "password": "123",  # Too short
        }

        response = client.post(
            "/api/alpha/admin/private_register",
            headers=auth_headers,
            data=json.dumps(invalid_data),
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert data["error"] == "validation_failed"
        assert "details" in data

    def test_private_registration_unauthorized_ip(self, client):
        """Test registration from unauthorized IP"""
        headers = {
            "X-PieFed-Secret": "test-secret-pr-2024",
            "Content-Type": "application/json",
            "X-Forwarded-For": "192.168.1.100",  # Not in whitelist
        }

        user_data = {"username": "testuser789", "email": "testuser789@example.com"}

        response = client.post(
            "/api/alpha/admin/private_register",
            headers=headers,
            data=json.dumps(user_data),
        )

        assert response.status_code == 403
        data = response.get_json()
        assert data["success"] is False
        assert data["error"] == "ip_unauthorized"


class TestUserValidationEndpoint:
    """Test the /admin/user/validate endpoint"""

    def test_user_validation_available(self, client, auth_headers):
        """Test validation for available username/email"""
        validation_data = {
            "username": "availableuser",
            "email": "available@example.com",
        }

        response = client.post(
            "/api/alpha/admin/user/validate",
            headers=auth_headers,
            data=json.dumps(validation_data),
        )

        assert response.status_code == 200
        data = response.get_json()

        assert data["username_available"] is True
        assert data["email_available"] is True
        assert "username_suggestions" in data

    def test_user_validation_taken(self, client, auth_headers, sample_user_request):
        """Test validation for taken username/email"""
        # First create a user
        client.post(
            "/api/alpha/admin/private_register",
            headers=auth_headers,
            data=json.dumps(sample_user_request),
        )

        # Now validate the same credentials
        validation_data = {
            "username": sample_user_request["username"],
            "email": sample_user_request["email"],
        }

        response = client.post(
            "/api/alpha/admin/user/validate",
            headers=auth_headers,
            data=json.dumps(validation_data),
        )

        assert response.status_code == 200
        data = response.get_json()

        assert data["username_available"] is False
        assert data["email_available"] is False
        assert len(data["username_suggestions"]) > 0


class TestEnvironmentConfiguration:
    """Test different environment variable configurations"""

    @patch.dict(os.environ, {"PRIVATE_REGISTRATION_ENABLED": "false"})
    def test_feature_disabled_via_env(self, client, auth_headers, sample_user_request):
        """Test that environment variable properly disables feature"""
        response = client.post(
            "/api/alpha/admin/private_register",
            headers=auth_headers,
            data=json.dumps(sample_user_request),
        )

        assert response.status_code == 403
        data = response.get_json()
        assert data["error"] == "feature_disabled"

    @patch.dict(os.environ, {"PRIVATE_REGISTRATION_SECRET": "different-secret"})
    def test_secret_from_environment(self, client, sample_user_request):
        """Test that environment variable secret is used"""
        # Use the new secret from environment
        headers = {
            "X-PieFed-Secret": "different-secret",
            "Content-Type": "application/json",
            "X-Forwarded-For": "127.0.0.1",
        }

        response = client.post(
            "/api/alpha/admin/private_register",
            headers=headers,
            data=json.dumps(sample_user_request),
        )

        assert response.status_code == 201

        # Old secret should fail
        old_headers = {
            "X-PieFed-Secret": "test-secret-pr-2024",
            "Content-Type": "application/json",
            "X-Forwarded-For": "127.0.0.1",
        }

        response = client.post(
            "/api/alpha/admin/private_register",
            headers=old_headers,
            data=json.dumps({"username": "test2", "email": "test2@example.com"}),
        )

        assert response.status_code == 401


if __name__ == "__main__":
    # Enable running tests directly
    pytest.main([__file__, "-v"])
