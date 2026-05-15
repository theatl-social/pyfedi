"""SP-016 regression: head_request and mime_type_using_head must route
through the SSRF guard.

Mirrors Lemmy GHSA-c482-7gjx-pp36. HEAD against an attacker-supplied URL
returns no body but still leaks port-open status, response headers
(Server, X-Powered-By), and lets an attacker enumerate internal services
even though SP-002 already guards GET.
"""

import ast
import pathlib
import socket
from unittest.mock import patch

import pytest

from app.activitypub.ssrf_guard import SsrfBlocked, safe_httpx_head

UTILS = pathlib.Path(__file__).resolve().parents[2] / "app" / "utils.py"


def _function_source(name):
    src = UTILS.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError(f"{name!r} not found in {UTILS}")


def test_head_request_uses_safe_httpx_head():
    src = _function_source("head_request")
    assert "safe_httpx_head" in src, (
        "SP-016 REGRESSION: head_request no longer uses safe_httpx_head. "
        "HEAD-based SSRF is back."
    )
    assert "httpx_client.head(" not in src, (
        "SP-016 REGRESSION: head_request still calls httpx_client.head "
        "directly (bypasses SSRF guard)."
    )


def test_mime_type_using_head_uses_safe_httpx_head():
    src = _function_source("mime_type_using_head")
    assert "safe_httpx_head" in src, (
        "SP-016 REGRESSION: mime_type_using_head no longer uses "
        "safe_httpx_head. HEAD-based SSRF is back."
    )
    assert "httpx_client.head(" not in src, (
        "SP-016 REGRESSION: mime_type_using_head still calls "
        "httpx_client.head directly."
    )


class _FakeResponse:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


class _FakeClient:
    def head(self, url, **kwargs):  # noqa: ARG002
        return _FakeResponse(200, {"Content-Type": "image/png"})


def test_safe_httpx_head_blocks_loopback():
    with pytest.raises(SsrfBlocked):
        safe_httpx_head(_FakeClient(), "http://127.0.0.1/", allow_http=True)


def test_safe_httpx_head_blocks_metadata_literal():
    with pytest.raises(SsrfBlocked):
        safe_httpx_head(_FakeClient(), "http://169.254.169.254/", allow_http=True)


def test_safe_httpx_head_allows_public_url():
    fake_addr_info = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    with patch("socket.getaddrinfo", return_value=fake_addr_info):
        resp = safe_httpx_head(_FakeClient(), "https://example.com/")
        assert resp.status_code == 200
