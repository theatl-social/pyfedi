"""
Regression tests for the fork's 30-second Redis lock lifetime on the two
OUTER vote locks in app/models.py (Post.vote / PostReply.vote).

Background: an upstream merge reverted these two locks from timeout=30 back
to timeout=10. Vote transactions in these methods can nest a second
(`lock:vote:` / `lock:user:`) lock inside the outer lock and, under load,
take longer than 10 seconds end to end. When the outer lock's timeout
expires before the `with` block exits, redis-py raises
`LockNotOwnedError` on release ("Cannot release a lock that's no longer
owned") because another process was handed the lock in the meantime. The
fork previously fixed this in commit 2610bf33; keep it at timeout=30.

This does NOT touch (and must NOT regress to timeout=30):
  - lock:vote:{...}
  - lock:user:{...}
  - the lock:post:{post.id} locks used elsewhere (e.g. around line ~894 and
    ~2898), which are separate call sites from the two vote() methods.

Note on the behavioral tests below: driving Post.vote() / PostReply.vote()
against a *real* database (even sqlite in-memory) was attempted and found
impractical for this narrow fix. app/models.py's schema uses several
Postgres-only column types with no SQLite equivalent -- `ARRAY`
(e.g. `User.read_language_ids`, `Post.cross_posts`), `BIT` (`File.hash`),
and `TSVECTOR` search-vector columns -- and `sqlalchemy_searchable`'s
`make_searchable()` also registers a `before_create` DDL event that emits
raw Postgres `CREATE OR REPLACE FUNCTION ...` SQL unconditionally. Each of
these makes `db.create_all()` fail outright on SQLite for the full schema,
and there is no Postgres-backed test harness in this repo to fall back to.
Instead, the behavioral tests below construct a bare (unpersisted) `Post`
/ `PostReply` instance with mocked relationships (`community`, `author`)
and a mocked `db.session`, so the *real* `vote()` method body runs (real
control flow, real f-string lock names) without touching a database at
all. This still exercises the actual call site, not just its source text.
"""

import inspect
import re
from datetime import datetime
from unittest.mock import Mock

import pytest

from app.models import Post, PostReply


def _outer_lock_call(source: str, lock_name_fragment: str) -> str:
    """Return the `redis_client.lock(...)` call text for the given lock name."""
    pattern = re.compile(
        r'redis_client\.lock\(\s*f"' + re.escape(lock_name_fragment) + r'"\s*,\s*[^)]*\)'
    )
    match = pattern.search(source)
    assert match is not None, (
        f"could not find redis_client.lock() call for {lock_name_fragment!r} in source"
    )
    return match.group(0)


class TestOuterVoteLockTimeoutSourceInspection:
    """Source-inspection tests: robust to method internals changing, and
    don't require a database or a real/fake redis client to drive the
    method end-to-end."""

    def test_post_vote_outer_lock_uses_timeout_30(self):
        source = inspect.getsource(Post.vote)
        call = _outer_lock_call(source, "lock:post:{self.id}")
        assert "timeout=30" in call, f"expected timeout=30 in {call!r}"
        assert "blocking_timeout=6" in call, f"expected blocking_timeout=6 in {call!r}"

    def test_post_reply_vote_outer_lock_uses_timeout_30(self):
        source = inspect.getsource(PostReply.vote)
        call = _outer_lock_call(source, "lock:post_reply:{self.id}")
        assert "timeout=30" in call, f"expected timeout=30 in {call!r}"
        assert "blocking_timeout=6" in call, f"expected blocking_timeout=6 in {call!r}"

    def test_post_vote_outer_lock_is_not_timeout_10(self):
        # Guards specifically against the upstream-merge regression that
        # prompted this fix.
        source = inspect.getsource(Post.vote)
        call = _outer_lock_call(source, "lock:post:{self.id}")
        assert "timeout=10" not in call

    def test_post_reply_vote_outer_lock_is_not_timeout_10(self):
        source = inspect.getsource(PostReply.vote)
        call = _outer_lock_call(source, "lock:post_reply:{self.id}")
        assert "timeout=10" not in call


class TestOtherLocksUnchangedGuard:
    """Guard against an over-broad edit: only the two outer vote() locks
    should have moved to timeout=30. Every other lock call in vote() must
    stay at timeout=10."""

    def test_post_vote_nested_locks_still_timeout_10(self):
        source = inspect.getsource(Post.vote)
        vote_call = _outer_lock_call(source, "lock:vote:{existing_vote.id}")
        assert "timeout=10" in vote_call
        assert "timeout=30" not in vote_call

        # There are multiple `lock:user:{...}` call sites inside Post.vote
        # (existing-vote path, new-vote path, and the last-seen update).
        # All of them must remain at timeout=10.
        user_lock_calls = re.findall(
            r'redis_client\.lock\(\s*f"lock:user:\{[^}]*\}"\s*,\s*[^)]*\)', source
        )
        assert len(user_lock_calls) >= 2, "expected multiple lock:user: call sites in Post.vote"
        for call in user_lock_calls:
            assert "timeout=10" in call, f"expected timeout=10 in {call!r}"
            assert "timeout=30" not in call, f"unexpected timeout=30 in {call!r}"

    def test_post_reply_vote_nested_user_locks_still_timeout_10(self):
        source = inspect.getsource(PostReply.vote)
        user_lock_calls = re.findall(
            r'redis_client\.lock\(\s*f"lock:user:\{[^}]*\}"\s*,\s*[^)]*\)', source
        )
        assert len(user_lock_calls) >= 2, "expected multiple lock:user: call sites in PostReply.vote"
        for call in user_lock_calls:
            assert "timeout=10" in call, f"expected timeout=10 in {call!r}"
            assert "timeout=30" not in call, f"unexpected timeout=30 in {call!r}"

    def test_other_lock_post_call_sites_outside_vote_still_timeout_10(self):
        """The lock:post:{post.id} locks used elsewhere in models.py (e.g.
        around federation/activity processing, not inside Post.vote /
        PostReply.vote) must be untouched by this change."""
        import app.models as models_module

        full_source = inspect.getsource(models_module)
        vote_source = inspect.getsource(Post.vote)

        all_post_lock_calls = re.findall(
            r'redis_client\.lock\(\s*f"lock:post:\{[^}]*\}"\s*,\s*[^)]*\)', full_source
        )
        vote_post_lock_calls = re.findall(
            r'redis_client\.lock\(\s*f"lock:post:\{[^}]*\}"\s*,\s*[^)]*\)', vote_source
        )

        other_calls = [c for c in all_post_lock_calls if c not in vote_post_lock_calls]
        assert other_calls, "expected at least one lock:post: call site outside Post.vote"
        for call in other_calls:
            assert "timeout=10" in call or "timeout=30, blocking_timeout=30" in call, (
                f"unexpected timeout change to a lock:post: call outside Post.vote: {call!r}"
            )
            # Specifically must not have picked up the vote()-only fix of
            # `timeout=30, blocking_timeout=6`.
            assert "timeout=30, blocking_timeout=6" not in call, (
                f"lock:post: call outside Post.vote unexpectedly got the vote() fix: {call!r}"
            )


class FakeRedisLock:
    """No-op lock context manager that never touches real redis."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class FakeRedisClient:
    """Fake redis client that records every `.lock(name, **kwargs)` call and
    hands back a no-op context manager, plus the handful of other redis
    methods Post.vote / PostReply.vote touch on the "cast a new vote" path
    (votes_cast_today bookkeeping)."""

    def __init__(self):
        self.lock_calls = []
        self._store = {}

    def lock(self, name, **kwargs):
        self.lock_calls.append((name, kwargs))
        return FakeRedisLock()

    def get(self, key):
        return self._store.get(key)

    def set(self, key, value, ex=None):
        self._store[key] = value

    def incr(self, key):
        self._store[key] = int(self._store.get(key, 0)) + 1


@pytest.fixture
def fake_redis(monkeypatch):
    """Patch the module-level `redis_client` that Post.vote / PostReply.vote
    pull in via their function-local `from app import redis_client` import.
    That import binds the name from the `app` package (app/__init__.py),
    not from app.models, so the patch target is `app.redis_client`."""
    import app as app_package

    fake = FakeRedisClient()
    monkeypatch.setattr(app_package, "redis_client", fake)
    return fake


@pytest.fixture
def app_context():
    """Minimal Flask app context -- needed because Post.vote() reads
    current_app.config['SPICY_UNDER_10'] etc. Does not touch a database."""
    from app import create_app
    from config import Config

    class _TC(Config):
        TESTING = True
        SECRET_KEY = "test-secret-key-that-is-at-least-32-characters"
        WTF_CSRF_ENABLED = False
        MAIL_SUPPRESS_SEND = True
        CACHE_TYPE = "NullCache"
        CACHE_REDIS_URL = "memory://"
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        SERVER_NAME = "test.localhost"
        RATELIMIT_ENABLED = False
        CELERY_ALWAYS_EAGER = True

    app = create_app(_TC)
    with app.app_context():
        yield app


class TestOuterVoteLockTimeoutBehavioral:
    """Behavioral tests that drive the real Post.vote() / PostReply.vote()
    method bodies (real control flow, real f-string lock names) with a
    fake redis client substituted in for lock recording. `db.session` is
    mocked (no real DB writes/reads) and `self.community` / `self.author`
    are Mocks, since standing up the real schema requires PostgreSQL (see
    module docstring). This still exercises the actual call site, not
    just its source text."""

    def test_post_vote_requests_timeout_30_on_outer_lock(self, app_context, fake_redis, monkeypatch):
        import app.models as models_module
        from app.models import PostVote

        monkeypatch.setattr(models_module.db.session, "execute", Mock())
        monkeypatch.setattr(models_module.db.session, "commit", Mock())
        monkeypatch.setattr(models_module.db.session, "add", Mock())
        monkeypatch.setattr(PostVote, "query", Mock())
        PostVote.query.filter_by.return_value.first.return_value = None

        post = Post()
        post.id = 42
        post.user_id = 7
        post.up_votes = 0
        post.down_votes = 0
        post.score = 0
        post.reply_count = 0
        post.created_at = datetime.now()
        post.community = Mock(low_quality=False)
        post.community.scale_by.return_value = 0
        post.author = Mock(id=7)
        post.author.has_blocked_user.return_value = False
        post.author.has_blocked_instance.return_value = False

        voter = Mock(id=9)
        voter.is_local.return_value = False

        post.vote(voter, "upvote", None)

        outer_calls = [
            (name, kwargs) for name, kwargs in fake_redis.lock_calls
            if name == f"lock:post:{post.id}"
        ]
        assert outer_calls, (
            f"expected a lock:post:{post.id} call; got {fake_redis.lock_calls!r}"
        )
        name, kwargs = outer_calls[0]
        assert kwargs.get("timeout") == 30
        assert kwargs.get("blocking_timeout") == 6

    def test_post_reply_vote_requests_timeout_30_on_outer_lock(self, app_context, fake_redis, monkeypatch):
        import app.models as models_module
        from app.models import PostReplyVote, User

        monkeypatch.setattr(models_module.db.session, "execute", Mock())
        monkeypatch.setattr(models_module.db.session, "commit", Mock())
        monkeypatch.setattr(models_module.db.session, "add", Mock())
        monkeypatch.setattr(models_module.db.session, "query", Mock())
        models_module.db.session.query.return_value.filter_by.return_value.first.return_value = None
        monkeypatch.setattr(PostReplyVote, "query", Mock())
        PostReplyVote.query.filter_by.return_value.first.return_value = None

        # `PostReply.author` is a relationship configured with
        # single_parent=True, which makes SQLAlchemy validate that
        # assigned values are real `User` instances (a Mock() trips that
        # check and, worse, crashes while formatting its own error
        # message against a Mock). Use a real, unpersisted User instead.
        author_user = User()
        author_user.id = 7

        reply = PostReply()
        reply.id = 99
        reply.user_id = 7
        reply.post_id = 42
        reply.up_votes = 0
        reply.down_votes = 0
        reply.score = 0
        reply.child_count = 0
        reply.title = None
        reply.created_at = datetime.now()
        reply.author = author_user

        voter = Mock(id=9)
        voter.is_local.return_value = False

        reply.vote(voter, "upvote", None)

        outer_calls = [
            (name, kwargs) for name, kwargs in fake_redis.lock_calls
            if name == f"lock:post_reply:{reply.id}"
        ]
        assert outer_calls, (
            f"expected a lock:post_reply:{reply.id} call; got {fake_redis.lock_calls!r}"
        )
        name, kwargs = outer_calls[0]
        assert kwargs.get("timeout") == 30
        assert kwargs.get("blocking_timeout") == 6
