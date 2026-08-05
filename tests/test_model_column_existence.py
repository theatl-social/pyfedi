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


# Run only against a real PostgreSQL database.
#
# The previous guard was `DATABASE_URL.startswith("sqlite")`, which is False for
# the *empty* DATABASE_URL the local/CI test env exports. The module then ran
# anyway and every test errored at fixture setup with
# `ArgumentError: Could not parse SQLAlchemy URL from given URL string`,
# because `os.environ.get("DATABASE_URL", "postgresql://...")` returns "" when
# the variable is set-but-empty (the default only applies to a missing key).
#
# Inverting the condition — require an explicitly PostgreSQL URL — is the honest
# form: this module inspects a live schema to prove every model column really
# exists, which is meaningless against the SQLite shim in tests/conftest.py
# (that shim maps TSVECTOR/ARRAY/BIT to text and integer columns purely so the
# DDL compiles). Point DATABASE_URL at PostgreSQL to actually run these.
_DATABASE_URL = os.environ.get("DATABASE_URL") or ""

pytestmark = pytest.mark.skipif(
    not _DATABASE_URL.startswith(("postgresql", "postgres://")),
    reason=(
        "requires a PostgreSQL DATABASE_URL; these tests verify model columns "
        "against a live schema, which SQLite cannot represent (TSVECTOR/ARRAY/BIT)"
    ),
)


class TestConfig(Config):
    """Test configuration - requires PostgreSQL"""

    TESTING = True
    # `or` rather than a dict default: DATABASE_URL is often set-but-empty.
    SQLALCHEMY_DATABASE_URI = _DATABASE_URL or "postgresql://localhost/test"
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
