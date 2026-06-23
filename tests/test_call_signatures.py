"""Static guard against call-signature drift in shared / `--ours` modules.

THE BUG THIS CATCHES (it took prod down once, PR #71):
  During an upstream merge, `app/utils.py` (and other shared modules) are taken
  `--ours` to preserve the SP security patches. Upstream sometimes changes a
  function's signature (e.g. adds `include_following=` to `get_deduped_post_ids`,
  or `s3_connection` to `archive_post`), and an auto-merged caller such as
  `app/main/routes.py` then calls it with the new argument. Our `--ours` copy
  lacks the parameter -> `TypeError` at REQUEST time. Import/`create_app()` smoke
  tests never call the function, so this slips through CI to production.

WHAT THIS DOES:
  Walks the AST of every module under `app/` and, for every call to a function
  imported from one of the GUARDED modules, asserts the call only passes
  arguments the function's signature accepts -- both the positional-argument
  count and the keyword-argument names -- unless the function declares *args /
  **kwargs. Pure static analysis: no DB, no app context, fast.

It is intentionally conservative (resolves callees by their `from X import name`
so there are no same-name collisions, and skips `*args`/`**kwargs`/method calls)
to avoid false positives. Extend GUARDED_MODULES if a new shared module starts
causing these.
"""

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
APP = REPO / "app"

# Modules frequently taken `--ours` during merges and called cross-module.
GUARDED_MODULES = {
    "app.utils",
    "app.shared.post",
    "app.shared.community",
}


def _module_file(dotted: str) -> pathlib.Path:
    return APP.joinpath(*dotted.split(".")[1:]).with_suffix(".py")


def _signatures(dotted: str) -> dict:
    """{func_name: sig} for MODULE-LEVEL defs only (class methods excluded)."""
    tree = ast.parse(_module_file(dotted).read_text())
    sigs = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = node.args
            sigs[node.name] = {
                "max_pos": len(a.posonlyargs) + len(a.args),
                "names": {arg.arg for arg in a.posonlyargs + a.args + a.kwonlyargs},
                "varargs": a.vararg is not None,
                "kwargs": a.kwarg is not None,
            }
    return sigs


def test_no_call_signature_mismatch_in_guarded_modules():
    sigs_by_mod = {m: _signatures(m) for m in GUARDED_MODULES}
    problems = []

    for path in APP.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue

        # local-name -> (source_module, original_name) for guarded imports
        imported = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in GUARDED_MODULES:
                for alias in node.names:
                    if alias.name != "*":
                        imported[alias.asname or alias.name] = (node.module, alias.name)
        if not imported:
            continue

        rel = path.relative_to(REPO)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            ref = imported.get(node.func.id)
            if not ref:
                continue
            mod, orig = ref
            sig = sigs_by_mod[mod].get(orig)
            if sig is None:
                continue

            # positional argument count
            star_in_call = any(isinstance(a, ast.Starred) for a in node.args)
            n_pos = sum(1 for a in node.args if not isinstance(a, ast.Starred))
            if not sig["varargs"] and not star_in_call and n_pos > sig["max_pos"]:
                problems.append(
                    f"{rel}:{node.lineno}: {orig}() called with {n_pos} positional "
                    f"args but {mod}.{orig} accepts at most {sig['max_pos']}"
                )

            # keyword argument names
            if not sig["kwargs"]:
                for kw in node.keywords:
                    if kw.arg is not None and kw.arg not in sig["names"]:
                        problems.append(
                            f"{rel}:{node.lineno}: {orig}(..., {kw.arg}=...) but "
                            f"{mod}.{orig} has no parameter '{kw.arg}'"
                        )

    assert not problems, (
        "Call-signature mismatches against guarded modules "
        "(a function is called with an argument its signature doesn't accept -- "
        "graft the upstream signature change into the --ours copy):\n  "
        + "\n  ".join(sorted(problems))
    )
