"""Celery must be configured with modern, lowercase-only settings.

Two properties are asserted here:

1. **Positive** — after ``create_app()`` the effective Celery configuration
   still carries every setting the worker depends on: the JSON-only
   serializer allowlist (SP-018), the three-queue routing map, the worker
   recycling limits, and startup broker retries.

2. **Negative** — ``create_app()`` must NOT dump the whole Flask config into
   Celery. The old ``celery.conf.update(app.config)`` pushed ~170 unrelated
   uppercase application keys (``S3_REGION``, ``S3_BUCKET``, ``CACHE_DIR``,
   ``BOUNCE_PASSWORD``, ...) into Celery, where Celery's legacy-name
   compatibility layer treats uppercase keys as deprecated Celery options and
   emits Celery 6 deprecation warnings.

   The negative assertion inspects ``celery.conf.changes`` — the mutable
   layer of Celery's ChainMap holding only what the application explicitly
   set. Membership tests against ``celery.conf`` itself are useless for this:
   ``"CELERY_TASK_SERIALIZER" in celery.conf`` is True via Celery's legacy
   alias shim even when nothing ever set that key.
"""

import pathlib
import os
import subprocess

import pytest

from app import celery, create_app
from config import Config

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ENTRYPOINT_WEB = REPO_ROOT / "entrypoint.sh"
ENTRYPOINT_CELERY = REPO_ROOT / "entrypoint_celery.sh"

EXPECTED_TASK_ROUTES = {
    "app.shared.tasks.users.check_user_application": {"queue": "background"},
    "app.user.utils.purge_user_then_delete_task": {"queue": "background"},
    "app.community.util.retrieve_mods_and_backfill": {"queue": "background"},
    "app.community.util.send_to_remote_instance_task": {"queue": "send"},
    "app.activitypub.signature.post_request": {"queue": "send"},
    "app.shared.tasks.maintenance.*": {"queue": "background"},
    "app.admin.routes.*": {"queue": "background"},
    "app.admin.util.*": {"queue": "background"},
}

# Flask-only settings that must never reach Celery. These are a representative
# sample of the ~170 keys the old bulk merge leaked.
FLASK_ONLY_KEYS = [
    "S3_REGION",
    "S3_BUCKET",
    "CACHE_DIR",
    "CACHE_REDIS_URL",
    "SECRET_KEY",
    "SQLALCHEMY_DATABASE_URI",
    "SERVER_NAME",
    "BOUNCE_PASSWORD",
    "MAIL_PASSWORD",
]


# Sentinel URLs, so the broker/backend assertions test that create_app()
# actually propagated *this* config rather than coincidentally matching a
# default. `Celery(__name__, broker=Config.CELERY_BROKER_URL)` at import time
# already seeds the real Config value, so asserting against the real value
# would pass even if create_app() stopped setting broker_url entirely.
SENTINEL_BROKER_URL = "redis://sentinel-broker.invalid:6379/9"
SENTINEL_RESULT_BACKEND = "redis://sentinel-backend.invalid:6379/8"


class _TestConfig(Config):
    """Inherit the real Config so every key create_app() reads is present.

    SECRET_KEY is pinned here so the test does not depend on the ambient
    environment (SP-003 refuses to boot without one).
    """

    TESTING = True
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True
    CACHE_TYPE = "NullCache"
    SECRET_KEY = "test-secret-key-xxxxxxxxxxxxxxxxxxxxxxxx"
    CELERY_BROKER_URL = SENTINEL_BROKER_URL
    RESULT_BACKEND = SENTINEL_RESULT_BACKEND


@pytest.fixture
def app():
    return create_app(_TestConfig)


def application_celery_settings():
    """Return only the settings the application explicitly set on celery.conf.

    ``celery.conf`` is a ChainMap whose first map (``changes``) holds what was
    explicitly set, layered over Celery's defaults. Two traps:

    * Before Celery finalizes its lazy ``PendingConfiguration``, iterating
      ``changes`` yields the *default* key set (~176 keys) rather than the
      application's. Touching any attribute forces finalization first.
    * ``deprecated_settings`` is Celery's own bookkeeping entry (the set of
      legacy names it detected), not an application setting, so it is dropped
      here and asserted on separately.
    """
    celery.conf.task_serializer  # force finalization of PendingConfiguration
    changes = dict(celery.conf.changes)
    changes.pop("deprecated_settings", None)
    return changes


# --------------------------------------------------------------------------
# Positive: required modern settings survive
# --------------------------------------------------------------------------


def test_broker_and_result_backend_configured(app):
    """create_app() must copy the Flask broker/backend settings into Celery.

    Note the ITEM access (``celery.conf["broker_url"]``) rather than attribute
    access. ``celery.app.utils.Settings.broker_url`` is a property whose first
    clause is ``os.environ.get("CELERY_BROKER_URL")``, so attribute access
    returns the environment variable — shadowing the stored setting — whenever
    one is set. ``tests/test_explore_real_world.py`` hard-assigns that env var
    at module import time, which made the attribute form order-dependent
    within a full-suite run. Item access reads the actual configuration, which
    is what create_app() is responsible for and what the worker uses when no
    env var is present.
    """
    assert celery.conf["broker_url"] == SENTINEL_BROKER_URL
    assert celery.conf["result_backend"] == SENTINEL_RESULT_BACKEND
    # And the values really came from the Flask config, not a default.
    assert app.config["CELERY_BROKER_URL"] == SENTINEL_BROKER_URL
    assert app.config["RESULT_BACKEND"] == SENTINEL_RESULT_BACKEND


def test_json_only_serialization(app):
    """SP-018: explicit JSON allowlist for broker messages and results."""
    assert celery.conf.task_serializer == "json"
    assert celery.conf.result_serializer == "json"
    assert celery.conf.accept_content == ["json"]


def test_worker_recycling_limits(app):
    assert celery.conf.worker_max_tasks_per_child == 1000
    assert celery.conf.worker_max_memory_per_child == 512000


def test_broker_connection_retry_on_startup(app):
    assert celery.conf.broker_connection_retry_on_startup is True


def test_task_routes_preserved(app):
    routes = celery.conf.task_routes
    assert routes is not None, "task_routes is unset — task routing is lost"
    for task, expected in EXPECTED_TASK_ROUTES.items():
        assert task in routes, f"routing entry for {task!r} is missing"
        assert routes[task] == expected, (
            f"routing for {task!r} changed: {routes[task]!r} != {expected!r}"
        )
    assert set(routes) == set(EXPECTED_TASK_ROUTES), (
        "task_routes gained or lost entries"
    )


# --------------------------------------------------------------------------
# Negative: no Flask config leaked into Celery
# --------------------------------------------------------------------------


def test_flask_config_not_leaked_into_celery(app):
    """create_app() must not bulk-merge app.config into celery.conf."""
    changes = application_celery_settings()
    leaked = [key for key in FLASK_ONLY_KEYS if key in changes]
    assert not leaked, (
        f"Flask-only settings leaked into celery.conf.changes: {leaked}. "
        "celery.conf.update(app.config) must not be used."
    )


def test_celery_conf_uses_only_lowercase_keys(app):
    """Every key the application sets must use a modern lowercase name.

    Uppercase names are the deprecated pre-4.0 Celery spelling and produce
    Celery 6 deprecation warnings.
    """
    uppercase = sorted(k for k in application_celery_settings() if k != k.lower())
    assert not uppercase, (
        f"deprecated uppercase Celery settings are being set: {uppercase}"
    )


def test_celery_detects_no_deprecated_setting_names(app):
    """Celery's own legacy-name detector must find nothing to warn about."""
    celery.conf.task_serializer  # force finalization
    detected = celery.conf.changes.get("deprecated_settings")
    assert not detected, (
        f"Celery flagged deprecated setting names: {sorted(detected)}. "
        "These produce Celery 6 deprecation warnings on every worker start."
    )


def test_celery_conf_changes_are_exactly_the_expected_keys(app):
    """Guard against a future bulk merge sneaking back in."""
    expected = {
        "broker_url",
        "result_backend",
        "task_serializer",
        "result_serializer",
        "accept_content",
        "task_routes",
        "worker_max_tasks_per_child",
        "worker_max_memory_per_child",
        "broker_connection_retry_on_startup",
    }
    actual = set(application_celery_settings())
    assert actual == expected, (
        f"unexpected Celery settings: extra={sorted(actual - expected)}, "
        f"missing={sorted(expected - actual)}"
    )


# --------------------------------------------------------------------------
# Worker privilege drop
# --------------------------------------------------------------------------


def test_celery_entrypoint_drops_privileges():
    """The worker must run as the unprivileged 'python' user via gosu."""
    script = ENTRYPOINT_CELERY.read_text()
    assert "exec gosu python" in script, (
        "entrypoint_celery.sh must drop root privileges with "
        "'exec gosu python', matching entrypoint.sh"
    )


def test_entrypoints_do_not_sync_the_venv_after_dropping_privileges():
    """`uv run` must not try to re-sync /app/.venv as the python user.

    The Dockerfile builds /app/.venv with `RUN uv sync` and declares no USER, so
    the venv -- including `_editable_impl_pyfedi.pth` -- is owned by root.
    Without --no-sync, `uv run` re-syncs the editable install at startup and
    tries to delete that file, which the unprivileged user cannot do:

        error: failed to remove file
        `/app/.venv/lib/python3.13/site-packages/_editable_impl_pyfedi.pth`:
        Permission denied (os error 13)

    This crash-looped the celery worker in production when it was switched from
    root to gosu. entrypoint.sh masked the same hazard because its root-side
    `uv run flask db upgrade` performs the sync first -- but that step is
    skipped for SQLite, so it is only incidentally safe.
    """
    for path in (ENTRYPOINT_CELERY, ENTRYPOINT_WEB):
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "gosu python" not in stripped:
                continue
            if "uv run" not in stripped:
                continue
            assert "--no-sync" in stripped, (
                f"{path.name}: `{stripped}` drops privileges and then runs "
                "`uv run` without --no-sync. It will try to rewrite the "
                "root-owned /app/.venv as the python user and exit 2 with "
                "'Permission denied'."
            )


def test_celery_entrypoint_keeps_worker_arguments():
    script = ENTRYPOINT_CELERY.read_text()
    for arg in (
        "-A celery_worker_docker.celery",
        "worker",
        "--concurrency=${CELERY_CONCURRENCY:-4}",
        "--queues=celery,background,send",
    ):
        assert arg in script, f"entrypoint_celery.sh lost worker argument {arg!r}"


@pytest.mark.parametrize("override,expected", [(None, "4"), ("7", "7")])
def test_celery_worker_concurrency_expands_default_and_override(override, expected):
    command = next(line for line in ENTRYPOINT_CELERY.read_text().splitlines() if line.startswith("exec gosu "))
    environment = dict(os.environ)
    environment.pop("CELERY_CONCURRENCY", None)
    if override is not None:
        environment["CELERY_CONCURRENCY"] = override
    # Expand the real worker command as shell arguments without starting services.
    arguments = subprocess.check_output(
        ["bash", "-c", 'set -- ' + command + '; printf "%s\\n" "$@"'],
        env=environment, text=True,
    ).splitlines()
    assert "--concurrency=" + expected in arguments
    assert arguments[:6] == ["exec", "gosu", "python", "uv", "run", "--no-sync"]
    assert "--queues=celery,background,send" in arguments
