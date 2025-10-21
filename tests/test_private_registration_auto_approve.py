"""
Test private registration auto-approval workflow.

This test verifies that when a user is created with auto_activate=false,
enabling them later properly calls finalize_user_setup() to generate
ActivityPub keys and profile URLs.

Critical for federation - users must have AP keys to participate in fediverse.
"""

import os

import pytest
from flask import Flask

from app import create_app, db
from app.api.admin.private_registration import create_private_user
from app.api.admin.user_management import perform_user_action
from app.models import User


@pytest.fixture
def app():
    """Create Flask app for testing"""
    os.environ["TESTING"] = "true"
    os.environ["SERVER_NAME"] = "test.local"
    os.environ["SECRET_KEY"] = "test-secret-key"
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

    app = create_app()
    app.config["TESTING"] = True
    app.config["SERVER_NAME"] = "test.local"

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def test_auto_activate_true_immediate_finalization(app):
    """
    Test that auto_activate=true immediately finalizes user with AP keys.

    This is the default behavior - user is ready to use immediately.
    """
    with app.app_context():
        # Create user with auto_activate=true (default)
        result = create_private_user(
            {
                "username": "alice_auto",
                "email": "alice_auto@test.com",
                "display_name": "Alice Auto",
                "password": "TestPassword123",
                "auto_activate": True,  # Default behavior
            }
        )

        assert result["success"] is True
        assert result["activation_required"] is False

        # Verify user is finalized
        user = User.query.filter_by(user_name="alice_auto").first()
        assert user is not None
        assert user.verified is True, "User should be verified immediately"

        # Verify AP keys were generated
        assert user.private_key is not None, "Private key should be generated"
        assert user.public_key is not None, "Public key should be generated"
        assert (
            user.ap_profile_id is not None
        ), "AP profile ID should be set (e.g., https://test.local/u/alice_auto)"
        assert user.ap_public_url is not None, "AP public URL should be set"
        assert user.ap_inbox_url is not None, "AP inbox URL should be set"

        # Verify URLs are correct format
        assert user.ap_profile_id == "https://test.local/u/alice_auto"
        assert user.ap_public_url == "https://test.local/u/alice_auto"
        assert user.ap_inbox_url == "https://test.local/u/alice_auto/inbox"


def test_auto_activate_false_deferred_activation(app):
    """
    Test that auto_activate=false creates user WITHOUT finalization.

    User is created but not ready - awaits admin approval.
    """
    with app.app_context():
        # Create user with auto_activate=false
        result = create_private_user(
            {
                "username": "bob_manual",
                "email": "bob_manual@test.com",
                "display_name": "Bob Manual",
                "password": "TestPassword123",
                "auto_activate": False,  # Manual activation required
            }
        )

        assert result["success"] is True
        assert result["activation_required"] is True, "Activation should be required"

        # Verify user is NOT finalized yet
        user = User.query.filter_by(user_name="bob_manual").first()
        assert user is not None
        assert user.verified is False, "User should NOT be verified yet"

        # Verify AP keys were NOT generated yet
        assert user.private_key is None, "Private key should NOT be generated yet"
        assert user.public_key is None, "Public key should NOT be generated yet"
        assert user.ap_profile_id is None, "AP profile ID should NOT be set yet"


def test_enable_user_finalizes_deferred_user(app):
    """
    CRITICAL TEST: Verify that enabling a deferred user calls finalize_user_setup().

    This is the bug fix - previously enabling would set verified=True but not
    generate AP keys, causing federation issues.
    """
    with app.app_context():
        # Step 1: Create user with auto_activate=false
        result = create_private_user(
            {
                "username": "charlie_deferred",
                "email": "charlie_deferred@test.com",
                "display_name": "Charlie Deferred",
                "password": "TestPassword123",
                "auto_activate": False,
            }
        )

        user_id = result["user_id"]
        user = User.query.get(user_id)

        # Verify initial state (not finalized)
        assert user.verified is False
        assert user.private_key is None
        assert user.ap_profile_id is None

        # Step 2: Admin enables the user
        enable_result = perform_user_action(user_id, "enable")

        assert enable_result["success"] is True
        assert enable_result["action"] == "enable"
        assert (
            "finalized" in enable_result["message"].lower()
        ), "Message should indicate finalization occurred"

        # Step 3: Verify user is NOW finalized with AP keys
        db.session.refresh(user)  # Reload from database

        assert user.verified is True, "User should be verified after enable"

        # THIS IS THE CRITICAL FIX - AP keys should now be generated
        assert (
            user.private_key is not None
        ), "BUG: Private key should be generated when enabling deferred user!"
        assert (
            user.public_key is not None
        ), "BUG: Public key should be generated when enabling deferred user!"
        assert (
            user.ap_profile_id is not None
        ), "BUG: AP profile ID should be set when enabling deferred user!"
        assert user.ap_public_url is not None
        assert user.ap_inbox_url is not None

        # Verify URLs are correct
        assert user.ap_profile_id == "https://test.local/u/charlie_deferred"
        assert user.ap_public_url == "https://test.local/u/charlie_deferred"
        assert user.ap_inbox_url == "https://test.local/u/charlie_deferred/inbox"


def test_enable_already_finalized_user_no_duplicate_keys(app):
    """
    Test that enabling an already-finalized user doesn't regenerate keys.

    If a user was disabled after being finalized, re-enabling should NOT
    generate new AP keys (would break federation).
    """
    with app.app_context():
        # Create user with auto_activate=true (finalized immediately)
        result = create_private_user(
            {
                "username": "diana_toggle",
                "email": "diana_toggle@test.com",
                "display_name": "Diana Toggle",
                "password": "TestPassword123",
                "auto_activate": True,
            }
        )

        user_id = result["user_id"]
        user = User.query.get(user_id)

        # Save original keys
        original_private_key = user.private_key
        original_public_key = user.public_key
        original_profile_id = user.ap_profile_id

        assert original_private_key is not None
        assert original_public_key is not None

        # Disable the user
        perform_user_action(user_id, "disable")
        db.session.refresh(user)
        assert user.verified is False

        # Re-enable the user
        enable_result = perform_user_action(user_id, "enable")
        db.session.refresh(user)

        assert user.verified is True
        assert (
            "finalized" not in enable_result["message"].lower()
        ), "Already finalized user should not show finalization message"

        # Verify keys were NOT regenerated
        assert (
            user.private_key == original_private_key
        ), "Private key should NOT change when re-enabling finalized user"
        assert (
            user.public_key == original_public_key
        ), "Public key should NOT change when re-enabling finalized user"
        assert user.ap_profile_id == original_profile_id


def test_complete_deferred_activation_workflow(app):
    """
    End-to-end test of the complete deferred activation workflow.

    This simulates the real-world scenario:
    1. Admin creates user with auto_activate=false
    2. User cannot log in yet (verified=false)
    3. Admin reviews and approves user
    4. Admin enables user via API
    5. User is now fully functional with AP federation
    """
    with app.app_context():
        # Phase 1: Create user (no activation)
        create_result = create_private_user(
            {
                "username": "eva_workflow",
                "email": "eva_workflow@test.com",
                "display_name": "Eva Workflow",
                "password": "SecurePass789",
                "auto_activate": False,
                "bio": "Software engineer",
            }
        )

        assert create_result["success"] is True
        assert create_result["activation_required"] is True
        user_id = create_result["user_id"]

        # Phase 2: Verify user cannot participate yet
        user = User.query.get(user_id)
        assert user.verified is False, "User should not be able to log in"
        assert user.private_key is None, "User cannot federate (no keys)"
        assert user.ap_profile_id is None, "User has no AP profile"

        # Phase 3: Admin approves and enables user
        enable_result = perform_user_action(user_id, "enable")

        assert enable_result["success"] is True
        assert enable_result["user_id"] == user_id

        # Phase 4: Verify user is now fully functional
        db.session.refresh(user)

        # Can log in
        assert user.verified is True

        # Can federate (has AP keys)
        assert user.private_key is not None
        assert user.public_key is not None
        assert len(user.private_key) > 100, "RSA key should be substantial"
        assert "BEGIN RSA PRIVATE KEY" in user.private_key

        # Has correct AP profile
        assert user.ap_profile_id == "https://test.local/u/eva_workflow"
        assert user.ap_public_url == "https://test.local/u/eva_workflow"
        assert user.ap_inbox_url == "https://test.local/u/eva_workflow/inbox"

        # Retained original profile data
        assert user.display_name == "Eva Workflow"
        assert user.bio == "Software engineer"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
