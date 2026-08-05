from datetime import datetime

import pytest
from flask import g
from sqlalchemy import event
from sqlalchemy.orm import configure_mappers

from app import create_app, db
from app.models import Instance, Role, Site, User
from config import Config

from tests.conftest import create_all_for_tests

# Deliberately far in the past. `User.password_updated_at` has a Python-side
# `default=utcnow` that SQLAlchemy applies to *any* None value at flush time,
# even one passed in explicitly — so the only way to get a value that reads
# as "in the past" is to set a real, distant one. This also sidesteps a
# pre-existing (out of scope to fix here) bug in
# app.utils.authorise_api_user(): it compares a JWT's `iat` (a real UTC
# epoch int) against `user.password_updated_at.timestamp()`, but
# password_updated_at is a *naive* UTC datetime, so `.timestamp()`
# reinterprets it in the local system timezone. On a machine west of UTC
# that makes a freshly-created user's password_updated_at appear to be hours
# in the future, which fails the `issued_at_time < password_updated_time`
# check for every token minted right after creating the user.
LONG_AGO = datetime(2000, 1, 1)


class TestConfig(Config):
    """Test configuration that inherits from the main Config"""

    TESTING = True
    WTF_CSRF_ENABLED = False
    # Disable real email sending during tests
    MAIL_SUPPRESS_SEND = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}  # SQLite doesn't support pool settings


def _seed(db):
    """Minimal baseline data: local instance, Site row (id=1, required by
    g.site / Site.query.get(1)) and an admin user (id=1)."""
    instance = Instance(id=1, domain="test.localhost", software="piefed")
    db.session.add(instance)

    site = Site(id=1, name="Test Site")
    db.session.add(site)

    admin_role = Role(id=4, name="ROLE_ADMIN")
    db.session.add(admin_role)
    db.session.flush()

    user = User(
        id=1,
        user_name="admin",
        email="admin@test.localhost",
        verified=True,
        instance_id=1,
        password_updated_at=LONG_AGO,
    )
    user.set_password("password")
    db.session.add(user)
    db.session.flush()
    user.roles.append(admin_role)

    db.session.commit()


def _prepare_sqlite_schema(db):
    """create_all_for_tests(), but first strip the per-*table* after_create /
    after_drop DDL listeners that sqlalchemy_searchable's
    SearchManager.attach_ddl_listeners() attaches for every tsvector column
    (e.g. "CREATE TRIGGER ... BEFORE UPDATE OR INSERT ...", "DROP FUNCTION
    ..." - both PostgreSQL-only syntax that SQLite's parser rejects).

    create_all_for_tests() in conftest.py already clears
    `db.metadata.dispatch.before_create` for the separate `parse_websearch()`
    function DDL, but that dispatch lives on the MetaData object; these
    listeners live on the individual Table objects instead, and are attached
    lazily via a `mapper "after_configured"` event the first time SQLAlchemy
    configures its mappers - which may already have happened by the time this
    runs (e.g. from a previous test in the same process) or may not have.
    Forcing configuration and stripping unconditionally makes create_all()/
    drop_all() behave the same regardless of what ran before. This only ever
    mattered for real PostgreSQL, so removing it is safe.
    """
    if db.engine.dialect.name != "sqlite":
        create_all_for_tests(db)
        return

    configure_mappers()
    for table in db.metadata.tables.values():
        for event_name in ("after_create", "after_drop"):
            for listener in list(getattr(table.dispatch, event_name)):
                event.remove(table, event_name, listener)
    create_all_for_tests(db)


@pytest.fixture
def app():
    """Create and configure a Flask app for testing using the app factory"""
    app = create_app(TestConfig)
    with app.app_context():
        _prepare_sqlite_schema(db)
        _seed(db)
        yield app
        db.session.remove()
        db.drop_all()


def test_api_get_site(app):
    with app.app_context():
        from app.api.alpha.utils.site import get_site

        g.site = Site.query.get(1)

        anon_response = get_site(None)
        assert anon_response is not None and "version" in anon_response
        assert "my_user" not in anon_response

        user_id = 1
        user = User.query.get(user_id)
        assert user is not None and hasattr(user, "id")
        jwt = user.encode_jwt_token()
        assert jwt is not None
        auth = f"Bearer {jwt}"

        logged_in_response = get_site(auth)
        assert logged_in_response is not None and "version" in logged_in_response
        assert "my_user" in logged_in_response
        assert (
            logged_in_response["my_user"]["local_user_view"]["show_read_posts"] == False
            if user.hide_read_posts == True
            else True
        )
