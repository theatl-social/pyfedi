"""SP-017 regression: uploaded and remotely-fetched SVG files must be
sanitized to strip <script>, event handlers, and javascript: URLs.

Mirrors upstream PieFed v1.6.27 (commit dc215422). SVG is image/svg+xml and
can carry active content that renders inline in user agents, so an attacker
uploading a malicious SVG (community icon, avatar, post image) achieves
persistent XSS for any user who views the SVG.
"""

import ast
import pathlib
import tempfile

import pytest

from app import create_app
from app.utils import sanitize_svg, sanitize_svg_bytes
from config import Config


class _TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True
    CACHE_TYPE = "NullCache"


@pytest.fixture
def app():
    return create_app(_TestConfig)


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
UTILS = REPO_ROOT / "app" / "utils.py"
UPLOAD = REPO_ROOT / "app" / "shared" / "upload.py"
SHARED_POST = REPO_ROOT / "app" / "shared" / "post.py"


def _function_source(path: pathlib.Path, name: str) -> str:
    src = path.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError(f"{name!r} not found in {path}")


# --- Behavioral tests on the sanitizer itself --------------------------------


def test_sanitize_strips_script_tag(app):
    with app.app_context():
        malicious = (
            b'<?xml version="1.0"?>'
            b'<svg xmlns="http://www.w3.org/2000/svg">'
            b"<script>alert(document.cookie)</script>"
            b'<rect width="10" height="10"/>'
            b"</svg>"
        )
        cleaned = sanitize_svg_bytes(malicious)
        assert b"<script" not in cleaned.lower()
        assert b"alert" not in cleaned
        # Benign content should survive
        assert b"<rect" in cleaned


def test_sanitize_strips_event_handler(app):
    with app.app_context():
        malicious = (
            b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">'
            b'<rect width="10" height="10" onclick="alert(2)"/>'
            b"</svg>"
        )
        cleaned = sanitize_svg_bytes(malicious)
        assert b"onload" not in cleaned.lower()
        assert b"onclick" not in cleaned.lower()
        assert b"alert" not in cleaned


def test_sanitize_strips_javascript_url(app):
    with app.app_context():
        malicious = (
            b'<svg xmlns="http://www.w3.org/2000/svg" '
            b'xmlns:xlink="http://www.w3.org/1999/xlink">'
            b'<a xlink:href="javascript:alert(1)"><rect width="10" height="10"/></a>'
            b"</svg>"
        )
        cleaned = sanitize_svg_bytes(malicious)
        assert b"javascript:" not in cleaned.lower()


def test_sanitize_svg_file_rewrites_on_disk(app):
    with app.app_context():
        malicious = (
            b'<svg xmlns="http://www.w3.org/2000/svg">'
            b'<script>alert(1)</script><rect width="10" height="10"/>'
            b"</svg>"
        )
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp:
            tmp.write(malicious)
            tmp_path = tmp.name
        try:
            ok = sanitize_svg(tmp_path)
            assert ok is True
            with open(tmp_path, "rb") as f:
                cleaned = f.read()
            assert b"<script" not in cleaned.lower()
            assert b"<rect" in cleaned
        finally:
            pathlib.Path(tmp_path).unlink(missing_ok=True)


def test_sanitize_handles_invalid_input_gracefully(app):
    """Garbage in: returns original bytes, logs error, does not raise."""
    with app.app_context():
        garbage = b"not actually svg content at all \x00\xff"
        # Should not raise; either strips to safe form or returns as-is.
        # The contract is "do no harm" — never raise on weird input.
        result = sanitize_svg_bytes(garbage)
        assert isinstance(result, bytes)


# --- Structural tests: call sites are wired up -------------------------------


def test_process_upload_sanitizes_svg():
    src = _function_source(UPLOAD, "process_upload")
    assert "sanitize_svg" in src, (
        "SP-017 REGRESSION: process_upload no longer calls sanitize_svg on "
        ".svg uploads. SVG XSS vector is open again."
    )


def test_edit_post_sanitizes_svg():
    src = _function_source(SHARED_POST, "edit_post")
    assert "sanitize_svg" in src, (
        "SP-017 REGRESSION: edit_post (image-post upload path) no longer "
        "calls sanitize_svg on .svg uploads."
    )


def test_url_to_thumbnail_sanitizes_svg():
    src = _function_source(UTILS, "url_to_thumbnail_file")
    assert "sanitize_svg_bytes" in src, (
        "SP-017 REGRESSION: url_to_thumbnail_file no longer sanitizes SVG "
        "content from remote og:image fetches."
    )
