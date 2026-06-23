"""SP-013 regression: verification_token must be rotated after successful use.

Previously verify_email() set user.verified = True but left
verification_token populated, allowing a captured token (from email logs,
ESP cache, browser history, referrer leak) to be replayed against the same
account.

Original SP-013 (this fork) set the token to None. Upstream PieFed v1.6.27
(commit b3474d19) instead rotates the token to a fresh random value, which
is equivalent in security terms (the old token is invalidated) but preserves
the unsubscribe URLs in newsletter/welcome emails that key off this column.
We adopted upstream's rotate-token approach to fix a usability regression
in our own newsletter sends. The email templates also got {% if %} guards
as belt-and-suspenders.

The test asserts:
- The function reassigns user.verification_token (rotation OR nulling, since
  either invalidates the captured token).
- The reassignment happens BEFORE db.session.commit() so the commit can't
  persist verified=True without invalidating the token (race window).
- The four email templates that reference verification_token wrap the
  reference in an {% if %} guard.
"""

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
AUTH_ROUTES = REPO_ROOT / "app" / "auth" / "routes.py"
TEMPLATE_DIR = REPO_ROOT / "app" / "templates" / "email"


def _function_source(name):
    src = AUTH_ROUTES.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError(f"{name!r} not found in {AUTH_ROUTES}")


def test_verify_email_rotates_or_clears_token():
    src = _function_source("verify_email")
    lines = src.splitlines()
    # Accept either rotation (random_token) or nulling (= None) — both
    # invalidate the captured token. Rotation is the preferred form because
    # it preserves email-template links.
    invalidate_line = next(
        (
            i
            for i, line in enumerate(lines)
            if "user.verification_token =" in line
            and "user.verification_token ==" not in line
        ),
        None,
    )
    commit_line = next(
        (i for i, line in enumerate(lines) if "db.session.commit()" in line),
        None,
    )
    assert invalidate_line is not None, (
        "SP-013 REGRESSION: verify_email no longer reassigns "
        "user.verification_token after marking verified. The captured token "
        "is replayable."
    )
    invalidate_text = lines[invalidate_line]
    assert "None" in invalidate_text or "random_token" in invalidate_text, (
        f"SP-013 REGRESSION: verify_email reassigns verification_token "
        f"but not to a recognized invalidating value (None or random_token). "
        f"Saw: {invalidate_text!r}"
    )
    if commit_line is not None:
        assert invalidate_line < commit_line, (
            f"SP-013 REGRESSION: verification_token reassignment at "
            f"function-line {invalidate_line} happens AFTER db.session.commit "
            f"at function-line {commit_line} — the commit could persist "
            f"verified=True without invalidating the token."
        )


def _template_has_token_guard(filename: str) -> bool:
    """Return True if every reference to user.verification_token /
    recipient.verification_token in the template is inside a Jinja
    {% if ... verification_token %} block."""
    path = TEMPLATE_DIR / filename
    text = path.read_text()
    # Simple heuristic: any line that references *.verification_token must
    # have an enclosing {% if %} block referencing verification_token within
    # a reasonable proximity above it.
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "verification_token" not in line:
            continue
        if "{%" in line and "endif" in line:
            continue
        if "{% if" in line and "verification_token" in line:
            continue
        # Look back up to 5 lines for an {% if ... verification_token %}
        window = "\n".join(lines[max(0, i - 5) : i])
        if "{% if" in window and "verification_token" in window:
            continue
        return False
    return True


def test_newsletter_html_guards_token():
    assert _template_has_token_guard("newsletter.html"), (
        "SP-013 REGRESSION: newsletter.html references verification_token "
        "without a {% if recipient.verification_token %} guard. "
        "Sends will crash with url_for(token=None) for users without a token."
    )


def test_newsletter_txt_guards_token():
    assert _template_has_token_guard("newsletter.txt"), (
        "SP-013 REGRESSION: newsletter.txt references verification_token "
        "without an {% if %} guard."
    )


def test_welcome_html_guards_token():
    assert _template_has_token_guard("welcome.html"), (
        "SP-013 REGRESSION: welcome.html references verification_token "
        "without an {% if %} guard."
    )


def test_welcome_txt_guards_token():
    assert _template_has_token_guard("welcome.txt"), (
        "SP-013 REGRESSION: welcome.txt references verification_token "
        "without an {% if %} guard."
    )
