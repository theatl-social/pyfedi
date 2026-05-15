"""SP-010 regression: url_to_thumbnail_file must route through the SSRF guard.

SP-006 patched retrieve_metadata_of_url but missed the downstream og:image
fetch. An attacker who creates a link post controls the og:image URL via
their own page's HTML, which then becomes the argument to
url_to_thumbnail_file. Without the guard, the attacker could exfiltrate
internal data via the stored thumbnail.
"""

import ast
import pathlib

UTILS = pathlib.Path(__file__).resolve().parents[2] / "app" / "utils.py"


def _function_source(name):
    src = UTILS.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError(f"{name!r} not found in {UTILS}")


def test_url_to_thumbnail_file_uses_safe_httpx_get():
    src = _function_source("url_to_thumbnail_file")
    assert "safe_httpx_get" in src, (
        "SP-010 REGRESSION: url_to_thumbnail_file no longer uses "
        "safe_httpx_get. og:image SSRF is back."
    )


def test_url_to_thumbnail_file_no_bare_httpx_client_get():
    """No bare httpx_client.get( in the function body (must go through guard)."""
    src = _function_source("url_to_thumbnail_file")
    assert "httpx_client.get(" not in src, (
        "SP-010 REGRESSION: url_to_thumbnail_file calls httpx_client.get "
        "directly, bypassing the SSRF guard."
    )
