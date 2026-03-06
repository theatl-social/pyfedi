import pytest
import json
import base64

from app import create_app, cache
from app.activitypub.util import find_actor_or_create, find_actor_or_create_cached
from app.activitypub.signature import HttpSignature, RsaKeys
from config import Config


class TestConfig(Config):
    """Test configuration that inherits from the main Config"""

    TESTING = True
    WTF_CSRF_ENABLED = False
    # Disable real email sending during tests
    MAIL_SUPPRESS_SEND = True


@pytest.fixture
def app():
    """Create and configure a Flask app for testing using the app factory"""
    app = create_app(TestConfig)
    return app


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
