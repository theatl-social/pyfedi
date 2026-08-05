"""The admin API's IP allowlist must not be bypassable via X-Forwarded-For.

Two related defects, both fixed on 2026-08-05:

1. **The allowlist was inert.** `get_private_registration_allowed_ips()` read
   only `get_setting("PRIVATE_REGISTRATION_IPS")` — a row in the `settings`
   table that no CLI command, admin route or startup path ever writes. So the
   list was always empty, `is_ip_whitelisted()` treats empty as "no restriction
   configured" and returned `True` for every address. One of the four gates in
   front of an account-provisioning API was silently absent, while
   `docs/PRIVATE_REGISTRATION_TESTING.md` and `ADMIN_API.md` told operators to
   configure it through environment variables nothing read.

2. **It trusted the client's own header.** `validate_private_registration_request()`
   read the raw `HTTP_X_FORWARDED_FOR` and took the *leftmost* entry, which is
   whatever the client sent. Anyone could add `X-Forwarded-For: <allowed ip>`
   and satisfy the check. Latent while (1) made the allowlist inert — and
   actively dangerous once it started enforcing, because it would then look like
   an access control while admitting everyone.

The correct source is `request.remote_addr`, which `ProxyFix(x_for=1)`
(`app/__init__.py`) has already resolved from the *rightmost* hop — the one our
own reverse proxy appended and a client cannot forge.
"""

import os
from unittest.mock import patch

import pytest

from app.api.admin.security import is_ip_whitelisted
from app.utils import get_private_registration_allowed_ips


@pytest.fixture
def app():
    from app import create_app, db
    from tests.conftest import TestConfig, create_all_for_tests

    application = create_app(TestConfig)
    # Tables are required: with no environment variable set,
    # get_private_registration_allowed_ips() falls through to
    # get_setting("PRIVATE_REGISTRATION_IPS"), which queries `settings`.
    with application.app_context():
        create_all_for_tests(db)
        yield application
        db.session.remove()


ALLOWED = "10.0.0.0/8"


def test_allowlist_reads_the_environment(app):
    """Defect 1: it previously read only a settings row nothing ever writes."""
    with app.app_context():
        with patch.dict(os.environ, {"PRIVATE_REGISTRATION_IPS": ALLOWED}):
            assert get_private_registration_allowed_ips() == [ALLOWED], (
                "REGRESSION: PRIVATE_REGISTRATION_IPS is ignored again, so the "
                "allowlist is inert and admits every address."
            )


def test_allowlist_accepts_the_other_documented_spelling(app):
    """ADMIN_API.md and the testing guide disagree; both must work."""
    with app.app_context():
        with patch.dict(os.environ, {"PRIVATE_REGISTRATION_ALLOWED_IPS": ALLOWED}):
            assert get_private_registration_allowed_ips() == [ALLOWED]


def test_configured_allowlist_actually_rejects(app):
    with app.app_context():
        with patch.dict(os.environ, {"PRIVATE_REGISTRATION_IPS": ALLOWED}):
            assert is_ip_whitelisted("10.1.2.3") is True
            assert is_ip_whitelisted("1.2.3.4") is False, (
                "REGRESSION: an address outside the configured range was "
                "admitted. The allowlist is not enforcing."
            )


def test_unconfigured_allowlist_is_open_by_design(app):
    """No allowlist configured means no IP restriction — the secret still gates."""
    with app.app_context():
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PRIVATE_REGISTRATION_IPS", None)
            os.environ.pop("PRIVATE_REGISTRATION_ALLOWED_IPS", None)
            assert is_ip_whitelisted("1.2.3.4") is True


def test_x_forwarded_for_cannot_forge_an_allowed_source(app):
    """Defect 2: the check must use ProxyFix's remote_addr, not the raw header.

    Driven through the real WSGI stack so ProxyFix participates: the request
    arrives from a disallowed address while claiming an allowed one.
    """
    from werkzeug.exceptions import Forbidden

    from app.api.admin.security import validate_private_registration_request

    with app.app_context():
        with patch.dict(
            os.environ,
            {
                "PRIVATE_REGISTRATION_IPS": ALLOWED,
                "PRIVATE_REGISTRATION_ENABLED": "true",
            },
        ):
            # REMOTE_ADDR is the untrusted peer; the header is the forgery.
            with app.test_request_context(
                "/api/alpha/admin/users",
                environ_base={"REMOTE_ADDR": "203.0.113.7"},
                headers={"X-Forwarded-For": "10.0.0.5"},
            ):
                with pytest.raises(Forbidden) as exc:
                    validate_private_registration_request()
                assert "IP not authorized" in str(exc.value), (
                    "REGRESSION: a spoofed X-Forwarded-For satisfied the IP "
                    "allowlist. The check must read request.remote_addr, which "
                    "ProxyFix resolves from the rightmost (proxy-appended) hop."
                )


def test_security_module_does_not_read_the_raw_header():
    """Structural: the raw header must not come back as the IP source."""
    import pathlib

    src = (
        pathlib.Path(__file__).resolve().parents[2]
        / "app"
        / "api"
        / "admin"
        / "security.py"
    ).read_text()
    offending = 'request.environ.get("HTTP_X_FORWARDED_FOR"'
    assert offending not in src, (
        "REGRESSION: validate_private_registration_request() reads the raw "
        "X-Forwarded-For header again. That value is client-supplied; use "
        "request.remote_addr (already normalised by ProxyFix)."
    )
