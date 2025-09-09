import pytest
from sqlalchemy import text

from app import create_app, db
from app.models import User
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


def test_api_user_subscriptions(app):
    with app.app_context():
        from app.api.alpha.utils.user import put_user_subscribe

        user_id = 1
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
