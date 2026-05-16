"""SP-011 regression: shared_inbox dedup must use atomic SETNX.

Previously dedup was `if redis_client.exists(id): return; redis_client.set(...)`
— a TOCTOU that lets two concurrent inbox POSTs for the same activity ID
both pass before either writes the marker. Fix uses SET ... NX EX which is
atomic at the redis-server level.
"""

import ast
import pathlib

ROUTES = (
    pathlib.Path(__file__).resolve().parents[2] / "app" / "activitypub" / "routes.py"
)


def _shared_inbox_source():
    src = ROUTES.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "shared_inbox":
            return ast.get_source_segment(src, node)
    raise AssertionError("shared_inbox not found")


def test_dedup_uses_setnx():
    """The dedup block must use redis SET with nx=True; no bare exists() check."""
    src = _shared_inbox_source()
    # The atomic form: redis_client.set(id, ..., nx=True)
    assert "nx=True" in src, (
        "SP-011 REGRESSION: shared_inbox dedup is no longer using SET ... NX. "
        "The non-atomic exists()+set() pattern allows concurrent duplicate "
        "activities to slip through within the dedup window."
    )


def test_no_separate_exists_then_set():
    """The vulnerable pattern was redis_client.exists(id) followed by
    redis_client.set(id, ...). Make sure neither remains in shared_inbox."""
    src = _shared_inbox_source()
    assert "redis_client.exists(id)" not in src, (
        "SP-011 REGRESSION: shared_inbox still calls redis_client.exists(id) "
        "(the TOCTOU half of the bug)."
    )
