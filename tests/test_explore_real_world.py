"""
Real-world test for the explore page that simulates actual user experience.

This test creates a complete application context with a real database,
seeds it with test data, and verifies the explore page renders correctly
with actual content visible to users.
"""

import os

import pytest
from bs4 import BeautifulSoup

# Set test environment before importing app. These use setdefault (not a
# hard `os.environ[...] = ...` assignment) so a value already present in the
# environment -- e.g. from the test-runner's env block, or set earlier by
# another test module executing first in the same pytest process -- wins.
# CELERY_BROKER_URL in particular used to be hard-set here unconditionally,
# which leaked "memory://localhost/" into every other test running later in
# the same process regardless of what they expected, causing an
# order-dependent failure elsewhere in the suite.
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("SERVER_NAME", "test.localhost")
os.environ.setdefault("SECRET_KEY", "test-secret-key-real-world-padding-xxxxxxxx")
os.environ.setdefault("CACHE_TYPE", "NullCache")
os.environ.setdefault("CACHE_REDIS_URL", "memory://")
os.environ.setdefault("CELERY_BROKER_URL", "memory://localhost/")
os.environ.setdefault("MAIL_SERVER", "")  # Disable mail in tests

from tests.explore_test_support import build_wired_app, make  # noqa: E402


@pytest.fixture(scope="module")
def app():
    """Create a fully configured test application with database.

    Uses build_wired_app() (see explore_test_support.py) rather than a bare
    `create_app()`: create_app() alone doesn't register the jinja globals
    (theme(), file_exists(), ...) or the before_request that populates
    g.site, both of which every real template needs (explore.html extends
    base.html). It also guarantees an in-memory SQLite database instead of
    this repo's default fallback of a real, git-tracked app.db file on disk.
    """
    from app import db
    from app.models import Community, Instance, Site, Topic, User

    application = build_wired_app()

    with application.app_context():
        # Create essential records
        site = make(
            Site,
            id=1,
            name="Test Site",
            description="Test site for real-world testing",
            private_instance=False,
            enable_downvotes=True,
            application_question="Test question",
            allowlist="",
            blocklist="",
            allow_or_block_list="neither",
            enable_nsfl=True,
            enable_nsfw=True,
            registration_mode="Open",
        )
        db.session.add(site)
        db.session.flush()

        # Create local instance
        instance = make(
            Instance,
            domain="test.localhost",
            software="pyfedi",
            version="1.2.0",
            dormant=False,
            trusted=True,
        )
        db.session.add(instance)
        db.session.flush()

        # Create test user
        user = make(
            User,
            user_name="testuser",
            email="test@test.localhost",
            password_hash="dummy",
            verified=True,
            banned=False,
            deleted=False,
            bot=False,
            reputation=100,
            instance_id=instance.id,
            ap_id="https://test.localhost/u/testuser",
            ap_public_url="https://test.localhost/u/testuser",
            ap_profile_id="https://test.localhost/u/testuser",
            ap_inbox_url="https://test.localhost/u/testuser/inbox",
            ap_preferred_username="testuser",
            ap_domain="test.localhost",
        )
        db.session.add(user)
        db.session.flush()

        # Create topics - this is what should appear on explore page
        tech_topic = make(
            Topic,
            name="Technology",
            machine_name="technology",
            num_communities=2,
        )

        science_topic = make(
            Topic,
            name="Science",
            machine_name="science",
            num_communities=1,
        )

        gaming_topic = make(
            Topic,
            name="Gaming",
            machine_name="gaming",
            parent_id=None,  # This will be updated after flush
            num_communities=1,
        )

        db.session.add_all([tech_topic, science_topic, gaming_topic])
        db.session.flush()

        # Create sub-topic
        pc_gaming_topic = make(
            Topic,
            name="PC Gaming",
            machine_name="pc-gaming",
            parent_id=gaming_topic.id,
            num_communities=1,
        )
        db.session.add(pc_gaming_topic)
        db.session.flush()

        # Create communities linked to topics
        programming_community = make(
            Community,
            name="programming",
            title="Programming Discussion",
            description="A community for programmers",
            rules="Be nice",
            topic_id=tech_topic.id,
            instance_id=instance.id,
            ap_id="https://test.localhost/c/programming",
            ap_public_url="https://test.localhost/c/programming",
            ap_profile_id="https://test.localhost/c/programming",
            ap_inbox_url="https://test.localhost/c/programming/inbox",
            ap_domain="test.localhost",
            show_all=True,
            show_popular=True,
            public_key="dummy_key",
            private_key="dummy_key",
        )

        physics_community = make(
            Community,
            name="physics",
            title="Physics Forum",
            description="Discuss physics topics",
            rules="Keep it scientific",
            topic_id=science_topic.id,
            instance_id=instance.id,
            ap_id="https://test.localhost/c/physics",
            ap_public_url="https://test.localhost/c/physics",
            ap_profile_id="https://test.localhost/c/physics",
            ap_inbox_url="https://test.localhost/c/physics/inbox",
            ap_domain="test.localhost",
            show_all=True,
            show_popular=True,
            public_key="dummy_key",
            private_key="dummy_key",
        )

        webdev_community = make(
            Community,
            name="webdev",
            title="Web Development",
            description="Web development discussion",
            rules="Be helpful",
            topic_id=tech_topic.id,
            instance_id=instance.id,
            ap_id="https://test.localhost/c/webdev",
            ap_public_url="https://test.localhost/c/webdev",
            ap_profile_id="https://test.localhost/c/webdev",
            ap_inbox_url="https://test.localhost/c/webdev/inbox",
            ap_domain="test.localhost",
            show_all=True,
            show_popular=True,
            public_key="dummy_key",
            private_key="dummy_key",
        )

        db.session.add_all(
            [programming_community, physics_community, webdev_community]
        )
        db.session.commit()

    yield application

    with application.app_context():
        db.session.remove()


@pytest.fixture
def client(app):
    """Get test client for the app."""
    return app.test_client()


def test_explore_page_shows_topics_and_communities(client, app):
    """
    Real-world test: Verify explore page displays topics and communities.

    This test simulates what a real user would see when visiting /explore
    """
    with app.app_context():
        # Make request to explore page
        response = client.get("/explore")

        # Should return success
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        # Get HTML content
        html = response.get_data(as_text=True)

        # Parse HTML with BeautifulSoup for accurate content checking
        soup = BeautifulSoup(html, "html.parser")

        # Check that we're on the explore page (has tabs)
        topics_tab = soup.find("a", {"id": "topics-pill"})
        assert topics_tab is not None, "Topics tab not found on explore page"

        feeds_tab = soup.find("a", {"id": "feeds-pill"})
        assert feeds_tab is not None, "Feeds tab not found on explore page"

        # Find the topics list
        topics_list = soup.find("ul", {"class": "topics_list"})

        # CRITICAL TEST: Topics list should exist and not be empty
        assert (
            topics_list is not None
        ), "Topics list not found - the explore page is showing empty container!"

        # Get all topic links
        topic_links = topics_list.find_all("a")
        topic_names = [link.get_text(strip=True) for link in topic_links]

        # Verify our test topics are displayed
        assert (
            "Technology" in topic_names
        ), f"Technology topic not found. Found topics: {topic_names}"
        assert (
            "Science" in topic_names
        ), f"Science topic not found. Found topics: {topic_names}"
        assert (
            "Gaming" in topic_names
        ), f"Gaming topic not found. Found topics: {topic_names}"
        assert (
            "PC Gaming" in topic_names
        ), f"PC Gaming sub-topic not found. Found topics: {topic_names}"

        # Verify it's NOT showing the empty state message
        assert (
            "There are no communities yet." not in html
        ), "Showing empty state despite having topics!"

        # Check for topic URLs (verify they're properly linked)
        tech_link = soup.find("a", href="/topic/technology")
        assert tech_link is not None, "Technology topic link not found"

        science_link = soup.find("a", href="/topic/science")
        assert science_link is not None, "Science topic link not found"

        # Verify the "More communities" button exists
        more_button = soup.find(
            "a", {"class": "btn btn-primary", "href": "/communities"}
        )
        assert more_button is not None, "More communities button not found"


def test_explore_page_empty_database(app):
    """
    Test explore page behavior when database has no topics.

    This verifies the empty state is handled gracefully.
    """
    from app import db
    from app.models import Community, Topic

    with app.app_context():
        # Clear all topics and communities
        Community.query.delete()
        Topic.query.delete()
        db.session.commit()

        with app.test_client() as client:
            response = client.get("/explore")

            assert response.status_code == 200
            html = response.get_data(as_text=True)

            # Should show empty state message
            assert (
                "There are no communities yet." in html
            ), "Empty state message not shown"

            # Should not have any topic links
            soup = BeautifulSoup(html, "html.parser")
            topics_list = soup.find("ul", {"class": "topics_list"})

            # Topics list should not exist or be empty when no topics
            if topics_list:
                topic_links = topics_list.find_all("a")
                assert (
                    len(topic_links) == 0
                ), f"Found topic links when database is empty: {topic_links}"


def test_explore_template_syntax_not_exposed(client, app):
    """
    Verify that template syntax errors are not exposed to users.

    This ensures that even if there were template issues, they wouldn't
    show raw Jinja2 syntax to users.
    """
    with app.app_context():
        response = client.get("/explore")
        html = response.get_data(as_text=True)

        # These should NEVER appear in rendered output
        forbidden_strings = [
            "len(topics)",  # The original bug
            "len(communities)",  # Similar potential bug
            "{%",  # Raw Jinja2 tags
            "{{",  # Raw Jinja2 variables
            "TemplateSyntaxError",  # Error messages
            "UndefinedError",  # Error messages
            "topics|length",  # Should be processed, not shown raw
        ]

        for forbidden in forbidden_strings:
            assert (
                forbidden not in html
            ), f"Found forbidden string in output: {forbidden}"
