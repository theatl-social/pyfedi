from datetime import datetime

import pytest
from sqlalchemy import desc, event
from sqlalchemy.orm import configure_mappers

from app import create_app, db
from app.constants import POST_STATUS_PUBLISHED, POST_TYPE_ARTICLE
from app.models import Community, Instance, Post, Role, Site, User
from config import Config

from tests.conftest import create_all_for_tests

# See tests/test_api_get_site.py for why this needs to be a real, distant
# datetime rather than None: User.password_updated_at has a Python-side
# `default=utcnow` that SQLAlchemy applies to any None value at flush time,
# and app.utils.authorise_api_user() compares a JWT's real UTC `iat` against
# `password_updated_at.timestamp()`, which mis-reinterprets a naive UTC
# datetime in the local system timezone.
LONG_AGO = datetime(2000, 1, 1)


class TestConfig(Config):
    """Test configuration that inherits from the main Config"""

    TESTING = True
    WTF_CSRF_ENABLED = False
    # Disable real email sending during tests
    MAIL_SUPPRESS_SEND = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}  # SQLite doesn't support pool settings


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


def _seed(db):
    instance = Instance(id=1, domain="test.localhost", software="piefed")
    db.session.add(instance)
    remote_instance = Instance(id=2, domain="remote.example.com", software="piefed")
    db.session.add(remote_instance)

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

    # A community on a *remote* instance with several published posts, so
    # get_post_list(community_id=...) has something to return before the
    # instance is blocked, and post_site_block() has a real remote instance
    # to block.
    remote_community = Community(
        id=30,
        name="remotecomm",
        title="remotecomm",
        ap_id="remotecomm@remote.example.com",
        ap_profile_id="https://remote.example.com/c/remotecomm",
        ap_public_url="https://remote.example.com/c/remotecomm",
        ap_domain="remote.example.com",
        instance_id=remote_instance.id,
        banned=False,
        post_count=3,
    )
    db.session.add(remote_community)
    db.session.flush()

    for i in range(3):
        db.session.add(
            Post(
                user_id=user.id,
                community_id=remote_community.id,
                instance_id=remote_instance.id,
                title=f"Remote post {i}",
                type=POST_TYPE_ARTICLE,
                status=POST_STATUS_PUBLISHED,
                deleted=False,
            )
        )

    db.session.commit()


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


@pytest.mark.skipif(
    TestConfig.SQLALCHEMY_DATABASE_URI.startswith("sqlite"),
    reason=(
        "get_post_list() unconditionally calls communities_banned_from_all_users() "
        "(app/utils.py) for any authenticated request, which runs a raw SQL query "
        "using ARRAY_AGG() - a PostgreSQL-only aggregate function with no SQLite "
        "equivalent (`sqlite3.OperationalError: no such function: ARRAY_AGG`). "
        "Covered by the production-mirror suite."
    ),
)
def test_api_instance_blocks(app):
    # get_post_list() reads `flask.request.referrer`, so this needs a real
    # request context, not just an app context (test_request_context()
    # provides both).
    with app.test_request_context():
        from app.api.alpha.utils.site import post_site_block
        from app.api.alpha.utils.post import get_post_list

        user_id = 1
        user = User.query.get(user_id)
        assert user is not None and hasattr(user, "id")
        jwt = user.encode_jwt_token()
        assert jwt is not None
        auth = f"Bearer {jwt}"

        # fail to block instance 1
        data = {"instance_id": 1, "block": True}
        with pytest.raises(Exception) as ex:
            post_site_block(auth, data)
        assert str(ex.value) == "You cannot block the local instance."

        high_post_community = (
            Community.query.filter(Community.instance_id != 1)
            .order_by(desc(Community.post_count))
            .first()
        )
        assert high_post_community is not None and hasattr(high_post_community, "id")

        # post list should be more than 0 before blocking the instance
        data = {"community_id": high_post_community.id}
        response = get_post_list(auth, data)
        assert "posts" in response and len(response["posts"]) > 0

        # block the instance, post list should be 0
        data = {"instance_id": high_post_community.instance_id, "block": True}
        response = post_site_block(auth, data)
        assert "blocked" in response and response["blocked"] == True
        data = {"community_id": high_post_community.id}
        response = get_post_list(auth, data)
        assert "posts" in response and len(response["posts"]) == 0

        # unblock the instance, post list should go back to more than 0
        data = {"instance_id": high_post_community.instance_id, "block": False}
        response = post_site_block(auth, data)
        assert "blocked" in response and response["blocked"] == False
        data = {"community_id": high_post_community.id}
        response = get_post_list(auth, data)
        assert "posts" in response and len(response["posts"]) > 0
