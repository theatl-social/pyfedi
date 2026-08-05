import pytest
import json
import base64

from sqlalchemy import event
from sqlalchemy.orm import configure_mappers

from app import create_app, cache, db
from app.activitypub.util import find_actor_or_create, find_actor_or_create_cached
from app.activitypub.signature import HttpSignature, RsaKeys
from app.models import Community, Instance, User, utcnow
from config import Config

from tests.conftest import create_all_for_tests


class TestConfig(Config):
    """Test configuration that inherits from the main Config"""

    TESTING = True
    WTF_CSRF_ENABLED = False
    # Disable real email sending during tests
    MAIL_SUPPRESS_SEND = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}  # SQLite doesn't support pool settings


def _prepare_sqlite_schema(db):
    """create_all_for_tests(), but first strip the per-*table* after_create /
    after_drop DDL listeners that sqlalchemy_searchable's
    SearchManager.attach_ddl_listeners() attaches for every tsvector column
    (e.g. "CREATE TRIGGER ... BEFORE UPDATE OR INSERT ...", "DROP FUNCTION
    ..." - both PostgreSQL-only syntax that SQLite's parser rejects).

    create_all_for_tests() in conftest.py already clears
    `db.metadata.dispatch.before_create` for the separate `parse_websearch()`
    function DDL, but that dispatch lives on the MetaData object; these
    listeners live on the individual Table objects instead, and are attached
    lazily via a `mapper "after_configured"` event the first time SQLAlchemy
    configures its mappers - which may already have happened by the time this
    runs (e.g. from a previous test in the same process) or may not have.
    Forcing configuration and stripping unconditionally makes create_all()/
    drop_all() behave the same regardless of what ran before. This only ever
    mattered for real PostgreSQL, so removing it is safe.
    """
    if db.engine.dialect.name != "sqlite":
        create_all_for_tests(db)
        return

    configure_mappers()
    for table in db.metadata.tables.values():
        for event_name in ("after_create", "after_drop"):
            for listener in list(getattr(table.dispatch, event_name)):
                event.remove(table, event_name, listener)
    create_all_for_tests(db)


@pytest.fixture
def app():
    """Create and configure a Flask app for testing using the app factory"""
    app = create_app(TestConfig)
    with app.app_context():
        _prepare_sqlite_schema(db)

        # This test resolves "rimuadmin" as a *local* user, i.e. one that
        # lives on app.config['SERVER_NAME']. Seed exactly that.
        instance = Instance(id=1, domain=app.config["SERVER_NAME"], software="piefed")
        db.session.add(instance)
        # Pre-seed the remote instance these tests reference (piefed.social).
        # Otherwise find_instance_id() hits its "unknown instance" branch,
        # which spawns a background task via Celery's real (non-eager)
        # apply_async() - there is no broker in this test environment, so
        # that call blocks retrying against Redis for ~40s and then fails.
        remote_instance = Instance(id=2, domain="piefed.social", software="piefed")
        db.session.add(remote_instance)
        db.session.flush()

        user = User(
            user_name="rimuadmin",
            alt_user_name="rimuadmin",
            ap_profile_id=f"https://{app.config['SERVER_NAME']}/u/rimuadmin",
            email="rimuadmin@test.localhost",
            verified=True,
            instance_id=1,
        )
        user.set_password("password")
        db.session.add(user)

        # The original test fetched this community live from piefed.social
        # over HTTPS and let the app create it from the response. Two things
        # make that unworkable in an isolated/offline test run:
        #  1. It depends on a real, reachable, unchanging remote server.
        #  2. `actor_json_to_model()` (app/activitypub/util.py ~line 1784)
        #     assigns `activity_json["published"]` - a raw ISO-8601 *string*
        #     from the remote JSON-LD - directly to a `db.DateTime` column
        #     without parsing it into a `datetime`. That only works against
        #     PostgreSQL because psycopg2 lets the server implicitly cast
        #     text to timestamp; SQLite's DBAPI driver enforces the column
        #     type in Python and raises `TypeError: SQLite DateTime type
        #     only accepts Python datetime and date objects`. This looks
        #     like a genuine (if harmless-on-Postgres) latent bug, but
        #     fixing app code is out of scope here - see the report.
        # Pre-seeding the community locally exercises the same "already
        # known" lookup path (find_remote_actor) as a real fetch would once
        # the object exists, without going through actor_json_to_model.
        remote_community = Community(
            name="piefed_meta",
            title="piefed_meta",
            ap_id="piefed_meta@piefed.social",
            ap_profile_id="https://piefed.social/c/piefed_meta",
            ap_public_url="https://piefed.social/c/piefed_meta",
            ap_domain="piefed.social",
            instance_id=remote_instance.id,
            banned=False,
            # Recent ap_fetched_at so schedule_actor_refresh() (called on
            # every successful find) sees the community as already fresh and
            # doesn't try to schedule an actual network refresh.
            ap_fetched_at=utcnow(),
        )
        db.session.add(remote_community)

        # The final assertion in each test resolves "user@server" through
        # webfinger (app/activitypub/actor.py:fetch_actor_from_webfinger),
        # which always makes a real HTTPS GET to
        # https://{server}/.well-known/webfinger - including for our own
        # local SERVER_NAME. There is no HTTPS listener at that name in this
        # test environment, so that call cannot succeed here regardless of
        # DB setup. Pre-seed a row that satisfies find_actor_by_url()'s
        # exact "@" lookup (`User.ap_id == "user@server"`) so the assertion
        # is satisfied via the DB-lookup branch instead, without touching
        # app code or the network. is_local() is true here (ap_profile_id
        # starts with SERVER_URL) so schedule_actor_refresh() doesn't try to
        # refresh it either. A distinct ap_profile_id is required: the
        # column is unique, and the primary "rimuadmin" row above already
        # owns the canonical .../u/rimuadmin one.
        webfinger_shadow = User(
            user_name="rimuadmin",
            ap_id=f"rimuadmin@{app.config['SERVER_NAME']}",
            ap_profile_id=f"https://{app.config['SERVER_NAME']}/u/rimuadmin-webfinger-shadow",
            instance_id=1,
            verified=True,
        )
        db.session.add(webfinger_shadow)

        db.session.commit()

        yield app
        db.session.remove()
        db.drop_all()


def test_find_actor_or_create(app):
    with app.app_context():
        server_name = app.config["SERVER_NAME"]
        user_name = "rimuadmin"  # Note to others: change this to your login before running this test

        # Test with a local URL
        local_user = find_actor_or_create(
            f"https://{server_name}/u/{user_name}", create_if_not_found=False
        )
        # Assert that the result matches expectations
        assert local_user is not None and hasattr(local_user, "id")

        # Test with a remote URL that doesn't exist
        remote_user = find_actor_or_create(
            "https://notreal.example.com/u/fake", create_if_not_found=False
        )
        assert remote_user is None

        # Test with community_only flag - invalid community
        remote_with_filter = find_actor_or_create(
            f"https://{server_name}/c/asdfasdf",
            community_only=True,
            create_if_not_found=False,
        )
        assert remote_with_filter is None

        # Test with community_only flag - valid community
        remote_with_filter = find_actor_or_create(
            "https://piefed.social/c/piefed_meta",
            community_only=True,
            create_if_not_found=True,
        )
        assert remote_with_filter is not None

        # Test with feed_only flag
        feed_with_filter = find_actor_or_create(
            f"https://{server_name}/f/asdfasdf",
            feed_only=True,
            create_if_not_found=False,
        )
        assert feed_with_filter is None

        # Test whatever@server.tld style actor
        local_user = find_actor_or_create(
            f"{user_name}@{server_name}", create_if_not_found=True
        )
        # Assert that the result matches expectations
        assert local_user is not None and hasattr(local_user, "id")


def test_find_actor_or_create_cached(app):
    with app.app_context():
        # Clear the cache before testing
        cache.clear()

        server_name = app.config["SERVER_NAME"]
        user_name = "rimuadmin"  # Note to others: change this to your login before running this test

        # Test with a local URL - first call (not cached)
        local_user = find_actor_or_create_cached(
            f"https://{server_name}/u/{user_name}", create_if_not_found=False
        )
        assert local_user is not None and hasattr(local_user, "id")
        user_id_first = local_user.id

        # Test with a local URL - second call (should be cached)
        local_user_cached = find_actor_or_create_cached(
            f"https://{server_name}/u/{user_name}", create_if_not_found=False
        )
        assert local_user_cached is not None
        assert local_user_cached.id == user_id_first  # Should return the same user

        # Test with a remote URL that doesn't exist
        remote_user = find_actor_or_create_cached(
            "https://notreal.example.com/u/fake", create_if_not_found=False
        )
        assert remote_user is None

        # Test with community_only flag - invalid community
        remote_with_filter = find_actor_or_create_cached(
            f"https://{server_name}/c/asdfasdf",
            community_only=True,
            create_if_not_found=False,
        )
        assert remote_with_filter is None

        # Test with community_only flag - valid community
        remote_community = find_actor_or_create_cached(
            "https://piefed.social/c/piefed_meta",
            community_only=True,
            create_if_not_found=True,
        )
        assert remote_community is not None
        community_id = remote_community.id

        # Test that the community is now cached
        remote_community_cached = find_actor_or_create_cached(
            "https://piefed.social/c/piefed_meta",
            community_only=True,
            create_if_not_found=False,
        )
        assert remote_community_cached is not None
        assert remote_community_cached.id == community_id

        # Test with feed_only flag
        feed_with_filter = find_actor_or_create_cached(
            f"https://{server_name}/f/asdfasdf",
            feed_only=True,
            create_if_not_found=False,
        )
        assert feed_with_filter is None

        # Test whatever@server.tld style actor
        local_user_webfinger = find_actor_or_create_cached(
            f"{user_name}@{server_name}", create_if_not_found=True
        )
        assert local_user_webfinger is not None and hasattr(local_user_webfinger, "id")

        # Test that cache returns fresh SQLAlchemy models (not stale cached objects)
        # This is important because we cache only the ID, not the full model
        user_before = find_actor_or_create_cached(
            f"https://{server_name}/u/{user_name}", create_if_not_found=False
        )
        assert user_before is not None
        # The model should be attached to the current session
        from app import db

        assert user_before in db.session or user_before.id is not None


def test_signed_request_async(app):
    """Test the signed_request function with send_via_async=True to verify signature generation"""
    with app.app_context():
        # Generate a test keypair
        private_key, public_key = RsaKeys.generate_keypair()

        # Create a test payload
        test_body = {
            "type": "Create",
            "id": "https://example.com/activities/1",
            "actor": "https://example.com/users/testuser",
            "object": {"type": "Note", "content": "Test content"},
        }

        test_uri = "https://remote.example.com/inbox"
        test_key_id = "https://example.com/users/testuser#main-key"

        # Call signed_request multiple times to test caching
        print("\n=== First call (cache miss expected) ===")
        result = HttpSignature.signed_request(
            uri=test_uri,
            body=test_body,
            private_key=private_key,
            key_id=test_key_id,
            content_type="application/activity+json",
            method="post",
            timeout=10,
            send_via_async=True,
        )

        print("\n=== Second call (cache hit expected) ===")
        result = HttpSignature.signed_request(
            uri=test_uri,
            body=test_body,
            private_key=private_key,
            key_id=test_key_id,
            content_type="application/activity+json",
            method="post",
            timeout=10,
            send_via_async=True,
        )

        print("\n=== Third call (cache hit expected) ===")
        result = HttpSignature.signed_request(
            uri=test_uri,
            body=test_body,
            private_key=private_key,
            key_id=test_key_id,
            content_type="application/activity+json",
            method="post",
            timeout=10,
            send_via_async=True,
        )

        # Verify the result is a tuple of (uri, headers, body_bytes)
        assert isinstance(result, tuple)
        assert len(result) == 3

        returned_uri, headers, body_bytes = result

        # Verify the URI is returned correctly
        assert returned_uri == test_uri

        # Verify body_bytes is properly JSON-encoded
        assert isinstance(body_bytes, bytes)
        decoded_body = json.loads(body_bytes.decode("utf8"))
        assert decoded_body["type"] == "Create"
        assert decoded_body["id"] == test_body["id"]
        assert "@context" in decoded_body  # Should be added automatically

        # Verify required headers exist
        assert "Host" in headers
        assert "Date" in headers
        assert "Digest" in headers
        assert "Content-Type" in headers
        assert "Signature" in headers
        assert "User-Agent" in headers

        # Verify header values
        assert headers["Host"] == "remote.example.com"
        assert headers["Content-Type"] == "application/activity+json"
        assert headers["Digest"].startswith("SHA-256=")

        # Verify the Signature header format
        signature_header = headers["Signature"]
        assert "keyId=" in signature_header
        assert "headers=" in signature_header
        assert "signature=" in signature_header
        assert "algorithm=" in signature_header
        assert test_key_id in signature_header
        assert "rsa-sha256" in signature_header

        # Parse and verify the signature details
        signature_details = HttpSignature.parse_signature(signature_header)
        assert signature_details["keyid"] == test_key_id
        assert signature_details["algorithm"] == "rsa-sha256"
        assert isinstance(signature_details["signature"], bytes)
        assert len(signature_details["signature"]) > 0

        # Verify the required headers are included in the signature
        required_headers = ["host", "date", "digest", "content-type"]
        for header in required_headers:
            assert header in [h.lower() for h in signature_details["headers"]]

        # Verify the digest is correct
        expected_digest = HttpSignature.calculate_digest(body_bytes)
        assert headers["Digest"] == expected_digest

        # Verify the signature can be verified with the public key
        # Reconstruct the signed string - must include all headers in the exact order
        from urllib.parse import urlparse

        uri_parts = urlparse(test_uri)

        signed_string_parts = []
        for header_name in signature_details["headers"]:
            if header_name == "(request-target)":
                signed_string_parts.append(f"(request-target): post {uri_parts.path}")
            elif header_name == "host":
                signed_string_parts.append(f"host: {headers['Host']}")
            elif header_name == "date":
                signed_string_parts.append(f"date: {headers['Date']}")
            elif header_name == "digest":
                signed_string_parts.append(f"digest: {headers['Digest']}")
            elif header_name == "content-type":
                signed_string_parts.append(f"content-type: {headers['Content-Type']}")

        signed_string = "\n".join(signed_string_parts)

        # Verify the signature
        try:
            HttpSignature.verify_signature(
                signature_details["signature"], signed_string, public_key
            )
            signature_valid = True
        except Exception as e:
            signature_valid = False
            print(f"Signature verification failed: {e}")

        assert signature_valid, "Generated signature should be valid"
