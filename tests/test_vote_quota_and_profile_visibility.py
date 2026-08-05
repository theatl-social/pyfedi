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


def test_anonymous_profile_shows_vote_totals_without_sensitive_metadata(
    app, monkeypatch
):
    from datetime import datetime, timezone

    from flask import render_template

    class ProfileUser:
        id = 42
        instance_id = 1
        user_name = "public-user"
        ap_id = None
        ap_profile_id = "https://test.localhost/u/public-user"
        ap_domain = "test.localhost"
        indexable = True
        searchable = True
        banned = False
        bot = False
        bot_override = False
        accept_private_messages = False
        matrix_user_id = None
        attitude = None
        reputation = "REPUTATION-SHOULD-STAY-PRIVATE"
        referrer = "REFERRER-SHOULD-STAY-PRIVATE"
        ip_address = "IP-SHOULD-STAY-PRIVATE"
        ip_address_country = "COUNTRY-SHOULD-STAY-PRIVATE"
        last_seen = "ACTIVE-TIME-SHOULD-STAY-PRIVATE"
        stripe_subscription_id = "DONOR-SHOULD-STAY-PRIVATE"
        post_count = 0
        post_reply_count = 0
        extra_fields = []
        about_html = ""
        created = datetime(2026, 1, 1, tzinfo=timezone.utc)
        avatar = SimpleNamespace(source_url=None)

        def avatar_image(self):
            return ""

        def cover_image(self):
            return ""

        def display_name(self):
            return "Public User"

        def get_id(self):
            return self.id

        def instance_domain(self):
            return "test.localhost"

        def is_instance_admin(self):
            return False

        def is_local(self):
            return True

        def is_staff(self):
            return False

        def link(self):
            return self.user_name

        def get_num_upvotes(self):
            return 7

        def get_num_downvotes(self):
            return 3

    user = ProfileUser()
    monkeypatch.setitem(app.jinja_env.filters, "shorten", lambda value: value)
    with app.test_request_context("/"):
        context = {
            "user": user,
            "posts": [],
            "post_replies": [],
            "moderates": [],
            "canonical": None,
            "subscribed": [],
            "user_notes": [],
            "posting_pattern_labels": [],
            "posting_pattern_values": [],
            "post_next_url": None,
            "post_prev_url": None,
            "replies_next_url": None,
            "replies_prev_url": None,
            "overview_items": [],
            "overview_next_url": None,
            "overview_prev_url": None,
            "same_ip_address": [],
            "archived_post_replies": [],
            "followers": [],
            "following": [],
            "bot_challenge": None,
            "vote_quota_used": 0,
            "user_has_public_feeds": False,
            "user_public_feeds": [],
            "admin_ids": [],
            "locale": "en",
            "low_bandwidth": True,
            "localize_datetime": lambda _value, _locale: "DATE",
        }
        app.update_template_context(context)
        template = app.jinja_env.get_template("user/show_profile.html")
        html = "".join(template.blocks["app_content"](template.new_context(context)))

    assert "7 / 3" in html
    assert "REFERRER-SHOULD-STAY-PRIVATE" not in html
    assert "IP-SHOULD-STAY-PRIVATE" not in html
    assert "COUNTRY-SHOULD-STAY-PRIVATE" not in html
    assert "ACTIVE-TIME-SHOULD-STAY-PRIVATE" not in html
    assert "DONOR-SHOULD-STAY-PRIVATE" not in html
    assert "REPUTATION-SHOULD-STAY-PRIVATE" not in html


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
