"""
Shared pytest fixtures for all test files.

## Why there is a SQLite compatibility shim in here

The production schema is PostgreSQL-specific in three ways that SQLite cannot
express, so a plain `db.create_all()` against SQLite aborts partway through and
leaves most tables missing. Historically this fixture swallowed that error:

    try:
        db.create_all()
    except Exception as e:
        if "parse_websearch" not in str(e) and "CREATE OR REPLACE" not in str(e):
            raise

which hid the failure but not its consequence — every test that touched the
database then died with `no such table: user`, and those test files were added
to an exclusion list in `.github/workflows/ci-cd.yml` so CI stayed green. That
quarantined roughly 40 tests, including SQL-injection and private-registration
security regressions.

`_install_sqlite_compat()` below makes `create_all()` actually complete:

1. `sqlalchemy_searchable.make_searchable()` registers a `before_create` hook
   that emits raw PostgreSQL (`CREATE OR REPLACE FUNCTION parse_websearch...`).
   It is dropped for SQLite engines only.
2. `BIT`, `ARRAY`, `TSVECTOR` and `JSONB` have no SQLite renderings, so they are
   compiled to the nearest storage-compatible types.

This is a **test-harness** accommodation, not a portability claim: full-text
search, array containment and bit operations still only work on PostgreSQL, and
tests that depend on those semantics belong in the Postgres-backed
production-mirror suite instead. What this buys is that ordinary CRUD, routing,
authorization and serialization tests can run without a database server.
"""

import pytest

# Import order matters: `config` does `import app.constants`, and `app/__init__`
# does `from config import Config`. conftest is imported before any test module,
# so importing config first starts that cycle from the config end and fails with
# "cannot import name 'Config' from partially initialized module 'config'".
# Importing the app package first lets config finish loading inside it.
import app as _app  # noqa: F401  (import for side effect: breaks the cycle)

from config import Config

_SQLITE_COMPAT_INSTALLED = False


def _install_sqlite_compat():
    """Teach SQLAlchemy to render the PostgreSQL-only column types on SQLite."""
    global _SQLITE_COMPAT_INSTALLED
    if _SQLITE_COMPAT_INSTALLED:
        return

    from sqlalchemy.dialects.postgresql import ARRAY, BIT, JSONB, TSVECTOR
    from sqlalchemy.ext.compiler import compiles

    # ARRAY/JSONB/TSVECTOR degrade to text storage; BIT to an integer. None of
    # these preserve PostgreSQL query semantics — they only let the DDL compile
    # so the rest of the table is created.
    for type_, rendered in (
        (BIT, "INTEGER"),
        (ARRAY, "TEXT"),
        (TSVECTOR, "TEXT"),
        (JSONB, "TEXT"),
    ):
        compiles(type_, "sqlite")(
            lambda element, compiler, _r=rendered, **kw: _r
        )

    _SQLITE_COMPAT_INSTALLED = True


class TestConfig(Config):
    """Standard test configuration.

    Inherits Config so every key `create_app()` reads is present. It previously
    did not, which made `create_app(TestConfig)` raise
    `KeyError: 'HTTP_PROTOCOL'` before it reached anything worth testing.
    """

    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}  # SQLite doesn't support pool settings
    MAIL_SUPPRESS_SEND = True
    SERVER_NAME = "test.localhost"
    # At least 32 chars: SP-003 refuses to boot on anything shorter.
    SECRET_KEY = "test-secret-key-xxxxxxxxxxxxxxxxxxxxxxxx"
    PRIVATE_REGISTRATION_ENABLED = "true"
    PRIVATE_REGISTRATION_SECRET = "test-secret-123"
    CACHE_TYPE = "NullCache"
    CACHE_REDIS_URL = "memory://"
    CELERY_ALWAYS_EAGER = True
    SENTRY_DSN = ""
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    RATELIMIT_ENABLED = False
    SERVE_API_DOCS = False
    GOOGLE_OAUTH_CLIENT_ID = ""
    GOOGLE_OAUTH_CLIENT_SECRET = ""
    MASTODON_OAUTH_CLIENT_ID = ""
    MASTODON_OAUTH_CLIENT_SECRET = ""
    DISCORD_OAUTH_CLIENT_ID = ""
    DISCORD_OAUTH_CLIENT_SECRET = ""
    MAIL_SERVER = ""


def create_all_for_tests(db):
    """`db.create_all()` that completes on SQLite as well as PostgreSQL.

    Requires an active application context.
    """
    if db.engine.dialect.name == "sqlite":
        _install_sqlite_compat()
        # sqlalchemy_searchable's before_create hook emits PostgreSQL DDL that
        # SQLite rejects, which aborts create_all() before most tables exist.
        # The drop-side hooks are the mirror image: they emit
        # `DROP FUNCTION IF EXISTS post_search_vector_update()`, which SQLite
        # rejects with `near "FUNCTION": syntax error` during fixture teardown.
        # The hooks live at two levels and both must go:
        #   * metadata-level, which emits `CREATE OR REPLACE FUNCTION
        #     parse_websearch(...)` and aborts create_all() before most tables
        #     exist;
        #   * per-table, which emits `DROP FUNCTION IF EXISTS
        #     post_search_vector_update()` during drop_all() teardown and fails
        #     with `near "FUNCTION": syntax error`.
        # Clearing only the metadata level leaves teardown broken.
        _clear_ddl_events(db.metadata)
        for table in db.metadata.tables.values():
            _clear_ddl_events(table)
    db.create_all()


def _clear_ddl_events(target):
    """Strip create/drop DDL listeners from a MetaData or Table."""
    dispatch = target.dispatch
    for event_name in ("before_create", "after_create", "before_drop", "after_drop"):
        # `.for_modify()` is required before mutating an event collection that
        # currently has no listeners — SQLAlchemy raises
        # "need to call for_modify()" on a bare _EmptyListener.clear().
        getattr(dispatch, event_name).for_modify(dispatch).clear()


@pytest.fixture
def test_app():
    """Create and configure a test application instance"""
    from app import create_app, db

    app = create_app(TestConfig)

    with app.app_context():
        create_all_for_tests(db)
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def app(test_app):
    """Alias for test_app for compatibility"""
    return test_app


@pytest.fixture
def client(test_app):
    """Create test client"""
    return test_app.test_client()
