"""Guard: an imported topic is committed before its id goes to a celery task.

`create_topic_and_children()` hands `new_topic.id` to
`process_topic_communities`, which runs in its own DB session (via
`get_task_session()`) and writes `community.topic_id` -- a foreign key to that
topic. Upstream v1.7.15.1 enqueued the task straight after `flush()` and only
committed after recursing through every child topic.

A flushed-but-uncommitted row is invisible to another session, and Postgres
does not wait for it: verified on Postgres 17 on 2026-09-12, the worker's
UPDATE fails immediately with `community_topic_id_fkey`, both before and after
the web transaction later commits. So with an idle worker, imported topics
silently ended up with no communities while the subscriptions still went out.

Source-level because the failure needs two real Postgres sessions; SQLite in CI
cannot reproduce it.
"""

import ast
import pathlib

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "app" / "admin" / "util.py"


def _function(name):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name}() not found in {SOURCE}")


def _is_commit(node):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "commit")


def _dispatches_task(node):
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Name) and func.id == "process_topic_communities":
            return True
        if (isinstance(func, ast.Attribute) and func.attr == "delay"
                and isinstance(func.value, ast.Name)
                and func.value.id == "process_topic_communities"):
            return True
    return False


def test_topic_committed_before_task_dispatch():
    fn = _function("create_topic_and_children")
    dispatch_index = next(
        (i for i, stmt in enumerate(fn.body) if _dispatches_task(stmt)), None
    )
    assert dispatch_index is not None, "process_topic_communities is no longer dispatched here"
    committed_before = any(
        _is_commit(sub)
        for stmt in fn.body[:dispatch_index]
        for sub in ast.walk(stmt)
    )
    assert committed_before, (
        "create_topic_and_children() dispatches process_topic_communities "
        "before committing the topic. The task's separate session cannot see "
        "the uncommitted row, so community.topic_id fails its foreign key."
    )
