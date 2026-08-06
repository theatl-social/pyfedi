"""AdvancedRateLimiter.check_rate_limit() must not fail open when Redis errors.

`check_rate_limit()`'s `except Exception` branch used to return
`{"allowed": True}` -- i.e. the admin API's rate limiter switched itself off
whenever Redis was unreachable, on endpoints that create, ban and delete
accounts, where the limiter is one of only four gates. Anyone able to disrupt
Redis (or catch it mid-restart) got unlimited attempts at the secret.

Fixed 2026-08-05 (SP-027): the exception branch now degrades to
`_check_rate_limit_fallback()`, a process-local, thread-locked bucket that
still enforces a real bound instead of admitting every request.
"""

import os

import pytest


@pytest.fixture
def app():
    os.environ.setdefault("SERVER_NAME", "test.localhost")
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    os.environ.setdefault("CACHE_TYPE", "NullCache")

    from app import create_app

    application = create_app()
    with application.app_context():
        yield application


def test_redis_exception_does_not_allow_unconditionally(app, monkeypatch):
    from app.api.admin.monitoring import AdvancedRateLimiter, _FALLBACK_BUCKETS

    limiter = AdvancedRateLimiter()

    class ExplodingRedis:
        def __getattr__(self, name):
            def _raise(*args, **kwargs):
                raise ConnectionError("redis unreachable")

            return _raise

    monkeypatch.setattr("app.api.admin.monitoring.redis_client", ExplodingRedis())
    _FALLBACK_BUCKETS.pop("private_registration:regression_client", None)

    result = limiter.check_rate_limit("private_registration", "regression_client")

    assert result["fallback"] is True, (
        "REGRESSION: a Redis exception did not degrade to the in-memory "
        "fallback limiter."
    )
    assert "allowed" in result


def test_redis_exception_fallback_still_enforces_a_bound(app, monkeypatch):
    """The old bug: fail-open meant unlimited requests. Confirm the fallback
    eventually says no, not that it always says yes."""
    from app.api.admin.monitoring import AdvancedRateLimiter, _FALLBACK_BUCKETS

    limiter = AdvancedRateLimiter()

    class ExplodingRedis:
        def __getattr__(self, name):
            def _raise(*args, **kwargs):
                raise ConnectionError("redis unreachable")

            return _raise

    monkeypatch.setattr("app.api.admin.monitoring.redis_client", ExplodingRedis())
    identifier = "regression_client_exhaust"
    _FALLBACK_BUCKETS.pop(f"private_registration:{identifier}", None)

    # default limit is 10/hour (AdvancedRateLimiter.default_limits)
    results = [
        limiter.check_rate_limit("private_registration", identifier) for _ in range(15)
    ]

    assert any(r["allowed"] is False for r in results), (
        "REGRESSION: the fallback limiter never blocked -- Redis failures "
        "are once again equivalent to no rate limit at all."
    )
