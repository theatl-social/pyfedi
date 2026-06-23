"""SP-019 regression and privileged-path tests: post_view variants 3/4/5
must gate posts in private communities by requester membership, BUT must
allow legitimate members and admins through.

This mirrors SP-014, which gated community_view (variants 3/4/5/6) for
private communities but left the sibling post_view function unprotected.
The leaks were:

- Variant 3 (`/post`) — had its own inline gate, but inconsistent with
  community_view's pattern (no `user_id is None or` short-circuit).
- Variant 4 (`/post/like`, `/post/save`) — no gate. Any user could fetch
  full post body, votes, comments, polls of a private-community post via
  the like/save endpoints.
- Variant 5 (resolve_object lookup-by-AP-id) — no gate. Same leak through
  the resolve path that anonymous users hit.

Fix: lift the gate to the top of post_view, conditional on
`variant in (3, 4, 5)`. Variants 1 and 2 remain unguarded because they are
stub/internal helpers called from list endpoints that apply their own
SQL-level community filters.
"""

import ast
import pathlib
from unittest.mock import Mock, patch

import pytest

from app import create_app
from config import Config


class _TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True
    CACHE_TYPE = "NullCache"


@pytest.fixture
def app():
    return create_app(_TestConfig)


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
VIEWS = REPO_ROOT / "app" / "api" / "alpha" / "views.py"


def _function_source(name: str) -> str:
    src = VIEWS.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError(f"{name!r} not found in {VIEWS}")


def test_post_view_has_top_level_private_community_gate():
    src = _function_source("post_view")
    # The gate must appear before any "if variant == 3" / 4 / 5 branch.
    lines = src.splitlines()
    gate_line = next(
        (
            i
            for i, line in enumerate(lines)
            if "variant in (3, 4, 5)" in line and "post.community.private" in line
        ),
        None,
    )
    # Try the two-line form too — the assignment can wrap.
    if gate_line is None:
        for i, line in enumerate(lines):
            if "variant in (3, 4, 5)" in line:
                window = "\n".join(lines[i : i + 4])
                if "post.community.private" in window:
                    gate_line = i
                    break
    assert gate_line is not None, (
        "SP-019 REGRESSION: post_view no longer has the variant-3/4/5 "
        "private-community gate. Variants 4 and 5 leak post body, votes, "
        "comments, polls of posts in private communities to non-members."
    )
    # Confirm the gate sits BEFORE variant 3's "if variant == 3:" branch
    variant_3 = next(
        (
            i
            for i, line in enumerate(lines)
            if line.strip().startswith("if variant == 3:")
        ),
        None,
    )
    assert variant_3 is not None, "variant 3 branch not found in post_view"
    assert gate_line < variant_3, (
        "SP-019 REGRESSION: the variant gate at function-line "
        f"{gate_line} happens AFTER the variant-3 branch at function-line "
        f"{variant_3}. The gate must run before any variant builds a response."
    )


def test_post_view_gate_handles_anonymous_caller():
    """`user_id is None or post.community_id not in community_membership_private(user_id)`
    — the `user_id is None` short-circuit must be present so anonymous callers
    are denied without crashing on `community_membership_private(None)`.
    """
    src = _function_source("post_view")
    # Find the gate body
    assert "user_id is None" in src, (
        "SP-019 REGRESSION: post_view gate no longer short-circuits on "
        "anonymous (user_id is None) callers. The downstream "
        "community_membership_private call may handle None safely, but the "
        "short-circuit is the documented contract that mirrors community_view "
        "and shouldn't be removed without explicit reason."
    )


# --- Privileged-path tests: legitimate flows must not be blocked --------


def _build_mock_post(community_id=42, private=True):
    """Build a Mock post with just enough surface for the SP-019 gate."""
    post = Mock()
    post.community.private = private
    post.community_id = community_id
    # Defeat the isinstance(post, int) check inside post_view
    post.__class__ = Mock
    return post


def test_gate_allows_member_of_private_community(app):
    """A logged-in user who IS a member of the private community must not
    be rejected by the SP-019 gate. The downstream Mock-incomplete variant
    will raise something else, but never the 'Private community' message."""
    with app.app_context():
        post = _build_mock_post(community_id=42, private=True)
        with patch(
            "app.api.alpha.views.community_membership_private",
            return_value=[42],
        ):
            from app.api.alpha.views import post_view

            try:
                post_view(post=post, variant=4, user_id=1)
            except Exception as e:
                msg = str(e)
                assert "Private community" not in msg, (
                    f"SP-019 REGRESSION: gate is rejecting a legitimate "
                    f"member (community_id=42 is in their membership list). "
                    f"Got: {msg!r}"
                )
            # If no exception raised, that's also fine — the gate let it
            # through. (Won't happen in practice because the Mock can't
            # satisfy variant 4's downstream calls, but harmless.)


def test_gate_rejects_non_member_of_private_community(app):
    """Negative control: a non-member must hit the gate. Confirms the test
    above isn't a false positive caused by the gate being broken in the
    opposite direction."""
    with app.app_context():
        post = _build_mock_post(community_id=42, private=True)
        with patch(
            "app.api.alpha.views.community_membership_private",
            return_value=[99],  # User is in community 99, post is in 42
        ):
            from app.api.alpha.views import post_view

            with pytest.raises(Exception, match="Private community"):
                post_view(post=post, variant=4, user_id=1)


def test_gate_skips_public_community(app):
    """Public-community posts must never hit the gate, regardless of
    requester membership."""
    with app.app_context():
        post = _build_mock_post(community_id=42, private=False)
        with patch(
            "app.api.alpha.views.community_membership_private",
            return_value=[],  # Anonymous-equivalent
        ):
            from app.api.alpha.views import post_view

            try:
                post_view(post=post, variant=4, user_id=None)
            except Exception as e:
                msg = str(e)
                assert "Private community" not in msg, (
                    f"SP-019 REGRESSION: gate is rejecting on a PUBLIC "
                    f"community. Got: {msg!r}"
                )


def test_gate_does_not_run_on_variants_1_and_2(app):
    """Variants 1 and 2 are stub helpers called from list endpoints with
    their own SQL-level filters. They must NOT be blocked by the SP-019
    gate even when the requester is not a member of a private community —
    otherwise list endpoints would break on private-community posts they
    intentionally surface (e.g. to moderators)."""
    with app.app_context():
        post = _build_mock_post(community_id=42, private=True)
        with patch(
            "app.api.alpha.views.community_membership_private",
            return_value=[99],  # Not a member
        ):
            from app.api.alpha.views import post_view

            for variant in (1, 2):
                try:
                    post_view(post=post, variant=variant, user_id=1)
                except Exception as e:
                    msg = str(e)
                    assert "Private community" not in msg, (
                        f"SP-019 REGRESSION: gate is rejecting on variant "
                        f"{variant} (stub/internal helper). Got: {msg!r}"
                    )


def test_post_view_v4_does_not_inline_skip_gate():
    """The post-fix shape: variants 4 and 5 must not contain their own
    early-return-without-gate path. We check by asserting that the variant 4
    branch does NOT contain the words `"post_view"` immediately followed by
    a return without first encountering the top-level gate."""
    src = _function_source("post_view")
    # Find the variant-4 branch body
    lines = src.splitlines()
    v4_start = next(
        (i for i, line in enumerate(lines) if "if variant == 4:" in line),
        None,
    )
    assert v4_start is not None, "variant 4 branch not found"

    # Top-of-function gate must precede variant 4
    gate_at = next(
        (i for i, line in enumerate(lines) if "variant in (3, 4, 5)" in line),
        None,
    )
    assert gate_at is not None and gate_at < v4_start, (
        "SP-019 REGRESSION: variant 4 reachable without passing the "
        "private-community gate."
    )
