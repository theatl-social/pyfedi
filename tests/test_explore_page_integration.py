"""
Integration test for the explore page that tests actual rendering behavior.

This test creates a real Flask app instance (in-memory SQLite) and tests the
explore route to verify it doesn't crash and returns content.
"""

import os

# Set environment variables before importing Flask app. These use setdefault
# so a value already present in the environment (e.g. the SERVER_NAME/
# SECRET_KEY/CACHE_* set by the test-runner's env block) wins; only fill gaps.
os.environ.setdefault("SERVER_NAME", "test.localhost")
os.environ.setdefault("SECRET_KEY", "test-secret-for-explore-test-padding-32c")
os.environ.setdefault("DATABASE_URL", "sqlite:///memory:test.db")
os.environ.setdefault("CACHE_TYPE", "NullCache")
os.environ.setdefault("CACHE_REDIS_URL", "memory://")
os.environ.setdefault("CELERY_BROKER_URL", "memory://localhost/")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("MAIL_SERVER", "")

import pytest
from unittest.mock import patch

from tests.explore_test_support import build_wired_app, make


@pytest.fixture(scope="module")
def app():
    """A fully-wired Flask app (same jinja globals / before_request / context
    processor as the real WSGI entrypoint, see explore_test_support.py) with
    an in-memory SQLite database and a Site row with id=1 -- required because
    the explore route's @login_required_if_private_instance decorator reads
    g.site, and every template extending base.html needs the jinja globals
    (theme(), file_exists(), etc.) that only get registered by pyfedi.py, not
    by app.create_app() alone.
    """
    application = build_wired_app()

    from app import db
    from app.models import Site

    with application.app_context():
        site = make(
            Site,
            id=1,
            name="Test Site",
            private_instance=False,
            registration_mode="Open",
        )
        db.session.add(site)
        db.session.commit()

    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def test_explore_route_responds(client):
    """Test that the explore route responds without crashing."""
    # Mock the topic_tree function to return empty list (simulating no topics)
    with patch("app.main.routes.topic_tree") as mock_topic_tree:
        mock_topic_tree.return_value = []

        # Mock the menu functions to return empty lists
        with (
            patch("app.main.routes.menu_instance_feeds") as mock_instance_feeds,
            patch("app.main.routes.menu_my_feeds") as mock_my_feeds,
            patch("app.main.routes.menu_subscribed_feeds") as mock_subscribed_feeds,
        ):
            mock_instance_feeds.return_value = []
            mock_my_feeds.return_value = []
            mock_subscribed_feeds.return_value = []

            response = client.get("/explore")

            # Should not crash - this was the original bug
            assert response.status_code == 200

            # Should return HTML content
            assert response.content_type.startswith("text/html")

            # Get the content
            html_content = response.get_data(as_text=True)

            # Should not contain template errors
            template_errors = [
                "TemplateSyntaxError",
                "UndefinedError",
                "No filter named",
                "len(topics)",  # The original bug
                "len(communities)",
            ]

            for error in template_errors:
                assert error not in html_content, f"Template error found: {error}"

            # Should contain the basic page structure (indicating it rendered successfully)
            assert "<html" in html_content or "<!DOCTYPE" in html_content
            assert "Topics" in html_content  # Should have the Topics tab
            assert "Feeds" in html_content  # Should have the Feeds tab

            # Should show the empty state message when no topics
            assert "There are no communities yet." in html_content


def test_explore_route_with_mock_topics(client):
    """Test that the explore route works when topics exist."""

    # Mock topic object
    class MockTopic:
        def __init__(self, name, parent_id=None):
            self.name = name
            self.parent_id = parent_id
            self.id = hash(name)  # Simple ID

        def path(self):
            return self.name.lower().replace(" ", "-")

    # Create mock topic tree
    mock_topics = [
        {
            "topic": MockTopic("Technology"),
            "children": [{"topic": MockTopic("Programming"), "children": []}],
        },
        {"topic": MockTopic("Science"), "children": []},
    ]

    with patch("app.main.routes.topic_tree") as mock_topic_tree:
        mock_topic_tree.return_value = mock_topics

        # Mock the menu functions
        with (
            patch("app.main.routes.menu_instance_feeds") as mock_instance_feeds,
            patch("app.main.routes.menu_my_feeds") as mock_my_feeds,
            patch("app.main.routes.menu_subscribed_feeds") as mock_subscribed_feeds,
        ):
            mock_instance_feeds.return_value = []
            mock_my_feeds.return_value = []
            mock_subscribed_feeds.return_value = []

            response = client.get("/explore")

            assert response.status_code == 200
            html_content = response.get_data(as_text=True)

            # Should contain the topic names
            assert "Technology" in html_content
            assert "Science" in html_content
            assert "Programming" in html_content

            # Should NOT show the empty state message
            assert "There are no communities yet." not in html_content

            # Should not contain template errors
            assert "len(topics)" not in html_content
            assert "TemplateSyntaxError" not in html_content


def test_explore_template_jinja_syntax():
    """Test that the explore template uses correct Jinja2 syntax."""
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "app", "templates", "explore.html"
    )

    if not os.path.exists(template_path):
        pytest.skip("explore.html template not found")

    with open(template_path, "r") as f:
        template_content = f.read()

    # Verify the specific line that was causing the bug
    assert "topics|length > 0" in template_content, "Template should use |length filter"
    assert (
        "len(topics)" not in template_content
    ), "Template should not use Python len() function"

    # Check for other potential issues
    assert (
        "{% if topics|length > 0 -%}" in template_content
    ), "Expected correct Jinja2 syntax for topics length check"


if __name__ == "__main__":
    # Allow running this test standalone
    import sys
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
    )

    sys.exit(result.returncode)
