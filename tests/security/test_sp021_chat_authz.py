"""SP-021 regression: Chat/DM authorization fixes.

Three findings consolidated:

1. **High (F-H-5)** — POST `/chat/<conversation_id>` skipped the membership
   check. The check only existed in the GET branch (line 39 of original).
   Any authenticated user could POST to any conversation_id and inject a
   message into a conversation they were not a participant of.

2. **High (F-H-6)** — API `post_private_message` ignored bidirectional
   blocks and the recipient's `accept_private_messages` preference. The
   web `new_message` route and the federation `ChatMessage` handler both
   enforce these; the API path bypassed them, letting a blocked user DM
   the blocker via /api/alpha/private_message.

3. **High (F-H-7)** — `chat_delete` cascaded into `Report.query.filter(
   suspect_conversation_id == conversation.id).delete()` unconditionally
   when any member triggered the delete. A reported user could destroy
   their own evidence by deleting the conversation before staff review.
   Admins still purge reports; non-admin members now leave reports
   intact with a nulled suspect_conversation_id pointer.
"""

import ast
import pathlib


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CHAT_ROUTES = REPO_ROOT / "app" / "chat" / "routes.py"
API_PM = REPO_ROOT / "app" / "api" / "alpha" / "utils" / "private_message.py"


def _function_source(path: pathlib.Path, name: str) -> str:
    src = path.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError(f"{name!r} not found in {path}")


# --- F-H-5: chat_home POST checks conversation membership


def test_chat_home_post_checks_membership():
    src = _function_source(CHAT_ROUTES, "chat_home")
    # Find the validate_on_submit branch
    lines = src.splitlines()
    submit_line = next(
        (i for i, line in enumerate(lines) if "form.validate_on_submit()" in line),
        None,
    )
    assert submit_line is not None, "validate_on_submit branch not found"
    send_line = next(
        (i for i, line in enumerate(lines) if "send_message(form.message.data" in line),
        None,
    )
    assert send_line is not None, "send_message call not found"
    # The membership check must appear between validate_on_submit and send_message
    between = "\n".join(lines[submit_line:send_line])
    has_member_check = (
        "conversation.is_member(current_user)" in between
        or "is_member(current_user)" in between
    )
    assert has_member_check, (
        "SP-021 REGRESSION: chat_home POST no longer checks conversation "
        "membership before calling send_message. Any authenticated user can "
        "inject messages into any conversation."
    )
    # Also must abort if not member
    assert "abort(" in between, (
        "SP-021 REGRESSION: chat_home POST checks membership but doesn't "
        "abort on failure."
    )


# --- F-H-6: API post_private_message honors blocks and accept_private_messages


def test_post_private_message_honors_block():
    src = _function_source(API_PM, "post_private_message")
    assert "has_blocked_user" in src, (
        "SP-021 REGRESSION: post_private_message no longer checks "
        "has_blocked_user. Blocked users can DM the blocker via the API."
    )


def test_post_private_message_honors_accept_preference():
    src = _function_source(API_PM, "post_private_message")
    assert "accept_private_messages" in src, (
        "SP-021 REGRESSION: post_private_message no longer checks "
        "recipient.accept_private_messages. Users who turned off PMs can be "
        "DM'd via the API."
    )


# --- F-H-7: chat_delete preserves Reports for non-admin members


def test_chat_delete_preserves_reports_for_member_initiated_delete():
    src = _function_source(CHAT_ROUTES, "chat_delete")
    # Must distinguish admin vs non-admin paths for the Report handling.
    # Multi-line statement-aware checks (ruff-format may split Report.query.filter(...)
    # across multiple lines).
    has_admin_check = "current_user.is_admin()" in src
    # The admin branch must call .delete() on a Report query.
    # Strip whitespace and check for the pattern across lines.
    src_collapsed = " ".join(src.split())
    has_delete = (
        "Report.query.filter(" in src_collapsed and ").delete()" in src_collapsed
    )
    has_update_null = (
        "Report.query.filter(" in src_collapsed and ".update({" in src_collapsed
    )
    assert has_admin_check, (
        "SP-021 REGRESSION: chat_delete no longer distinguishes admin "
        "vs non-admin deleters. The Report-purge path applies to anyone."
    )
    assert has_delete, (
        "SP-021 REGRESSION: chat_delete no longer has a Report-delete "
        "path for admins (expected behavior is admins purge; non-admins "
        "tombstone)."
    )
    assert has_update_null, (
        "SP-021 REGRESSION: chat_delete no longer has a Report-update "
        "path (expected: non-admin deleters null out suspect_conversation_id "
        "instead of deleting the Report row, so evidence survives)."
    )
    # The admin-purge must be inside the admin branch. AST-walk to confirm.
    tree = ast.parse(src)
    func = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "chat_delete"
    )
    # Find the `if current_user.is_admin():` if-node nested inside the function
    admin_if = None
    for node in ast.walk(func):
        if isinstance(node, ast.If):
            # Check whether the test is a `current_user.is_admin()` call
            ast_dump = ast.unparse(node.test)
            if ast_dump == "current_user.is_admin()":
                admin_if = node
                break
    assert admin_if is not None, (
        "SP-021 REGRESSION: chat_delete no longer contains an "
        "`if current_user.is_admin():` branch."
    )
    # Confirm the .delete() call is inside that if-branch's body (true branch).
    admin_body_src = "\n".join(ast.unparse(n) for n in admin_if.body)
    assert ".delete()" in admin_body_src, (
        "SP-021 REGRESSION: Report.delete() is not inside the admin branch. "
        "Any member can purge reports."
    )
    # Confirm the .update() call is in the else branch.
    else_body_src = "\n".join(ast.unparse(n) for n in admin_if.orelse)
    assert ".update(" in else_body_src, (
        "SP-021 REGRESSION: the non-admin branch no longer null-updates "
        "suspect_conversation_id."
    )


def test_chat_delete_orders_update_before_conversation_delete():
    """Privileged-path: the Report update/delete must appear in source BEFORE
    the Conversation delete. SQLAlchemy's flush dependency tracking generally
    handles this correctly, but source-order is the safer guarantee — if
    someone refactors to db.session.delete(conversation) first, we'd hit FK
    violations or (worse) lose Reports to the cascade before we can null
    their FK column."""
    src = _function_source(CHAT_ROUTES, "chat_delete")
    tree = ast.parse(src)
    func = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "chat_delete"
    )

    # Walk the body in source order and find:
    # (a) the line that touches Report.query (any .delete() or .update())
    # (b) the line that calls db.session.delete(conversation)
    report_line = None
    conv_delete_line = None
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            call_src = ast.unparse(node)
            if "Report.query" in call_src and (
                ".delete()" in call_src or ".update(" in call_src
            ):
                if report_line is None or node.lineno < report_line:
                    report_line = node.lineno
            if "db.session.delete" in call_src and "conversation" in call_src:
                if conv_delete_line is None or node.lineno < conv_delete_line:
                    conv_delete_line = node.lineno

    assert report_line is not None, (
        "SP-021 REGRESSION: chat_delete contains no Report.query touch — "
        "the Report-handling logic has disappeared entirely."
    )
    assert conv_delete_line is not None, (
        "SP-021 REGRESSION: chat_delete no longer calls "
        "db.session.delete(conversation)."
    )
    assert report_line < conv_delete_line, (
        f"SP-021 REGRESSION: Report.query update/delete at line "
        f"{report_line} comes AFTER db.session.delete(conversation) at "
        f"line {conv_delete_line}. With FK constraints this will either "
        f"fail with a foreign-key violation or (if cascade is set) wipe "
        f"Report rows we intended to preserve."
    )
