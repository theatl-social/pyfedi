"""
Integration test for the explore page that tests actual rendering behavior.

This test creates a minimal Flask app instance and tests the explore route
to verify it doesn't crash and returns content.
"""

import os

# Set environment variables before importing Flask app
os.environ.setdefault("SERVER_NAME", "test.localhost")
os.environ.setdefault("SECRET_KEY", "test-secret-for-explore-test")
os.environ.setdefault("DATABASE_URL", "sqlite:///memory:test.db")
os.environ.setdefault("CACHE_TYPE", "NullCache")
os.environ.setdefault("CACHE_REDIS_URL", "memory://")
os.environ.setdefault("CELERY_BROKER_URL", "memory://localhost/")
os.environ.setdefault("TESTING", "true")

import pytest
from unittest.mock import patch
from flask import url_for


def test_explore_route_responds():
    """Test that the explore route responds without crashing."""
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False

    with app.test_client() as client:
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


def test_explore_route_with_mock_topics():
    """Test that the explore route works when topics exist."""
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False

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

    with app.test_client() as client:
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
