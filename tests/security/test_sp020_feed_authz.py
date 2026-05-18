"""SP-020 regression: Feed authorization fixes.

Three findings consolidated into SP-020:

1. **Critical** — `feed_add_community` read `user_id` from `request.args`,
   making the ownership check `Feed.query.get(feed_id).user_id != user_id`
   tautological. Any logged-in user could add/remove communities to/from
   any other user's feed (and for public feeds, federate the change signed
   by the victim feed's private key).

2. **High** — `make_feed` accepted `is_instance_feed=True` from any user.
   `edit_feed` gated this on `user.is_admin()`; creation did not. The flag
   surfaces a feed in the site-wide instance-feeds menu, effectively
   letting unprivileged users publish into a global navigation surface.

3. **High** — `show_feed_rss` had no privacy gate. The HTML sibling
   `show_feed` rejects non-owner/non-subscriber requests on private feeds;
   the .rss path served anonymous requests. Private feed names are
   auto-suffixed with the owner's username and are enumerable.
"""

import ast
import pathlib


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FEED_ROUTES = REPO_ROOT / "app" / "feed" / "routes.py"
SHARED_FEED = REPO_ROOT / "app" / "shared" / "feed.py"


def _function_source(path: pathlib.Path, name: str) -> str:
    src = path.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError(f"{name!r} not found in {path}")


# --- F-CRIT-1: feed_add_community no longer trusts user_id from query string


def test_feed_add_community_does_not_read_user_id_from_args():
    src = _function_source(FEED_ROUTES, "feed_add_community")
    assert "request.args.get('user_id')" not in src, (
        "SP-020 REGRESSION: feed_add_community reads user_id from "
        "request.args again. The tautological ownership check is back; any "
        "logged-in user can add communities to any other user's feed."
    )
    assert 'request.args.get("user_id")' not in src, (
        "SP-020 REGRESSION: feed_add_community reads user_id from "
        "request.args (double-quoted form)."
    )
    # Positive: must source user_id from current_user
    assert "current_user.id" in src, (
        "SP-020 REGRESSION: feed_add_community no longer sources user_id "
        "from current_user.id."
    )


def test_feed_add_community_resolves_target_feed_and_checks_ownership():
    src = _function_source(FEED_ROUTES, "feed_add_community")
    # Must look up the target feed by feed_id and verify ownership against
    # current_user (or admin override).
    assert "get_or_404" in src, (
        "SP-020 REGRESSION: feed_add_community no longer uses get_or_404 "
        "to resolve the target feed — silent None-returns leak existence."
    )
    # The check should be against current_user, not args-derived user_id
    has_target_check = (
        "target_feed.user_id != user_id" in src
        or "target_feed.user_id != current_user.id" in src
    )
    assert has_target_check, (
        "SP-020 REGRESSION: feed_add_community no longer enforces "
        "target_feed.user_id matches the session user."
    )


# --- F-H-3: make_feed forces is_instance_feed=False for non-admins


def test_make_feed_gates_is_instance_feed_on_admin():
    src = _function_source(SHARED_FEED, "make_feed")
    # The gate can be expressed as `if is_instance_feed and not user.is_admin():`
    # or `is_instance_feed = is_instance_feed and user.is_admin()`. Either is OK.
    has_gate = (
        "is_instance_feed" in src and "is_admin" in src and "False" in src
    ) or "is_instance_feed and user.is_admin" in src
    assert has_gate, (
        "SP-020 REGRESSION: make_feed no longer admin-gates is_instance_feed. "
        "Non-admins can create site-wide-menu feeds."
    )


# --- F-H-4: show_feed_rss now has the same privacy gate as show_feed


def test_show_feed_rss_has_privacy_gate():
    src = _function_source(FEED_ROUTES, "show_feed_rss")
    assert "feed.public" in src, (
        "SP-020 REGRESSION: show_feed_rss no longer references feed.public. "
        "Private feed RSS leak is back."
    )
    # The function should also have login_required_if_private_instance
    # decorator (one line above the function def). Check the surrounding text.
    full_src = FEED_ROUTES.read_text()
    # Find the show_feed_rss definition and look at the preceding ~5 lines.
    lines = full_src.splitlines()
    def_idx = next(
        (i for i, line in enumerate(lines) if "def show_feed_rss(" in line),
        None,
    )
    assert def_idx is not None, "show_feed_rss not found in routes.py"
    preceding = "\n".join(lines[max(0, def_idx - 5) : def_idx])
    assert "login_required_if_private_instance" in preceding, (
        "SP-020 REGRESSION: show_feed_rss is missing the "
        "login_required_if_private_instance decorator. Anonymous users on a "
        "private-instance can fetch any feed RSS."
    )
