"""Guard: the fork's private-registration admin API is actually ROUTED.

## Why this file exists

`app/api/admin/routes.py` and `app/api/admin/monitoring_routes.py` define 19
endpoints for private account provisioning, user management and monitoring.
A single merge — `4c611576` ("Merge upstream PieFed v1.6.9", 2026-03-06) —
broke them in **two independent ways** at once, and they stayed broken for five
months and six upstream merges. Every endpoint 404'd in production the whole
time, on this fork's live instance.

1. **The imports vanished.** A Flask route only exists if its
   `@route(...)` decorator executes, which requires the module to be imported.
   Nothing else in the tree imports either module; the two lines that did so
   sat at the bottom of `app/api/alpha/__init__.py` and were dropped in
   conflict resolution.

2. **The URL prefix collapsed.** The fork's blueprint was
   `ApiBlueprint("Admin", url_prefix="/api/alpha/admin")`. Upstream v1.6.9
   independently added its *own* blueprint — same name `"Admin"` — with the
   generic `url_prefix="/api/alpha"`, spelling `/admin/...` in its two route
   decorators instead. The merge kept upstream's line. Because the fork's
   decorators are bare (`"/private_register"`), on the assumption the prefix
   supplies `/admin`, every endpoint silently moved to
   `/api/alpha/private_register`. Fixing only the imports would have left them
   registered at the wrong paths — and put secret-gated admin endpoints like
   `PUT`/`DELETE /api/alpha/user/<id>` directly into the frozen public
   namespace.

The fix for (2) is a dedicated `private_admin_bp`, so upstream can never move
these endpoints by editing its own blueprint again. That is why the endpoint
names below are `PrivateAdmin.*`.

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
    ("PrivateAdmin.create_private_user_endpoint", "/api/alpha/admin/private_register"),
    ("PrivateAdmin.validate_user_endpoint", "/api/alpha/admin/user/validate"),
    ("PrivateAdmin.list_users_endpoint", "/api/alpha/admin/users"),
    ("PrivateAdmin.lookup_user_endpoint", "/api/alpha/admin/user/lookup"),
    ("PrivateAdmin.health_check_endpoint", "/api/alpha/admin/health"),
    ("PrivateAdmin.update_user_endpoint", "/api/alpha/admin/user/<int:user_id>"),
    ("PrivateAdmin.delete_user_endpoint", "/api/alpha/admin/user/<int:user_id>"),
    ("PrivateAdmin.disable_user_endpoint", "/api/alpha/admin/user/<int:user_id>/disable"),
    ("PrivateAdmin.enable_user_endpoint", "/api/alpha/admin/user/<int:user_id>/enable"),
    ("PrivateAdmin.ban_user_endpoint", "/api/alpha/admin/user/<int:user_id>/ban"),
    ("PrivateAdmin.unban_user_endpoint", "/api/alpha/admin/user/<int:user_id>/unban"),
    ("PrivateAdmin.bulk_user_operations_endpoint", "/api/alpha/admin/users/bulk"),
    ("PrivateAdmin.export_users_endpoint", "/api/alpha/admin/users/export"),
    ("PrivateAdmin.user_statistics_endpoint", "/api/alpha/admin/stats/users"),
    ("PrivateAdmin.registration_statistics_endpoint", "/api/alpha/admin/stats/registrations"),
    ("PrivateAdmin.get_metrics", "/api/alpha/admin/metrics"),
    ("PrivateAdmin.comprehensive_health_check", "/api/alpha/admin/monitoring/health"),
    ("PrivateAdmin.get_audit_trail", "/api/alpha/admin/monitoring/audit"),
    ("PrivateAdmin.get_rate_limit_status", "/api/alpha/admin/monitoring/rate-limits"),
]


@pytest.mark.parametrize(
    "endpoint,rule", REQUIRED_ADMIN_ENDPOINTS, ids=lambda v: str(v)
)
def test_admin_api_endpoint_is_registered(app, endpoint, rule):
    registered = {(r.endpoint, str(r)) for r in app.url_map.iter_rules()}
    assert (endpoint, rule) in registered, (
        f"REGRESSION: {endpoint} ({rule}) is not registered, so it 404s. "
        "Two things to check in app/api/alpha/__init__.py, both of which broke "
        "together in the v1.6.9 merge (4c611576) and stayed broken for five "
        "months: (a) the file must still end with `from app.api.admin import "
        "routes as admin_routes` and `from app.api.admin import "
        "monitoring_routes` — a route needs its decorator to execute; and "
        "(b) `private_admin_bp` must still carry url_prefix=\"/api/alpha/admin\". "
        "If the endpoint exists but at /api/alpha/<name> without the /admin "
        "segment, it is (b)."
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

    The fork's admin endpoints use bare route paths (`/users`, `/user/<id>`)
    and rely on their blueprint prefix to place them under `/api/alpha/admin`.
    If that prefix is ever lost again they land directly on `/api/alpha/users`
    and `/api/alpha/user/<id>`, where they can shadow Lemmy-compatible routes
    and silently change public API behaviour. Assert that every (rule, method)
    pair resolves to exactly one endpoint.
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
        "/api/alpha/admin/users",
        "/api/alpha/admin/user/lookup?username=someone",
        "/api/alpha/admin/stats/users",
        "/api/alpha/admin/health",
        "/api/alpha/admin/metrics",
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
