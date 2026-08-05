from datetime import datetime

import pytest
from sqlalchemy import event
from sqlalchemy.orm import configure_mappers

from app import create_app, db
from app.models import Community, CommunityMember, Instance, Role, Site, User
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

    other_user = User(
        id=2,
        user_name="otheruser",
        email="other@test.localhost",
        verified=True,
        instance_id=1,
        password_updated_at=LONG_AGO,
    )
    other_user.set_password("password")
    db.session.add(other_user)
    db.session.flush()
    user.roles.append(admin_role)

    # community_view()'s `name`-based lookup (`get_community(data={"name": ...})`)
    # splits on "@" and matches `Community.name` + `Community.ap_domain`. That
    # only works for a community that looks federated (a non-null `ap_id` in
    # "name@domain" form) - the app's own locally-created communities have
    # `ap_id = None` and are looked up by `Community.id` instead, so `data["name"]`
    # would be `None` for one of those and blow up before reaching community_view.
    community_remote_shaped = Community(
        id=20,
        name="testcomm",
        title="Test Community",
        ap_id="testcomm@remote.example.com",
        ap_profile_id="https://remote.example.com/c/testcomm",
        ap_public_url="https://remote.example.com/c/testcomm",
        ap_domain="remote.example.com",
        instance_id=remote_instance.id,
        banned=False,
    )
    db.session.add(community_remote_shaped)

    # A community the primary user (id=1) is a member of - the "Subscribed"
    # case.
    community_subscribed = Community(
        id=21, name="subscribed", title="subscribed", instance_id=1
    )
    db.session.add(community_subscribed)

    # A community a *different* user (id=2) is a member of, and the primary
    # user is not - the "NotSubscribed" case.
    community_other_member = Community(
        id=22, name="othermember", title="othermember", instance_id=1
    )
    db.session.add(community_other_member)
    db.session.flush()

    db.session.add(CommunityMember(user_id=user.id, community_id=community_subscribed.id))
    db.session.add(
        CommunityMember(user_id=other_user.id, community_id=community_other_member.id)
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


def test_api_get_community(app):
    with app.app_context():
        from app.api.alpha.utils.community import get_community

        community = Community.query.filter_by(banned=False).first()

        # get_community() does `if "id" not in data and "name" not in data:`,
        # which requires `data` to support `in` - passing None (as this test
        # originally did) raises `TypeError: argument of type 'NoneType' is
        # not iterable` before that validation ever runs, and never produces
        # the "missing parameters for community" message this test used to
        # assert (that message does not appear anywhere in
        # app/api/alpha/utils/community.py). Passing `{}` is what actually
        # exercises the "no id or name provided" validation path, and its
        # real error message is "id or name required".
        with pytest.raises(Exception) as ex:
            get_community(None, {})
        assert str(ex.value) == "id or name required"

        data = {"id": community.id}
        anon_response = get_community(None, data)
        assert (
            anon_response is not None
            and anon_response["community_view"]["community"]["name"] == community.name
        )

        data = {"name": community.ap_id}
        anon_response = get_community(None, data)
        assert (
            anon_response is not None
            and anon_response["community_view"]["community"]["id"] == community.id
        )

        user_id = 1
        user = User.query.get(user_id)
        assert user is not None and hasattr(user, "id")
        jwt = user.encode_jwt_token()
        assert jwt is not None
        auth = f"Bearer {jwt}"

        cm = CommunityMember.query.filter_by(user_id=user_id).first()
        data = {"id": cm.community_id}
        logged_in_response = get_community(auth, data)
        assert (
            logged_in_response is not None
            and logged_in_response["community_view"]["subscribed"] == "Subscribed"
        )

        cm = CommunityMember.query.filter(CommunityMember.user_id != user_id).first()
        data = {"id": cm.community_id}
        logged_in_response = get_community(auth, data)
        assert (
            logged_in_response is not None
            and logged_in_response["community_view"]["subscribed"] == "NotSubscribed"
        )
