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


def test_sanitize_never_returns_unsanitized_input(app):
    """Garbage in: sanitized bytes out, or an exception. Never the input.

    Contract change, 2026-08-05 (upstream v1.7.10): sanitize_svg_bytes is now
    fail-CLOSED. It previously wrapped its whole body in
    `except Exception: return svg_bytes`, so an SVG crafted to crash the
    sanitizer was persisted verbatim — the attacker chose the input, so
    failing open was exactly backwards. It may now raise, and every caller is
    responsible for dropping the file rather than falling back.
    """
    with app.app_context():
        garbage = b"not actually svg content at all \x00\xff"
        try:
            result = sanitize_svg_bytes(garbage)
        except Exception:
            return  # fail-closed is the acceptable outcome
        assert isinstance(result, bytes)
        assert result != garbage, (
            "SP-017 REGRESSION: sanitize_svg_bytes returned its input "
            "unchanged. Returning unsanitized attacker-controlled bytes is "
            "the fail-open behaviour this patch exists to prevent."
        )


def test_sanitize_rejects_oversized_svg(app):
    """A decompression/parser bomb must be rejected before parsing."""
    with app.app_context():
        with pytest.raises(ValueError, match="too large"):
            sanitize_svg_bytes(b"<svg>" + b"a" * (10 * 1024 * 1024 + 1))


def test_sanitize_strips_doctype_and_processing_instructions(app):
    """XXE / billion-laughs vectors live in DOCTYPE and <?...?> nodes.

    Uses a benign external DTD reference so the document is still well-formed
    once those nodes are stripped, isolating the stripping behaviour itself.
    """
    with app.app_context():
        payload = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<?xml-stylesheet type="text/xsl" href="https://evil.example/x.xsl"?>'
            b'<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" '
            b'"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">'
            b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>'
        )
        result = sanitize_svg_bytes(payload)
        assert b"<!DOCTYPE" not in result
        assert b"svg11.dtd" not in result, "external DTD reference survived"
        # Note: filter_svg re-serializes and emits its own <?xml ...?> header,
        # so assert on the attacker-supplied PI content rather than on "<?xml".
        assert b"evil.example" not in result, "attacker processing instruction survived"
        assert b"xml-stylesheet" not in result
        assert b"<rect" in result, "stripping must not destroy the actual image"


def test_sanitize_rejects_xxe_entity_expansion(app):
    """An entity-expansion XXE payload must not survive as usable output.

    Stripping the DOCTYPE removes the &xxe; definition, so the reference no
    longer resolves and the parser rejects the document. Failing closed here
    is the point: under the pre-v1.7.10 fail-open body this raise was caught
    and the original bytes — DOCTYPE, ENTITY and all — were returned.
    """
    with app.app_context():
        hostile = (
            b'<?xml version="1.0"?>'
            b'<!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            b'<svg xmlns="http://www.w3.org/2000/svg"><text>&xxe;</text></svg>'
        )
        with pytest.raises(Exception):
            sanitize_svg_bytes(hostile)


def test_url_to_thumbnail_does_not_fall_back_to_unsanitized_svg():
    """The remote-fetch caller must drop the thumbnail, not keep raw bytes.

    sanitize_svg_bytes can now raise. If url_to_thumbnail_file caught that and
    carried on with `response_content` untouched, the fail-closed sanitizer
    would be silently converted back into a fail-open one at the call site.
    """
    src = _function_source(UTILS, "url_to_thumbnail_file")
    assert "sanitize_svg_bytes" in src, (
        "SP-017 REGRESSION: url_to_thumbnail_file no longer sanitizes SVG."
    )
    # Every except-block guarding a sanitize call must bail out, not continue.
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        body_src = ast.dump(node)
        if "sanitize_svg_bytes" not in body_src:
            continue
        for handler in node.handlers:
            assert any(
                isinstance(stmt, ast.Return) for stmt in ast.walk(handler)
            ), (
                "SP-017 REGRESSION: an exception from sanitize_svg_bytes in "
                "url_to_thumbnail_file is swallowed without returning. The "
                "unsanitized bytes would then be persisted as a thumbnail."
            )


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
