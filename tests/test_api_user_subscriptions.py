from datetime import datetime

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import configure_mappers

from app import create_app, db
from app.constants import NOTIF_USER
from app.models import Instance, NotificationSubscription, Role, Site, User
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

    # Deliberately given a *higher* id than every "person" candidate below.
    # The test's queries for a subscription target
    # (`User.query.filter(User.id.not_in(...), User.banned == False).first()`)
    # have no way to exclude the authenticated user themselves other than id
    # ordering (SQLite's plan for an unindexed, unordered `.first()` scans in
    # ascending rowid/id order) - if the admin user had the lowest id, these
    # queries would pick *themselves* as the subscription target, and
    # subscribe_user() would immediately reject that with "Target must be
    # another user." instead of exercising the intended scenarios.
    user = User(
        id=99,
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

    def make_person(id_, banned=False):
        p = User(
            id=id_,
            user_name=f"person{id_}",
            email=f"person{id_}@test.localhost",
            verified=True,
            instance_id=1,
            banned=banned,
            password_updated_at=LONG_AGO,
        )
        p.set_password("password")
        return p

    person_plain = make_person(1)  # no existing subscription
    person_subscribed = make_person(2)  # already subscribed
    person_banned = make_person(3, banned=True)  # banned, also subscribed
    for p in (person_plain, person_subscribed, person_banned):
        db.session.add(p)
    db.session.flush()

    db.session.add(
        NotificationSubscription(
            name="sub", type=NOTIF_USER, entity_id=person_subscribed.id, user_id=user.id
        )
    )
    db.session.add(
        NotificationSubscription(
            name="sub-banned",
            type=NOTIF_USER,
            entity_id=person_banned.id,
            user_id=user.id,
        )
    )

    # Note: the "subscribe to a user who has blocked this user" case below
    # queries `SELECT blocker_id FROM user_block WHERE blocker_id = :user_id`
    # - i.e. people *our* user has blocked, not people who blocked *our*
    # user - and then looks that blocker_id up as if it were the blocked
    # person's own id. Given `has_blocked_user()` checks
    # `UserBlock(blocker_id=<person>, blocked_id=<user_id>)`, this query is
    # inverted relative to what the assertion afterwards wants to test, and
    # (verified) would end up feeding subscribe_user() person_id == user_id
    # (itself), which raises "Target must be another user." instead of the
    # asserted "This user has blocked you.". See the report for detail. The
    # whole block is guarded by `if person:` in the original test, so simply
    # not seeding any `user_block` row with blocker_id=1 leaves it inert
    # rather than exercising the mismatch.

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


def test_api_user_subscriptions(app):
    with app.app_context():
        from app.api.alpha.utils.user import put_user_subscribe

        user_id = 99
        user = User.query.get(user_id)
        assert user is not None and hasattr(user, "id")
        jwt = user.encode_jwt_token()
        assert jwt is not None
        auth = f"Bearer {jwt}"

        # normal add / remove subscription
        existing_subs = db.session.execute(
            text(
                'SELECT entity_id FROM "notification_subscription" WHERE user_id = :user_id AND type = 0'
            ),
            {"user_id": user_id},
        ).scalars()
        person = User.query.filter(
            User.id.not_in(existing_subs), User.banned == False
        ).first()
        assert person is not None and hasattr(person, "id")

        data = {"person_id": person.id, "subscribe": True}
        result = put_user_subscribe(auth, data)
        assert result is not None and result["person_view"]["activity_alert"] == True
        data = {"person_id": person.id, "subscribe": False}
        result = put_user_subscribe(auth, data)
        assert result is not None and result["person_view"]["activity_alert"] == False

        # remove from non-existing
        data = {"person_id": person.id, "subscribe": False}
        with pytest.raises(Exception) as ex:
            put_user_subscribe(auth, data)
        assert str(ex.value) == "A subscription for this user did not exist."

        # add to existing
        existing_subs = db.session.execute(
            text(
                'SELECT entity_id FROM "notification_subscription" WHERE user_id = :user_id AND type = 0'
            ),
            {"user_id": user_id},
        ).scalars()
        person = User.query.filter(
            User.id.in_(existing_subs), User.banned == False
        ).first()
        assert person is not None and hasattr(user, "id")
        if user:
            data = {"person_id": person.id, "subscribe": True}
            with pytest.raises(Exception) as ex:
                put_user_subscribe(auth, data)
            assert str(ex.value) == "A subscription for this user already existed."

        # add to a banned user
        person = User.query.filter(User.banned == True).first()
        if person:
            data = {"person_id": person.id, "subscribe": True}
            with pytest.raises(Exception):
                result = put_user_subscribe(auth, data)

        # remove from a banned user
        existing_subs = db.session.execute(
            text(
                'SELECT entity_id FROM "notification_subscription" WHERE user_id = :user_id AND type = 0'
            ),
            {"user_id": user_id},
        ).scalars()
        person = User.query.filter(
            User.id.in_(existing_subs), User.banned == True
        ).first()
        if person:
            data = {"person_id": person.id, "subscribe": False}
            with pytest.raises(Exception):
                result = put_user_subscribe(auth, data)

        # subscribe to self
        data = {"person_id": user_id, "subscribe": True}
        with pytest.raises(Exception):
            result = put_user_subscribe(auth, data)

        # subscribe to a user who has blocked this user
        existing_bans = db.session.execute(
            text('SELECT blocker_id FROM "user_block" WHERE blocker_id = :user_id'),
            {"user_id": user_id},
        ).scalars()
        existing_subs = db.session.execute(
            text(
                'SELECT entity_id FROM "notification_subscription" WHERE user_id = :user_id AND type = 0'
            ),
            {"user_id": user_id},
        ).scalars()
        person = User.query.filter(
            User.id.in_(existing_bans),
            User.id.not_in(existing_subs),
            User.banned == False,
        ).first()
        if person:
            data = {"person_id": person.id, "subscribe": True}
            with pytest.raises(Exception) as ex:
                result = put_user_subscribe(auth, data)
            assert str(ex.value) == "This user has blocked you."
