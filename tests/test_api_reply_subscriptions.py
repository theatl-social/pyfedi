import pytest
from sqlalchemy import text

from app import create_app, db
from app.models import User, Post, PostReply
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


def test_api_reply_subscriptions(app):
    with app.app_context():
        from app.api.alpha.utils.reply import put_reply_subscribe

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
