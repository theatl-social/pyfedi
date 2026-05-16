"""SP-005 regression: security-sensitive token/ID generators must use `secrets`,
not `random`. random.Random is Mersenne Twister — predictable from observed
output. secrets.* reads from os.urandom every call.
"""

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
AUTH_UTIL = REPO / "app" / "auth" / "util.py"
APP_UTIL = REPO / "app" / "utils.py"


def _calls_in_function(path, name):
    """Walk a function's AST and yield (module, attr) pairs for each ATTRIBUTE
    call (e.g. `secrets.choice(...)` -> ('secrets', 'choice'))."""
    src = path.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == name):
            continue
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and isinstance(sub.func.value, ast.Name)
            ):
                yield (sub.func.value.id, sub.func.attr)
        return
    raise AssertionError(f"function {name!r} not found in {path}")


def test_random_token_uses_secrets():
    """The function used for password-reset / verification tokens must use
    secrets.choice, not random.choice."""
    calls = list(_calls_in_function(AUTH_UTIL, "random_token"))
    assert ("secrets", "choice") in calls, (
        "SP-005 REGRESSION: random_token() no longer calls secrets.choice. "
        "Predictable tokens enable account takeover via password-reset replay."
    )
    assert (
        "random",
        "choice",
    ) not in calls, "SP-005 REGRESSION: random_token() still calls random.choice."


def test_gibberish_uses_secrets():
    """gibberish() generates IDs that may end up in URLs / filenames."""
    calls = list(_calls_in_function(APP_UTIL, "gibberish"))
    assert (
        "secrets",
        "choice",
    ) in calls, "SP-005 REGRESSION: gibberish() no longer calls secrets.choice."
    assert (
        "random",
        "choice",
    ) not in calls, "SP-005 REGRESSION: gibberish() still calls random.choice."
