"""SP-006 regression: retrieve_metadata_of_url must route through the SSRF
guard, not call httpx_client directly.

The function is invoked from link-post creation and reads URLs supplied by
the user. Without the SSRF guard, an attacker can probe internal addresses.
"""

import ast
import pathlib

COMM_ROUTES = (
    pathlib.Path(__file__).resolve().parents[2] / "app" / "community" / "routes.py"
)


def _function_source(name):
    src = COMM_ROUTES.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError(f"{name!r} not found in {COMM_ROUTES}")


def test_retrieve_metadata_of_url_uses_safe_httpx_get():
    src = _function_source("retrieve_metadata_of_url")
    assert "safe_httpx_get" in src, (
        "SP-006 REGRESSION: retrieve_metadata_of_url no longer uses "
        "safe_httpx_get. The bare httpx_client.get path is SSRF-vulnerable."
    )
    # The bare 'httpx_client.get(' should not be the primary HTTP call site
    # in this function any more.
    assert "httpx_client.get(" not in src, (
        "SP-006 REGRESSION: retrieve_metadata_of_url still calls "
        "httpx_client.get directly (bypasses SSRF guard)."
    )
