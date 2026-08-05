from datetime import datetime

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import configure_mappers

from app import create_app, db
from app.constants import NOTIF_COMMUNITY
from app.models import Community, CommunityBan, Instance, NotificationSubscription, Role, Site, User
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

    # Community the user is not (yet) subscribed to - the "normal add /
    # remove" and "remove from non-existing" cases.
    community_plain = Community(id=10, name="plain", title="plain", instance_id=1)
    db.session.add(community_plain)

    # Community the user is already subscribed to - the "add to existing"
    # case.
    community_subscribed = Community(
        id=11, name="subscribed", title="subscribed", instance_id=1
    )
    db.session.add(community_subscribed)

    # Banned community, with an existing subscription - covers both "add to
    # a banned community" and "remove from a banned community" (both just
    # need `Community.banned == True`; subscribe_community() 404s via
    # `Community.query.filter_by(banned=False).one()` before it even looks
    # at the subscription).
    community_banned = Community(
        id=12, name="banned", title="banned", instance_id=1, banned=True
    )
    db.session.add(community_banned)

    # Community the user is banned *from* (but not subscribed to) - the
    # "add to a community this user is banned from" case.
    community_user_banned_from = Community(
        id=13, name="userbanned", title="userbanned", instance_id=1
    )
    db.session.add(community_user_banned_from)
    db.session.flush()

    db.session.add(
        NotificationSubscription(
            name="sub",
            type=NOTIF_COMMUNITY,
            entity_id=community_subscribed.id,
            user_id=user.id,
        )
    )
    db.session.add(
        NotificationSubscription(
            name="sub-banned-community",
            type=NOTIF_COMMUNITY,
            entity_id=community_banned.id,
            user_id=user.id,
        )
    )
    db.session.add(
        CommunityBan(user_id=user.id, community_id=community_user_banned_from.id)
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


def test_api_community_subscriptions(app):
    with app.app_context():
        from app.api.alpha.utils.community import put_community_subscribe

        user_id = 1
        user = User.query.get(user_id)
        assert user is not None and hasattr(user, "id")
        jwt = user.encode_jwt_token()
        assert jwt is not None
        auth = f"Bearer {jwt}"

        # normal add / remove subscription
        existing_subs = db.session.execute(
            text(
                'SELECT entity_id FROM "notification_subscription" WHERE user_id = :user_id AND type = 1'
            ),
            {"user_id": user_id},
        ).scalars()
        community = Community.query.filter(
            Community.id.not_in(existing_subs), Community.banned == False
        ).first()
        assert community is not None and hasattr(community, "id")

        data = {"community_id": community.id, "subscribe": True}
        result = put_community_subscribe(auth, data)
        assert result is not None and result["community_view"]["activity_alert"] == True
        data = {"community_id": community.id, "subscribe": False}
        result = put_community_subscribe(auth, data)
        assert (
            result is not None and result["community_view"]["activity_alert"] == False
        )

        # remove from non-existing
        data = {"community_id": community.id, "subscribe": False}
        with pytest.raises(Exception) as ex:
            put_community_subscribe(auth, data)
        assert str(ex.value) == "A subscription for this community did not exist."

        # add to existing
        existing_subs = db.session.execute(
            text(
                'SELECT entity_id FROM "notification_subscription" WHERE user_id = :user_id AND type = 1'
            ),
            {"user_id": user_id},
        ).scalars()
        community = Community.query.filter(
            Community.id.in_(existing_subs), Community.banned == False
        ).first()
        assert community is not None and hasattr(community, "id")
        if community:
            data = {"community_id": community.id, "subscribe": True}
            with pytest.raises(Exception) as ex:
                put_community_subscribe(auth, data)
            assert str(ex.value) == "A subscription for this community already existed."

        # add to a banned community
        community = Community.query.filter(Community.banned == True).first()
        if community:
            data = {"community_id": community.id, "subscribe": True}
            with pytest.raises(Exception):
                result = put_community_subscribe(auth, data)

        # remove from a banned community
        existing_subs = db.session.execute(
            text(
                'SELECT entity_id FROM "notification_subscription" WHERE user_id = :user_id AND type = 1'
            ),
            {"user_id": user_id},
        ).scalars()
        community = Community.query.filter(
            Community.id.in_(existing_subs), Community.banned == True
        ).first()
        if community:
            data = {"community_id": community.id, "subscribe": False}
            with pytest.raises(Exception):
                result = put_community_subscribe(auth, data)

        # add to a community this user is banned from
        existing_bans = db.session.execute(
            text('SELECT community_id FROM "community_ban" WHERE user_id = :user_id'),
            {"user_id": user_id},
        ).scalars()
        existing_subs = db.session.execute(
            text(
                'SELECT entity_id FROM "notification_subscription" WHERE user_id = :user_id AND type = 1'
            ),
            {"user_id": user_id},
        ).scalars()
        community = Community.query.filter(
            Community.id.in_(existing_bans),
            Community.id.not_in(existing_subs),
            Community.banned == False,
        ).first()
        if community:
            data = {"community_id": community.id, "subscribe": True}
            with pytest.raises(Exception) as ex:
                result = put_community_subscribe(auth, data)
            assert str(ex.value) == "You are banned from this community."
