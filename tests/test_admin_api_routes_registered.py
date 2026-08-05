"""Guard: the fork's private-registration admin API is actually ROUTED.

## Why this file exists

`app/api/admin/routes.py` and `app/api/admin/monitoring_routes.py` define 18
endpoints with `@admin_bp.route(...)`. A Flask route only exists if that
decorator executes, which only happens if the module is imported — and nothing
else in the tree imports either module. The two import lines that did so live at
the bottom of `app/api/alpha/__init__.py`.

They were dropped during conflict resolution in `4c611576` ("Merge upstream
PieFed v1.6.9", 2026-03-06) and stayed missing for five months and six upstream
merges. Every one of these endpoints returned 404 in production the whole time,
including on this fork's live instance.

Two things let it hide for that long, and both are the same anti-pattern —
checking for a *proxy* instead of the *behaviour*:

1. CLAUDE.md's post-merge checklist verified the feature with
   `ls app/api/admin/private_registration.py`. The file was present throughout.
   A file existing says nothing about whether its routes are reachable.
2. The tests that would have caught it
   (`tests/test_private_registration_security*.py`) were in the
   `-not -name` exclusion list in `.github/workflows/ci-cd.yml`, and
   `tests/test_private_registration_endpoints.py` wraps its fixture in
   `except Exception: pytest.skip(...)`, so it skipped silently instead of
   failing.

So this test asserts against the live `app.url_map` of a real `create_app()`.
That is the only check that would have failed in March. Do not "optimize" it
into an import check or a file-existence check — those are precisely what did
not work.
"""

import pathlib

import pytest

from app import create_app
from config import Config


class _TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    CACHE_TYPE = "NullCache"
    SECRET_KEY = "test-secret-key-xxxxxxxxxxxxxxxxxxxxxxxx"
    # Pin to in-memory. Config's default is `sqlite:///<repo>/app.db` whenever
    # DATABASE_URL is unset-or-empty, and app.db is a tracked file — tests must
    # not write to it.
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}


@pytest.fixture(scope="module")
def app():
    return create_app(_TestConfig)


@pytest.fixture
def app_with_db():
    """App with tables built — the feature flag reads the `settings` table."""
    from app import db
    from tests.conftest import create_all_for_tests

    application = create_app(_TestConfig)
    with application.app_context():
        create_all_for_tests(db)
        yield application
        # No drop_all(): this is `sqlite:///:memory:`, so the schema is
        # discarded with the connection. Calling it here would also re-enter
        # sqlalchemy_searchable's DROP FUNCTION DDL path via the module-scoped
        # `app` fixture's separate engine, which SQLite cannot parse.
        db.session.remove()


# (endpoint name, rule) for every route the fork's admin API must expose.
# Endpoint names are asserted alongside rules because a rule can be satisfied by
# an unrelated blueprint, which would make a rule-only check pass vacuously.
REQUIRED_ADMIN_ENDPOINTS = [
    ("Admin.create_private_user_endpoint", "/api/alpha/private_register"),
    ("Admin.validate_user_endpoint", "/api/alpha/user/validate"),
    ("Admin.list_users_endpoint", "/api/alpha/users"),
    ("Admin.lookup_user_endpoint", "/api/alpha/user/lookup"),
    ("Admin.health_check_endpoint", "/api/alpha/health"),
    ("Admin.update_user_endpoint", "/api/alpha/user/<int:user_id>"),
    ("Admin.delete_user_endpoint", "/api/alpha/user/<int:user_id>"),
    ("Admin.disable_user_endpoint", "/api/alpha/user/<int:user_id>/disable"),
    ("Admin.enable_user_endpoint", "/api/alpha/user/<int:user_id>/enable"),
    ("Admin.ban_user_endpoint", "/api/alpha/user/<int:user_id>/ban"),
    ("Admin.unban_user_endpoint", "/api/alpha/user/<int:user_id>/unban"),
    ("Admin.bulk_user_operations_endpoint", "/api/alpha/users/bulk"),
    ("Admin.export_users_endpoint", "/api/alpha/users/export"),
    ("Admin.user_statistics_endpoint", "/api/alpha/stats/users"),
    ("Admin.registration_statistics_endpoint", "/api/alpha/stats/registrations"),
    ("Admin.get_metrics", "/api/alpha/metrics"),
    ("Admin.comprehensive_health_check", "/api/alpha/monitoring/health"),
    ("Admin.get_audit_trail", "/api/alpha/monitoring/audit"),
    ("Admin.get_rate_limit_status", "/api/alpha/monitoring/rate-limits"),
]


@pytest.mark.parametrize(
    "endpoint,rule", REQUIRED_ADMIN_ENDPOINTS, ids=lambda v: str(v)
)
def test_admin_api_endpoint_is_registered(app, endpoint, rule):
    registered = {(r.endpoint, str(r)) for r in app.url_map.iter_rules()}
    assert (endpoint, rule) in registered, (
        f"REGRESSION: {endpoint} ({rule}) is not registered. The fork's "
        "private-registration admin API is defined but unrouted, so this "
        "endpoint 404s. Check that app/api/alpha/__init__.py still ends with "
        "`from app.api.admin import routes as admin_routes` and "
        "`from app.api.admin import monitoring_routes` — those imports were "
        "silently dropped once before, in the v1.6.9 merge (4c611576), and "
        "stayed missing for five months."
    )


def test_alpha_init_imports_the_admin_route_modules():
    """Belt and braces: the imports are load-bearing, so say so in one place.

    The url_map assertions above are the real check. This one exists so that a
    merge conflict which deletes the import lines produces an error message
    naming the exact lines to restore.
    """
    src = (
        pathlib.Path(__file__).resolve().parents[1]
        / "app"
        / "api"
        / "alpha"
        / "__init__.py"
    ).read_text()
    for needed in (
        "from app.api.admin import routes as admin_routes",
        "from app.api.admin import monitoring_routes",
    ):
        assert needed in src, (
            f"REGRESSION: `{needed}` is missing from app/api/alpha/__init__.py. "
            "Flask registers a route only when its decorator runs, which "
            "requires the module to be imported; nothing else imports it. "
            "Without this line the entire admin API 404s."
        )


def test_no_route_collisions_on_the_frozen_alpha_surface(app):
    """`/api/alpha/*` is frozen (see CLAUDE.md). Nothing may shadow it.

    The fork's admin endpoints sit on generic paths (`/api/alpha/users`,
    `/api/alpha/user/<id>`), so re-registering them could in principle shadow a
    Lemmy-compatible route and silently change API behaviour. Assert that every
    (rule, method) pair resolves to exactly one endpoint.
    """
    from collections import defaultdict

    seen = defaultdict(list)
    for rule in app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            seen[(str(rule), method)].append(rule.endpoint)

    collisions = {k: v for k, v in seen.items() if len(v) > 1}
    assert not collisions, (
        f"Route collisions detected: {collisions}. Two endpoints claim the same "
        "path and method, so one shadows the other. `/api/alpha/*` is a frozen "
        "public surface — see the IMMUTABILITY CONSTRAINTS section of CLAUDE.md."
    )


def test_admin_endpoints_are_auth_gated(app_with_db):
    """Registering these routes must not expose them.

    Defence in depth (app/api/admin/security.py:74): the
    PRIVATE_REGISTRATION_ENABLED feature flag is checked first and defaults to
    false, then an IP allowlist, then the X-PieFed-Secret header, then a rate
    limit. An unauthenticated request must never reach handler logic.
    """
    client = app_with_db.test_client()
    # Paths whose schemas are satisfied, so the request reaches the auth gate.
    # (`/user/lookup` needs a query arg and `/private_register` a body;
    # without them flask-smorest's schema validation returns 400 *before* the
    # auth decorator runs. That reveals nothing beyond the schema, but it does
    # mean 400 is not evidence of authorization, so those are exercised with
    # valid-shaped input here.)
    for path in (
        "/api/alpha/users",
        "/api/alpha/user/lookup?username=someone",
        "/api/alpha/stats/users",
        "/api/alpha/health",
        "/api/alpha/metrics",
    ):
        resp = client.get(path)
        assert resp.status_code in (401, 403, 429), (
            f"{path} returned {resp.status_code} to an unauthenticated request; "
            "expected 401/403/429. These endpoints create and modify accounts."
        )
        body = resp.get_data(as_text=True)
        assert "feature_disabled" in body or resp.status_code in (401, 429), (
            f"{path} was rejected with {resp.status_code} but not by the "
            f"PRIVATE_REGISTRATION_ENABLED feature gate: {body[:200]}"
        )
