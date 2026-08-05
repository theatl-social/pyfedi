# Unlimited Votes and Public Profile Vote Totals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Allow this fork to disable daily vote quotas with VOTE_QUOTA=0 and publicly show each profile's aggregate upvote/downvote totals.

**Architecture:** Keep the existing environment variable and Redis counter. Add one small shared predicate that preserves the positive-quota threshold exactly and treats only zero as unlimited; reuse it in local/API and inbound ActivityPub flows. Extract the public aggregate totals into a tiny template partial and keep all sensitive profile fields in their existing admin-only wrapper.

**Tech Stack:** Python 3.14, Flask, SQLAlchemy, Jinja2, pytest, unittest.mock.

## Global Constraints

- VOTE_QUOTA=0 disables quota rejection; absent or positive values preserve the existing behavior.
- Apply the disabled mode to browser, API, and inbound ActivityPub Like/Dislike votes.
- Expose only aggregate upvotes / downvotes; never expose voter identities or existing admin-only profile metadata.
- Do not add a migration, dependency, endpoint, or ActivityPub schema change.
- Do not deploy or publish this branch as part of implementation; production must set VOTE_QUOTA=0 in its own runtime environment when the release is authorized.
- Run tests with CACHE_TYPE=NullCache CACHE_REDIS_URL=memory:// SERVER_NAME=localhost on macOS.

---

## File Structure

- Create app/shared/voting.py: one reusable quota predicate shared by local/API and ActivityPub vote handlers.
- Modify app/shared/post.py: use the predicate before casting post votes.
- Modify app/shared/reply.py: use the predicate before casting reply votes.
- Modify app/activitypub/routes.py: use the predicate before accepting Like and Dislike activities.
- Modify app/user/routes.py: calculate a profile quota fraction only when a non-zero quota exists.
- Create app/templates/user/_profile_vote_totals.html: public aggregate vote-count presentation.
- Modify app/templates/user/show_profile.html: include the public partial outside the admin-only block.
- Modify config.py: document the supported VOTE_QUOTA=0 release setting without changing parsing behavior.
- Create tests/test_vote_quota_and_profile_visibility.py: focused regression coverage for the helper, all enforcement boundaries, and public-profile output.
- Modify docs/RELEASE_NOTES.md: record the operator action and the public-profile privacy change for the next fork release.

### Task 1: Lock the zero-quota contract with focused failing tests

**Files:**

- Create: tests/test_vote_quota_and_profile_visibility.py

**Interfaces:**

- Consumes: app.shared.voting.vote_quota_exceeded(user_id: int) -> bool (introduced in Task 2).
- Consumes: app.user.routes.profile_vote_quota_used(user_id: int) -> float (introduced in Task 4).
- Produces: regression tests that later tasks must satisfy.

- [ ] **Step 1: Add a minimal SQLite application fixture and imports**

~~~
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app import create_app
from config import Config


class _TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True
    CACHE_TYPE = "NullCache"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    SERVER_NAME = "test.localhost"
    RATELIMIT_ENABLED = False
    CELERY_ALWAYS_EAGER = True


@pytest.fixture
def app():
    return create_app(_TestConfig)
~~~

- [ ] **Step 2: Write failing tests for the shared contract and profile arithmetic**

~~~
@pytest.mark.parametrize(
    ("quota", "votes_cast", "expected"),
    [(0, 10_000, False), (240, 240, False), (240, 241, True)],
)
def test_vote_quota_exceeded_preserves_threshold_and_disables_at_zero(
    app, quota, votes_cast, expected
):
    from app.shared.voting import vote_quota_exceeded

    app.config["VOTE_QUOTA"] = quota
    with app.app_context(), patch(
        "app.shared.voting.votes_cast_today", return_value=votes_cast
    ):
        assert vote_quota_exceeded(42) is expected


def test_profile_quota_fraction_is_zero_when_quota_is_disabled(app):
    from app.user.routes import profile_vote_quota_used

    app.config["VOTE_QUOTA"] = 0
    with app.app_context(), patch(
        "app.user.routes.votes_cast_today", return_value=10_000
    ):
        assert profile_vote_quota_used(42) == 0
~~~

- [ ] **Step 3: Write failing local/API enforcement tests**

Use SRC_API so browser authentication is outside this focused test. Mock the API user, permission gate, query result, quota predicate, task queue, and mark-as-read call. Run each handler once with vote_quota_exceeded returning False and once with it returning True:

~~~
def test_post_and_reply_votes_continue_when_quota_is_disabled(app):
    from app.constants import SRC_API
    from app.shared.post import vote_for_post
    from app.shared.reply import vote_for_reply

    app.config["VOTE_QUOTA"] = 0
    user = SimpleNamespace(id=42, banned=False)
    post = SimpleNamespace(id=1, community=Mock(), vote=Mock(return_value=None))
    reply = SimpleNamespace(id=2, community=Mock(), vote=Mock(return_value=None))

    with app.app_context(), \
        patch("app.shared.post.authorise_api_user", return_value=user), \
        patch("app.shared.post.can_upvote", return_value=True), \
        patch("app.shared.post.db.session.query") as post_query, \
        patch("app.shared.post.mark_post_read"), \
        patch("app.shared.post.vote_quota_exceeded", return_value=False), \
        patch("app.shared.post.task_selector"), \
        patch("app.shared.reply.authorise_api_user", return_value=user), \
        patch("app.shared.reply.can_upvote", return_value=True), \
        patch("app.shared.reply.db.session.query") as reply_query, \
        patch("app.shared.reply.vote_quota_exceeded", return_value=False), \
        patch("app.shared.reply.task_selector"):
        post_query.return_value.get.return_value = post
        reply_query.return_value.filter_by.return_value.one.return_value = reply
        vote_for_post(1, "upvote", False, None, SRC_API, auth="token")
        vote_for_reply(2, "upvote", False, None, SRC_API, auth="token")

    post.vote.assert_called_once_with(user, "upvote", None)
    reply.vote.assert_called_once_with(user, "upvote", None)
~~~

Add companion cases using pytest.raises(TooManyRequests) with each module predicate returning True. Assert post.vote and reply.vote are not called in those companion cases.

- [ ] **Step 4: Write failing inbound ActivityPub enforcement tests**

Call process_upvote and process_downvote directly. Patch the module's Post and PostReply types to controlled classes, find_liked_object, permission helpers, blocked_users, instance_banned, log_incoming_ap, announce_activity_to_followers, and vote_quota_exceeded. Parameterize the two handler names and assert the synthetic liked object receives one vote when the predicate returns False. Repeat with the predicate returning True and assert it receives none.

~~~
@pytest.mark.parametrize(
    ("handler_name", "direction"),
    [("process_upvote", "upvote"), ("process_downvote", "downvote")],
)
def test_inbound_votes_continue_when_quota_is_disabled(
    app, monkeypatch, handler_name, direction
):
    import app.activitypub.routes as routes

    class Liked:
        community = Mock()
        author = SimpleNamespace(id=99)
        vote = Mock()

    liked = Liked()
    remote_user = SimpleNamespace(
        id=42, instance=SimpleNamespace(domain="remote.test")
    )
    monkeypatch.setattr(routes, "Post", Liked)
    monkeypatch.setattr(routes, "PostReply", type("Reply", (), {}))
    monkeypatch.setattr(routes, "find_liked_object", lambda _ap_id: liked)
    monkeypatch.setattr(routes, "can_upvote", lambda *_args: direction == "upvote")
    monkeypatch.setattr(routes, "can_downvote", lambda *_args: direction == "downvote")
    monkeypatch.setattr(routes, "instance_banned", lambda _domain: False)
    monkeypatch.setattr(routes, "blocked_users", lambda _user_id: [])
    monkeypatch.setattr(routes, "vote_quota_exceeded", lambda _user_id: False)
    monkeypatch.setattr(routes, "log_incoming_ap", Mock())
    monkeypatch.setattr(routes, "announce_activity_to_followers", Mock())

    with app.app_context():
        getattr(routes, handler_name)(
            remote_user,
            False,
            {
                "id": "https://remote.test/activity/1",
                "object": "https://test.localhost/post/1",
            },
            False,
        )

    liked.vote.assert_called_once()
~~~

- [ ] **Step 5: Write failing public-profile presentation tests**

~~~
def test_profile_vote_totals_partial_needs_no_authenticated_viewer(app):
    from flask import render_template

    user = SimpleNamespace(
        get_num_upvotes=lambda: 7,
        get_num_downvotes=lambda: 3,
    )
    with app.app_context():
        html = render_template("user/_profile_vote_totals.html", user=user)

    assert "Votes" in html
    assert "7 / 3" in html


def test_profile_includes_public_vote_totals_before_admin_only_metadata():
    template = Path("app/templates/user/show_profile.html").read_text()
    public_totals = '{% include "user/_profile_vote_totals.html" %}'
    admin_block = (
        "{% if current_user.is_authenticated and "
        "current_user.get_id() in admin_ids -%}"
    )

    assert public_totals in template
    assert template.index(public_totals) < template.index(admin_block)
~~~

- [ ] **Step 6: Run the new test file to verify it fails**

Run: CACHE_TYPE=NullCache CACHE_REDIS_URL=memory:// SERVER_NAME=localhost uv run pytest tests/test_vote_quota_and_profile_visibility.py -v

Expected: collection fails because app.shared.voting, profile_vote_quota_used, and the profile totals partial do not yet exist.

- [ ] **Step 7: Commit the failing tests**

~~~
git add tests/test_vote_quota_and_profile_visibility.py
git commit -m "test: cover unlimited votes and public profile totals"
~~~

### Task 2: Centralize quota interpretation without changing positive-limit semantics

**Files:**

- Create: app/shared/voting.py
- Modify: config.py:254
- Modify: tests/test_vote_quota_and_profile_visibility.py

**Interfaces:**

- Produces: vote_quota_exceeded(user_id: int) -> bool.
- Consumes: votes_cast_today(user_id: int) -> int and current_app.config["VOTE_QUOTA"].
- Preserves: a positive quota is exceeded only when the existing count is strictly greater than its limit.

- [ ] **Step 1: Implement the smallest shared predicate**

~~~
# app/shared/voting.py
from flask import current_app

from app.models import votes_cast_today


def vote_quota_exceeded(user_id: int) -> bool:
    quota = current_app.config["VOTE_QUOTA"]
    return quota != 0 and votes_cast_today(user_id) > quota
~~~

Use quota != 0, not quota > 0, so malformed negative deployments retain their pre-existing behavior rather than silently becoming unlimited.

- [ ] **Step 2: Document the supported zero setting beside the existing configuration**

~~~
    # Set VOTE_QUOTA=0 to disable the daily quota; absent values default to 240.
    VOTE_QUOTA = int(os.environ.get("VOTE_QUOTA") or 240)
~~~

- [ ] **Step 3: Run the shared contract test**

Run: CACHE_TYPE=NullCache CACHE_REDIS_URL=memory:// SERVER_NAME=localhost uv run pytest tests/test_vote_quota_and_profile_visibility.py::test_vote_quota_exceeded_preserves_threshold_and_disables_at_zero -v

Expected: 3 passed.

- [ ] **Step 4: Commit the helper and configuration documentation**

~~~
git add app/shared/voting.py config.py tests/test_vote_quota_and_profile_visibility.py
git commit -m "feat: support unlimited vote quota mode"
~~~

### Task 3: Route every vote path through the shared quota predicate

**Files:**

- Modify: app/shared/post.py:12,112
- Modify: app/shared/reply.py:10,33
- Modify: app/activitypub/routes.py:86,3851-3855,3879-3885
- Modify: tests/test_vote_quota_and_profile_visibility.py

**Interfaces:**

- Consumes: app.shared.voting.vote_quota_exceeded(user_id: int) -> bool.
- Produces: HTTP 429 only when the helper says the quota is exceeded; inbound Like/Dislike processing only when it is not exceeded.

- [ ] **Step 1: Run the local/API tests to verify the current direct checks fail the planned seam**

Run: CACHE_TYPE=NullCache CACHE_REDIS_URL=memory:// SERVER_NAME=localhost uv run pytest tests/test_vote_quota_and_profile_visibility.py -k post_and_reply -v

Expected: FAIL because the handlers do not yet import or call vote_quota_exceeded.

- [ ] **Step 2: Replace only the local/API quota expressions**

~~~
# app/shared/post.py and app/shared/reply.py
from app.shared.voting import vote_quota_exceeded

if vote_quota_exceeded(user.id):
    abort(429)
~~~

Remove the direct votes_cast_today import from each module only if it is no longer used elsewhere in that file. Retain ban, permission, task, and response behavior unchanged.

- [ ] **Step 3: Replace both inbound ActivityPub quota clauses**

~~~
# app/activitypub/routes.py
from app.shared.voting import vote_quota_exceeded

# In process_upvote and process_downvote, retain every existing permission,
# instance-ban, type, and blocked-user condition; replace only this clause:
and not vote_quota_exceeded(user.id)
~~~

Remove the votes_cast_today model import only if no other reference remains in app/activitypub/routes.py.

- [ ] **Step 4: Run all vote enforcement tests**

Run: CACHE_TYPE=NullCache CACHE_REDIS_URL=memory:// SERVER_NAME=localhost uv run pytest tests/test_vote_quota_and_profile_visibility.py -k "quota or inbound or post_and_reply" -v

Expected: PASS. Post, reply, inbound Like, and inbound Dislike accept a vote with a zero quota and preserve rejection when the helper reports exceeded.

- [ ] **Step 5: Commit the boundary integration**

~~~
git add app/shared/post.py app/shared/reply.py app/activitypub/routes.py tests/test_vote_quota_and_profile_visibility.py
git commit -m "feat: disable quota across all vote paths"
~~~

### Task 4: Make aggregate profile vote totals public and suppress disabled quota UI

**Files:**

- Modify: app/user/routes.py:293-297
- Create: app/templates/user/_profile_vote_totals.html
- Modify: app/templates/user/show_profile.html:160-166
- Modify: tests/test_vote_quota_and_profile_visibility.py

**Interfaces:**

- Produces: profile_vote_quota_used(user_id: int) -> float.
- Consumes: current_app.config["VOTE_QUOTA"] and votes_cast_today(user_id).
- Produces: a public template partial that needs only user.get_num_upvotes() and user.get_num_downvotes().

- [ ] **Step 1: Run the profile tests before implementation**

Run: CACHE_TYPE=NullCache CACHE_REDIS_URL=memory:// SERVER_NAME=localhost uv run pytest tests/test_vote_quota_and_profile_visibility.py -k profile -v

Expected: FAIL with missing profile_vote_quota_used and user/_profile_vote_totals.html.

- [ ] **Step 2: Add the quota-fraction helper and use it from show_profile**

~~~
def profile_vote_quota_used(user_id: int) -> float:
    quota = current_app.config["VOTE_QUOTA"]
    if quota == 0:
        return 0
    return votes_cast_today(user_id) / quota


# inside show_profile
if current_user.is_authenticated:
    vote_quota_used = profile_vote_quota_used(user.id)
else:
    vote_quota_used = 0
~~~

The existing Jinja if vote_quota_used stays unchanged, so an unlimited deployment has no quota progress bar and no division-by-zero error.

- [ ] **Step 3: Add the public aggregate-only partial**

~~~
{# app/templates/user/_profile_vote_totals.html #}
{{ _('Votes') }}: {{ user.get_num_upvotes() }} / {{ user.get_num_downvotes() }}<br />
~~~

- [ ] **Step 4: Include the partial before the admin-only profile block**

~~~
{% if vote_quota_used -%}
{{ _('Vote quota used') }} <progress value="{{ vote_quota_used | round(precision=2) }}"></progress><br />
{% endif -%}
{% include "user/_profile_vote_totals.html" %}
{% if current_user.is_authenticated and current_user.get_id() in admin_ids -%}
~~~

Delete the original Votes line inside that admin-only block. Do not move reputation, referrer, IP/country, last-active, or donor markup.

- [ ] **Step 5: Run profile and template quality checks**

Run: CACHE_TYPE=NullCache CACHE_REDIS_URL=memory:// SERVER_NAME=localhost uv run pytest tests/test_vote_quota_and_profile_visibility.py -k profile -v

Expected: PASS, including rendering totals without a viewer object and proving the include appears before the admin-only wrapper.

Run: uv run djlint app/templates/user/show_profile.html app/templates/user/_profile_vote_totals.html --lint

Expected: 0 errors.

- [ ] **Step 6: Commit the profile privacy change**

~~~
git add app/user/routes.py app/templates/user/show_profile.html app/templates/user/_profile_vote_totals.html tests/test_vote_quota_and_profile_visibility.py
git commit -m "feat: publish aggregate profile vote totals"
~~~

### Task 5: Document release behavior and verify the complete branch

**Files:**

- Modify: docs/RELEASE_NOTES.md:1

**Interfaces:**

- Consumes: the completed zero-quota and public-profile behavior.
- Produces: operator and user-facing release notes without selecting a release version or deploying.

- [ ] **Step 1: Add a Next fork release section above the current newest release**

~~~
## Next fork release

- **Unlimited voting is opt-in.** Set VOTE_QUOTA=0 in the web and worker
  runtime environment, then restart both services. Positive values retain the
  daily limit; an unset value remains 240. This applies to local, API, and
  inbound federated votes.
- **Profile vote totals are public.** Profiles now show aggregate upvotes and
  downvotes cast to anonymous and signed-in visitors. Individual voter lists
  and existing administrator-only metadata remain restricted.
~~~

- [ ] **Step 2: Run the focused suite and static checks**

Run: CACHE_TYPE=NullCache CACHE_REDIS_URL=memory:// SERVER_NAME=localhost uv run pytest tests/test_vote_quota_and_profile_visibility.py -v

Expected: PASS.

Run: CACHE_TYPE=NullCache CACHE_REDIS_URL=memory:// SERVER_NAME=localhost uv run pytest tests/test_field_consistency_simple.py -v

Expected: 4 passed.

Run: uv run ruff check app/shared/voting.py app/shared/post.py app/shared/reply.py app/activitypub/routes.py app/user/routes.py tests/test_vote_quota_and_profile_visibility.py

Expected: no lint findings.

Run: uv run djlint app/templates/user/show_profile.html app/templates/user/_profile_vote_totals.html --lint

Expected: 0 errors.

- [ ] **Step 3: Inspect the final diff and commit release notes**

~~~
git diff --check
git status --short
git add docs/RELEASE_NOTES.md
git commit -m "docs: note unlimited voting and public vote totals"
git log --oneline main..HEAD
~~~

Expected: only the focused implementation, test, design/plan, and release-note commits appear on this release branch. Do not push, open a PR, deploy, or set production environment variables without a separate authorization.
