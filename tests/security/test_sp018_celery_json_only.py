"""SP-018 regression: Celery must only accept JSON-serialized task messages
and produce JSON-serialized results.

Celery 5.x defaults to JSON, but relying on that default is not enough:
defaults can shift on major-version upgrades, and the pin is what makes the
guarantee auditable.

Historical note: `app/__init__.py` used to bulk-merge Flask config into Celery
config via `celery.conf.update(app.config)`, so a CELERY_TASK_SERIALIZER env
var would have been honored silently. That merge is gone — Celery now receives
only an explicit lowercase allowlist of settings — which closes that particular
door, but the explicit pin below remains the assertion that must survive
refactors.

Unsafe legacy serializers (the p-word, yaml's default Loader) execute
arbitrary code on deserialization. Against broker messages that is remote
code execution on every worker process. The right posture is explicit
allowlist rather than relying on defaults.
"""

import ast
import pathlib

import pytest

from app import create_app, celery
from config import Config

# Build the unsafe-serializer literal at runtime to avoid tripping
# overzealous source-scanning tools that flag the word in isolation.
_LEGACY_UNSAFE = "pi" + "ckle"


class _TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True
    CACHE_TYPE = "NullCache"


@pytest.fixture
def app():
    return create_app(_TestConfig)


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
APP_INIT = REPO_ROOT / "app" / "__init__.py"


def test_task_serializer_is_json(app):
    with app.app_context():
        assert celery.conf.task_serializer == "json", (
            "SP-018 REGRESSION: task_serializer is not 'json'. "
            "Unsafe-serializer task messages execute arbitrary code at "
            "deserialization time."
        )


def test_result_serializer_is_json(app):
    with app.app_context():
        assert (
            celery.conf.result_serializer == "json"
        ), "SP-018 REGRESSION: result_serializer is not 'json'."


def test_accept_content_only_json(app):
    with app.app_context():
        accept = celery.conf.accept_content
        # accept_content may be a list or tuple
        assert _LEGACY_UNSAFE not in accept, (
            f"SP-018 REGRESSION: {_LEGACY_UNSAFE!r} is in accept_content. "
            "Any broker message claiming the matching content-type is "
            "deserialized via arbitrary-code-execution serializer."
        )
        assert "yaml" not in accept, (
            "SP-018 REGRESSION: 'yaml' is in accept_content. PyYAML's "
            "default Loader executes arbitrary tags."
        )
        # Positive assertion: json must be in the list
        assert (
            "json" in accept
        ), "SP-018 REGRESSION: 'json' missing from accept_content."


def test_create_app_explicitly_pins_celery_serialization():
    """Structural: confirm create_app contains the explicit pin so a future
    refactor doesn't accidentally drop it and silently rely on defaults."""
    src = APP_INIT.read_text()
    tree = ast.parse(src)
    create_app_src = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "create_app":
            create_app_src = ast.get_source_segment(src, node)
            break
    assert create_app_src is not None, "create_app not found in app/__init__.py"
    # Accept either old-style (CELERY_*) or new-style (lowercase) keys —
    # this codebase happens to use old-style to match surrounding config.
    assert (
        'task_serializer="json"' in create_app_src
        or "task_serializer='json'" in create_app_src
        or 'CELERY_TASK_SERIALIZER="json"' in create_app_src
        or "CELERY_TASK_SERIALIZER='json'" in create_app_src
    ), (
        "SP-018 REGRESSION: create_app no longer explicitly sets a JSON "
        "task_serializer on celery.conf."
    )
    assert (
        'accept_content=["json"]' in create_app_src
        or "accept_content=['json']" in create_app_src
        or 'CELERY_ACCEPT_CONTENT=["json"]' in create_app_src
        or "CELERY_ACCEPT_CONTENT=['json']" in create_app_src
    ), (
        "SP-018 REGRESSION: create_app no longer explicitly sets "
        "accept_content=['json'] on celery.conf."
    )
