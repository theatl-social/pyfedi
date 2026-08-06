"""get_ip_address() / ip_address() must not trust the raw X-Forwarded-For header.

Both functions used to fall back to `request.headers.get("X-Forwarded-For")` --
the client-supplied, leftmost entry -- whenever `CF-Connecting-IP` was absent.
`get_ip_address()` is the Flask-Limiter key function for all 13 rate-limited
endpoints (login, register, password reset, search); `ip_address()` feeds IP
bans, country blocking, and the IP recorded on users/posts/instances. A client
able to set an arbitrary `X-Forwarded-For` could pick its own rate-limit
bucket, evade an IP ban, or forge the IP attached to their account.

Fixed 2026-08-06 (SP-026): the fallback is now `request.remote_addr`, which
`ProxyFix(x_for=1)` has already resolved from the rightmost (proxy-appended)
hop. Confirmed topology: client -> Cloudflare -> haproxy -> app (one hop).
See docs/TRUSTED_CLIENT_IP.md.
"""

import pathlib

import pytest


@pytest.fixture
def app():
    from app import create_app
    from tests.conftest import TestConfig

    application = create_app(TestConfig)
    yield application


def test_get_ip_address_ignores_spoofed_x_forwarded_for(app):
    from app import get_ip_address

    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "203.0.113.7"},
        headers={"X-Forwarded-For": "10.0.0.5"},
    ):
        assert get_ip_address() == "203.0.113.7", (
            "REGRESSION: get_ip_address() trusted a client-supplied "
            "X-Forwarded-For instead of request.remote_addr. This is the "
            "Flask-Limiter key function -- a forged header lets a client "
            "pick its own rate-limit bucket."
        )


def test_ip_address_ignores_spoofed_x_forwarded_for(app):
    from app.utils import ip_address

    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "203.0.113.7"},
        headers={"X-Forwarded-For": "10.0.0.5"},
    ):
        assert ip_address() == "203.0.113.7", (
            "REGRESSION: ip_address() trusted a client-supplied "
            "X-Forwarded-For instead of request.remote_addr. This value "
            "feeds IP bans, country blocking, and the IP recorded on "
            "users/posts/instances."
        )


def test_cf_connecting_ip_still_honored(app):
    """Cloudflare overwrites this header on every proxied request; it remains
    the preferred source over remote_addr."""
    from app import get_ip_address

    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "203.0.113.7"},  # haproxy's own address
        headers={"CF-Connecting-IP": "198.51.100.9"},
    ):
        assert get_ip_address() == "198.51.100.9"


def test_neither_function_reads_the_raw_header():
    """Structural: guard against reintroducing the forgeable fallback."""
    for rel_path in ("app/__init__.py", "app/utils.py"):
        src = (pathlib.Path(__file__).resolve().parents[2] / rel_path).read_text()
        assert 'request.headers.get("X-Forwarded-For")' not in src, (
            f"REGRESSION: {rel_path} reads the raw X-Forwarded-For header "
            f"again. Its leftmost entry is client-supplied; use "
            f"request.remote_addr."
        )
