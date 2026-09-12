"""Guard: a translated string's %(name)s placeholders are actually filled.

flask-babel's gettext only interpolates when keyword arguments are passed:

    s = t.ugettext(string)
    return s if not variables else s % variables

So `_('Saved. <a href="/post/%(post_id)d/edit">Edit it</a>')` with no
`post_id=` does not raise; it silently renders the literal placeholder.
Upstream v1.7.15.1 shipped exactly that in `post_edit()`, wrapped in `Markup`,
so every successful edit flashed a link to `/post/%(post_id)d/edit`. The same
defect had sat in `protocol_handler()` since 2025 ("Failed to look up %(url)s").

AST-based so it covers the whole class across `app/`, not the two known lines.
Allowed forms: every placeholder passed as a keyword, `**kwargs`, or
`_('...%(x)s') % {...}` formatted by the caller.
"""

import ast
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PLACEHOLDER = re.compile(r"%\((\w+)\)")
GETTEXT_NAMES = {"_", "_l", "gettext", "lazy_gettext"}


def _unfilled_placeholders(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in GETTEXT_NAMES):
            continue
        if not (node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            continue
        names = set(PLACEHOLDER.findall(node.args[0].value))
        if not names:
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Mod) and parent.left is node:
            continue
        if any(kw.arg is None for kw in node.keywords):
            continue
        missing = names - {kw.arg for kw in node.keywords}
        if missing:
            yield node.lineno, sorted(missing)


def test_gettext_placeholders_are_filled():
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{lineno} missing {missing}"
        for path in sorted((REPO_ROOT / "app").rglob("*.py"))
        for lineno, missing in _unfilled_placeholders(path)
    ]
    assert not offenders, (
        "gettext calls with placeholders that are never filled -- flask-babel "
        "renders these literally instead of raising:\n  " + "\n  ".join(offenders)
    )
