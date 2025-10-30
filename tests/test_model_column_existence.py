"""
Test that all model columns actually exist in the database.

This test catches issues where:
1. Model has a column defined but migration wasn't run
2. Migration exists but wasn't applied to the database
3. Merge conflicts caused migrations to be skipped

NOTE: These tests require PostgreSQL and won't work with SQLite due to
TSVector columns and PostgreSQL-specific functions. They are skipped in CI
but should be run manually against a PostgreSQL database.
"""

import os
import pytest
from sqlalchemy import inspect

from app import create_app, db
from app.models import User, Post, Community, PostReply
from config import Config


# Skip all tests in this module if using SQLite
pytestmark = pytest.mark.skipif(
    os.environ.get("DATABASE_URL", "").startswith("sqlite"),
    reason="These tests require PostgreSQL (TSVector columns not supported in SQLite)",
)


class TestConfig(Config):
    """Test configuration - requires PostgreSQL"""

    TESTING = True
    # Use environment DATABASE_URL or skip tests
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://localhost/test"
    )
    WTF_CSRF_ENABLED = False


@pytest.fixture
def app():
    """Create test app with in-memory database"""
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def test_user_model_columns_exist_in_database(app):
    """Verify all User model columns exist in actual database schema"""
    with app.app_context():
        inspector = inspect(db.engine)
        db_columns = {col["name"] for col in inspector.get_columns("user")}

        # Get model columns from User model
        model_columns = {col.name for col in User.__table__.columns}

        # Find missing columns
        missing_columns = model_columns - db_columns

        assert (
            not missing_columns
        ), f"User model has columns that don't exist in database: {missing_columns}"


def test_post_model_columns_exist_in_database(app):
    """Verify all Post model columns exist in actual database schema"""
    with app.app_context():
        inspector = inspect(db.engine)
        db_columns = {col["name"] for col in inspector.get_columns("post")}

        model_columns = {col.name for col in Post.__table__.columns}
        missing_columns = model_columns - db_columns

        assert (
            not missing_columns
        ), f"Post model has columns that don't exist in database: {missing_columns}"


def test_community_model_columns_exist_in_database(app):
    """Verify all Community model columns exist in actual database schema"""
    with app.app_context():
        inspector = inspect(db.engine)
        db_columns = {col["name"] for col in inspector.get_columns("community")}

        model_columns = {col.name for col in Community.__table__.columns}
        missing_columns = model_columns - db_columns

        assert not missing_columns, f"Community model has columns that don't exist in database: {missing_columns}"


def test_post_reply_model_columns_exist_in_database(app):
    """Verify all PostReply model columns exist in actual database schema"""
    with app.app_context():
        inspector = inspect(db.engine)
        db_columns = {col["name"] for col in inspector.get_columns("post_reply")}

        model_columns = {col.name for col in PostReply.__table__.columns}
        missing_columns = model_columns - db_columns

        assert not missing_columns, f"PostReply model has columns that don't exist in database: {missing_columns}"


def test_critical_user_columns_present(app):
    """Test that critical User columns are present (catches missing migrations)"""
    with app.app_context():
        inspector = inspect(db.engine)
        db_columns = {col["name"] for col in inspector.get_columns("user")}

        # Critical columns that must exist
        critical_columns = {
            "id",
            "user_name",
            "email",
            "password",
            "created",
            "verified",
            "deleted",
            "banned",
            "private_key",
            "public_key",
            "ap_profile_id",
            "ap_inbox_url",
            "ap_public_url",
            "code_style",  # Added in migration 25ac2012570d - this was causing the error
        }

        missing_critical = critical_columns - db_columns

        assert not missing_critical, f"Critical User columns missing from database: {missing_critical}. Run 'flask db upgrade' to apply migrations."
