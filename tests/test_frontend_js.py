"""Guard: the browser JavaScript must at least parse, and its setup list must resolve.

The v1.8.11 merge (PR #107) produced an app/static/js/scripts.js that git
auto-merged with no conflict and that no browser can run: upstream had folded
three setup arrays into one list, and the merge spliced half of each version
together, leaving an unclosed array (``Unexpected token 'const'``). It also
dropped ``function setupPopupTooltips`` while keeping the call. A syntax error
stops the whole file, so in production the mobile 3-line menu and the mobile
Subscribed/Local/Popular/All filter dropdown (``select.navigate_on_change``)
stopped working. Every Python test, template check and the image build were
green, because nothing in CI looked at JavaScript.

These tests run on every PR. The browser-level check (does the page actually
run the script) is scripts/js_browser_smoke.py, run in its own CI job.
"""

import os
import pathlib
import re
import shutil
import subprocess

import pytest

STATIC_JS = pathlib.Path(__file__).resolve().parents[1] / "app" / "static" / "js"
SCRIPTS_JS = STATIC_JS / "scripts.js"


def _first_party_js():
    return sorted(p for p in STATIC_JS.rglob("*.js") if not p.name.endswith(".min.js"))


def _node():
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("node is required in CI to check browser JavaScript syntax")
        pytest.skip("node not installed; CI runs this check")
    return node


@pytest.mark.parametrize(
    "path", _first_party_js(), ids=lambda p: str(p.relative_to(STATIC_JS))
)
def test_static_js_parses(path):
    node = _node()
    result = subprocess.run(
        [node, "--check", str(path)], capture_output=True, text=True
    )
    assert result.returncode == 0, (
        f"{path.relative_to(STATIC_JS.parents[2])} is not valid JavaScript -- the browser "
        f"will run none of it:\n{result.stderr}"
    )


def _defined_js_functions():
    names = set()
    for path in _first_party_js():
        text = path.read_text(errors="ignore")
        names.update(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", text))
        names.update(re.findall(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=", text))
    return names


def test_every_dom_ready_setup_is_defined():
    text = SCRIPTS_JS.read_text()
    handler = text.split('document.addEventListener("DOMContentLoaded"', 1)
    assert len(handler) == 2, "scripts.js no longer has its DOMContentLoaded handler"
    lists = re.findall(r"const\s+\w*[sS]etups\s*=\s*\[(.*?)\];", handler[1], re.S)
    assert lists, "no setup list found in scripts.js's DOMContentLoaded handler"
    called = set()
    for body in lists:
        body = re.sub(r"//[^\n]*", "", body)
        called.update(re.findall(r"\b((?:setup|prevent)[A-Za-z0-9_]+)\b", body))
    missing = sorted(called - _defined_js_functions())
    assert not missing, (
        f"scripts.js calls setup functions that no static JS file defines: {missing}. "
        "Look for a function the merge dropped."
    )
