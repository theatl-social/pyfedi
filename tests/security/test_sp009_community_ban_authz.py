"""SP-009 regression: community ban/unban endpoints must require mod/owner/admin.

Previously both routes had only `@login_required`, so any authenticated user
could ban or unban anyone from any community by POSTing to the route. Now
they must check `community.is_owner() or current_user.is_admin() or
community.is_moderator()` before processing the request.

Structural test (AST-based) — no Flask app context needed.
"""

import ast
import pathlib

ROUTES = pathlib.Path(__file__).resolve().parents[2] / "app" / "community" / "routes.py"


def _function_node(name):
    src = ROUTES.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node, src
    raise AssertionError(f"function {name!r} not found in {ROUTES}")


def _function_has_authz_check(node, src):
    """Look for an authz pattern that calls is_moderator / is_owner / is_admin
    BEFORE any state-mutating call (db.session.add, .commit, .delete)."""
    src_seg = ast.get_source_segment(src, node) or ""
    has_check = "is_moderator" in src_seg and (
        "is_owner" in src_seg or "is_admin" in src_seg
    )
    return has_check


def test_community_ban_user_has_authz_check():
    node, src = _function_node("community_ban_user")
    assert _function_has_authz_check(node, src), (
        "SP-009 REGRESSION: community_ban_user no longer has the "
        "is_moderator/is_owner/is_admin authorization check. Any "
        "authenticated user could ban anyone from any community."
    )


def test_community_unban_user_has_authz_check():
    node, src = _function_node("community_unban_user")
    assert _function_has_authz_check(node, src), (
        "SP-009 REGRESSION: community_unban_user no longer has the "
        "is_moderator/is_owner/is_admin authorization check."
    )


def test_authz_check_precedes_state_mutation():
    """The check must appear textually BEFORE any db.session mutation, or
    a request that fails authz could still mutate state."""
    for name in ("community_ban_user", "community_unban_user"):
        node, src = _function_node(name)
        seg = ast.get_source_segment(src, node) or ""
        # Find the line numbers of authz keywords vs db.session.commit/add/delete
        # within the function source.
        lines = seg.splitlines()
        first_authz = next(
            (i for i, line in enumerate(lines) if "is_moderator" in line),
            None,
        )
        first_mutate = next(
            (
                i
                for i, line in enumerate(lines)
                if any(
                    k in line
                    for k in (
                        "db.session.add(",
                        "db.session.delete(",
                        "db.session.commit(",
                    )
                )
            ),
            None,
        )
        assert first_authz is not None, f"{name}: no authz check found at all"
        if first_mutate is not None:
            assert first_authz < first_mutate, (
                f"SP-009 REGRESSION in {name}: authz check at function-line "
                f"{first_authz} appears AFTER first state mutation at "
                f"function-line {first_mutate}"
            )
