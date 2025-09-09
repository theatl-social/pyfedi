import pytest
from sqlalchemy import text

from app import create_app, db
from app.models import Community, User
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
