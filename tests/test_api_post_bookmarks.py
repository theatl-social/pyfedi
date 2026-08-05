from datetime import datetime

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import configure_mappers

from app import create_app, db
from app.constants import POST_STATUS_PUBLISHED, POST_STATUS_REVIEWING, POST_TYPE_ARTICLE
from app.models import Community, Instance, Post, PostBookmark, Role, Site, User
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

    community = Community(id=40, name="testcomm", title="testcomm", instance_id=1)
    db.session.add(community)
    db.session.flush()

    def make_post(id_, deleted=False):
        return Post(
            id=id_,
            user_id=user.id,
            community_id=community.id,
            instance_id=1,
            title=f"Post {id_}",
            type=POST_TYPE_ARTICLE,
            status=POST_STATUS_PUBLISHED,
            deleted=deleted,
        )

    post_plain = make_post(401)  # no existing bookmark
    post_bookmarked = make_post(402)  # already bookmarked
    post_deleted = make_post(403, deleted=True)  # deleted, no bookmark
    post_deleted_bookmarked = make_post(404, deleted=True)  # deleted, bookmarked
    for post in (post_plain, post_bookmarked, post_deleted, post_deleted_bookmarked):
        db.session.add(post)
    db.session.flush()

    db.session.add(PostBookmark(user_id=user.id, post_id=post_bookmarked.id))
    db.session.add(PostBookmark(user_id=user.id, post_id=post_deleted_bookmarked.id))

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
        "put_post_save() renders its response via post_view(variant=4, "
        "user_id=...), and post_view() variants 3/4/5 unconditionally call "
        "moderating_communities_ids_all_users() (app/utils.py) for any "
        "authenticated request, which runs a raw SQL query using ARRAY_AGG() "
        "- a PostgreSQL-only aggregate function with no SQLite equivalent "
        "(`sqlite3.OperationalError: no such function: ARRAY_AGG`). "
        "Covered by the production-mirror suite."
    ),
)
def test_api_post_bookmarks(app):
    with app.app_context():
        from app.api.alpha.utils.post import put_post_save

        user_id = 1
        user = User.query.get(user_id)
        assert user is not None and hasattr(user, "id")
        jwt = user.encode_jwt_token()
        assert jwt is not None
        auth = f"Bearer {jwt}"

        # normal add / remove bookmark
        existing_bookmarks = db.session.execute(
            text('SELECT post_id FROM "post_bookmark" WHERE user_id = :user_id'),
            {"user_id": user_id},
        ).scalars()
        post = Post.query.filter(
            Post.id.not_in(existing_bookmarks),
            Post.deleted == False,
            Post.status > POST_STATUS_REVIEWING,
        ).first()
        assert post is not None and hasattr(post, "id")

        data = {"post_id": post.id, "save": True}
        result = put_post_save(auth, data)
        assert result is not None and result["post_view"]["saved"] == True
        data = {"post_id": post.id, "save": False}
        result = put_post_save(auth, data)
        assert result is not None and result["post_view"]["saved"] == False

        # remove from non-existing
        data = {"post_id": post.id, "save": False}
        with pytest.raises(Exception) as ex:
            put_post_save(auth, data)
        assert str(ex.value) == "This post was not bookmarked."

        # add to existing
        existing_bookmarks = db.session.execute(
            text('SELECT post_id FROM "post_bookmark" WHERE user_id = :user_id'),
            {"user_id": user_id},
        ).scalars()
        post = Post.query.filter(
            Post.id.in_(existing_bookmarks),
            Post.deleted == False,
            Post.status > POST_STATUS_REVIEWING,
        ).first()
        if post:
            data = {"post_id": post.id, "save": True}
            with pytest.raises(Exception) as ex:
                put_post_save(auth, data)
            assert str(ex.value) == "This post has already been bookmarked."

        # add to deleted
        post = Post.query.filter(Post.deleted == True).first()
        if post:
            data = {"post_id": post.id, "save": True}
            with pytest.raises(Exception):
                result = put_post_save(auth, data)

        # remove from deleted
        existing_bookmarks = db.session.execute(
            text('SELECT post_id FROM "post_bookmark" WHERE user_id = :user_id'),
            {"user_id": user_id},
        ).scalars()
        post = Post.query.filter(
            Post.id.in_(existing_bookmarks), Post.deleted == True
        ).first()
        if post:
            data = {"post_id": post.id, "save": False}
            with pytest.raises(Exception):
                result = put_post_save(auth, data)
