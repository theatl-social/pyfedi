"""SP-003 regression: SECRET_KEY must be a strong, non-default value.

Tests _validate_secret_key() directly so we don't need full Flask context.
"""

import pytest

from app import _validate_secret_key


SECRET_OK = "a" * 32 + "_strong_random_key"


def test_missing_secret_key_raises():
    with pytest.raises(RuntimeError, match=r"SP-003.*not set"):
        _validate_secret_key(None)


def test_empty_secret_key_raises():
    with pytest.raises(RuntimeError, match=r"SP-003.*not set"):
        _validate_secret_key("")


@pytest.mark.parametrize(
    "bad",
    [
        "you-will-never-guesss",
        "you-will-never-guess",
        "change-me",
        "changeme",
        "secret",
        "dev",
        "development",
        "test",
    ],
)
def test_known_default_keys_rejected(bad):
    with pytest.raises(RuntimeError, match=r"SP-003.*known-default"):
        _validate_secret_key(bad)


def test_short_key_rejected():
    short_but_unknown = "x" * 16
    with pytest.raises(RuntimeError, match=r"SP-003.*too short"):
        _validate_secret_key(short_but_unknown)


def test_strong_key_accepted():
    _validate_secret_key(SECRET_OK)  # no exception = pass


def test_config_no_longer_has_fallback_literal():
    """The literal default 'you-will-never-guesss' must not appear as a fallback in config.py."""
    import pathlib

    config_path = pathlib.Path(__file__).resolve().parents[2] / "config.py"
    content = config_path.read_text()
    # The string may still appear in the known-bad-list IMPORT, but not in the
    # SECRET_KEY ASSIGNMENT line.
    for line in content.splitlines():
        if "SECRET_KEY = " in line and "STRIPE" not in line:
            assert "you-will-never-guesss" not in line, (
                f"SP-003 REGRESSION: config.py SECRET_KEY line still contains "
                f"the default fallback: {line!r}"
            )


def test_create_app_calls_validator():
    """create_app must invoke _validate_secret_key before blueprints register."""
    import ast
    import pathlib

    init_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "__init__.py"
    tree = ast.parse(init_path.read_text())
    create_app_calls_validator = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "create_app":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    func = sub.func
                    name = (
                        func.id
                        if isinstance(func, ast.Name)
                        else (func.attr if isinstance(func, ast.Attribute) else None)
                    )
                    if name == "_validate_secret_key":
                        create_app_calls_validator = True
                        break
    assert create_app_calls_validator, (
        "SP-003 REGRESSION: create_app() does not call _validate_secret_key. "
        "The startup validator is the load-bearing check."
    )
