"""SP-002 regression: outbound HTTP requests must refuse internal targets.

These tests exercise the SSRF guard module directly. They do NOT require
Flask, DB, or Redis.
"""

import socket
from unittest.mock import patch

import pytest

from app.activitypub.ssrf_guard import (
    SsrfBlocked,
    safe_httpx_get,
    validate_outbound_url,
)


# --- validate_outbound_url ---------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost/",
        "http://127.0.0.1:6379/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[fd00:ec2::254]/",
        "http://0.0.0.0/",
        "https://127.0.0.1/",
    ],
)
def test_blocks_private_loopback_metadata_and_unspecified(url):
    with pytest.raises(SsrfBlocked):
        validate_outbound_url(url, allow_http=True)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/",  # http blocked by default
        "ftp://example.com/",
        "file:///etc/passwd",
        "gopher://example.com/",
        "javascript:alert(1)",
    ],
)
def test_blocks_disallowed_schemes(url):
    with pytest.raises(SsrfBlocked):
        validate_outbound_url(url)


def test_blocks_url_without_hostname():
    with pytest.raises(SsrfBlocked):
        validate_outbound_url("https:///path")


def test_dns_rebinding_resolved_to_loopback_blocked():
    """If a hostname resolves to a private IP, refuse it."""
    fake_addr_info = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
    with patch("socket.getaddrinfo", return_value=fake_addr_info):
        with pytest.raises(SsrfBlocked):
            validate_outbound_url("https://attacker.example/")


def test_resolved_to_cloud_metadata_blocked():
    fake_addr_info = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))
    ]
    with patch("socket.getaddrinfo", return_value=fake_addr_info):
        with pytest.raises(SsrfBlocked):
            validate_outbound_url("https://attacker.example/")


def test_dns_failure_blocked():
    with patch("socket.getaddrinfo", side_effect=socket.gaierror("no such host")):
        with pytest.raises(SsrfBlocked):
            validate_outbound_url("https://unresolvable.example/")


def test_allow_private_bypass_works_for_dev_mode():
    """When explicitly allowed (dev/test), private IPs pass."""
    host, ips = validate_outbound_url(
        "http://127.0.0.1/", allow_private=True, allow_http=True
    )
    assert host == "127.0.0.1"
    assert "127.0.0.1" in ips


def test_public_https_url_resolves_to_real_ip_passes():
    """A real public URL should validate cleanly. Network-gated."""
    fake_addr_info = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    with patch("socket.getaddrinfo", return_value=fake_addr_info):
        host, ips = validate_outbound_url("https://example.com/")
        assert host == "example.com"
        assert ips == ["93.184.216.34"]


# --- safe_httpx_get redirect-chain validation ---------------------------------


class _FakeResponse:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


class _FakeClient:
    """A minimal httpx-like client that returns scripted responses."""

    def __init__(self, scripted_responses):
        self.scripted = list(scripted_responses)
        self.calls = []

    def get(self, url, follow_redirects=False, **kwargs):  # noqa: ARG002
        self.calls.append(url)
        return self.scripted.pop(0)


def test_safe_httpx_get_blocks_redirect_to_internal():
    """A 302 redirect from a public URL to a private IP must be blocked."""
    client = _FakeClient(
        [
            _FakeResponse(302, {"Location": "http://169.254.169.254/latest/"}),
        ]
    )
    fake_addr_info = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    with patch("socket.getaddrinfo", return_value=fake_addr_info):
        with pytest.raises(SsrfBlocked):
            safe_httpx_get(client, "https://example.com/", follow_redirects=True)


def test_safe_httpx_get_follows_legitimate_redirect_chain():
    """A redirect chain to legitimate public URLs is followed."""
    client = _FakeClient(
        [
            _FakeResponse(302, {"Location": "https://example.com/final"}),
            _FakeResponse(200, {}),
        ]
    )
    fake_addr_info = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    with patch("socket.getaddrinfo", return_value=fake_addr_info):
        resp = safe_httpx_get(client, "https://example.com/", follow_redirects=True)
        assert resp.status_code == 200
        assert client.calls == ["https://example.com/", "https://example.com/final"]


def test_safe_httpx_get_no_follow_returns_redirect_response():
    client = _FakeClient([_FakeResponse(302, {"Location": "https://elsewhere/"})])
    fake_addr_info = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    with patch("socket.getaddrinfo", return_value=fake_addr_info):
        resp = safe_httpx_get(client, "https://example.com/", follow_redirects=False)
        assert resp.status_code == 302
