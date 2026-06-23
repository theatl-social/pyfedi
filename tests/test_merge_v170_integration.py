"""Integration guards for the v1.7.0 upstream merge's ours/theirs seam.

The merge kept the fork API layer (api/alpha/routes.py, views.py,
utils/private_message.py) at our SP-patched version while auto-merging
utils/{post,reply,user}.py from upstream. Those auto-merged modules import
serializers from views.py at module load, so a future merge that drops a
serializer from our views.py would ImportError at app startup. The app-build
and import tests below catch that whole class of breakage early.

It also documents the deliberate deferral of four upstream moderation/report
+ logout API functions that were NOT routed (to avoid re-applying SP-014/019/021
to the API layer). If someone routes one without re-applying authz, the guard
test should make them stop and think.
"""

import pathlib

import pytest

# Import app before config to avoid the config<->app circular import.
from app import create_app, db
from config import Config

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ROUTES = REPO_ROOT / "app" / "api" / "alpha" / "routes.py"


class _TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True
    CACHE_TYPE = "NullCache"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    SERVER_NAME = "test.localhost"
    RATELIMIT_ENABLED = False
    CELERY_ALWAYS_EAGER = True


@pytest.fixture
def app():
    application = create_app(_TestConfig)
    with application.app_context():
        try:
            db.create_all()
        except Exception as e:  # tolerate Postgres-only DDL on SQLite
            if "parse_websearch" not in str(e) and "CREATE OR REPLACE" not in str(e):
                raise
        yield application
        db.session.remove()
        db.drop_all()


def test_app_builds_with_routes(app):
    rules = list(app.url_map.iter_rules())
    assert len(rules) > 100, "create_app() produced too few routes; build likely broke"


def test_api_util_modules_import():
    # These auto-merged modules import serializers from app.api.alpha.views at
    # module load. A successful import proves our (ours) views.py provides every
    # serializer name they reference.
    import app.api.alpha.utils.post  # noqa: F401
    import app.api.alpha.utils.reply  # noqa: F401
    import app.api.alpha.utils.user  # noqa: F401
    import app.api.alpha.views  # noqa: F401


def test_actor_json_to_model_rejects_cross_server_id(app):
    # v1.6.27 backport (ada8e2ea): an actor whose `id` is not on the server it
    # was fetched from must be rejected, so an instance can't impersonate actors
    # on another domain.
    from app.activitypub.util import actor_json_to_model

    with app.app_context():
        spoof = {"type": "Person", "id": "https://evil.example/u/spoof"}
        assert actor_json_to_model(spoof, "spoof@good.example", "good.example") is None
        # an actor with no type is also rejected (pre-existing guard, unaffected)
        assert actor_json_to_model({}, "x@good.example", "good.example") is None


def test_circular_import_architecture():
    # The fork owns cached_modlist_* in shared.community to break the
    # views <-> community circular import. test_ci_fixes covers this too; we
    # re-assert it here because the merge touched both sides.
    from app.shared.community import (  # noqa: F401
        cached_modlist_for_community,
        cached_modlist_for_user,
    )


def test_deferred_api_functions_remain_unrouted():
    """These four upstream functions were intentionally left unrouted because
    re-applying SP-014/019/021 to the API layer was deferred. If you wire one
    up, re-apply the authorization gate FIRST, then update this guard.

    (comment/distinguish and comment/report/list are NOT in this list: they are
    pre-existing v1.6.21 fork endpoints and are safely routed.)
    """
    routes_src = ROUTES.read_text()
    for fn in [
        "get_post_report_list",
        "put_post_report_resolve",
        "put_reply_report_resolve",
        "post_user_logout",
    ]:
        assert f"{fn}(" not in routes_src, (
            f"{fn} got routed in api/alpha/routes.py -- re-apply SP-014/019/021 "
            f"authz before enabling this endpoint, then update this test."
        )
