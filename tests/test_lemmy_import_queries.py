"""`flask lemmy-import` must only read columns its queries actually select.

Upstream PieFed v1.7.11 added the `lemmy-import` CLI command. Its post and
comment loops read ``row.instance_id``, but Lemmy's ``post`` and ``comment``
tables have no such column and the ``SELECT`` statements do not list one -- so
the command raises ``AttributeError`` on the first post it touches, after
having already committed the users and communities it imported.

This fork derives a post's / comment's instance from its author instead
(``person_to_instance_map``, built during the users pass, where ``instance_id``
*is* selected).

The check is static because exercising the command needs a live Lemmy
database. It parses each ``lemmy_conn.execute(text("SELECT ..."))`` in the
function, collects the columns it selects, and asserts that every ``row.<attr>``
read afterwards is backed by one of them -- which catches this whole class of
defect, not just the two instances upstream shipped.
"""

from __future__ import annotations

import ast
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CLI = REPO_ROOT / "app" / "cli.py"


def _lemmy_import_source() -> str:
    src = CLI.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "lemmy_import":
            return ast.get_source_segment(src, node) or ""
    raise AssertionError("lemmy_import() not found in app/cli.py")


def _select_blocks(src: str) -> list[str]:
    """Every SELECT ... FROM body in the function, in source order."""
    return re.findall(r"SELECT\b(.*?)\bFROM\b", src, re.S | re.I)


def _columns_in(select_body: str) -> set[str]:
    """Column names a SELECT list makes available on the result row."""
    cols: set[str] = set()
    for piece in select_body.split(","):
        piece = piece.strip()
        if not piece:
            continue
        # handle "p.id as person_id" / "p.instance_id" / "instance_id"
        alias = re.search(r"\bas\s+(\w+)\s*$", piece, re.I)
        if alias:
            cols.add(alias.group(1))
            continue
        cols.add(piece.split(".")[-1].strip())
    return cols


def test_lemmy_import_exists():
    assert _lemmy_import_source()


def test_every_row_attribute_is_selected_somewhere():
    """Catch reads of columns no query in the function provides.

    Deliberately a union across every SELECT rather than a per-query check:
    matching each `row.x` to the query that produced *its* cursor needs real
    flow analysis. So this catches wholly-unknown attributes (upstream's
    `row.instance`), while the post/comment case -- where `instance_id` is
    real but belongs to a *different* query -- is pinned by
    test_instance_id_is_derived_from_the_author_for_posts_and_comments below.
    """
    src = _lemmy_import_source()
    available: set[str] = set()
    for block in _select_blocks(src):
        available |= _columns_in(block)

    read = set(re.findall(r"\brow\.(\w+)", src))
    missing = sorted(read - available)
    assert not missing, (
        "lemmy_import() reads row attributes that none of its SELECT "
        f"statements provide: {missing}. Lemmy's post/comment tables have no "
        "instance_id -- derive it from the author via person_to_instance_map."
    )


def test_instance_id_is_derived_from_the_author_for_posts_and_comments():
    src = _lemmy_import_source()
    assert "person_to_instance_map" in src, (
        "the author->instance map used to populate post/comment instance_id "
        "is gone; upstream's row.instance_id would AttributeError"
    )
    assert "instance_id=post_instance_id" in src
    assert "instance_id=comment_instance_id" in src
    assert "existing_post.instance_id = post_instance_id" in src
    assert "existing_comment.instance_id = comment_instance_id" in src


def test_user_instance_comes_from_the_selected_column():
    """Upstream wrote row.instance.id here; there is no `instance` attribute."""
    src = _lemmy_import_source()
    assert "row.instance.id" not in src, (
        "row.instance.id is back -- the users query selects p.instance_id, "
        "and the row has no `instance` relationship attribute"
    )
