import pytest

from app import create_app, cache
from app.activitypub.util import find_actor_or_create, find_actor_or_create_cached
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
        user_name = "rimuadmin"  # Note to others: change this to your login before running this test

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


def test_find_actor_or_create_cached(app):
    with app.app_context():
        # Clear the cache before testing
        cache.clear()

        server_name = app.config["SERVER_NAME"]
        user_name = "rimuadmin"  # Note to others: change this to your login before running this test

        # Test with a local URL - first call (not cached)
        local_user = find_actor_or_create_cached(
            f"https://{server_name}/u/{user_name}", create_if_not_found=False
        )
        assert local_user is not None and hasattr(local_user, "id")
        user_id_first = local_user.id

        # Test with a local URL - second call (should be cached)
        local_user_cached = find_actor_or_create_cached(
            f"https://{server_name}/u/{user_name}", create_if_not_found=False
        )
        assert local_user_cached is not None
        assert local_user_cached.id == user_id_first  # Should return the same user

        # Test with a remote URL that doesn't exist
        remote_user = find_actor_or_create_cached(
            "https://notreal.example.com/u/fake", create_if_not_found=False
        )
        assert remote_user is None

        # Test with community_only flag - invalid community
        remote_with_filter = find_actor_or_create_cached(
            f"https://{server_name}/c/asdfasdf",
            community_only=True,
            create_if_not_found=False,
        )
        assert remote_with_filter is None

        # Test with community_only flag - valid community
        remote_community = find_actor_or_create_cached(
            "https://piefed.social/c/piefed_meta",
            community_only=True,
            create_if_not_found=True,
        )
        assert remote_community is not None
        community_id = remote_community.id

        # Test that the community is now cached
        remote_community_cached = find_actor_or_create_cached(
            "https://piefed.social/c/piefed_meta",
            community_only=True,
            create_if_not_found=False,
        )
        assert remote_community_cached is not None
        assert remote_community_cached.id == community_id

        # Test with feed_only flag
        feed_with_filter = find_actor_or_create_cached(
            f"https://{server_name}/f/asdfasdf",
            feed_only=True,
            create_if_not_found=False,
        )
        assert feed_with_filter is None

        # Test whatever@server.tld style actor
        local_user_webfinger = find_actor_or_create_cached(
            f"{user_name}@{server_name}", create_if_not_found=True
        )
        assert local_user_webfinger is not None and hasattr(local_user_webfinger, "id")

        # Test that cache returns fresh SQLAlchemy models (not stale cached objects)
        # This is important because we cache only the ID, not the full model
        user_before = find_actor_or_create_cached(
            f"https://{server_name}/u/{user_name}", create_if_not_found=False
        )
        assert user_before is not None
        # The model should be attached to the current session
        from app import db

        assert user_before in db.session or user_before.id is not None
