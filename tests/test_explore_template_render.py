"""
Test the explore template rendering with different data scenarios.

Originally this rendered explore.html through a bare `jinja2.Environment`
with hand-mocked globals, explicitly to avoid needing a full application
context. That doesn't work against the real template: explore.html's first
line is `{% from 'bootstrap5/form.html' import render_form -%}`, which comes
from Flask-Bootstrap's own template loader -- only registered onto
`app.jinja_loader` by `bootstrap.init_app(app)` inside `create_app()`. A bare
`jinja2.Environment(loader=FileSystemLoader(...))` never sees it and raises
`TemplateNotFound: 'bootstrap5/form.html'` before rendering anything, so
these two tests could never actually have passed. base.html (which
explore.html extends) also needs `g.site` and the jinja globals/context
processor that only pyfedi.py registers on top of `create_app()` -- see
tests/explore_test_support.py for why a full, correctly-wired Flask app is
required and how it's built safely (in-memory SQLite, not the real app.db).

The topics/menu data is still passed explicitly to render_template(), same
as before, so what each test actually exercises (empty-state vs.
topics-rendered) is unchanged.
"""

import os

import pytest
from flask import render_template

from tests.explore_test_support import build_wired_app, make


@pytest.fixture(scope="module")
def app():
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


def _render(app, **context):
    """Render explore.html inside a real request context so before_request
    (which sets g.site/g.nonce/g.locale) and the app's context processor run
    exactly as they would for a real /explore request."""
    with app.test_request_context("/explore"):
        app.preprocess_request()
        return render_template(
            "explore.html",
            menu_instance_feeds=[],
            menu_my_feeds=None,
            menu_subscribed_feeds=None,
            **context,
        )


def test_explore_template_renders_with_empty_topics(app):
    """Test that explore template renders when topics list is empty."""
    rendered = _render(app, topics=[])

    # Should render without errors
    assert rendered is not None
    assert len(rendered) > 0

    # Should contain the empty state message
    assert "There are no communities yet." in rendered

    # Should contain basic structure
    assert "Topics" in rendered
    assert "Feeds" in rendered


def test_explore_template_renders_with_topics(app):
    """Test that explore template renders when topics exist."""

    # Mock topic object
    class MockTopic:
        def __init__(self, name):
            self.name = name

        def path(self):
            return self.name.lower().replace(" ", "-")

    # Create mock topic tree structure
    mock_topics = [
        {
            "topic": MockTopic("Technology"),
            "children": [{"topic": MockTopic("Programming"), "children": []}],
        },
        {"topic": MockTopic("Science"), "children": []},
    ]

    rendered = _render(app, topics=mock_topics)

    # Should render without errors
    assert rendered is not None
    assert len(rendered) > 0

    # Should contain topic names
    assert "Technology" in rendered
    assert "Science" in rendered
    assert "Programming" in rendered

    # Should NOT contain empty state message
    assert "There are no communities yet." not in rendered


def test_explore_template_length_filter_usage():
    """Test that the template correctly uses |length filter."""
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "app", "templates", "explore.html"
    )

    if not os.path.exists(template_path):
        pytest.skip("explore.html template not found")

    with open(template_path, "r") as f:
        template_content = f.read()

    # The critical line that was causing the bug
    assert (
        "topics|length > 0" in template_content
    ), "Template should use |length filter on line 20"

    # Make sure it doesn't use the old buggy syntax
    assert (
        "len(topics)" not in template_content
    ), "Template should not use Python len() function"
