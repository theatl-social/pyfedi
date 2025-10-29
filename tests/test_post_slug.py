import pytest
from unittest.mock import Mock, patch

from app import create_app, db
from app.models import Post, Community
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


def test_generate_slug_basic(app):
    """Test basic slug generation with no conflicts"""
    with app.app_context():
        # Create a mock community
        community = Mock()
        community.name = "testcommunity@example.com"
        community.lemmy_link.return_value = "!testcommunity@example.com"

        # Create a mock post
        post = Post()
        post.id = 123
        post.title = "This is a Test Post"
        post.slug = None

        # Mock Post.get_by_slug to return None (no conflicts)
        with patch.object(Post, "get_by_slug", return_value=None):
            post.generate_slug(community)

        # Verify the slug was generated correctly
        assert post.slug is not None
        assert post.slug.startswith("/c/testcommunity@example.com/p/123/")
        assert "this-is-a-test-post" in post.slug


def test_generate_slug_with_one_conflict(app):
    """Test slug generation when one slug already exists"""
    with app.app_context():
        community = Mock()
        community.name = "testcommunity@example.com"
        community.lemmy_link.return_value = "!testcommunity@example.com"

        post = Post()
        post.id = 456
        post.title = "Duplicate Title"
        post.slug = None

        expected_base_slug = "/c/testcommunity@example.com/p/456/duplicate-title"

        # Mock Post.get_by_slug to return a conflict for base slug, then None
        def mock_get_by_slug(slug):
            if slug == expected_base_slug:
                return Mock()  # Existing post found
            else:
                return None  # No conflict

        with patch.object(Post, "get_by_slug", side_effect=mock_get_by_slug):
            post.generate_slug(community)

        # Should append "1" to the slug
        assert post.slug == f"{expected_base_slug}1"


def test_generate_slug_with_multiple_conflicts(app):
    """Test slug generation when multiple slugs already exist"""
    with app.app_context():
        community = Mock()
        community.name = "community@server.com"
        community.lemmy_link.return_value = "!community@server.com"

        post = Post()
        post.id = 789
        post.title = "Popular Title"
        post.slug = None

        expected_base_slug = "/c/community@server.com/p/789/popular-title"

        # Mock Post.get_by_slug to return conflicts for base, 1, 2, then None for 3
        def mock_get_by_slug(slug):
            if slug in [
                expected_base_slug,
                f"{expected_base_slug}1",
                f"{expected_base_slug}2",
            ]:
                return Mock()  # Existing post found
            else:
                return None  # No conflict

        with patch.object(Post, "get_by_slug", side_effect=mock_get_by_slug):
            post.generate_slug(community)

        # Should append "3" to the slug
        assert post.slug == f"{expected_base_slug}3"


def test_generate_slug_fallback_after_ten_conflicts(app):
    """Test that after 10 conflicts, it falls back to simple /post/{id} format"""
    with app.app_context():
        community = Mock()
        community.name = "busy@example.com"
        community.lemmy_link.return_value = "!busy@example.com"

        post = Post()
        post.id = 999
        post.title = "Very Popular Title"
        post.slug = None

        # Mock Post.get_by_slug to always return a conflict (simulate many existing posts)
        with patch.object(Post, "get_by_slug", return_value=Mock()):
            post.generate_slug(community)

        # Should fall back to simple format after 10 attempts
        assert post.slug == "/post/999"


def test_generate_slug_does_not_overwrite_existing_slug(app):
    """Test that generate_slug does nothing if slug already exists"""
    with app.app_context():
        community = Mock()
        community.name = "test@example.com"
        community.lemmy_link.return_value = "!test@example.com"

        post = Post()
        post.id = 111
        post.title = "Test Title"
        post.slug = "/existing/custom/slug"

        original_slug = post.slug

        # Call generate_slug - it should not modify the existing slug
        post.generate_slug(community)

        assert post.slug == original_slug


def test_generate_slug_with_empty_string_slug(app):
    """Test that generate_slug works when slug is empty string"""
    with app.app_context():
        community = Mock()
        community.name = "test@example.com"
        community.lemmy_link.return_value = "!test@example.com"

        post = Post()
        post.id = 222
        post.title = "New Post"
        post.slug = ""

        with patch.object(Post, "get_by_slug", return_value=None):
            post.generate_slug(community)

        assert post.slug != ""
        assert post.slug.startswith("/c/test@example.com/p/222/")


def test_generate_slug_with_special_characters(app):
    """Test slug generation with title containing special characters"""
    with app.app_context():
        community = Mock()
        community.name = "test@example.com"
        community.lemmy_link.return_value = "!test@example.com"

        post = Post()
        post.id = 333
        post.title = "Hello! How are you? & Welcome #2024"
        post.slug = None

        with patch.object(Post, "get_by_slug", return_value=None):
            post.generate_slug(community)

        # Special characters should be handled by slugify
        assert post.slug is not None
        assert "/p/333/" in post.slug
        # Verify no special characters remain (except hyphens and slashes in path)
        slug_part = post.slug.split("/p/333/")[1]
        assert all(c.isalnum() or c == "-" for c in slug_part)


def test_generate_slug_uniqueness_logic(app):
    """Test that the slug generation correctly builds unique slugs without accumulation"""
    with app.app_context():
        community = Mock()
        community.name = "test@server.com"
        community.lemmy_link.return_value = "!test@server.com"

        post = Post()
        post.id = 555
        post.title = "Test"
        post.slug = None

        expected_base_slug = "/c/test@server.com/p/555/test"

        # Track all slugs that get_by_slug was called with
        slugs_checked = []

        def mock_get_by_slug(slug):
            slugs_checked.append(slug)
            # First two attempts have conflicts
            if len(slugs_checked) <= 2:
                return Mock()
            return None

        with patch.object(Post, "get_by_slug", side_effect=mock_get_by_slug):
            post.generate_slug(community)

        # Verify the correct sequence of slugs was checked
        assert slugs_checked[0] == expected_base_slug
        assert slugs_checked[1] == f"{expected_base_slug}1"
        assert slugs_checked[2] == f"{expected_base_slug}2"

        # Verify final slug is correct (not accumulated like "test12")
        assert post.slug == f"{expected_base_slug}2"


# Tests for generate_ap_id()


def test_generate_ap_id_basic(app):
    """Test basic AP ID generation with no conflicts"""
    with app.app_context():
        # Create a mock community
        community = Mock()
        community.name = "testcommunity@example.com"
        community.lemmy_link.return_value = "!testcommunity@example.com"

        # Create a mock post
        post = Post()
        post.id = 123
        post.title = "This is a Test Post"
        post.ap_id = None

        # Mock Post.get_by_ap_id to return None (no conflicts)
        with patch.object(Post, "get_by_ap_id", return_value=None):
            post.generate_ap_id(community)

        # Verify the AP ID was generated correctly
        assert post.ap_id is not None
        assert post.ap_id.startswith("https://")
        assert "/c/testcommunity@example.com/p/123/" in post.ap_id
        assert "this-is-a-test-post" in post.ap_id

        # Verify the slug was also set
        assert post.slug is not None
        assert post.slug.startswith("/c/testcommunity@example.com/p/123/")
        assert "this-is-a-test-post" in post.slug


def test_generate_ap_id_with_one_conflict(app):
    """Test AP ID generation when one AP ID already exists"""
    with app.app_context():
        from flask import current_app

        community = Mock()
        community.name = "testcommunity@example.com"
        community.lemmy_link.return_value = "!testcommunity@example.com"

        post = Post()
        post.id = 456
        post.title = "Duplicate Title"
        post.ap_id = None

        protocol = current_app.config["HTTP_PROTOCOL"]
        server = current_app.config["SERVER_NAME"]
        expected_base_ap_id = (
            f"{protocol}://{server}/c/testcommunity@example.com/p/456/duplicate-title"
        )
        expected_base_slug = "/c/testcommunity@example.com/p/456/duplicate-title"

        # Mock Post.get_by_ap_id to return a conflict for base AP ID, then None
        def mock_get_by_ap_id(ap_id):
            if ap_id == expected_base_ap_id:
                return Mock()  # Existing post found
            else:
                return None  # No conflict

        with patch.object(Post, "get_by_ap_id", side_effect=mock_get_by_ap_id):
            post.generate_ap_id(community)

        # Should append "1" to both AP ID and slug
        assert post.ap_id == f"{expected_base_ap_id}1"
        assert post.slug == f"{expected_base_slug}1"


def test_generate_ap_id_with_multiple_conflicts(app):
    """Test AP ID generation when multiple AP IDs already exist"""
    with app.app_context():
        from flask import current_app

        community = Mock()
        community.name = "community@server.com"
        community.lemmy_link.return_value = "!community@server.com"

        post = Post()
        post.id = 789
        post.title = "Popular Title"
        post.ap_id = None

        protocol = current_app.config["HTTP_PROTOCOL"]
        server = current_app.config["SERVER_NAME"]
        expected_base_ap_id = (
            f"{protocol}://{server}/c/community@server.com/p/789/popular-title"
        )
        expected_base_slug = "/c/community@server.com/p/789/popular-title"

        # Mock Post.get_by_ap_id to return conflicts for base, 1, 2, then None for 3
        def mock_get_by_ap_id(ap_id):
            if ap_id in [
                expected_base_ap_id,
                f"{expected_base_ap_id}1",
                f"{expected_base_ap_id}2",
            ]:
                return Mock()  # Existing post found
            else:
                return None  # No conflict

        with patch.object(Post, "get_by_ap_id", side_effect=mock_get_by_ap_id):
            post.generate_ap_id(community)

        # Should append "3" to both AP ID and slug
        assert post.ap_id == f"{expected_base_ap_id}3"
        assert post.slug == f"{expected_base_slug}3"


def test_generate_ap_id_fallback_after_ten_conflicts(app):
    """Test that after 10 conflicts, it falls back to simple /post/{id} format"""
    with app.app_context():
        from flask import current_app

        community = Mock()
        community.name = "busy@example.com"
        community.lemmy_link.return_value = "!busy@example.com"

        post = Post()
        post.id = 999
        post.title = "Very Popular Title"
        post.ap_id = None

        protocol = current_app.config["HTTP_PROTOCOL"]
        server = current_app.config["SERVER_NAME"]

        # Mock Post.get_by_ap_id to always return a conflict (simulate many existing posts)
        with patch.object(Post, "get_by_ap_id", return_value=Mock()):
            post.generate_ap_id(community)

        # Should fall back to simple format after 10 attempts
        assert post.ap_id == f"{protocol}://{server}/post/999"
        assert post.slug == "/post/999"


def test_generate_ap_id_does_not_overwrite_existing(app):
    """Test that generate_ap_id does nothing if AP ID already exists"""
    with app.app_context():
        community = Mock()
        community.name = "test@example.com"
        community.lemmy_link.return_value = "!test@example.com"

        post = Post()
        post.id = 111
        post.title = "Test Title"
        post.ap_id = "https://remote.instance/post/original-ap-id"

        original_ap_id = post.ap_id

        # Call generate_ap_id - it should not modify the existing AP ID
        # Note: The condition checks for None, empty string, or length == 10
        post.generate_ap_id(community)

        assert post.ap_id == original_ap_id


def test_generate_ap_id_with_empty_string(app):
    """Test that generate_ap_id works when AP ID is empty string"""
    with app.app_context():
        community = Mock()
        community.name = "test@example.com"
        community.lemmy_link.return_value = "!test@example.com"

        post = Post()
        post.id = 222
        post.title = "New Post"
        post.ap_id = ""

        with patch.object(Post, "get_by_ap_id", return_value=None):
            post.generate_ap_id(community)

        assert post.ap_id != ""
        assert post.ap_id.startswith("https://")
        assert "/c/test@example.com/p/222/" in post.ap_id


def test_generate_ap_id_with_length_ten_string(app):
    """Test that generate_ap_id regenerates when AP ID length is exactly 10"""
    with app.app_context():
        community = Mock()
        community.name = "test@example.com"
        community.lemmy_link.return_value = "!test@example.com"

        post = Post()
        post.id = 333
        post.title = "New Post"
        post.ap_id = "0123456789"  # Exactly 10 characters

        with patch.object(Post, "get_by_ap_id", return_value=None):
            post.generate_ap_id(community)

        # Should regenerate despite having an AP ID (length == 10 is a special case)
        assert post.ap_id != "0123456789"
        assert post.ap_id.startswith("https://")


def test_generate_ap_id_uniqueness_logic(app):
    """Test that AP ID generation correctly builds unique IDs without accumulation"""
    with app.app_context():
        from flask import current_app

        community = Mock()
        community.name = "test@server.com"
        community.lemmy_link.return_value = "!test@server.com"

        post = Post()
        post.id = 555
        post.title = "Test"
        post.ap_id = None

        protocol = current_app.config["HTTP_PROTOCOL"]
        server = current_app.config["SERVER_NAME"]
        expected_base_ap_id = f"{protocol}://{server}/c/test@server.com/p/555/test"
        expected_base_slug = "/c/test@server.com/p/555/test"

        # Track all AP IDs that get_by_ap_id was called with
        ap_ids_checked = []

        def mock_get_by_ap_id(ap_id):
            ap_ids_checked.append(ap_id)
            # First two attempts have conflicts
            if len(ap_ids_checked) <= 2:
                return Mock()
            return None

        with patch.object(Post, "get_by_ap_id", side_effect=mock_get_by_ap_id):
            post.generate_ap_id(community)

        # Verify the correct sequence of AP IDs was checked
        assert ap_ids_checked[0] == expected_base_ap_id
        assert ap_ids_checked[1] == f"{expected_base_ap_id}1"
        assert ap_ids_checked[2] == f"{expected_base_ap_id}2"

        # Verify final AP ID and slug are correct (not accumulated like "test12")
        assert post.ap_id == f"{expected_base_ap_id}2"
        assert post.slug == f"{expected_base_slug}2"


def test_generate_ap_id_with_special_characters(app):
    """Test AP ID generation with title containing special characters"""
    with app.app_context():
        community = Mock()
        community.name = "test@example.com"
        community.lemmy_link.return_value = "!test@example.com"

        post = Post()
        post.id = 444
        post.title = "Hello! How are you? & Welcome #2024"
        post.ap_id = None

        with patch.object(Post, "get_by_ap_id", return_value=None):
            post.generate_ap_id(community)

        # Special characters should be handled by slugify
        assert post.ap_id is not None
        assert "/p/444/" in post.ap_id
        # Verify no special characters remain in the slug part
        ap_id_slug_part = post.ap_id.split("/p/444/")[1]
        assert all(c.isalnum() or c == "-" for c in ap_id_slug_part)
