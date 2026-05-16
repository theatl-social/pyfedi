"""SP-015 regression: resend_email and reset_password_request must NOT
reveal whether an email is registered. Both endpoints now flash the same
neutral message regardless of account existence.

Mirrors Lemmy GHSA-qxrw-f6fh-34r7. The original PieFed code flashed
"No user found with that email address." vs "Verification email sent!"
and "No account with that email address exists" vs "Check your email…",
both trivially enumeration-friendly.
"""

import ast
import pathlib

AUTH = pathlib.Path(__file__).resolve().parents[2] / "app" / "auth" / "routes.py"


def _function_source(name):
    src = AUTH.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError(f"{name!r} not found in {AUTH}")


# The exact differential strings that previously revealed account existence.
# If any reappear in the function body, the patch has regressed.
_FORBIDDEN_RESEND = [
    "No user found with that email address.",
]
_FORBIDDEN_RESET = [
    "No account with that email address exists",
]


def test_resend_email_no_account_enumeration():
    src = _function_source("resend_email")
    for forbidden in _FORBIDDEN_RESEND:
        assert forbidden not in src, (
            f"SP-015 REGRESSION: resend_email flashes {forbidden!r} when the "
            f"account does not exist — trivial email-enumeration."
        )


def test_reset_password_request_no_account_enumeration():
    src = _function_source("reset_password_request")
    for forbidden in _FORBIDDEN_RESET:
        assert forbidden not in src, (
            f"SP-015 REGRESSION: reset_password_request flashes {forbidden!r} "
            f"when the account does not exist — trivial email-enumeration."
        )


def test_resend_email_returns_same_redirect_path_for_both_cases():
    """Both branches (user-exists vs not) must redirect to the same place,
    otherwise an attacker can enumerate via the redirect URL."""
    src = _function_source("resend_email")
    # Find all redirect(...) calls. The exists and not-exists branches should
    # both go to check_email.
    tree = ast.parse(src)
    redirect_targets = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "redirect"
            and node.args
            and isinstance(node.args[0], ast.Call)
            and isinstance(node.args[0].func, ast.Name)
            and node.args[0].func.id == "url_for"
            and node.args[0].args
            and isinstance(node.args[0].args[0], ast.Constant)
        ):
            redirect_targets.append(node.args[0].args[0].value)
    # The legitimate-path redirect is "auth.check_email"; the no-user path
    # should also redirect to check_email (not back to resend_email).
    assert "auth.resend_email" not in redirect_targets, (
        "SP-015 REGRESSION: resend_email redirects to itself when no user "
        "exists — distinct from the success path's check_email, allowing "
        "enumeration via Location header inspection."
    )
