from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from werkzeug.exceptions import TooManyRequests

from app import create_app
from config import Config


class _TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key-that-is-at-least-32-characters"
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


@pytest.mark.parametrize(
    ("quota", "votes_cast", "expected"),
    [(0, 10_000, False), (240, 240, False), (240, 241, True)],
)
def test_vote_quota_exceeded_preserves_threshold_and_disables_at_zero(
    app, quota, votes_cast, expected
):
    from app.shared.voting import vote_quota_exceeded

    app.config["VOTE_QUOTA"] = quota
    with (
        app.app_context(),
        patch("app.shared.voting.votes_cast_today", return_value=votes_cast),
    ):
        assert vote_quota_exceeded(42) is expected


def test_profile_quota_fraction_is_zero_when_quota_is_disabled(app):
    from app.user.routes import profile_vote_quota_used

    app.config["VOTE_QUOTA"] = 0
    with (
        app.app_context(),
        patch("app.user.routes.votes_cast_today", return_value=10_000),
    ):
        assert profile_vote_quota_used(42) == 0


def test_post_and_reply_votes_continue_when_quota_is_disabled(app):
    from app.constants import SRC_API
    from app.shared.post import vote_for_post
    from app.shared.reply import vote_for_reply

    app.config["VOTE_QUOTA"] = 0
    user = SimpleNamespace(id=42, banned=False)
    post = SimpleNamespace(id=1, community=Mock(), vote=Mock(return_value=None))
    reply = SimpleNamespace(id=2, community=Mock(), vote=Mock(return_value=None))

    with (
        app.app_context(),
        patch("app.shared.post.authorise_api_user", return_value=user),
        patch("app.shared.post.can_upvote", return_value=True),
        patch("app.shared.post.db.session.query") as post_query,
        patch("app.shared.post.mark_post_read"),
        patch("app.shared.post.vote_quota_exceeded", return_value=False),
        patch("app.shared.post.task_selector"),
        patch("app.shared.reply.authorise_api_user", return_value=user),
        patch("app.shared.reply.can_upvote", return_value=True),
        patch("app.shared.reply.db.session.query") as reply_query,
        patch("app.shared.reply.vote_quota_exceeded", return_value=False),
        patch("app.shared.reply.task_selector"),
    ):
        post_query.return_value.get.return_value = post
        reply_query.return_value.filter_by.return_value.one.return_value = reply
        vote_for_post(1, "upvote", False, None, SRC_API, auth="token")
        vote_for_reply(2, "upvote", False, None, SRC_API, auth="token")

    post.vote.assert_called_once_with(user, "upvote", None)
    reply.vote.assert_called_once_with(user, "upvote", None)


def test_post_and_reply_votes_stop_when_quota_is_exceeded(app):
    from app.constants import SRC_API
    from app.shared.post import vote_for_post
    from app.shared.reply import vote_for_reply

    user = SimpleNamespace(id=42, banned=False)
    post = SimpleNamespace(id=1, community=Mock(), vote=Mock(return_value=None))
    reply = SimpleNamespace(id=2, community=Mock(), vote=Mock(return_value=None))

    with (
        app.app_context(),
        patch("app.shared.post.authorise_api_user", return_value=user),
        patch("app.shared.post.can_upvote", return_value=True),
        patch("app.shared.post.db.session.query") as post_query,
        patch("app.shared.post.mark_post_read"),
        patch("app.shared.post.vote_quota_exceeded", return_value=True),
        patch("app.shared.post.task_selector"),
        patch("app.shared.reply.authorise_api_user", return_value=user),
        patch("app.shared.reply.can_upvote", return_value=True),
        patch("app.shared.reply.db.session.query") as reply_query,
        patch("app.shared.reply.vote_quota_exceeded", return_value=True),
        patch("app.shared.reply.task_selector"),
    ):
        post_query.return_value.get.return_value = post
        reply_query.return_value.filter_by.return_value.one.return_value = reply
        with pytest.raises(TooManyRequests):
            vote_for_post(1, "upvote", False, None, SRC_API, auth="token")
        with pytest.raises(TooManyRequests):
            vote_for_reply(2, "upvote", False, None, SRC_API, auth="token")

    post.vote.assert_not_called()
    reply.vote.assert_not_called()


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
    remote_user = SimpleNamespace(id=42, instance=SimpleNamespace(domain="remote.test"))
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


@pytest.mark.parametrize(
    ("handler_name", "direction"),
    [("process_upvote", "upvote"), ("process_downvote", "downvote")],
)
def test_inbound_votes_stop_when_quota_is_exceeded(
    app, monkeypatch, handler_name, direction
):
    import app.activitypub.routes as routes

    class Liked:
        community = Mock()
        author = SimpleNamespace(id=99)
        vote = Mock()

    liked = Liked()
    remote_user = SimpleNamespace(id=42, instance=SimpleNamespace(domain="remote.test"))
    monkeypatch.setattr(routes, "Post", Liked)
    monkeypatch.setattr(routes, "PostReply", type("Reply", (), {}))
    monkeypatch.setattr(routes, "find_liked_object", lambda _ap_id: liked)
    monkeypatch.setattr(routes, "can_upvote", lambda *_args: direction == "upvote")
    monkeypatch.setattr(routes, "can_downvote", lambda *_args: direction == "downvote")
    monkeypatch.setattr(routes, "instance_banned", lambda _domain: False)
    monkeypatch.setattr(routes, "blocked_users", lambda _user_id: [])
    monkeypatch.setattr(routes, "vote_quota_exceeded", lambda _user_id: True)
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

    liked.vote.assert_not_called()


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
