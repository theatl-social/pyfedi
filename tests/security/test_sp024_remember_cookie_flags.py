"""SP-024 regression: the remember-me cookie must be as hardened as the session cookie.

Flask-Login configures its remember-me cookie separately from Flask's session
cookie, and its library defaults are weaker — flask_login/config.py ships
`COOKIE_SECURE = False` and `COOKIE_SAMESITE = None`, which login_manager.py reads
via `config.get("REMEMBER_COOKIE_*", <library default>)`.

That matters here because `app/auth/routes.py` calls `login_user(user, remember=True)`
on every login, so the 365-day remember cookie is the long-lived credential. Leaving
REMEMBER_COOKIE_* unset gave it no Secure flag (transmissible over plain HTTP) and no
explicit SameSite, while the short-lived session cookie had both.

These tests assert the two cookies stay in sync, so a future change that hardens one
without the other is caught.
"""

import pytest

SESSION_KEYS = [
    "SESSION_COOKIE_SECURE",
    "SESSION_COOKIE_HTTPONLY",
    "SESSION_COOKIE_SAMESITE",
]
REMEMBER_KEYS = [
    "REMEMBER_COOKIE_SECURE",
    "REMEMBER_COOKIE_HTTPONLY",
    "REMEMBER_COOKIE_SAMESITE",
]


@pytest.fixture(scope="module")
def app():
    from app import create_app
    from config import Config

    class _TestConfig(Config):
        TESTING = True
        SERVER_NAME = "localhost"
        SECRET_KEY = "test-secret-key-for-ci-padding-must-be-32-plus-chars"
        CACHE_TYPE = "NullCache"

    return create_app(_TestConfig)


@pytest.mark.parametrize("key", REMEMBER_KEYS)
def test_remember_cookie_setting_is_explicit(app, key):
    """Unset means Flask-Login silently falls back to its weaker library default."""
    assert key in app.config, (
        f"SP-024 REGRESSION: {key} is unset, so Flask-Login falls back to its "
        f"library default (COOKIE_SECURE=False / COOKIE_SAMESITE=None). "
        f"See SECURITY_PATCHES.md SP-024."
    )


def test_remember_cookie_is_secure(app):
    assert app.config["REMEMBER_COOKIE_SECURE"] is True, (
        "SP-024 REGRESSION: the 365-day remember-me cookie may be transmitted "
        "over plain HTTP."
    )


def test_remember_cookie_is_httponly(app):
    assert app.config["REMEMBER_COOKIE_HTTPONLY"] is True, (
        "SP-024 REGRESSION: the remember-me cookie is readable from JavaScript."
    )


def test_remember_cookie_samesite_is_explicit_lax(app):
    """An omitted SameSite leans on browser defaults, and Chrome's Lax+POST
    intervention grants a ~2 minute cross-site POST window to cookies that have
    no explicit SameSite attribute."""
    assert app.config["REMEMBER_COOKIE_SAMESITE"] == "Lax", (
        "SP-024 REGRESSION: remember-me cookie SameSite is not explicitly Lax."
    )


@pytest.mark.parametrize("session_key,remember_key", zip(SESSION_KEYS, REMEMBER_KEYS))
def test_remember_cookie_matches_session_cookie(app, session_key, remember_key):
    """The two cookies must be hardened together — hardening one alone leaves the
    other as the weak link."""
    assert app.config[remember_key] == app.config[session_key], (
        f"SP-024 REGRESSION: {remember_key}={app.config[remember_key]!r} but "
        f"{session_key}={app.config[session_key]!r}. The remember-me cookie is the "
        f"longer-lived credential; it must not be weaker than the session cookie."
    )


def test_flask_login_defaults_are_still_weak():
    """Guards the premise: if Flask-Login ever ships secure defaults, this patch
    becomes redundant rather than load-bearing, and the note in SECURITY_PATCHES.md
    should be revisited."""
    from flask_login import config as fl_config

    assert fl_config.COOKIE_SECURE is False and fl_config.COOKIE_SAMESITE is None, (
        "Flask-Login now ships hardened cookie defaults -- SP-024 may be redundant. "
        "Re-read SECURITY_PATCHES.md SP-024 before removing anything."
    )
