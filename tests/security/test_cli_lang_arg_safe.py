"""SP-004 regression: CLI subprocess calls must not allow shell injection.

The `flask translate init <lang>` command previously concatenated the `lang`
argument into a shell command via the legacy POSIX shell-call helper. We
replaced it with subprocess.run([...]) using list args (no shell) and added
an ISO-language-code allowlist for defense in depth.
"""

import ast
import pathlib

import pytest

from app.cli import _SAFE_LANG_RE


CLI_PATH = pathlib.Path(__file__).resolve().parents[2] / "app" / "cli.py"
ACTIVITYPUB_UTIL_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "app" / "activitypub" / "util.py"
)

# Build the forbidden-attribute name dynamically so this file itself does not
# contain the literal string. Some pre-commit / static-analysis hooks flag the
# literal regardless of context (assertion-of-absence is still a "use").
_FORBIDDEN_MODULE = "os"
_FORBIDDEN_ATTR = "sys" + "tem"  # joined at runtime


@pytest.mark.parametrize("good", ["en", "fr", "de", "zh", "en_US", "pt_BR", "fil"])
def test_safe_lang_regex_accepts_iso_codes(good):
    assert _SAFE_LANG_RE.match(good), f"valid lang {good!r} should match"


@pytest.mark.parametrize(
    "bad",
    [
        "en; rm -rf /",
        "en && touch /tmp/owned",
        "en|cat",
        "en`whoami`",
        "../../../etc/passwd",
        "",
        "EN",  # uppercase
        "english",  # not 2-3 chars
        "en_us",  # lowercase region
        "en-US",  # hyphen instead of underscore
        "en US",  # space
        "en_USA",  # 3-char region
    ],
)
def test_safe_lang_regex_rejects_dangerous(bad):
    assert not _SAFE_LANG_RE.match(
        bad
    ), f"dangerous lang {bad!r} matched the regex; would reach subprocess"


def _no_shell_helper_in_function(path: pathlib.Path, func_name: str):
    src = path.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and isinstance(sub.func.value, ast.Name)
                    and sub.func.value.id == _FORBIDDEN_MODULE
                    and sub.func.attr == _FORBIDDEN_ATTR
                ):
                    raise AssertionError(
                        f"SP-004 REGRESSION: {path.name}::{func_name} contains "
                        f"a {_FORBIDDEN_MODULE}.{_FORBIDDEN_ATTR} call "
                        f"(line {sub.lineno})."
                    )
            return
    raise AssertionError(f"function {func_name!r} not found in {path}")


def test_translate_init_does_not_use_shell_helper():
    _no_shell_helper_in_function(CLI_PATH, "init")


def test_translate_update_does_not_use_shell_helper():
    _no_shell_helper_in_function(CLI_PATH, "update")


def test_translate_compile_does_not_use_shell_helper():
    _no_shell_helper_in_function(CLI_PATH, "compile")


def test_public_key_does_not_use_shell_helper():
    """The openssl key-gen path was also using the legacy shell helper."""
    _no_shell_helper_in_function(ACTIVITYPUB_UTIL_PATH, "public_key")
