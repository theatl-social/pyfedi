"""SP-022 regression: choose_topics() must validate the CSRF token.

Upstream v1.7.4 (ae1859d3, shipped in v1.7.8) replaced `form.validate_on_submit()`
with a bare `request.method == 'POST'` check to fix topic selection, which never
submitted because `chosen_topics` is a MultiCheckboxField whose `.choices` are
never populated. This fork registers no global CSRFProtect, so validate_on_submit()
was this endpoint's only CSRF gate — taking upstream's form verbatim leaves a
state-changing POST (joining topics, and every community under them) with no CSRF
protection. We keep upstream's fix and validate the token explicitly.

A future merge that resolves this conflict in upstream's favor reopens the hole,
which is what these tests catch.
"""

import ast
import pathlib

import pytest

ONBOARDING = (
    pathlib.Path(__file__).resolve().parents[2] / "app" / "auth" / "onboarding.py"
)


def _source():
    return ONBOARDING.read_text()


def _function_source(name):
    src = _source()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError(f"{name!r} not found in {ONBOARDING}")


def test_choose_topics_validates_csrf_token():
    src = _function_source("choose_topics")
    assert "validate_csrf" in src, (
        "SP-022 REGRESSION: choose_topics() no longer calls validate_csrf(). "
        "This fork has no global CSRFProtect, so the endpoint is now CSRF-open. "
        "See SECURITY_PATCHES.md SP-022."
    )


def test_choose_topics_csrf_failure_aborts():
    """A bad token must abort, not fall through to the join logic."""
    src = _function_source("choose_topics")
    tree = ast.parse(src)

    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            handler_src = "".join(
                ast.dump(h) for h in node.handlers if isinstance(h, ast.ExceptHandler)
            )
            if "abort" in handler_src:
                return

    raise AssertionError(
        "SP-022 REGRESSION: choose_topics() does not abort when CSRF validation "
        "raises. A forged POST would proceed to join topics."
    )


def test_validate_csrf_is_imported():
    src = _source()
    tree = ast.parse(src)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "flask_wtf.csrf":
            if any(alias.name == "validate_csrf" for alias in node.names):
                return

    raise AssertionError(
        "SP-022 REGRESSION: validate_csrf is no longer imported from flask_wtf.csrf "
        f"in {ONBOARDING}."
    )


@pytest.mark.parametrize("guard", ["validate_csrf", "abort"])
def test_guard_precedes_topic_join(guard):
    """The CSRF guard must run before join_topic(), not after."""
    src = _function_source("choose_topics")
    assert guard in src, f"{guard} missing from choose_topics()"
    assert src.index(guard) < src.index("join_topic"), (
        f"SP-022 REGRESSION: {guard} appears after join_topic() in choose_topics(); "
        "the CSRF check must gate the state change, not follow it."
    )
