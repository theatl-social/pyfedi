"""Shared support for the explore-page integration tests.

Not a test module itself (no `test_*` prefix, so pytest does not collect it).
Used by test_explore_page_integration.py and test_explore_real_world.py.

## Why this exists

`app.create_app()` is a bare Flask *factory* -- it wires up extensions
(SQLAlchemy, Bootstrap, Babel, Limiter, ...) but registers none of the jinja
globals (`theme`, `file_exists`, `digits`, ...), the `before_request` that
populates `g.site` / `g.nonce` / `g.locale`, or the `context_processor` that
injects `site`, `notif_server`, `admin_ids`, etc. into every template. All of
that lives in `pyfedi.py`, the real WSGI entrypoint, registered on the one
module-level `app = create_app()` object it builds.

Any test that renders a real production template (anything extending
`base.html`, which is nearly everything, including explore.html) needs that
wiring, or rendering fails with `UndefinedError` for `theme()`/`file_exists()`
or `AttributeError: site` on `g.site` (surfaced through
`login_required_if_private_instance`, which every page-view route uses).

`pyfedi.py` always calls the bare `create_app()` (no config override), which
-- given this repo's test-runner env block sets `DATABASE_URL=` (empty) --
falls back to `config.Config`'s default: a real, git-tracked SQLite file at
`<repo>/app.db`. Importing pyfedi.py naively and then mutating
`app.config["SQLALCHEMY_DATABASE_URI"]` afterwards does NOT redirect it: this
was confirmed by experiment -- Flask-SQLAlchemy resolves the engine as soon as
`db.init_app(app)` runs inside `create_app()`, before pyfedi.py's module body
finishes, and a later config mutation has no effect on the already-bound
engine. Just calling `create_all_for_tests(db)` after that would silently
recreate/alter tables in the tracked `app.db` file on disk.

So instead of importing `pyfedi` as-is, this module temporarily overrides
`app.create_app`'s default `config_class` argument to `tests.conftest.
TestConfig` (in-memory SQLite, safe SECRET_KEY, NullCache) *before*
`pyfedi.py`'s module body executes `app = create_app()`, then restores the
original default immediately after. `importlib.reload()` is used so every
call gets its own fresh app instance (own jinja env, own before_request/
context_processor closures) rather than reusing one process-wide singleton
across unrelated test modules -- avoiding any risk of one file's Site/Topic/
Community rows leaking into another file's assertions. All app instances
still share the single process-wide `db` SQLAlchemy object (the normal,
already-established pattern used by tests/conftest.py), so each caller must
create/drop its own tables around its own app instance.
"""

import importlib

import pyfedi  # imported once; see build_wired_app() for how it's (re)used safely


def _strip_sqlite_ddl_listeners(db):
    """Idempotently detach every per-table after_create/after_drop DDL
    listener (sqlalchemy_searchable's CreateSearchFunctionSQL /
    CreateSearchTriggerSQL / DropSearchFunctionSQL, which emit PostgreSQL-only
    DDL like "CREATE TRIGGER ... BEFORE UPDATE OR INSERT ...") so
    db.create_all()/drop_all() can complete on SQLite.

    Deliberately does NOT go through `sqlalchemy_searchable.search_manager
    .remove_listeners()/.attach_ddl_listeners()`: that API keeps its own
    internal bookkeeping of what it attached, and throws
    `InvalidRequestError` if asked to remove a listener that's already gone
    -- which happens here, because tests/test_activitypub_util.py's
    `_prepare_sqlite_schema()` strips these same listeners directly via
    `event.remove()` without going through search_manager, desyncing its
    bookkeeping from the real registry for the rest of the process. Working
    directly against `table.dispatch` (as that file does) sidesteps
    search_manager's bookkeeping entirely, so it stays correct regardless of
    what already ran earlier in the same pytest session.

    Returns the (table, event_name, listener) tuples that were removed, so
    they can be restored with `_restore_ddl_listeners()`.
    """
    from sqlalchemy import event
    from sqlalchemy.orm import configure_mappers

    # attach_ddl_listeners() runs off the mapper "after_configured" event,
    # which fires lazily -- force it now so there's something to strip.
    configure_mappers()

    removed = []
    for table in db.metadata.tables.values():
        for event_name in ("after_create", "after_drop"):
            for listener in list(getattr(table.dispatch, event_name)):
                event.remove(table, event_name, listener)
                removed.append((table, event_name, listener))
    return removed


def _restore_ddl_listeners(removed):
    from sqlalchemy import event

    for table, event_name, listener in removed:
        if not event.contains(table, event_name, listener):
            event.listen(table, event_name, listener)


def build_wired_app():
    """Build a fresh, fully-wired Flask app backed by in-memory SQLite.

    Returns the app with tables created (see `create_all_for_tests`) but NO
    data seeded -- callers add their own Site/Instance/User/Topic/Community
    rows inside `with app.app_context():`.
    """
    import app as _app_pkg
    from sqlalchemy import event
    from sqlalchemy_searchable import sql_expressions

    from tests.conftest import TestConfig, create_all_for_tests

    orig_defaults = _app_pkg.create_app.__defaults__
    _app_pkg.create_app.__defaults__ = (TestConfig,)
    try:
        importlib.reload(pyfedi)
    finally:
        _app_pkg.create_app.__defaults__ = orig_defaults

    application = pyfedi.app
    application.config["TESTING"] = True
    application.config["WTF_CSRF_ENABLED"] = False

    from app import db

    with application.app_context():
        # Hard safety net: never let this proceed against the real,
        # git-tracked app.db file. See module docstring -- this class of
        # mistake already happened once while developing this helper.
        engine_url = str(db.engine.url)
        assert ":memory:" in engine_url, (
            "build_wired_app() must never bind to a non-in-memory database "
            f"(got {engine_url!r}); refusing to run create_all_for_tests() "
            "against it."
        )

        sqlite = db.engine.dialect.name == "sqlite"
        removed = _strip_sqlite_ddl_listeners(db) if sqlite else []
        try:
            create_all_for_tests(db)
        finally:
            if sqlite:
                _restore_ddl_listeners(removed)
            # create_all_for_tests() clears *every* before_create listener on
            # db.metadata, not just the PostgreSQL-only one it means to
            # silence. db.metadata is one process-wide object shared by every
            # Flask app built via create_app() in this test run, so leaving
            # it cleared would permanently break any other test file whose
            # fixture depends on that hook firing (e.g. an old-style `try:
            # db.create_all() / except: tolerate "parse_websearch"` pattern).
            # Put it back so this helper leaves no lasting mutation on shared
            # state. See tests/conftest.py's create_all_for_tests() docstring.
            if sqlite and not event.contains(
                db.metadata, "before_create", sql_expressions
            ):
                event.listen(db.metadata, "before_create", sql_expressions)

    return application


def make(model, **kwargs):
    """Instantiate `model` with only the kwargs that are real columns on it.

    Model schemas drift over merges; callers of this helper pass a
    best-effort, representative set of fields and any that no longer exist
    are silently dropped rather than raising TypeError, so these fixtures
    degrade gracefully instead of bit-rotting outright.
    """
    valid_columns = {c.name for c in model.__table__.columns}
    filtered = {k: v for k, v in kwargs.items() if k in valid_columns}
    return model(**filtered)
