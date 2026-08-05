import json
from datetime import datetime

import pytest
from flask import g
from sqlalchemy import event, text
from sqlalchemy.orm import configure_mappers

from app import create_app, db
from app.constants import NOTIF_REPLY, POST_STATUS_PUBLISHED, POST_TYPE_ARTICLE
from app.models import (
    Community,
    Instance,
    NotificationSubscription,
    Post,
    PostReply,
    Role,
    Site,
    User,
)
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


_ARRAY_VALUE_COMPAT_INSTALLED = False


def _install_sqlite_array_value_compat():
    """Teach postgresql.ARRAY to round-trip *values*, not just DDL, on SQLite.

    conftest.py's `_install_sqlite_compat()` (via `@compiles`) only makes
    `CREATE TABLE` for an ARRAY column succeed, by rendering it as a TEXT
    column. It says nothing about *values*: SQLAlchemy's ARRAY type still
    hands the raw Python `list` to the SQLite DBAPI at bind time, and
    `sqlite3` doesn't know how to bind a `list`
    (`sqlite3.ProgrammingError: Error binding parameter 1: type 'list' is
    not supported`) - hit here because reply_view() calls
    calculate_path(reply), which assigns a real list to
    `PostReply.path` (an `ARRAY(Integer)` column).

    This patches ARRAY.bind_processor/result_processor to JSON-encode on the
    way in and decode on the way out, for the sqlite dialect only (the
    PostgreSQL-dialect behavior is left untouched via dialect-name dispatch).
    This does not attempt to support real array semantics (containment,
    `ANY`, etc.) - only faithful storage and read-back of a whole list
    value, which is all `calculate_path()`/`.path` access here needs.
    """
    global _ARRAY_VALUE_COMPAT_INSTALLED
    if _ARRAY_VALUE_COMPAT_INSTALLED:
        return

    from sqlalchemy.dialects.postgresql import ARRAY

    original_bind_processor = ARRAY.bind_processor
    original_result_processor = ARRAY.result_processor

    def bind_processor(self, dialect):
        if dialect.name != "sqlite":
            return original_bind_processor(self, dialect)

        def process(value):
            return None if value is None else json.dumps(list(value))

        return process

    def result_processor(self, dialect, coltype):
        if dialect.name != "sqlite":
            return original_result_processor(self, dialect, coltype)

        def process(value):
            if value is None:
                return None
            return json.loads(value) if isinstance(value, str) else value

        return process

    ARRAY.bind_processor = bind_processor
    ARRAY.result_processor = result_processor
    _ARRAY_VALUE_COMPAT_INSTALLED = True


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

    _install_sqlite_array_value_compat()
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

    community = Community(id=70, name="testcomm", title="testcomm", instance_id=1)
    db.session.add(community)
    db.session.flush()

    post_plain = Post(
        id=701,
        user_id=user.id,
        community_id=community.id,
        instance_id=1,
        title="Post 701",
        type=POST_TYPE_ARTICLE,
        status=POST_STATUS_PUBLISHED,
        deleted=False,
    )
    # subscribe_reply() rejects a reply whose *post* is deleted too
    # (`.filter_by(deleted=False)` on the joined Post), so this covers the
    # "reply not deleted but its post is" half of the "add/remove from
    # deleted" cases.
    post_deleted = Post(
        id=702,
        user_id=user.id,
        community_id=community.id,
        instance_id=1,
        title="Post 702",
        type=POST_TYPE_ARTICLE,
        status=POST_STATUS_PUBLISHED,
        deleted=True,
    )
    db.session.add(post_plain)
    db.session.add(post_deleted)
    db.session.flush()

    def make_reply(id_, post_, deleted=False):
        return PostReply(
            id=id_,
            user_id=user.id,
            post_id=post_.id,
            community_id=community.id,
            instance_id=1,
            body=f"Reply {id_}",
            deleted=deleted,
        )

    reply_plain = make_reply(703, post_plain)  # no existing subscription
    reply_subscribed = make_reply(704, post_plain)  # already subscribed
    # deleted reply, live post - subscribe_reply() rejects via its own
    # `deleted=False` filter regardless of subscription state
    reply_deleted = make_reply(705, post_plain, deleted=True)
    # live reply, but its post is deleted
    reply_post_deleted = make_reply(706, post_deleted)
    for reply in (reply_plain, reply_subscribed, reply_deleted, reply_post_deleted):
        db.session.add(reply)
    db.session.flush()

    db.session.add(
        NotificationSubscription(
            name="sub", type=NOTIF_REPLY, entity_id=reply_subscribed.id, user_id=user.id
        )
    )
    # Both "deleted" replies also carry a subscription, so the "remove from
    # deleted" queries (which require `id IN existing_subs`) find them too.
    db.session.add(
        NotificationSubscription(
            name="sub-deleted-reply",
            type=NOTIF_REPLY,
            entity_id=reply_deleted.id,
            user_id=user.id,
        )
    )
    db.session.add(
        NotificationSubscription(
            name="sub-deleted-post",
            type=NOTIF_REPLY,
            entity_id=reply_post_deleted.id,
            user_id=user.id,
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


def test_api_reply_subscriptions(app):
    with app.app_context():
        from app.api.alpha.utils.reply import put_reply_subscribe

        # reply_view() reads g.admin_ids directly (no hasattr guard); this is
        # normally populated by pyfedi.py's @app.before_request, which never
        # runs when tests call create_app() and the util function directly.
        g.admin_ids = [1]

        user_id = 1
        user = User.query.get(user_id)
        assert user is not None and hasattr(user, "id")
        jwt = user.encode_jwt_token()
        assert jwt is not None
        auth = f"Bearer {jwt}"

        # normal add / remove subscription
        existing_subs = db.session.execute(
            text(
                'SELECT entity_id FROM "notification_subscription" WHERE user_id = :user_id AND type = 4'
            ),
            {"user_id": user_id},
        ).scalars()
        reply = PostReply.query.filter(
            PostReply.id.not_in(existing_subs), PostReply.deleted == False
        ).first()
        assert reply is not None and hasattr(reply, "id")

        data = {"comment_id": reply.id, "subscribe": True}
        result = put_reply_subscribe(auth, data)
        assert result is not None and result["comment_view"]["activity_alert"] == True
        data = {"comment_id": reply.id, "subscribe": False}
        result = put_reply_subscribe(auth, data)
        assert result is not None and result["comment_view"]["activity_alert"] == False

        # remove from non-existing
        data = {"comment_id": reply.id, "subscribe": False}
        with pytest.raises(Exception) as ex:
            put_reply_subscribe(auth, data)
        assert str(ex.value) == "A subscription for this comment did not exist."

        # add to existing
        existing_subs = db.session.execute(
            text(
                'SELECT entity_id FROM "notification_subscription" WHERE user_id = :user_id AND type = 4'
            ),
            {"user_id": user_id},
        ).scalars()
        reply = PostReply.query.filter(
            PostReply.id.in_(existing_subs), PostReply.deleted == False
        ).first()
        if reply:
            data = {"comment_id": reply.id, "subscribe": True}
            with pytest.raises(Exception) as ex:
                put_reply_subscribe(auth, data)
            assert str(ex.value) == "A subscription for this comment already existed."

        # add to deleted (reply or post)
        reply = PostReply.query.filter(PostReply.deleted == True).first()
        if reply:
            data = {"comment_id": reply.id, "subscribe": True}
            with pytest.raises(Exception):
                result = put_reply_subscribe(auth, data)
        reply = (
            PostReply.query.filter_by(deleted=True)
            .join(Post, Post.id == PostReply.post_id)
            .filter_by(deleted=True)
            .first()
        )
        if reply:
            data = {"comment_id": reply.id, "subscribe": True}
            with pytest.raises(Exception):
                result = put_reply_subscribe(auth, data)

        # remove from deleted (reply or post)
        existing_subs = db.session.execute(
            text(
                'SELECT entity_id FROM "notification_subscription" WHERE user_id = :user_id AND type = 4'
            ),
            {"user_id": user_id},
        ).scalars()
        reply = PostReply.query.filter(
            PostReply.id.in_(existing_subs), PostReply.deleted == True
        ).first()
        if reply:
            data = {"comment_id": reply.id, "subscribe": False}
            with pytest.raises(Exception):
                result = put_reply_subscribe(auth, data)
        existing_subs = db.session.execute(
            text(
                'SELECT entity_id FROM "notification_subscription" WHERE user_id = :user_id AND type = 4'
            ),
            {"user_id": user_id},
        ).scalars()
        reply = (
            PostReply.query.filter(
                PostReply.id.in_(existing_subs), PostReply.deleted == True
            )
            .join(Post, Post.id == PostReply.post_id)
            .filter_by(deleted=True)
            .first()
        )
        if reply:
            data = {"comment_id": reply.id, "subscribe": False}
            with pytest.raises(Exception):
                result = put_reply_subscribe(auth, data)
