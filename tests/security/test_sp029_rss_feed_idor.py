"""SP-029 — RSS feed routes must verify the feed belongs to the community.

Upstream PieFed v1.7.11's community RSS routes take two independent path
parameters, ``community_id`` and ``feed_id``, and authorize on the first only::

    community = Community.query.get_or_404(community_id)
    if community.is_moderator() or current_user.is_admin():
        rss_feed = RssFeed.query.get_or_404(feed_id)   # never checked

A moderator legitimately passes a ``community_id`` they moderate and any
``feed_id`` they like. That gives every moderator of every community:

* **edit** — retarget another community's feed at a URL of their choosing, so
  that community starts publishing attacker-selected content under the
  ``feed_bot`` author; and
* **delete** — ``RssFeed.delete_dependencies()`` deletes every ``Post`` the
  feed ever created, so an unowned ``feed_id`` destroys another community's
  content.

Both routes now compare ``rss_feed.community_id`` against ``community.id`` and
404 on a mismatch.

Source-level assertions: exercising the routes needs a populated database, a
second community, and a moderator session, while the defect is the *absence* of
one comparison -- which is what a merge conflict silently reintroduces.
"""

from __future__ import annotations

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
ROUTES = REPO_ROOT / "app" / "community" / "routes.py"

OWNERSHIP_CHECK = "rss_feed.community_id != community.id"


def _function_source(name: str) -> str:
    source = ROUTES.read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"{name}() not found in {ROUTES}")


def test_edit_route_checks_feed_belongs_to_community():
    src = _function_source("community_rss_feed_edit")
    assert OWNERSHIP_CHECK in src, (
        "community_rss_feed_edit() must reject a feed_id belonging to another "
        "community; the moderator check only covers community_id."
    )
    assert "abort(404)" in src


def test_delete_route_checks_feed_belongs_to_community():
    src = _function_source("community_rss_feed_delete")
    assert OWNERSHIP_CHECK in src, (
        "community_rss_feed_delete() must reject a feed_id belonging to "
        "another community -- delete_dependencies() also deletes every post "
        "the feed created."
    )
    assert "abort(404)" in src


def test_edit_route_does_not_500_on_unknown_feed_id():
    """Upstream used .get(), then wrote attributes on the resulting None."""
    src = _function_source("community_rss_feed_edit")
    assert "RssFeed.query.get_or_404(feed_id)" in src, (
        "community_rss_feed_edit() should use get_or_404 for a supplied "
        "feed_id; upstream's .get() returned None and then assigned to it."
    )


def test_ownership_check_precedes_any_mutation():
    """The 404 must come before the first write, not after."""
    for fn, first_write in (
        ("community_rss_feed_edit", "rss_feed.title = form.name.data"),
        ("community_rss_feed_delete", "rss_feed.delete_dependencies()"),
    ):
        src = _function_source(fn)
        assert src.index(OWNERSHIP_CHECK) < src.index(first_write), (
            f"{fn}(): the ownership check must run before the first mutation"
        )
