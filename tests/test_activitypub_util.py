import pytest

from app import create_app
from app.activitypub.util import find_actor_or_create
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


def test_find_actor_or_create(app):
    with app.app_context():
        server_name = app.config["SERVER_NAME"]
        user_name = (
            "rimu"  # Note to others: change this to your login before running this test
        )

        # Test with a local URL
        local_user = find_actor_or_create(
            f"https://{server_name}/u/{user_name}", create_if_not_found=False
        )
        # Assert that the result matches expectations
        assert local_user is not None and hasattr(local_user, "id")

        # Test with a remote URL that doesn't exist
        remote_user = find_actor_or_create(
            "https://notreal.example.com/u/fake", create_if_not_found=False
        )
        assert remote_user is None

        # Test with community_only flag - invalid community
        remote_with_filter = find_actor_or_create(
            f"https://{server_name}/c/asdfasdf",
            community_only=True,
            create_if_not_found=False,
        )
        assert remote_with_filter is None

        # Test with community_only flag - valid community
        remote_with_filter = find_actor_or_create(
            "https://piefed.social/c/piefed_meta",
            community_only=True,
            create_if_not_found=True,
        )
        assert remote_with_filter is not None

        # Test with feed_only flag
        feed_with_filter = find_actor_or_create(
            f"https://{server_name}/f/asdfasdf",
            feed_only=True,
            create_if_not_found=False,
        )
        assert feed_with_filter is None

        # Test whatever@server.tld style actor
        local_user = find_actor_or_create(
            f"{user_name}@{server_name}", create_if_not_found=True
        )
        # Assert that the result matches expectations
        assert local_user is not None and hasattr(local_user, "id")
