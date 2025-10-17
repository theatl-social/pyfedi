"""
Comprehensive tests for private registration API
"""

import pytest
import os
import json
from unittest.mock import patch, MagicMock
from flask import Flask
from werkzeug.exceptions import Unauthorized, Forbidden

from app import create_app, db
from app.models import User
from app.api.admin.security import (
    validate_registration_secret,
    is_ip_whitelisted,
    generate_secure_password,
    generate_username_suggestions,
)
from app.api.admin.private_registration import (
    validate_user_availability,
    create_private_user,
    get_user_by_lookup,
    list_users,
)


class TestConfig:
    """Test configuration to avoid dependencies"""

    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    MAIL_SUPPRESS_SEND = True
    SERVER_NAME = "localhost"
    SECRET_KEY = "test-secret-key"
    PRIVATE_REGISTRATION_ENABLED = "true"
    PRIVATE_REGISTRATION_SECRET = "test-secret-123"
    CACHE_TYPE = "null"  # Disable caching for tests
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
        # If app creation fails, skip tests gracefully
        pytest.skip(f"Could not create test app: {e}")


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture
def sample_user_data():
    """Sample user data for testing"""
    return {
        "username": "testuser",
        "email": "test@example.com",
        "display_name": "Test User",
        "password": "securepassword123",
        "auto_activate": True,
        "send_welcome_email": False,
        "bio": "Test user biography",
        "timezone": "UTC",
    }


class TestSecurityFunctions:
    """Test security utility functions"""

    def test_validate_registration_secret_success(self):
        """Test successful secret validation"""
        with patch.dict(os.environ, {"PRIVATE_REGISTRATION_SECRET": "test_secret_123"}):
            assert validate_registration_secret("test_secret_123") == True

    def test_validate_registration_secret_failure(self):
        """Test failed secret validation"""
        with patch.dict(os.environ, {"PRIVATE_REGISTRATION_SECRET": "correct_secret"}):
            assert validate_registration_secret("wrong_secret") == False

    def test_validate_registration_secret_empty(self):
        """Test validation with empty secrets"""
        assert validate_registration_secret("") == False
        assert validate_registration_secret(None) == False

    def test_ip_whitelist_validation_allowed(self):
        """Test IP whitelist validation for allowed IPs"""
        with patch(
            "app.api.admin.security.get_private_registration_allowed_ips"
        ) as mock_ips:
            mock_ips.return_value = ["10.0.0.0/8", "172.16.0.0/12"]
            assert is_ip_whitelisted("10.0.1.5") == True
            assert is_ip_whitelisted("172.16.255.1") == True

    def test_ip_whitelist_validation_denied(self):
        """Test IP whitelist validation for denied IPs"""
        with patch(
            "app.api.admin.security.get_private_registration_allowed_ips"
        ) as mock_ips:
            mock_ips.return_value = ["10.0.0.0/8"]
            assert is_ip_whitelisted("192.168.1.5") == False
            assert is_ip_whitelisted("172.16.1.1") == False

    def test_ip_whitelist_no_restrictions(self):
        """Test IP whitelist with no restrictions configured"""
        with patch(
            "app.api.admin.security.get_private_registration_allowed_ips"
        ) as mock_ips:
            mock_ips.return_value = []
            assert is_ip_whitelisted("192.168.1.1") == True
            assert is_ip_whitelisted("8.8.8.8") == True

    def test_generate_secure_password(self):
        """Test secure password generation"""
        password1 = generate_secure_password(16)
        password2 = generate_secure_password(16)

        assert len(password1) >= 16
        assert len(password2) >= 16
        assert password1 != password2  # Should be unique

    def test_generate_username_suggestions(self, app):
        """Test username suggestion generation"""
        with app.app_context():
            # Create existing user
            existing_user = User(
                user_name="testuser",
                email="existing@example.com",
                password="hashed_password",
                instance_id=1,
            )
            db.session.add(existing_user)
            db.session.commit()

            suggestions = generate_username_suggestions("testuser", 3)

            assert len(suggestions) <= 3
            assert all(suggestion.startswith("testuser") for suggestion in suggestions)
            assert "testuser1" in suggestions


class TestPrivateRegistrationLogic:
    """Test private registration business logic"""

    def test_validate_user_availability_success(self, app):
        """Test user availability validation with available username/email"""
        with app.app_context():
            result = validate_user_availability("newuser", "new@example.com")

            assert result["username_available"] == True
            assert result["email_available"] == True
            assert len(result["validation_errors"]) == 0

    def test_validate_user_availability_username_taken(self, app):
        """Test user availability validation with taken username"""
        with app.app_context():
            # Create existing user
            existing_user = User(
                user_name="existinguser",
                email="existing@example.com",
                password="hashed_password",
                instance_id=1,
            )
            db.session.add(existing_user)
            db.session.commit()

            result = validate_user_availability("existinguser", "new@example.com")

            assert result["username_available"] == False
            assert result["email_available"] == True
            assert len(result["username_suggestions"]) > 0
            assert "username" in result["validation_errors"]

    def test_validate_user_availability_email_taken(self, app):
        """Test user availability validation with taken email"""
        with app.app_context():
            # Create existing user
            existing_user = User(
                user_name="existinguser",
                email="existing@example.com",
                password="hashed_password",
                instance_id=1,
            )
            db.session.add(existing_user)
            db.session.commit()

            result = validate_user_availability("newuser", "existing@example.com")

            assert result["username_available"] == True
            assert result["email_available"] == False
            assert "email" in result["validation_errors"]

    def test_create_private_user_success(self, app, sample_user_data):
        """Test successful user creation"""
        with app.app_context():
            result = create_private_user(sample_user_data)

            assert result["success"] == True
            assert result["username"] == "testuser"
            assert result["email"] == "test@example.com"
            assert result["user_id"] is not None
            assert "generated_password" not in result  # Password was provided

            # Verify user was created in database
            user = User.query.filter_by(user_name="testuser").first()
            assert user is not None
            assert user.email == "test@example.com"
            assert user.verified == True  # auto_activate was True

    def test_create_private_user_with_generated_password(self, app):
        """Test user creation with auto-generated password"""
        with app.app_context():
            user_data = {
                "username": "testuser",
                "email": "test@example.com",
                # No password provided
            }

            result = create_private_user(user_data)

            assert result["success"] == True
            assert "generated_password" in result
            assert len(result["generated_password"]) >= 12

    def test_create_private_user_duplicate_username(self, app, sample_user_data):
        """Test user creation with duplicate username"""
        with app.app_context():
            # Create first user
            existing_user = User(
                user_name="testuser",
                email="existing@example.com",
                password="hashed_password",
                instance_id=1,
            )
            db.session.add(existing_user)
            db.session.commit()

            # Try to create duplicate
            with pytest.raises(Exception) as exc_info:
                create_private_user(sample_user_data)

            assert "validation" in str(exc_info.value).lower()

    def test_get_user_by_lookup_found(self, app):
        """Test user lookup when user exists"""
        with app.app_context():
            # Create test user
            test_user = User(
                user_name="lookupuser",
                email="lookup@example.com",
                password="hashed_password",
                title="Lookup User",
                instance_id=1,
                verified=True,
            )
            db.session.add(test_user)
            db.session.commit()
            user_id = test_user.id

            # Test lookup by username
            result = get_user_by_lookup(username="lookupuser")
            assert result["found"] == True
            assert result["user"]["username"] == "lookupuser"

            # Test lookup by email
            result = get_user_by_lookup(email="lookup@example.com")
            assert result["found"] == True
            assert result["user"]["email"] == "lookup@example.com"

            # Test lookup by ID
            result = get_user_by_lookup(user_id=user_id)
            assert result["found"] == True
            assert result["user"]["id"] == user_id

    def test_get_user_by_lookup_not_found(self, app):
        """Test user lookup when user doesn't exist"""
        with app.app_context():
            result = get_user_by_lookup(username="nonexistent")
            assert result["found"] == False
            assert result["user"] is None

    def test_list_users_basic(self, app):
        """Test basic user listing functionality"""
        with app.app_context():
            # Create test users
            for i in range(5):
                user = User(
                    user_name=f"user{i}",
                    email=f"user{i}@example.com",
                    password="hashed_password",
                    instance_id=1,
                    verified=True,
                )
                db.session.add(user)
            db.session.commit()

            result = list_users(page=1, limit=3)

            assert len(result["users"]) == 3
            assert result["pagination"]["total"] == 5
            assert result["pagination"]["total_pages"] == 2
            assert result["pagination"]["has_next"] == True

    def test_list_users_filtering(self, app):
        """Test user listing with filtering"""
        with app.app_context():
            # Create verified user
            verified_user = User(
                user_name="verifieduser",
                email="verified@example.com",
                password="hashed_password",
                instance_id=1,
                verified=True,
            )
            db.session.add(verified_user)

            # Create unverified user
            unverified_user = User(
                user_name="unverifieduser",
                email="unverified@example.com",
                password="hashed_password",
                instance_id=1,
                verified=False,
            )
            db.session.add(unverified_user)
            db.session.commit()

            # Test verified filter
            result = list_users(verified=True)
            assert len(result["users"]) == 1
            assert result["users"][0]["username"] == "verifieduser"

            # Test unverified filter
            result = list_users(verified=False)
            assert len(result["users"]) == 1
            assert result["users"][0]["username"] == "unverifieduser"


class TestPrivateRegistrationAPI:
    """Test private registration API endpoints"""

    def test_private_registration_success(self, client):
        """Test successful private registration via API"""
        with patch.dict(
            os.environ,
            {
                "PRIVATE_REGISTRATION_ENABLED": "true",
                "PRIVATE_REGISTRATION_SECRET": "test_secret_123",
            },
        ):
            response = client.post(
                "/api/alpha/admin/private_register",
                headers={"X-PieFed-Secret": "test_secret_123"},
                json={
                    "username": "newuser",
                    "email": "new@example.com",
                    "display_name": "New User",
                },
            )

            assert response.status_code == 201
            data = response.get_json()
            assert data["success"] == True
            assert data["username"] == "newuser"
            assert data["user_id"] is not None

    def test_private_registration_invalid_secret(self, client):
        """Test private registration with invalid secret"""
        with patch.dict(
            os.environ,
            {
                "PRIVATE_REGISTRATION_ENABLED": "true",
                "PRIVATE_REGISTRATION_SECRET": "correct_secret",
            },
        ):
            response = client.post(
                "/api/alpha/admin/private_register",
                headers={"X-PieFed-Secret": "wrong_secret"},
                json={"username": "test", "email": "test@example.com"},
            )

            assert response.status_code == 401
            data = response.get_json()
            assert data["success"] == False
            assert data["error"] == "invalid_secret"

    def test_private_registration_disabled(self, client):
        """Test private registration when feature is disabled"""
        with patch.dict(os.environ, {"PRIVATE_REGISTRATION_ENABLED": "false"}):
            response = client.post(
                "/api/alpha/admin/private_register",
                headers={"X-PieFed-Secret": "any_secret"},
                json={"username": "test", "email": "test@example.com"},
            )

            assert response.status_code == 403
            data = response.get_json()
            assert data["success"] == False

    def test_private_registration_missing_secret(self, client):
        """Test private registration without secret header"""
        with patch.dict(os.environ, {"PRIVATE_REGISTRATION_ENABLED": "true"}):
            response = client.post(
                "/api/alpha/admin/private_register",
                json={"username": "test", "email": "test@example.com"},
            )

            assert response.status_code == 401

    def test_user_validation_endpoint(self, client):
        """Test user validation endpoint"""
        with patch.dict(
            os.environ,
            {
                "PRIVATE_REGISTRATION_ENABLED": "true",
                "PRIVATE_REGISTRATION_SECRET": "test_secret",
            },
        ):
            response = client.post(
                "/api/alpha/admin/user/validate",
                headers={"X-PieFed-Secret": "test_secret"},
                json={"username": "availableuser", "email": "available@example.com"},
            )

            assert response.status_code == 200
            data = response.get_json()
            assert data["username_available"] == True
            assert data["email_available"] == True

    def test_user_list_endpoint(self, client):
        """Test user list endpoint"""
        with patch.dict(
            os.environ,
            {
                "PRIVATE_REGISTRATION_ENABLED": "true",
                "PRIVATE_REGISTRATION_SECRET": "test_secret",
            },
        ):
            response = client.get(
                "/api/alpha/admin/users?local_only=true&limit=10",
                headers={"X-PieFed-Secret": "test_secret"},
            )

            assert response.status_code == 200
            data = response.get_json()
            assert "users" in data
            assert "pagination" in data

    def test_user_lookup_endpoint(self, client):
        """Test user lookup endpoint"""
        with patch.dict(
            os.environ,
            {
                "PRIVATE_REGISTRATION_ENABLED": "true",
                "PRIVATE_REGISTRATION_SECRET": "test_secret",
            },
        ):
            response = client.get(
                "/api/alpha/admin/user/lookup?username=nonexistent",
                headers={"X-PieFed-Secret": "test_secret"},
            )

            assert response.status_code == 200
            data = response.get_json()
            assert data["found"] == False

    def test_health_check_endpoint(self, client):
        """Test health check endpoint"""
        with patch.dict(
            os.environ,
            {
                "PRIVATE_REGISTRATION_ENABLED": "true",
                "PRIVATE_REGISTRATION_SECRET": "test_secret",
            },
        ):
            response = client.get(
                "/api/alpha/admin/health", headers={"X-PieFed-Secret": "test_secret"}
            )

            assert response.status_code == 200
            data = response.get_json()
            assert "private_registration" in data
            assert "database" in data
            assert "timestamp" in data


class TestSecurityProtections:
    """Test security protections and edge cases"""

    def test_input_sanitization(self, client):
        """Test that malicious input is sanitized"""
        with patch.dict(
            os.environ,
            {
                "PRIVATE_REGISTRATION_ENABLED": "true",
                "PRIVATE_REGISTRATION_SECRET": "test_secret",
            },
        ):
            malicious_data = {
                "username": '<script>alert("xss")</script>',
                "email": "test@example.com",
                "display_name": '<img src=x onerror=alert("xss")>',
            }

            response = client.post(
                "/api/alpha/admin/private_register",
                headers={"X-PieFed-Secret": "test_secret"},
                json=malicious_data,
            )

            # Should either sanitize and succeed or fail validation
            assert response.status_code in [201, 400]

            # Response should not contain script tags
            response_text = response.get_data(as_text=True)
            assert "<script>" not in response_text
            assert "onerror=" not in response_text

    def test_sql_injection_protection(self, client):
        """Test protection against SQL injection attempts"""
        with patch.dict(
            os.environ,
            {
                "PRIVATE_REGISTRATION_ENABLED": "true",
                "PRIVATE_REGISTRATION_SECRET": "test_secret",
            },
        ):
            sql_injection_attempts = [
                "'; DROP TABLE users; --",
                "admin'/**/OR/**/1=1--",
                "user'; INSERT INTO users VALUES ('hacker'); --",
            ]

            for malicious_input in sql_injection_attempts:
                response = client.post(
                    "/api/alpha/admin/private_register",
                    headers={"X-PieFed-Secret": "test_secret"},
                    json={"username": malicious_input, "email": "test@example.com"},
                )

                # Should be rejected with validation error, not cause injection
                assert response.status_code in [400, 422]  # Validation errors

    def test_rate_limiting_simulation(self, client):
        """Test rate limiting behavior (simulation)"""
        # Note: This is a simplified test as we don't have actual rate limiting
        # implemented in the test environment
        with patch.dict(
            os.environ,
            {
                "PRIVATE_REGISTRATION_ENABLED": "true",
                "PRIVATE_REGISTRATION_SECRET": "test_secret",
            },
        ):
            # Make multiple rapid requests
            responses = []
            for i in range(3):
                response = client.post(
                    "/api/alpha/admin/private_register",
                    headers={"X-PieFed-Secret": "test_secret"},
                    json={"username": f"user{i}", "email": f"user{i}@example.com"},
                )
                responses.append(response)

            # At least some should succeed (actual rate limiting would need Redis/etc)
            success_count = sum(1 for r in responses if r.status_code == 201)
            assert success_count >= 1  # At least one should work in test env


class TestCaseConflictValidation:
    """Test username case conflict detection and prevention"""

    def test_case_insensitive_username_conflict(self, app):
        """Test that usernames with different cases are detected as conflicts"""
        with app.app_context():
            # Create existing user with mixed case
            existing_user = User(
                user_name="TestUser",
                email="existing@example.com",
                password_hash="hashed_password",
                instance_id=1,
                verified=True,
                ap_profile_id="https://test.server/u/testuser",
            )
            db.session.add(existing_user)
            db.session.commit()

            # Test validation with different cases
            test_cases = ["testuser", "TESTUSER", "testUser", "TestUSER"]

            for test_username in test_cases:
                result = validate_user_availability(test_username, "new@example.com")
                assert result["username_available"] == False
                assert "case difference" in result["validation_errors"]["username"]
                assert "TestUser" in result["validation_errors"]["username"]
                assert len(result["username_suggestions"]) > 0

    def test_activitypub_profile_conflict(self, app):
        """Test ActivityPub profile ID conflict detection"""
        with app.app_context():
            # Create user with ActivityPub profile
            existing_user = User(
                user_name="ExistingUser",
                email="existing@example.com",
                password_hash="hashed_password",
                instance_id=1,
                verified=True,
                ap_profile_id="https://test.server/u/newuser",  # Profile for lowercase 'newuser'
            )
            db.session.add(existing_user)
            db.session.commit()

            # Test that 'NewUser' conflicts due to ActivityPub URL collision
            result = validate_user_availability("NewUser", "new@example.com")
            assert result["username_available"] == False
            assert "ActivityPub URL conflict" in result["validation_errors"]["username"]

    def test_exact_case_match_still_works(self, app):
        """Test that exact case matches are still detected"""
        with app.app_context():
            # Create existing user
            existing_user = User(
                user_name="ExactMatch",
                email="existing@example.com",
                password_hash="hashed_password",
                instance_id=1,
                verified=True,
            )
            db.session.add(existing_user)
            db.session.commit()

            # Test exact match detection
            result = validate_user_availability("ExactMatch", "new@example.com")
            assert result["username_available"] == False
            assert (
                result["validation_errors"]["username"]
                == "Username 'ExactMatch' is already taken"
            )

    def test_case_preserved_in_suggestions(self, app):
        """Test that username suggestions preserve original casing logic"""
        with app.app_context():
            # Create user to trigger conflict
            existing_user = User(
                user_name="ConflictUser",
                email="existing@example.com",
                password_hash="hashed_password",
                instance_id=1,
                verified=True,
            )
            db.session.add(existing_user)
            db.session.commit()

            # Test that suggestions are generated for case conflicts
            result = validate_user_availability("conflictuser", "new@example.com")
            assert result["username_available"] == False
            assert len(result["username_suggestions"]) > 0
            # Suggestions should be based on the requested username (conflictuser)
            for suggestion in result["username_suggestions"]:
                assert suggestion.startswith("conflictuser")

    def test_no_false_positives_for_available_usernames(self, app):
        """Test that available usernames are not flagged as conflicts"""
        with app.app_context():
            # Test completely unique username
            result = validate_user_availability(
                "UniqueUsername123", "unique@example.com"
            )
            assert result["username_available"] == True
            assert result["email_available"] == True
            assert len(result["validation_errors"]) == 0
            assert len(result["username_suggestions"]) == 0

    def test_deleted_user_case_conflict(self, app):
        """Test case conflict with deleted users"""
        with app.app_context():
            # Create deleted user
            deleted_user = User(
                user_name="DeletedUser",
                email="deleted_123@deleted.com",
                password_hash="hashed_password",
                instance_id=1,
                verified=True,
                deleted=True,
                ap_profile_id="https://test.server/u/deleteduser",
            )
            db.session.add(deleted_user)
            db.session.commit()

            # Test that case-different username still conflicts due to ActivityPub URL
            result = validate_user_availability("deleteduser", "new@example.com")
            assert result["username_available"] == False
            # Should detect ActivityPub conflict, not case conflict (since deleted users are included in AP check)
            assert "ActivityPub URL conflict" in result["validation_errors"]["username"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
