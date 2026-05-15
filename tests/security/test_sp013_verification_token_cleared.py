"""SP-013 regression: verification_token must be cleared after successful use.

Previously verify_email() set user.verified = True but left
verification_token populated, allowing a captured token (from email logs,
ESP cache, browser history, referrer leak) to be replayed against the same
account. Clearing it makes captured tokens inert after first use.
"""

import ast
import pathlib

AUTH_ROUTES = pathlib.Path(__file__).resolve().parents[2] / "app" / "auth" / "routes.py"


def _function_source(name):
    src = AUTH_ROUTES.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError(f"{name!r} not found in {AUTH_ROUTES}")


def test_verify_email_clears_token():
    src = _function_source("verify_email")
    # The clearing assignment must appear and must come BEFORE the first
    # db.session.commit() inside the function (otherwise the commit could
    # persist user.verified=True without clearing the token, allowing a race
    # window).
    lines = src.splitlines()
    clear_line = next(
        (i for i, line in enumerate(lines) if "user.verification_token = None" in line),
        None,
    )
    commit_line = next(
        (i for i, line in enumerate(lines) if "db.session.commit()" in line),
        None,
    )
    assert clear_line is not None, (
        "SP-013 REGRESSION: verify_email no longer clears "
        "user.verification_token after marking verified."
    )
    if commit_line is not None:
        assert clear_line < commit_line, (
            f"SP-013 REGRESSION: verification_token clearing at function-line "
            f"{clear_line} happens AFTER db.session.commit at function-line "
            f"{commit_line} — the commit could persist verified=True without "
            f"clearing the token."
        )
