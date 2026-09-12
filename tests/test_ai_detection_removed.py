"""Guard: upstream's two automated AI-detection features stay out of this fork.

Both were removed deliberately on 2026-09-12. Upstream will keep shipping them,
so without this file the next merge would quietly re-enable both.

## 1. Text detection via an external service (upstream v1.6.0, Nov 2025)

An operator-configured endpoint (config key built from `DETECT_AI` + `_ENDPOINT`)
was called with the public URL of posts and comments by recently created
accounts. What it did with the answer:

- **Auto-banned users.** If three or more of a new account's posts/comments in
  24 hours scored as not-human at >80% confidence, `Post.new()` /
  `PostReply.new()` set `user.banned = True` with no human in the loop, based
  on a third-party classifier's opinion. Detections were tracked in a Redis
  sorted set keyed `ai_detection:user:<id>`.
- Set `ai_generated` on posts it scored as AI.
- Exposed `/post/<id>/check_ai` and `/post_reply/<id>/check_ai` with **no
  authentication**: anyone logged out could make the server call the service
  for any post. Those handlers also concatenated the service's
  `detection_result` string into HTML unescaped, and 500'd on a missing id.
- `/post/<id>/set_ai` was only reachable from that route's output.

## 2. C2PA image-provenance inspection (upstream v1.7.13, Aug 2026)

`inspect_image_c2pa()` parsed every uploaded image **and every remote image
fetched for a federated post** with `c2pa-python`, a native library, setting
`Post.ai_generated` when an embedded Content Credentials manifest claimed AI
origin. Always on, no setting. It added a native parser to an untrusted-input
path, and the signal is weak in both directions: stripping the manifest is a
screenshot away, and nothing checked the manifest's signature validity.

## What deliberately stays

- The `ai_generated` column on `post` (schema is immutable per CLAUDE.md) and
  any manual labelling of it by authors.
- Existing rows already flagged by either feature are left as they are.
- The admin-toggleable em-dash heuristic in `PostReply.new()` is a separate
  feature and is not covered here.

If either feature is ever wanted back, delete the matching test in the same
commit, and fix the problems listed above first.

Assertions match identifiers, so a comment in `app/` that names one of these
will trip them — reword the comment rather than weakening the guard.
"""

import pathlib
import tomllib

import pytest

from app import create_app
from config import Config

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = REPO_ROOT / "app"

SOURCE_FILES = sorted(APP.rglob("*.py")) + [REPO_ROOT / "config.py", REPO_ROOT / "pyfedi.py"]
TEMPLATES = sorted((APP / "templates").rglob("*.html"))

# Assembled so this file does not itself contain the literal it forbids.
ENDPOINT_KEY = "DETECT_AI" + "_ENDPOINT"


class _TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    CACHE_TYPE = "NullCache"
    SECRET_KEY = "test-secret-key-xxxxxxxxxxxxxxxxxxxxxxxx"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}


@pytest.fixture(scope="module")
def app():
    return create_app(_TestConfig)


def _offenders(needle, files):
    return [str(p.relative_to(REPO_ROOT)) for p in files if needle in p.read_text(encoding="utf-8")]


# --- 1. external text detection ------------------------------------------


def test_no_detection_endpoint_setting():
    offenders = _offenders(ENDPOINT_KEY, SOURCE_FILES + TEMPLATES)
    assert not offenders, (
        f"The external AI-detection endpoint setting is back in {offenders}. "
        "It drove automatic bans of new accounts from a third-party classifier "
        "score. See this module's docstring."
    )


def test_no_auto_ban_detection_tracking():
    offenders = _offenders("ai_detection:user:", SOURCE_FILES)
    assert not offenders, (
        f"The Redis detection tally that auto-bans users is back in {offenders}."
    )


def test_no_can_detect_ai_template_flag():
    offenders = _offenders("can_detect_ai", SOURCE_FILES + TEMPLATES)
    assert not offenders, (
        f"`can_detect_ai` is back in {offenders}; it gates the 'Written by AI?' "
        "menu items that call the unauthenticated check routes."
    )


@pytest.mark.parametrize(
    "endpoint",
    ["post.post_check_ai", "post.post_reply_check_ai", "post.post_set_ai"],
)
def test_check_ai_routes_not_registered(app, endpoint):
    """Assert the live url_map, not the source: a route exists only if registered."""
    assert endpoint not in app.view_functions, (
        f"{endpoint} is routed again. The check routes had no authentication, "
        "let anonymous users trigger outbound requests, and wrote the service's "
        "response into HTML unescaped."
    )


def test_no_check_ai_urls_in_templates():
    offenders = _offenders("check_ai", TEMPLATES) + _offenders("set_ai", TEMPLATES)
    assert not offenders, f"Templates reference the removed AI check routes: {offenders}"


# --- 2. C2PA image inspection --------------------------------------------


def test_no_c2pa_in_app_code():
    offenders = _offenders("c2pa", SOURCE_FILES)
    assert not offenders, (
        f"C2PA inspection is back in {offenders}. It ran a native parser over "
        "every remote post image for a signal that is trivially stripped."
    )


def test_c2pa_not_a_dependency():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = pyproject["project"]["dependencies"]
    offenders = [d for d in deps if d.lower().startswith("c2pa")]
    assert not offenders, f"c2pa is a dependency again: {offenders}. Also run `uv lock`."


def test_c2pa_not_in_lockfile():
    lock = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    assert 'name = "c2pa-python"' not in lock, (
        "c2pa-python is still in uv.lock — run `uv lock` after removing it from pyproject.toml."
    )
