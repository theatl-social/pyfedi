"""
Advanced security tests for private registration API

These tests focus on:
- Rate limiting enforcement
- IP whitelist security
- Concurrent request handling
- Attack scenario simulation
"""

import pytest
import time
import threading
import json
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor, as_completed

# sqlalchemy_searchable attaches its per-table `DROP FUNCTION ...` teardown hook
# lazily -- the first time any ORM query triggers SQLAlchemy's configure_mappers()
# -- which can happen *after* tests/conftest.py's create_all_for_tests() has
# already run its hook-stripping pass. If a test in this file is the first ORM
# query of the whole pytest session, the hook reappears afterward and the
# test_app fixture's teardown `db.drop_all()` fails with
# `near "FUNCTION": syntax error` on `DROP FUNCTION IF EXISTS
# post_search_vector_update()`. Configuring mappers here, at import time (i.e.
# before any fixture runs), ensures the hook already exists when
# create_all_for_tests() strips it. This does not touch tests/conftest.py.
import app as _app  # noqa: F401,E402
from sqlalchemy.orm import configure_mappers as _configure_mappers  # noqa: E402

_configure_mappers()


class TestRateLimiting:
    """Test rate limiting functionality"""

    @patch.dict(
        "os.environ",
        {
            "PRIVATE_REGISTRATION_RATE_LIMIT": "3",
            "PRIVATE_REGISTRATION_ENABLED": "true",
            "PRIVATE_REGISTRATION_SECRET": "test-rate-limit-secret",
        },
    )
    def test_rate_limit_enforcement(self, test_app):
        """Test that rate limiting is properly enforced"""
        client = test_app.test_client()

        headers = {
            "X-PieFed-Secret": "test-rate-limit-secret",
            "Content-Type": "application/json",
            "X-Forwarded-For": "127.0.0.1",
        }

        # Make requests up to the limit (should succeed)
        for i in range(3):
            user_data = {
                "username": f"ratetest{i}",
                "email": f"ratetest{i}@example.com",
                "auto_activate": True,
            }

            response = client.post(
                "/api/alpha/admin/private_register",
                headers=headers,
                data=json.dumps(user_data),
            )

            assert response.status_code == 201, f"Request {i+1} should succeed"

        # Next request should be rate limited
        user_data = {
            "username": "ratetest_overflow",
            "email": "ratetest_overflow@example.com",
            "auto_activate": True,
        }

        response = client.post(
            "/api/alpha/admin/private_register",
            headers=headers,
            data=json.dumps(user_data),
        )

        assert response.status_code == 429
        data = response.get_json()
        assert data["success"] is False
        assert data["error"] == "rate_limited"

    @patch.dict(
        "os.environ",
        {
            "PRIVATE_REGISTRATION_RATE_LIMIT": "3",
            "PRIVATE_REGISTRATION_ENABLED": "true",
            "PRIVATE_REGISTRATION_SECRET": "test-rate-limit-secret",
        },
    )
    def test_rate_limit_not_bypassable_by_changing_client_ip(self, test_app):
        """Rate limiting buckets by caller identity, not by client IP.

        This test was previously named `test_rate_limit_per_ip` and asserted the
        opposite: that exhausting the quota from 127.0.0.1 left 10.0.0.1 free to
        keep registering. The application does not work that way and must not.

        AdvancedRateLimiter.get_client_identifier()
        (app/api/admin/monitoring.py) keys the bucket on a hash of the
        X-PieFed-Secret header and only falls back to the client IP when no
        secret was sent. On these endpoints the secret is always present:
        @require_private_registration_auth rejects the request before
        check_advanced_rate_limit() ever runs, so the IP branch is unreachable
        here. One secret therefore means one bucket, which is the stricter
        behaviour -- and the only safe one, because the "IP" in question comes
        from X-Forwarded-For, a header the caller sets. Bucketing per IP would
        let anyone holding the secret reset their own account-creation quota at
        will by editing a request header.

        The original expectation was also unreachable for a second reason: it
        configured no PRIVATE_REGISTRATION_RATE_LIMIT at all, so the limit was
        the 10/hour default and four requests could never trip it.
        """
        client = test_app.test_client()

        headers_ip1 = {
            "X-PieFed-Secret": "test-rate-limit-secret",
            "Content-Type": "application/json",
            "X-Forwarded-For": "127.0.0.1",
        }

        headers_ip2 = {
            "X-PieFed-Secret": "test-rate-limit-secret",
            "Content-Type": "application/json",
            "X-Forwarded-For": "10.0.0.1",
        }

        # Use up the quota from IP1
        for i in range(3):
            user_data = {
                "username": f"ip1test{i}",
                "email": f"ip1test{i}@example.com",
                "auto_activate": True,
            }

            response = client.post(
                "/api/alpha/admin/private_register",
                headers=headers_ip1,
                data=json.dumps(user_data),
            )

            assert response.status_code == 201

        # IP1 is now rate limited
        response = client.post(
            "/api/alpha/admin/private_register",
            headers=headers_ip1,
            data=json.dumps(
                {"username": "ip1overflow", "email": "ip1overflow@example.com"}
            ),
        )
        assert response.status_code == 429
        assert response.get_json()["error"] == "rate_limited"

        # Presenting a different X-Forwarded-For with the same secret must NOT
        # hand back a fresh quota.
        response = client.post(
            "/api/alpha/admin/private_register",
            headers=headers_ip2,
            data=json.dumps({"username": "ip2test", "email": "ip2test@example.com"}),
        )
        assert response.status_code == 429, (
            "Changing X-Forwarded-For reset the rate limit bucket; "
            "the quota must follow the secret, not the client-supplied IP"
        )
        assert response.get_json()["error"] == "rate_limited"


class TestIPSecurity:
    """Test IP whitelist security features"""

    @patch.dict(
        "os.environ",
        {
            "PRIVATE_REGISTRATION_ALLOWED_IPS": "127.0.0.1,10.0.0.0/8",
            "PRIVATE_REGISTRATION_ENABLED": "true",
            "PRIVATE_REGISTRATION_SECRET": "test-ip-security-secret",
        },
    )
    def test_allowed_ip_ranges(self, test_app):
        """Test various IP ranges in whitelist"""
        client = test_app.test_client()

        # Test cases: (IP, should_succeed)
        test_cases = [
            ("127.0.0.1", True),  # Exact match
            ("10.0.0.1", True),  # In range
            ("10.255.255.255", True),  # Edge of range
            ("192.168.1.1", False),  # Not in range
            ("172.16.0.1", False),  # Not in range
            ("11.0.0.1", False),  # Outside range
        ]

        for test_ip, should_succeed in test_cases:
            headers = {
                "X-PieFed-Secret": "test-ip-security-secret",
                "Content-Type": "application/json",
                "X-Forwarded-For": test_ip,
            }

            user_data = {
                "username": f'iptest_{test_ip.replace(".", "_")}',
                "email": f'iptest_{test_ip.replace(".", "_")}@example.com',
                "auto_activate": True,
            }

            response = client.post(
                "/api/alpha/admin/private_register",
                headers=headers,
                data=json.dumps(user_data),
            )

            if should_succeed:
                assert response.status_code == 201, f"IP {test_ip} should be allowed"
            else:
                assert response.status_code == 403, f"IP {test_ip} should be blocked"
                data = response.get_json()
                assert data["error"] == "ip_unauthorized"

    @patch.dict(
        "os.environ",
        {
            "PRIVATE_REGISTRATION_ENABLED": "true",
            "PRIVATE_REGISTRATION_SECRET": "test-ip-security-secret",
        },
    )
    def test_x_forwarded_for_parsing(self, test_app):
        """Test proper parsing of X-Forwarded-For header with multiple IPs"""
        client = test_app.test_client()

        # Test with multiple forwarded IPs (should use first one)
        headers = {
            "X-PieFed-Secret": "test-ip-security-secret",
            "Content-Type": "application/json",
            "X-Forwarded-For": "127.0.0.1, 192.168.1.1, 10.0.0.1",  # First IP is allowed
        }

        user_data = {
            "username": "forwarded_test",
            "email": "forwarded_test@example.com",
            "auto_activate": True,
        }

        response = client.post(
            "/api/alpha/admin/private_register",
            headers=headers,
            data=json.dumps(user_data),
        )

        # Should succeed because first IP (127.0.0.1) is allowed
        assert response.status_code == 201

    def test_no_ip_restrictions(self, test_app):
        """Test behavior when no IP restrictions are configured"""
        with patch.dict(
            "os.environ",
            {
                "PRIVATE_REGISTRATION_ALLOWED_IPS": "",  # No restrictions
                "PRIVATE_REGISTRATION_ENABLED": "true",
                "PRIVATE_REGISTRATION_SECRET": "test-no-ip-secret",
            },
        ):
            client = test_app.test_client()

            # Should allow any IP when no restrictions
            headers = {
                "X-PieFed-Secret": "test-no-ip-secret",
                "Content-Type": "application/json",
                "X-Forwarded-For": "192.168.1.100",  # Random IP
            }

            user_data = {
                "username": "anyip_test",
                "email": "anyip_test@example.com",
                "auto_activate": True,
            }

            response = client.post(
                "/api/alpha/admin/private_register",
                headers=headers,
                data=json.dumps(user_data),
            )

            assert response.status_code == 201


@pytest.fixture
def threaded_app(tmp_path):
    """An app whose request handling is thread-safe, unlike the `test_app` one.

    conftest's `test_app` cannot serve genuinely concurrent requests, for two
    independent reasons, and neither is a property of the application:

    1. Connection. Its SQLALCHEMY_DATABASE_URI is "sqlite:///:memory:", and
       Flask-SQLAlchemy special-cases in-memory SQLite onto `StaticPool` with
       `check_same_thread=False` (flask_sqlalchemy/extension.py:610-616) --
       it has to, since a second connection would open a second, empty
       database. Every worker thread therefore drives the *same* sqlite3
       connection object at once, which surfaces as
       `sqlite3.InterfaceError: bad parameter or other API misuse`, on plain
       SELECTs as readily as on writes.

    2. Session. `test_app` yields from inside `with app.app_context():`, and
       Flask's RequestContext.push() reuses an already-pushed app context for
       the same app rather than creating one. So every test-client request in
       that fixture shares one app context, and `db.session` -- scoped to the
       app context -- is one SQLAlchemy Session shared by all threads. Sessions
       are documented as not thread-safe; one thread's rollback discards
       another's pending INSERT, which is where the
       "UPDATE statement on table 'user' expected to update 1 row(s); 0 were
       matched" errors come from.

    Under gunicorn neither holds: each request gets its own app context and its
    own session, and PostgreSQL hands out a connection per checkout. This
    fixture reproduces that -- a file-backed SQLite database (normal pooling,
    one connection per thread) and no ambient app context, so each request
    pushes its own. Measured across five runs: 5/5 registrations succeed every
    time here, versus 0-3/5 with `test_app`.
    """
    from app import create_app, db
    from tests.conftest import TestConfig, create_all_for_tests

    class _ThreadedTestConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'concurrent.sqlite'}"
        # Give a blocked writer time to acquire the lock instead of failing
        # immediately with "database is locked".
        SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"timeout": 30}}

    app = create_app(_ThreadedTestConfig)

    # Push a context only for the schema work, then pop it, so that the
    # requests below each get their own.
    with app.app_context():
        create_all_for_tests(db)

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()


class TestConcurrentRequests:
    """Test handling of concurrent requests"""

    @patch.dict(
        "os.environ",
        {
            "PRIVATE_REGISTRATION_ENABLED": "true",
            "PRIVATE_REGISTRATION_SECRET": "test-concurrent-secret",
            # The limiter buckets by secret hash, so all five requests share one
            # bucket; the default is 10/hour but pin it so the test cannot start
            # failing for rate-limit reasons if that default is retuned.
            "PRIVATE_REGISTRATION_RATE_LIMIT": "100",
        },
    )
    def test_concurrent_registrations(self, threaded_app):
        """Test multiple concurrent registration requests"""
        client = threaded_app.test_client()

        headers = {
            "X-PieFed-Secret": "test-concurrent-secret",
            "Content-Type": "application/json",
            "X-Forwarded-For": "127.0.0.1",
        }

        def register_user(user_id):
            """Helper function to register a user"""
            user_data = {
                "username": f"concurrent_user_{user_id}",
                "email": f"concurrent_user_{user_id}@example.com",
                "auto_activate": True,
            }

            response = client.post(
                "/api/alpha/admin/private_register",
                headers=headers,
                data=json.dumps(user_data),
            )

            return response.status_code, user_id

        # Start 5 concurrent registration requests
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(register_user, i) for i in range(5)]
            results = [future.result() for future in as_completed(futures)]

        # All should succeed (different usernames/emails)
        success_count = sum(1 for status, _ in results if status == 201)
        assert (
            success_count == 5
        ), f"Expected 5 successful registrations, got {success_count}"

    @patch.dict(
        "os.environ",
        {
            "PRIVATE_REGISTRATION_ENABLED": "true",
            "PRIVATE_REGISTRATION_SECRET": "test-concurrent-dup-secret",
            "PRIVATE_REGISTRATION_RATE_LIMIT": "100",
        },
    )
    def test_concurrent_duplicate_registrations(self, threaded_app):
        """Test concurrent attempts to register the same user

        Uses `threaded_app` for the reasons documented on that fixture. On
        conftest's `test_app` this failed roughly one run in ten with
        "Expected 1 successful registration, got 0" -- all three requests
        losing to the shared in-memory SQLite connection rather than to each
        other.
        """
        client = threaded_app.test_client()

        headers = {
            "X-PieFed-Secret": "test-concurrent-dup-secret",
            "Content-Type": "application/json",
            "X-Forwarded-For": "127.0.0.1",
        }

        # Same user data for all requests
        user_data = {
            "username": "duplicate_concurrent",
            "email": "duplicate_concurrent@example.com",
            "auto_activate": True,
        }

        def register_duplicate():
            """Try to register the same user"""
            response = client.post(
                "/api/alpha/admin/private_register",
                headers=headers,
                data=json.dumps(user_data),
            )
            return response.status_code

        # Start 3 concurrent registration requests for same user
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(register_duplicate) for _ in range(3)]
            results = [future.result() for future in as_completed(futures)]

        # Only one should succeed (201), others should fail (400)
        success_count = sum(1 for status in results if status == 201)
        failure_count = sum(1 for status in results if status == 400)

        assert (
            success_count == 1
        ), f"Expected 1 successful registration, got {success_count}"
        assert (
            failure_count == 2
        ), f"Expected 2 failed registrations, got {failure_count}"


class TestAttackScenarios:
    """Test various attack scenarios"""

    @patch.dict(
        "os.environ",
        {
            "PRIVATE_REGISTRATION_ENABLED": "true",
            "PRIVATE_REGISTRATION_SECRET": "correct-secret-not-sent-by-this-test",
        },
    )
    def test_secret_brute_force_protection(self, test_app):
        """Test protection against secret brute force attempts"""
        client = test_app.test_client()

        headers_base = {
            "Content-Type": "application/json",
            "X-Forwarded-For": "127.0.0.1",
        }

        user_data = {
            "username": "brute_force_test",
            "email": "brute_force_test@example.com",
            "auto_activate": True,
        }

        # Try multiple wrong secrets rapidly
        wrong_secrets = ["wrong1", "wrong2", "wrong3", "admin123", "password"]

        for secret in wrong_secrets:
            headers = headers_base.copy()
            headers["X-PieFed-Secret"] = secret

            response = client.post(
                "/api/alpha/admin/private_register",
                headers=headers,
                data=json.dumps(user_data),
            )

            # Should always return 401 for wrong secret
            assert response.status_code == 401
            data = response.get_json()
            assert data["error"] == "invalid_secret"

    def test_large_payload_handling(self, test_app):
        """Test handling of unusually large payloads"""
        client = test_app.test_client()

        headers = {
            "X-PieFed-Secret": "test-large-payload-secret",
            "Content-Type": "application/json",
            "X-Forwarded-For": "127.0.0.1",
        }

        # Create large bio (beyond typical limits)
        large_bio = "A" * 10000  # 10KB bio

        user_data = {
            "username": "large_payload_test",
            "email": "large_payload_test@example.com",
            "bio": large_bio,
            "auto_activate": True,
        }

        response = client.post(
            "/api/alpha/admin/private_register",
            headers=headers,
            data=json.dumps(user_data),
        )

        # Should handle gracefully (either succeed or fail with validation error)
        assert response.status_code in [201, 400]

        if response.status_code == 400:
            data = response.get_json()
            assert data["error"] == "validation_failed"

    def test_malicious_headers(self, test_app):
        """Test handling of malicious or malformed headers"""
        client = test_app.test_client()

        user_data = {
            "username": "malicious_header_test",
            "email": "malicious_header_test@example.com",
            "auto_activate": True,
        }

        # Test various malicious header scenarios
        malicious_headers = [
            # SQL injection attempt in secret
            {"X-PieFed-Secret": "'; DROP TABLE users; --"},
            # XSS attempt in forwarded IP
            {
                "X-PieFed-Secret": "test-secret",
                "X-Forwarded-For": '<script>alert("xss")</script>',
            },
            # Very long secret
            {"X-PieFed-Secret": "A" * 1000},
            # Binary data in secret
            {"X-PieFed-Secret": "\x00\x01\x02"},
        ]

        for malicious_header in malicious_headers:
            headers = {
                "Content-Type": "application/json",
                "X-Forwarded-For": "127.0.0.1",  # Default safe IP
            }
            headers.update(malicious_header)

            response = client.post(
                "/api/alpha/admin/private_register",
                headers=headers,
                data=json.dumps(user_data),
            )

            # Should handle malicious headers gracefully
            assert response.status_code in [400, 401, 403]

            # Should not cause server errors
            assert response.status_code != 500
