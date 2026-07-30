"""SP-023 regression: HX-Current-Url must be validated before it is echoed into
HX-Redirect.

`HX-Current-Url` is set by htmx but is an ordinary request header, so it is
client-controlled. Upstream v1.7.8's `user_flair_unblock` echoes it back after
only a substring test (`if "/user/" in curr_url`), which `https://evil.com/user/x`
satisfies. That is the same open-redirect shape SP-007 covers for `instance_url`
in the same file.

Not directly exploitable through a browser today: HX-Current-Url is a non-simple
header, so a cross-origin fetch triggers a CORS preflight, and this app never
emits Access-Control-Allow-Headers. This is defense-in-depth, consistent with the
fork's existing posture on the bug class.
"""

import pytest

from app.utils import safe_hx_redirect_url

FALLBACK = "/fallback"


@pytest.fixture
def app():
    from app import create_app
    from config import Config

    class _TestConfig(Config):
        TESTING = True
        SERVER_NAME = "localhost"
        SECRET_KEY = "test-secret-key-for-ci-padding-must-be-32-plus-chars"
        CACHE_TYPE = "NullCache"
        WTF_CSRF_ENABLED = False

    return create_app(_TestConfig)


@pytest.mark.parametrize(
    "hostile",
    [
        "https://evil.com/user/x",  # the substring bypass upstream allows
        "http://evil.com/user/",
        "https://evil.com/user/../admin",
        "//evil.com/user/x",  # protocol-relative
        "https://localhost.evil.com/user/x",  # suffix-confusion on the real host
        "javascript:alert(1)//user/",
        "data:text/html,<script>/user/</script>",
    ],
)
def test_offsite_urls_are_rejected(app, hostile):
    with app.test_request_context("/", base_url="https://localhost"):
        assert safe_hx_redirect_url(hostile, "/user/", FALLBACK) == FALLBACK, (
            f"SP-023 REGRESSION: {hostile!r} was accepted as an HX-Redirect target."
        )


@pytest.mark.parametrize(
    "benign",
    [
        "/user/alice",
        "/user/alice?tab=posts",
        "https://localhost/user/alice",
    ],
)
def test_same_origin_urls_are_preserved(app, benign):
    with app.test_request_context("/", base_url="https://localhost"):
        assert safe_hx_redirect_url(benign, "/user/", FALLBACK) == benign


def test_wrong_path_prefix_is_rejected(app):
    with app.test_request_context("/", base_url="https://localhost"):
        assert safe_hx_redirect_url("/admin/panel", "/user/", FALLBACK) == FALLBACK


@pytest.mark.parametrize("empty", [None, ""])
def test_missing_header_falls_back(app, empty):
    with app.test_request_context("/", base_url="https://localhost"):
        assert safe_hx_redirect_url(empty, "/user/", FALLBACK) == FALLBACK


def test_user_flair_unblock_uses_the_validator():
    """The route must not regress to a bare substring check."""
    import ast
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[2] / "app" / "user" / "routes.py"
    src = path.read_text()
    tree = ast.parse(src)

    fn_src = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "user_flair_unblock":
            fn_src = ast.get_source_segment(src, node)

    assert fn_src, "user_flair_unblock not found"
    code = "\n".join(
        line for line in fn_src.split("\n") if not line.strip().startswith("#")
    )

    assert "safe_hx_redirect_url" in code, (
        "SP-023 REGRESSION: user_flair_unblock no longer validates HX-Current-Url."
    )
    assert '"/user/" in curr_url' not in code, (
        "SP-023 REGRESSION: upstream's substring check was reintroduced."
    )
