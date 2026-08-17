"""SP-028 — "Reject" on a follow request must not accept it.

Upstream PieFed v1.7.11 shipped the manual follow-approval feature with two
independent defects that both landed on the same side:

1. ``user_follow_request_reject()`` set ``is_accepted = True`` -- a copy/paste
   of the accept route -- so rejecting a request granted the follow locally
   while telling the remote server it had been rejected.
2. ``follow_requests.html`` pointed the *Reject* button's ``hx-post`` at
   ``user.user_follow_request_accept``, so the reject route was unreachable
   from the UI in the first place.

Together there was no way to refuse a follower: both buttons accepted. For a
user who deliberately enabled ``ap_manually_approves_followers``, that turns a
privacy control into a no-op.

These are source-level assertions on purpose. The behavioural path needs a
populated database plus outbound federation, and the failure mode here is a
one-token edit (``True``/``False``, ``accept``/``reject``) that a future merge
conflict can silently reintroduce -- exactly what these guards exist to catch.
"""

from __future__ import annotations

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
ROUTES = REPO_ROOT / "app" / "user" / "routes.py"
TEMPLATE = REPO_ROOT / "app" / "templates" / "user" / "follow_requests.html"


def _function_source(name: str) -> str:
    """Return the source of a top-level function in app/user/routes.py."""
    source = ROUTES.read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"{name}() not found in {ROUTES}")


def test_reject_route_exists():
    assert _function_source("user_follow_request_reject")


def test_reject_route_does_not_accept_the_follow():
    src = _function_source("user_follow_request_reject")
    assert "is_accepted = False" in src, (
        "user_follow_request_reject() must set is_accepted = False. Upstream "
        "v1.7.11 set it to True, so clicking Reject granted the follow."
    )
    assert "is_accepted = True" not in src, (
        "user_follow_request_reject() sets is_accepted = True somewhere -- "
        "rejecting a follow request must never accept it."
    )


def test_accept_route_still_accepts():
    """Guard against 'fixing' the reject route by breaking the accept route."""
    src = _function_source("user_follow_request_accept")
    assert "is_accepted = True" in src
    assert "is_accepted = False" not in src


def test_reject_route_federates_a_reject():
    src = _function_source("user_follow_request_reject")
    assert '"type": "Reject"' in src, (
        "the reject route must send a Reject activity, not an Accept"
    )
    assert '"type": "Accept"' not in src


def test_reject_button_posts_to_the_reject_route():
    html = TEMPLATE.read_text()
    assert "user.user_follow_request_reject" in html, (
        "follow_requests.html never references user_follow_request_reject. "
        "Upstream pointed both buttons at user_follow_request_accept, so the "
        "reject route was unreachable from the UI."
    )
    # One accept button, one reject button -- not two accept buttons.
    assert html.count("user.user_follow_request_accept") == 1, (
        "expected exactly one Accept button in follow_requests.html"
    )
    assert html.count("user.user_follow_request_reject") == 1, (
        "expected exactly one Reject button in follow_requests.html"
    )


def test_pending_requests_are_the_ones_awaiting_a_decision():
    """The listing must show is_accepted IS NULL, not rejected rows too."""
    src = _function_source("user_follow_requests")
    assert "UserFollower.is_accepted == None" in src, (
        "the follow-request listing must filter on is_accepted IS NULL so "
        "rejected requests (False) do not reappear as pending"
    )
