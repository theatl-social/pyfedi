"""
Simple field consistency tests that avoid circular imports.
These tests directly inspect model definitions to ensure immutability.
"""

import os
import sys

import pytest

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_user_model_columns_exist():
    """Test that critical User model columns exist"""
    # Import only what we need to avoid circular imports
    from app.models import User

    # Critical columns that must never change
    required_columns = {
        "id",
        "user_name",
        "email",
        "password_hash",
        "verified",
        "banned",
        "deleted",
        "created",
        "last_seen",
    }

    actual_columns = {col.name for col in User.__table__.columns}

    # All required columns must still exist
    missing_columns = required_columns - actual_columns
    assert (
        not missing_columns
    ), f"User table missing critical columns: {missing_columns}"


def test_user_name_field_consistency():
    """Test that User model uses 'user_name' not 'username'"""
    from app.models import User

    column_names = [col.name for col in User.__table__.columns]

    # Verify we use consistent naming
    assert "user_name" in column_names, "User model should have 'user_name' field"
    assert "username" not in column_names, "User model should NOT have 'username' field"


def test_post_model_columns_exist():
    """Test that critical Post model columns exist"""
    from app.models import Post

    required_columns = {
        "id",
        "title",
        "body",
        "user_id",
        "community_id",
        "posted_at",
        "deleted",
        "nsfw",
    }

    actual_columns = {col.name for col in Post.__table__.columns}

    missing_columns = required_columns - actual_columns
    assert (
        not missing_columns
    ), f"Post table missing critical columns: {missing_columns}"


def test_community_model_columns_exist():
    """Test that critical Community model columns exist"""
    from app.models import Community

    required_columns = {
        "id",
        "name",
        "title",
        "description",
        "created_at",
        "user_id",
        "nsfw",
        "restricted_to_mods",
    }

    actual_columns = {col.name for col in Community.__table__.columns}

    missing_columns = required_columns - actual_columns
    assert (
        not missing_columns
    ), f"Community table missing critical columns: {missing_columns}"


if __name__ == "__main__":
    pytest.main([__file__])
