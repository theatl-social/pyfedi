import pytest

from app import create_app
from app.models import Community, CommunityMember, User
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


def test_api_get_community(app):
    with app.app_context():
        from app.api.alpha.utils.community import get_community

        community = Community.query.filter_by(banned=False).first()

        with pytest.raises(Exception) as ex:
            get_community(None, None)
        assert str(ex.value) == "missing parameters for community"

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
