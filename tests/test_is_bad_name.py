"""
Tests for is_bad_name() community filtering helper.

This function filters community names containing profanity or low-effort patterns,
based on George Carlin's "Seven Words" plus additional terms.
"""

import os
import pytest


# Set up environment before importing app
os.environ.setdefault("SERVER_NAME", "test.localhost")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CACHE_TYPE", "NullCache")
os.environ.setdefault("TESTING", "true")


@pytest.fixture(scope="module")
def app_context():
    """Create app context for tests that need it"""
    from app import create_app

    app = create_app()
    with app.app_context():
        yield app


@pytest.fixture(scope="module")
def is_bad_name(app_context):
    """Import is_bad_name within app context to avoid circular imports"""
    from app.community.util import is_bad_name

    return is_bad_name


class TestIsBadName:
    """Test the is_bad_name() community name filter"""

    def test_clean_names_pass(self, is_bad_name):
        """Normal community names should pass the filter"""
        clean_names = [
            "python",
            "programming",
            "news",
            "science",
            "technology",
            "gaming",
            "movies",
            "books",
            "photography",
            "art",
            "music",
            "food",
            "travel",
            "fitness",
            "DIY",
            "worldnews",
            "askscience",
            "explainlikeimfive",
        ]
        for name in clean_names:
            assert is_bad_name(name) is False, f"'{name}' should be allowed"

    def test_profanity_blocked(self, is_bad_name):
        """Community names with profanity should be blocked"""
        # These are the "seven words" from Carlin's bit
        bad_names = [
            "shit",
            "piss",
            "fuck",
            "cunt",
            "cocksucker",
            "motherfucker",
            "tits",
        ]
        for name in bad_names:
            assert is_bad_name(name) is True, f"'{name}' should be blocked"

    def test_low_effort_patterns_blocked(self, is_bad_name):
        """Low-effort community name patterns should be blocked"""
        low_effort = [
            "greentext",
            "4chan",
        ]
        for name in low_effort:
            assert is_bad_name(name) is True, f"'{name}' should be blocked"

    def test_case_insensitive(self, is_bad_name):
        """Filter should be case-insensitive"""
        variations = [
            "SHIT",
            "Shit",
            "sHiT",
            "FUCK",
            "Fuck",
            "FuCk",
            "GREENTEXT",
            "GreenText",
            "4CHAN",
            "4Chan",
        ]
        for name in variations:
            assert (
                is_bad_name(name) is True
            ), f"'{name}' should be blocked (case-insensitive)"

    def test_substring_matching(self, is_bad_name):
        """Words containing blocked terms should also be blocked"""
        # Names that contain blocked words as substrings
        substring_cases = [
            "bullshit",
            "noshit",
            "shitposting",
            "fuckery",
            "clusterfuck",
            "unfuckingbelievable",
            "4channers",
            "greentextstories",
        ]
        for name in substring_cases:
            assert is_bad_name(name) is True, f"'{name}' should be blocked (substring)"

    def test_similar_but_allowed(self, is_bad_name):
        """Names that are similar but don't contain blocked words should pass"""
        similar_allowed = [
            "ship",  # not "shit"
            "duck",  # not "fuck"
            "pass",  # not "piss"
            "hunt",  # not "cunt"
            "bits",  # not "tits"
            "greentech",  # not "greentext"
            "chan",  # not "4chan"
            "mother",  # not "motherfucker"
        ]
        for name in similar_allowed:
            assert is_bad_name(name) is False, f"'{name}' should be allowed"

    def test_empty_string(self, is_bad_name):
        """Empty string should be allowed (not a bad name)"""
        assert is_bad_name("") is False

    def test_numeric_names(self, is_bad_name):
        """Numeric-only names should be allowed"""
        assert is_bad_name("123") is False
        assert is_bad_name("2024") is False

    def test_special_characters(self, is_bad_name):
        """Names with special characters should be properly evaluated"""
        # These contain blocked words
        assert is_bad_name("f_u_c_k") is False  # underscores break the word
        assert is_bad_name("f.u.c.k") is False  # dots break the word
        # But direct matches still work
        assert is_bad_name("shit_posting") is True  # contains "shit"
