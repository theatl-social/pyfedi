"""Guards for the anonymous-viewer comment filters in app/post/util.py.

Both anonymous branches once called ``comments.filter(...)`` and threw the
result away. SQLAlchemy's Query is immutable -- ``filter()`` returns a *new*
query -- so the low-score cutoff never applied, and heavily-downvoted comments
stayed visible to logged-out visitors and crawlers. Upstream added instance
silencing directly above one of those lines without noticing.

Source-level rather than behavioural on purpose: exercising the real query
needs a populated database, and the defect is invisible at runtime -- no
error, no warning, just unfiltered rows. app.post.util cannot be imported
directly either (app/post/__init__.py pulls in routes, which is circular), so
this parses the file.
"""

import ast
import pathlib

SOURCE = pathlib.Path(__file__).resolve().parent.parent / "app" / "post" / "util.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))

# Functions whose `else:` branch is the anonymous (no viewer) code path.
ANON_FILTERED_FUNCTIONS = ["post_replies", "get_comment_branch"]


def _function(name):
    for node in TREE.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name}() not found in {SOURCE}")


def _anonymous_branch_statements(name):
    """Statements in the top-level `if viewer: ... else:` branch."""
    fn = _function(name)
    for node in fn.body:
        if isinstance(node, ast.If) and node.orelse:
            return node.orelse
    raise AssertionError(f"{name}(): no anonymous `else:` branch found")


def test_anonymous_filter_results_are_not_discarded():
    """A bare `comments.filter(...)` expression statement is a no-op."""
    for name in ANON_FILTERED_FUNCTIONS:
        for stmt in _anonymous_branch_statements(name):
            for sub in ast.walk(stmt):
                if (
                    isinstance(sub, ast.Expr)
                    and isinstance(sub.value, ast.Call)
                    and isinstance(sub.value.func, ast.Attribute)
                    and sub.value.func.attr == "filter"
                ):
                    raise AssertionError(
                        f"{name}(): result of .filter() discarded at line "
                        f"{sub.lineno}. Query.filter() returns a new query -- "
                        f"assign it back to `comments`."
                    )


def _anonymous_branch_source(name):
    return "\n".join(ast.unparse(s) for s in _anonymous_branch_statements(name))


def test_anonymous_branches_apply_the_low_score_cutoff():
    for name in ANON_FILTERED_FUNCTIONS:
        src = _anonymous_branch_source(name)
        assert "PostReply.score > -20" in src, f"{name}(): low-score cutoff missing"


def test_anonymous_branches_apply_instance_silencing():
    """Silencing must cover the branch view too, or it is one click to bypass."""
    for name in ANON_FILTERED_FUNCTIONS:
        src = _anonymous_branch_source(name)
        assert "silenced_instances()" in src, (
            f"{name}(): anonymous branch does not filter silenced instances"
        )
