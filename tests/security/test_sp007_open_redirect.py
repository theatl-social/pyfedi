"""SP-007 regression: fediverse_redirect must validate instance_url before
interpolating it into a redirect URL. Otherwise an attacker can supply
'evil.com/path' or 'evil.com@victim/' to steer victims off-site (open
redirect → phishing).
"""

import ast
import pathlib

import pytest

USER_ROUTES = pathlib.Path(__file__).resolve().parents[2] / "app" / "user" / "routes.py"


def _function_source(name):
    src = USER_ROUTES.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError(f"{name!r} not found in {USER_ROUTES}")


def test_fediverse_redirect_validates_instance_url():
    src = _function_source("fediverse_redirect")
    assert "_SAFE_INSTANCE_HOST_RE" in src, (
        "SP-007 REGRESSION: fediverse_redirect no longer references the "
        "_SAFE_INSTANCE_HOST_RE validator. Open-redirect risk."
    )


def _extract_regex_pattern():
    """Pull the regex pattern out of the module source via AST so we don't
    have to actually import app.user.routes (which has unrelated circular
    imports that would force us to bring up the full Flask app)."""
    import re

    src = USER_ROUTES.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_SAFE_INSTANCE_HOST_RE"
            for t in node.targets
        ):
            # The right-hand side is `re.compile(r'...')`. The first arg is
            # the pattern string literal.
            call = node.value
            if isinstance(call, ast.Call) and call.args:
                first = call.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    return re.compile(first.value)
    raise AssertionError(
        "_SAFE_INSTANCE_HOST_RE not found as a re.compile assignment in user/routes.py"
    )


def test_safe_instance_host_re_imports_and_works():
    """Verify the regex itself accepts valid hosts and rejects attack patterns."""
    regex = _extract_regex_pattern()
    for good in [
        "mastodon.social",
        "lemmy.world",
        "fed.example.org",
        "sub.domain.example.co.uk",
    ]:
        assert regex.match(good), f"valid host {good!r} rejected"

    for bad in [
        "",  # empty
        "evil.com/path/to/phish",  # path
        "evil.com@victim.com",  # userinfo trick
        "evil.com:8080",  # port
        "https://evil.com",  # full URL
        "evil.com#fragment",
        "evil.com?q=x",
        # Note: bare IPv4 literals like '127.0.0.1' DO match the LDH regex
        # (digits-and-dots), which is OK for the open-redirect threat model:
        # an IP literal in a redirect URL doesn't help phishing because the
        # victim sees the IP, not a deceptive domain. SSRF is a different
        # class and is protected at the outbound HTTP layer (SP-002).
        "localhost",  # single-label
        "evil",  # single-label
        "evil.com/",  # trailing slash
        "-evil.com",  # leading dash
        "evil.com.",  # trailing dot
        "evil .com",  # space
        "ev<il.com",  # special char
    ]:
        assert not regex.match(bad), f"attack host {bad!r} should have been rejected"
