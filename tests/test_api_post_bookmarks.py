import pytest
from sqlalchemy import text

from app import create_app, db
from app.constants import POST_STATUS_REVIEWING
from app.models import User, Post
from config import Config


class TestConfig(Config):
    """Test configuration that inherits from the main Config"""

    TESTING = True
    WTF_CSRF_ENABLED = False
    # Disable real email sending during tests
    MAIL_SUPPRESS_SEND = True


@pytest.fixture
def app():
    """Create and configure a Flask app for testing using the app factory"""
    app = create_app(TestConfig)
    return app


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
