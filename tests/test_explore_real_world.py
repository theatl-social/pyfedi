"""
Real-world test for the explore page that simulates actual user experience.

This test creates a complete application context with a real database,
seeds it with test data, and verifies the explore page renders correctly
with actual content visible to users.
"""

import os
import tempfile
import pytest
from bs4 import BeautifulSoup
from unittest.mock import patch, MagicMock

# Set test environment before importing app
os.environ["TESTING"] = "true"
os.environ["SERVER_NAME"] = "test.localhost"
os.environ["SECRET_KEY"] = "test-secret-key-real-world"
os.environ["CACHE_TYPE"] = "NullCache"
os.environ["CACHE_REDIS_URL"] = "memory://"
os.environ["CELERY_BROKER_URL"] = "memory://localhost/"
os.environ["MAIL_SERVER"] = ""  # Disable mail in tests

# Use a temporary SQLite database for tests
test_db_fd, test_db_path = tempfile.mkstemp()
os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"


@pytest.fixture(scope="module")
def app():
    """Create a fully configured test application with database."""
    from app import create_app, db
    from app.models import Site, Instance, User, Topic, Community

    # Patch PostgreSQL-specific functions that don't work in SQLite
    with patch("app.models.db.engine.execute") as mock_execute:
        # Mock the PostgreSQL function creation that fails in SQLite
        mock_execute.return_value = MagicMock()

        app = create_app()
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        app.config["PRIVATE_INSTANCE"] = False

        with app.app_context():
            # Create tables (skip the PostgreSQL-specific functions)
            with patch("sqlalchemy.schema.DDL") as mock_ddl:
                mock_ddl.return_value = MagicMock()

                # Create core tables only
                db.metadata.create_all(
                    db.engine,
                    tables=[
                        db.metadata.tables.get("site"),
                        db.metadata.tables.get("instance"),
                        db.metadata.tables.get("user"),
                        db.metadata.tables.get("topic"),
                        db.metadata.tables.get("community"),
                        db.metadata.tables.get("community_member"),
                        db.metadata.tables.get("post"),
                        db.metadata.tables.get("file"),
                        db.metadata.tables.get("actor"),
                        db.metadata.tables.get("domain"),
                        db.metadata.tables.get("domain_ban"),
                    ],
                    checkfirst=True,
                )

            # Create essential records
            site = Site(
                name="Test Site",
                description="Test site for real-world testing",
                private_instance=False,
                enable_downvotes=True,
                show_nsfw_content=True,
                application_question="Test question",
                allowlist="",
                blocklist="",
                allow_or_block_list="neither",
                enable_nsfl_content=True,
                show_communities_above_posts=True,
                federation=False,  # Disable federation for tests
                google_site_verification="",
                msvalidate="",
                yandex_verification="",
                searchable=True,
                enable_login=True,
                enable_guest_login=False,
                legal_page_id=None,
                privacy_page_id=None,
                csp_text="",
            )
            db.session.add(site)
            db.session.flush()

            # Create local instance
            instance = Instance(
                domain="test.localhost",
                software="pyfedi",
                version="1.2.0",
                online=True,
                indexed=True,
                dormant=False,
                trusted=True,
            )
            db.session.add(instance)
            db.session.flush()

            # Create test user
            user = User(
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
            tech_topic = Topic(
                name="Technology",
                machine_name="technology",
                ap_id="https://test.localhost/t/technology",
                num_communities=2,
            )

            science_topic = Topic(
                name="Science",
                machine_name="science",
                ap_id="https://test.localhost/t/science",
                num_communities=1,
            )

            gaming_topic = Topic(
                name="Gaming",
                machine_name="gaming",
                ap_id="https://test.localhost/t/gaming",
                parent_id=None,  # This will be updated after flush
                num_communities=1,
            )

            db.session.add_all([tech_topic, science_topic, gaming_topic])
            db.session.flush()

            # Create sub-topic
            pc_gaming_topic = Topic(
                name="PC Gaming",
                machine_name="pc-gaming",
                ap_id="https://test.localhost/t/pc-gaming",
                parent_id=gaming_topic.id,
                num_communities=1,
            )
            db.session.add(pc_gaming_topic)
            db.session.flush()

            # Create communities linked to topics
            programming_community = Community(
                name="programming",
                title="Programming Discussion",
                description="A community for programmers",
                rules="Be nice",
                topic_id=tech_topic.id,
                instance_id=instance.id,
                created_by=user.id,
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

            physics_community = Community(
                name="physics",
                title="Physics Forum",
                description="Discuss physics topics",
                rules="Keep it scientific",
                topic_id=science_topic.id,
                instance_id=instance.id,
                created_by=user.id,
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

            webdev_community = Community(
                name="webdev",
                title="Web Development",
                description="Web development discussion",
                rules="Be helpful",
                topic_id=tech_topic.id,
                instance_id=instance.id,
                created_by=user.id,
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

            # Store site in g-like object for request context
            @app.before_request
            def load_site():
                from flask import g

                g.site = site

        yield app

        # Cleanup
        with app.app_context():
            db.drop_all()

    # Clean up temp database
    os.close(test_db_fd)
    os.unlink(test_db_path)


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

        print("✅ Real-world test passed: Explore page displays topics correctly!")
        print(f"   Found {len(topic_names)} topics displayed")
        print(f"   Topics: {', '.join(topic_names)}")


def test_explore_page_empty_database(app):
    """
    Test explore page behavior when database has no topics.

    This verifies the empty state is handled gracefully.
    """
    from app import db
    from app.models import Topic, Community

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

            print(
                "✅ Empty state test passed: Shows appropriate message when no topics exist"
            )


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

        print("✅ Template security test passed: No raw template syntax exposed")


if __name__ == "__main__":
    """Run tests standalone with detailed output."""
    import sys
    import traceback

    # Create test app and client
    try:
        from app import create_app

        print("🧪 Running real-world explore page tests...\n")

        # Run each test
        for test_func in [
            test_explore_page_shows_topics_and_communities,
            test_explore_page_empty_database,
            test_explore_template_syntax_not_exposed,
        ]:
            # Create fresh app for each test
            app_fixture = app()
            test_app = next(app_fixture)

            with test_app.test_client() as test_client:
                try:
                    if (
                        test_func.__name__
                        == "test_explore_page_shows_topics_and_communities"
                    ):
                        test_func(test_client, test_app)
                    elif test_func.__name__ == "test_explore_page_empty_database":
                        test_func(test_app)
                    else:
                        test_func(test_client, test_app)

                except AssertionError as e:
                    print(f"❌ {test_func.__name__} failed: {e}")
                    traceback.print_exc()
                    sys.exit(1)
                except Exception as e:
                    print(f"❌ {test_func.__name__} error: {e}")
                    traceback.print_exc()
                    sys.exit(1)

        print("\n🎉 All real-world tests passed!")
        print("The explore page is working correctly with actual data.")

    except Exception as e:
        print(f"❌ Test setup failed: {e}")
        traceback.print_exc()
        sys.exit(1)
