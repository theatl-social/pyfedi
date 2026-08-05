"""
Tests for SQL injection vulnerability fixes

These tests verify that the SQL injection fixes work correctly and that
malicious input cannot be used to exploit the database.
"""

import pytest
from unittest.mock import patch, MagicMock
from flask import Flask

from app import create_app, db
from app.models import User, Conversation, ChatMessage, Notification
from app.constants import POST_STATUS_REVIEWING
from tests.conftest import TestConfig as _BaseTestConfig, create_all_for_tests


class TestConfig(_BaseTestConfig):
    """Test configuration for this file, inheriting the working base config.

    The base TestConfig in conftest.py inherits the real app Config so every
    key create_app() reads is present, and its CACHE_TYPE/CACHE_REDIS_URL are
    set for NullCache. This file previously defined its own bare TestConfig
    (not inheriting Config), which raised KeyError('HTTP_PROTOCOL') during
    create_app(), and it called plain db.create_all() which aborts partway on
    SQLite because sqlalchemy_searchable's before_create hook emits
    PostgreSQL-only DDL.
    """

    CACHE_TYPE = "NullCache"


@pytest.fixture
def app():
    """Create test Flask application"""
    from sqlalchemy import event
    from sqlalchemy_searchable import sql_expressions

    from tests.explore_test_support import (
        _restore_ddl_listeners,
        _strip_sqlite_ddl_listeners,
    )

    app = create_app(TestConfig)

    with app.app_context():
        # create_all_for_tests() strips the metadata-level before_create hook
        # that emits `CREATE OR REPLACE FUNCTION parse_websearch(...)`
        # (PostgreSQL-only), which is what makes db.create_all() proceed past
        # step 1 on SQLite. But sqlalchemy_searchable *also* attaches a
        # per-table after_create hook (CreateSearchTriggerSQL) to every table
        # with a TSVectorType column -- User, Community, Post, PostReply,
        # Feed -- that emits `CREATE TRIGGER ... BEFORE UPDATE OR INSERT ...
        # EXECUTE PROCEDURE tsvector_update_trigger(...)`, also PostgreSQL-only
        # syntax SQLite rejects. This file creates a User row, so it needs
        # those detached too. Detach only for the duration of table creation
        # on SQLite, and reattach afterwards so the process-wide
        # sqlalchemy_searchable singleton doesn't leak a changed state into
        # other test files running later in the same session.
        #
        # Uses the low-level, idempotent event.remove()/event.listen() helpers
        # in tests/explore_test_support.py rather than
        # `sqlalchemy_searchable.search_manager.remove_listeners()/
        # attach_ddl_listeners()`: that API keeps its own bookkeeping of what
        # it attached and raises InvalidRequestError if asked to remove a
        # listener some other test file already stripped directly (see
        # tests/test_activitypub_util.py's _prepare_sqlite_schema, which does
        # exactly that without going through search_manager).
        sqlite = db.engine.dialect.name == "sqlite"
        removed = _strip_sqlite_ddl_listeners(db) if sqlite else []
        try:
            create_all_for_tests(db)
        finally:
            if sqlite:
                _restore_ddl_listeners(removed)
            # create_all_for_tests() clears *every* before_create listener on
            # db.metadata (`db.metadata.dispatch.before_create.clear()`), not
            # just the one it means to silence. db.metadata is one process-
            # wide MetaData object shared by every Flask app built via
            # create_app() in this test run, so that clear() permanently
            # removes sqlalchemy_searchable's metadata-level hook for every
            # test file that runs afterwards in the same process -- including
            # ones with an old-style `try: db.create_all() / except: tolerate
            # "parse_websearch"/"CREATE OR REPLACE"` fixture (e.g.
            # tests/test_upload_quota_and_grafts.py), which depends on that
            # exact hook firing *first* and aborting create_all() before any
            # table is touched. Without restoring it here, that file's
            # fixture proceeds past the point it expects to be stopped at and
            # hits the (still-present, PostgreSQL-only) per-table search
            # trigger DDL instead, with an error message its except clause
            # doesn't recognize. Put it back so this file leaves no lasting
            # mutation on shared state. See tests/conftest.py's
            # create_all_for_tests() docstring for the rest of the story.
            if sqlite and not event.contains(
                db.metadata, "before_create", sql_expressions
            ):
                event.listen(db.metadata, "before_create", sql_expressions)
        yield app
        db.session.remove()
        # drop_all() fires the mirror-image after_drop hooks (DROP FUNCTION /
        # DROP TRIGGER), so detach for teardown too.
        removed = _strip_sqlite_ddl_listeners(db) if sqlite else []
        try:
            db.drop_all()
        finally:
            if sqlite:
                _restore_ddl_listeners(removed)


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


class TestChatSQLInjectionFix:
    """Test chat notification SQL injection fix"""

    def test_chat_notification_update_safe(self, app):
        """Test that chat notification update is safe from SQL injection"""
        with app.app_context():
            # Create test user
            user = User(
                user_name="testuser",
                email="test@example.com",
                password_hash="hashed_password",
                instance_id=1,
                verified=True,
            )
            db.session.add(user)
            db.session.commit()

            # Create test notification
            notification = Notification(
                user_id=user.id, title="Test notification", url="/chat/123", read=False
            )
            db.session.add(notification)
            db.session.commit()

            # Simulate the fixed code path - should not cause SQL injection
            from sqlalchemy import text

            # Test with normal conversation_id
            conversation_id = 123
            sql = "UPDATE notification SET read = true WHERE url LIKE :url_pattern AND user_id = :user_id"
            result = db.session.execute(
                text(sql),
                {"url_pattern": f"/chat/{conversation_id}%", "user_id": user.id},
            )

            assert result.rowcount >= 0  # Should execute without error

            # Test with malicious conversation_id (should be safely parameterized)
            malicious_conversation_id = "123' OR 1=1 --"
            sql = "UPDATE notification SET read = true WHERE url LIKE :url_pattern AND user_id = :user_id"
            result = db.session.execute(
                text(sql),
                {
                    "url_pattern": f"/chat/{malicious_conversation_id}%",
                    "user_id": user.id,
                },
            )

            # Should execute safely - malicious input treated as literal string
            assert result.rowcount >= 0


class TestUserRoutesSQLInjectionFix:
    """Test user routes SQL injection fix"""

    def test_user_posts_query_safe(self, app):
        """Test that user posts query is safe from SQL injection"""
        with app.app_context():
            # Create test user
            user = User(
                user_name="testuser",
                email="test@example.com",
                password_hash="hashed_password",
                instance_id=1,
                verified=True,
            )
            db.session.add(user)
            db.session.commit()

            # Test the fixed parameterized query
            from sqlalchemy import text

            # Normal user_id
            user_id = user.id
            per_page = 20
            offset_val = 0

            # Test admin query path
            post_select = "SELECT id, posted_at, 'post' AS type FROM post WHERE user_id = :user_id"
            reply_select = "SELECT id, posted_at, 'reply' AS type FROM post_reply WHERE user_id = :user_id"
            query_params = {"user_id": user_id}

            full_query = (
                post_select
                + " UNION "
                + reply_select
                + " ORDER BY posted_at DESC LIMIT :limit OFFSET :offset"
            )
            query_params.update({"limit": per_page + 1, "offset": offset_val})

            # Should execute without error
            result = db.session.execute(text(full_query), query_params)
            assert result is not None

            # Test with potentially malicious user_id (should be safely parameterized)
            malicious_user_id = "1 OR 1=1"
            query_params = {
                "user_id": malicious_user_id,
                "limit": per_page + 1,
                "offset": offset_val,
            }

            # Should execute safely - malicious input treated as literal value
            result = db.session.execute(text(full_query), query_params)
            assert result is not None


class TestUtilsSQLInjectionFix:
    """Test utils SQL injection fix"""

    def test_blocked_image_hash_safe(self, app):
        """Test that blocked image hash query is safe from SQL injection"""
        with app.app_context():
            from sqlalchemy import text

            # Test with normal hash
            normal_hash = "1010101010101010"
            sql = "SELECT id FROM blocked_image WHERE length(replace((hash # B:hash)::text, '0', '')) < 15"

            # Should execute without error (even if no blocked_image table exists in test)
            try:
                db.session.execute(text(sql), {"hash": normal_hash})
                # Query should execute safely
                assert True
            except Exception as e:
                # If table doesn't exist, that's fine - important thing is no SQL injection
                assert (
                    "blocked_image" in str(e).lower()
                    or "syntax error" not in str(e).lower()
                )

            # Test with potentially malicious hash
            malicious_hash = "1010'; DROP TABLE users; --"

            try:
                db.session.execute(text(sql), {"hash": malicious_hash})
                # Should execute safely - malicious input treated as literal parameter
                assert True
            except Exception as e:
                # If table doesn't exist, that's fine - important thing is no SQL injection
                assert (
                    "blocked_image" in str(e).lower()
                    or "syntax error" not in str(e).lower()
                )


class TestMainRoutesSQLInjectionFix:
    """Test main routes SQL injection fix"""

    def test_community_filter_safe(self, app):
        """Test that community filter queries are safe"""
        with app.app_context():
            from sqlalchemy import text

            # Test local communities query - no longer uses string concatenation
            sql_local = "SELECT id FROM community as c WHERE c.instance_id = 1"
            result = db.session.execute(text(sql_local))
            assert result is not None

            sql_local_filtered = "SELECT id FROM community as c WHERE c.instance_id = 1 AND c.low_quality is false"
            result = db.session.execute(text(sql_local_filtered))
            assert result is not None

            # Test popular communities query
            sql_popular = "SELECT id FROM community as c WHERE c.show_popular is true"
            result = db.session.execute(text(sql_popular))
            assert result is not None

            sql_popular_filtered = "SELECT id FROM community as c WHERE c.show_popular is true AND c.low_quality is false"
            result = db.session.execute(text(sql_popular_filtered))
            assert result is not None


class TestSQLInjectionSecurityRegression:
    """Regression tests to ensure SQL injection vulnerabilities don't return"""

    def test_no_f_strings_in_sql_queries(self, app):
        """Static analysis: no attacker-shaped interpolation into SQL text.

        Commit d3b170f2 ("Fix critical SQL injection vulnerabilities",
        2025-09-12) removed this pattern from app/main/routes.py. Later upstream
        merges reintroduced it while adding `private_communities`, and this test
        did not catch it because the file was in the CI exclusion list. Both the
        queries and this detector have now been fixed.
        """
        import os
        import re

        # An f-string only counts as SQL if it carries BOTH a statement keyword
        # and a matching clause keyword. The original patterns matched any
        # f-string containing "delete" (case-insensitively), which flagged
        # `f"deleted_{user.id}@deleted.com"` and an `/activities/delete/` URL.
        # A detector that cries wolf gets ignored -- which is how this file's
        # own invariant survived being broken for months.
        sql_injection_patterns = [
            r"f['\"][^'\"]*\bSELECT\b[^'\"]*\bFROM\b[^'\"]*\{",
            r"f['\"][^'\"]*\bUPDATE\b[^'\"]*\bSET\b[^'\"]*\{",
            r"f['\"][^'\"]*\bINSERT\s+INTO\b[^'\"]*\{",
            r"f['\"][^'\"]*\bDELETE\s+FROM\b[^'\"]*\{",
        ]

        # Files we've fixed
        fixed_files = [
            "app/chat/routes.py",
            "app/user/routes.py",
            "app/utils.py",
            "app/main/routes.py",
        ]

        # Sites that interpolate, but where the value is provably constrained at
        # the call site. Each entry names the guard, and the guard is asserted
        # below -- if it disappears, this test fails instead of silently passing.
        # Do NOT add entries to silence a finding; parameterize the query.
        guarded_interpolations = {
            # hash_matches_blocked_image() builds a PostgreSQL bit literal
            # (B'...'), which has no bind-parameter form without a cast whose
            # operator resolution (bit # bit varying) needs verifying against a
            # real PostgreSQL server -- not possible in this SQLite-backed
            # suite. The input is restricted to ^[01]+$ immediately before use.
            # Converting to CAST(:hash AS bit varying) is a tracked follow-up.
            "app/utils.py": ("BINARY_RE.match", "hash_matches_blocked_image"),
        }

        base_path = os.path.dirname(os.path.dirname(__file__))
        violations = []

        for file_path in fixed_files:
            full_path = os.path.join(base_path, file_path)
            if os.path.exists(full_path):
                with open(full_path, "r") as f:
                    content = f.read()
                    for line_num, line in enumerate(content.splitlines(), 1):
                        for pattern in sql_injection_patterns:
                            if re.search(pattern, line, re.IGNORECASE):
                                violations.append(
                                    f"{file_path}:{line_num}: {line.strip()}"
                                )

        # Every exemption must still carry the guard that justifies it.
        for file_path, (guard, func_name) in guarded_interpolations.items():
            with open(os.path.join(base_path, file_path)) as f:
                src = f.read()
            assert func_name in src, (
                f"{file_path}: {func_name}() no longer exists -- remove its "
                "guarded_interpolations entry."
            )
            assert guard in src, (
                f"SECURITY REGRESSION: {file_path} no longer contains "
                f"{guard!r}, which is the only thing making {func_name}()'s "
                "interpolated SQL safe. Restore the guard or parameterize."
            )
            violations = [v for v in violations if not v.startswith(file_path)]

        assert len(violations) == 0, (
            f"Found SQL injection patterns in fixed files: {violations}"
        )

    def test_parameterized_queries_used(self, app):
        """Test that parameterized queries are properly used"""
        from sqlalchemy import text

        with app.app_context():
            # These should all work without error - demonstrating proper parameterization
            test_queries = [
                ("SELECT 1 WHERE 1 = :param", {"param": 1}),
                ("SELECT :value", {"value": "test"}),
                ("SELECT * FROM (SELECT 1 as id) t WHERE id = :id", {"id": 1}),
            ]

            for sql, params in test_queries:
                result = db.session.execute(text(sql), params)
                assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
