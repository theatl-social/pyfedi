"""SP-024 regression: the /anoobis `next` parameter must not be an open redirect.

Upstream PieFed v1.7.10 introduced the "anoobis" proof-of-work challenge. Its
route accepted a client-supplied `next` and validated it with furl:

    f = furl(next)
    if next and (f.host is None or f.host == SERVER_NAME) and \\
            (f.scheme is None or f.scheme.startswith('http')):
        return render_template('anoobis.html', next=next, ...)

`anoobis.html` then runs `location.href = '<next>'` once the challenge solves.

furl reports **no host** for backslash-prefixed values, but browsers normalise
backslashes to forward slashes while parsing URLs. So `/\\evil.com` passes the
host check and then navigates to `//evil.com` — protocol-relative, i.e. another
origin entirely.

Impact is worse than a plain off-site link: the attacker distributes a URL on
*our* domain that shows our challenge page and then lands the victim on their
phishing page, so the origin the user inspects is ours.

Fixed by `safe_next_path()` in app/utils.py, which allowlists plain relative
same-origin paths instead of trying to enumerate normalisation quirks.
"""

import pytest

from app.utils import safe_next_path


# Values a browser will navigate off-origin, all of which defeated the
# original furl host check.
OFF_ORIGIN = [
    "/\\evil.com",
    "/\\/evil.com",
    "\\\\evil.com",
    "\\/evil.com",
    "http:/\\evil.com",
    "//evil.com/",
    "///evil.com",
    "https://evil.com",
    "http://evil.com",
    "https://localhost.evil.com/",
    "//evil.com\\@localhost/",
]

# Non-http(s) schemes: script execution / data exfiltration sinks.
DANGEROUS_SCHEMES = [
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
]

# Control characters browsers strip mid-URL, used to smuggle payloads.
CONTROL_CHAR_SMUGGLING = [
    "/\x00//evil.com",
    "/\n//evil.com",
    "/\t/\\evil.com",
    "/\r\n//evil.com",
]

SAFE = [
    "/",
    "/feed",
    "/c/example",
    "/post/123",
    "/u/alice",
    "/search?q=hello&sort=new",
    "/post/1#comment-2",
    "/c/a_b-c.d/",
]


@pytest.mark.parametrize("candidate", OFF_ORIGIN)
def test_rejects_off_origin_targets(candidate):
    assert safe_next_path(candidate) == "", (
        f"SP-024 REGRESSION: {candidate!r} accepted as a `next` target. "
        "A browser normalises this to another origin, making /anoobis an "
        "open redirect on our own domain."
    )


@pytest.mark.parametrize("candidate", DANGEROUS_SCHEMES)
def test_rejects_dangerous_schemes(candidate):
    assert safe_next_path(candidate) == "", (
        f"SP-024 REGRESSION: {candidate!r} accepted. location.href with this "
        "value executes script or loads attacker content."
    )


@pytest.mark.parametrize("candidate", CONTROL_CHAR_SMUGGLING)
def test_rejects_control_characters(candidate):
    assert safe_next_path(candidate) == "", (
        f"SP-024 REGRESSION: {candidate!r} accepted. Browsers strip these "
        "characters mid-URL, so the validated string and the navigated string "
        "differ."
    )


@pytest.mark.parametrize("candidate", SAFE)
def test_allows_relative_same_origin_paths(candidate):
    assert safe_next_path(candidate) == candidate, (
        f"{candidate!r} is a legitimate same-origin path and must be allowed, "
        "otherwise the challenge cannot return users where they were going."
    )


@pytest.mark.parametrize("candidate", ["", None, 0, [], {}])
def test_rejects_empty_and_non_string(candidate):
    assert safe_next_path(candidate) == ""


def test_route_does_not_raise_before_abort():
    """Upstream wrote `raise Exception(...)` immediately before `abort(403)`.

    That made the abort dead code, turned a rejection into a 500, and echoed
    the configured SERVER_NAME into the error path.
    """
    import ast
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[2] / "app" / "main" / "routes.py"
    tree = ast.parse(src.read_text())
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "anoobis"
    )
    raises = [n for n in ast.walk(fn) if isinstance(n, ast.Raise)]
    assert not raises, (
        "SP-024 REGRESSION: anoobis() raises instead of aborting. This returns "
        "500 rather than 403 and leaks configuration into the error response."
    )


def test_route_validates_next():
    import pathlib

    src = (
        pathlib.Path(__file__).resolve().parents[2] / "app" / "main" / "routes.py"
    ).read_text()
    start = src.index("def anoobis(")
    body = src[start : start + 1200]
    assert "safe_next_path(" in body, (
        "SP-024 REGRESSION: anoobis() no longer routes `next` through "
        "safe_next_path(). The open redirect is reachable again."
    )


def test_template_uses_js_escaping():
    """`location.href` is a JS string context; HTML autoescaping is wrong there."""
    import pathlib

    tpl = (
        pathlib.Path(__file__).resolve().parents[2]
        / "app"
        / "templates"
        / "anoobis.html"
    ).read_text()
    assert "location.href = {{ next | tojson }}" in tpl, (
        "SP-024 REGRESSION: anoobis.html no longer uses |tojson for the "
        "redirect target. Jinja's HTML escaping does not correctly escape a "
        "JavaScript string literal."
    )
