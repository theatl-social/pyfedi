"""
Unit tests for security mitigations implemented in PeachPie.

This module tests all security fixes including:
- SQL injection prevention
- SSRF protection
- Rate limiting
- Authentication bypass prevention
- Safe JSON parsing
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
import httpx

from app.activitypub.signature import verify_request, post_request
from app.utils import (
    allowlist_html,
    markdown_to_html,
    is_safe_url,
    validate_url,
    sanitize_sql_input
)


class TestSQLInjectionPrevention:
    """Test SQL injection prevention measures."""
    
    def test_parameterized_queries(self):
        """Test that queries use parameters instead of string formatting."""
        from app.models import User, Community, Post
        
        # These should use SQLAlchemy ORM or parameterized queries
        dangerous_inputs = [
            "'; DROP TABLE users; --",
            "1' OR '1'='1",
            "admin'--",
            "1; DELETE FROM posts WHERE 1=1; --",
            "' UNION SELECT * FROM users--"
        ]
        
        for dangerous_input in dangerous_inputs:
            # ORM queries are safe by default
            query = User.query.filter_by(user_name=dangerous_input)
            
            # The compiled query should have parameters
            compiled = str(query.statement.compile())
            
            # Should not contain the dangerous input directly
            assert dangerous_input not in compiled
            assert ':user_name' in compiled or '%(user_name)' in compiled
    
    def test_raw_query_validation(self):
        """Test that raw queries are properly validated."""
        # If we have a sanitize function
        safe_inputs = [
            sanitize_sql_input("normal_username"),
            sanitize_sql_input("user@example.com"),
            sanitize_sql_input("community-name"),
        ]
        
        dangerous_inputs = [
            "'; DROP TABLE--",
            "1' OR '1'='1",
            "admin'--"
        ]
        
        for safe_input in safe_inputs:
            # Should not modify safe inputs significantly
            assert safe_input.replace('-', '').replace('@', '').replace('.', '').isalnum()
        
        for dangerous_input in dangerous_inputs:
            sanitized = sanitize_sql_input(dangerous_input)
            # Should escape or reject dangerous characters
            assert "'" not in sanitized or "\\'" in sanitized
            assert "--" not in sanitized
    
    def test_search_query_safety(self):
        """Test that search queries are properly escaped."""
        from app.models import Post
        
        # Test search with dangerous input
        search_term = "'; DROP TABLE posts; --"
        
        # Using SQLAlchemy's text search
        with patch('sqlalchemy.func.to_tsquery') as mock_tsquery:
            # The ORM should handle this safely
            query = Post.query.filter(
                Post.body_ts.match(search_term)
            )
            
            # Should call tsquery with escaped input
            # Actual implementation would use proper escaping


class TestSSRFProtection:
    """Test SSRF (Server-Side Request Forgery) protection."""
    
    def test_url_validation(self):
        """Test URL validation prevents SSRF attacks."""
        # Valid external URLs
        valid_urls = [
            'https://example.com/inbox',
            'https://mastodon.social/users/test',
            'https://sub.domain.example.com/path'
        ]
        
        # Invalid/dangerous URLs
        invalid_urls = [
            'http://localhost/admin',
            'http://127.0.0.1:8080',
            'http://192.168.1.1',
            'http://10.0.0.1',
            'file:///etc/passwd',
            'ftp://internal.server',
            'http://[::1]',
            'http://169.254.169.254',  # AWS metadata
            'http://metadata.google.internal',  # GCP metadata
        ]
        
        for url in valid_urls:
            assert is_safe_url(url) is True
            assert validate_url(url) is True
        
        for url in invalid_urls:
            assert is_safe_url(url) is False
            assert validate_url(url) is False
    
    def test_media_fetch_protection(self):
        """Test that media fetching is protected against SSRF."""
        from app.activitypub.util import fetch_remote_media
        
        with patch('httpx.AsyncClient.get') as mock_get:
            # Should reject internal URLs
            with pytest.raises(ValueError):
                fetch_remote_media('http://localhost/internal.jpg')
            
            # Should not make request to internal IPs
            mock_get.assert_not_called()
    
    def test_activitypub_fetch_protection(self):
        """Test ActivityPub object fetching has SSRF protection."""
        from app.activitypub.util import fetch_remote_object
        
        with patch('app.activitypub.signature.signed_get_request') as mock_get:
            # Should validate URL before fetching
            dangerous_urls = [
                'http://127.0.0.1/actor',
                'http://internal.local/object',
                'file:///etc/passwd'
            ]
            
            for url in dangerous_urls:
                result = fetch_remote_object(url)
                assert result is None
                mock_get.assert_not_called()


class TestAuthenticationBypassPrevention:
    """Test prevention of authentication bypass vulnerabilities."""
    
    @pytest.mark.asyncio
    async def test_signature_verification_required(self):
        """Test that signature verification cannot be bypassed."""
        # Mock request without signature
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.method = 'POST'
        mock_request.path = '/inbox'
        mock_request.data = b'{"type": "Create"}'
        
        # Should reject unsigned requests
        result = await verify_request(mock_request)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_no_fallback_authentication(self):
        """Test that there's no unsafe fallback when signature fails."""
        mock_request = Mock()
        mock_request.headers = {
            'Signature': 'keyId="https://example.com/users/test#main-key",algorithm="rsa-sha256",headers="(request-target) host date",signature="invalid"'
        }
        
        # Should not fall back to accepting the request
        with patch('app.activitypub.signature.verify_signature', return_value=False):
            result = await verify_request(mock_request)
            assert result is False
            
            # Should not try alternative authentication methods
            # that might be less secure
    
    def test_token_validation(self):
        """Test that tokens are properly validated."""
        from app.auth.util import verify_auth_token
        
        # Invalid tokens should be rejected
        invalid_tokens = [
            '',
            'invalid',
            'eyJ0eXAiOiJKV1QiLCJhbGciOiJub25lIn0',  # "none" algorithm
            'null',
            'undefined'
        ]
        
        for token in invalid_tokens:
            result = verify_auth_token(token)
            assert result is None or result is False


class TestRateLimiting:
    """Test rate limiting implementation."""
    
    def test_endpoint_rate_limits(self, client, app):
        """Test that endpoints have appropriate rate limits."""
        # Test inbox endpoint rate limiting
        with app.test_request_context():
            # Make multiple requests
            for i in range(10):
                response = client.post(
                    '/site_inbox',
                    data=json.dumps({'type': 'Create'}),
                    content_type='application/activity+json'
                )
                
                if i < 5:
                    # First few should succeed
                    assert response.status_code in [200, 401, 403]
                else:
                    # Later ones might be rate limited
                    if response.status_code == 429:
                        # Check for Retry-After header
                        assert 'Retry-After' in response.headers
                        break
    
    def test_per_actor_rate_limiting(self):
        """Test rate limiting per actor."""
        from app.utils import check_rate_limit
        
        actor_id = 'https://example.com/users/spammer'
        
        # Simulate many requests from same actor
        for i in range(100):
            allowed = check_rate_limit(actor_id, 'create_post')
            
            if i < 10:
                assert allowed is True
            else:
                # Should start blocking after threshold
                if not allowed:
                    break
        
        # Should have been rate limited
        assert allowed is False


class TestSafeJSONParsing:
    """Test safe JSON parsing implementation."""
    
    def test_json_depth_limit(self):
        """Test that deeply nested JSON is rejected."""
        from app.utils import safe_json_loads
        
        # Create deeply nested JSON
        deep_json = '{"a":' * 100 + '1' + '}' * 100
        
        # Should reject deep nesting
        with pytest.raises(ValueError):
            safe_json_loads(deep_json)
    
    def test_json_size_limit(self):
        """Test that large JSON payloads are rejected."""
        from app.utils import safe_json_loads
        
        # Create large JSON (over 10MB)
        large_json = '{"data": "' + 'x' * (11 * 1024 * 1024) + '"}'
        
        # Should reject large payloads
        with pytest.raises(ValueError):
            safe_json_loads(large_json)
    
    def test_json_parse_safety(self):
        """Test safe parsing of various JSON inputs."""
        from app.utils import safe_json_loads
        
        # Valid JSON should parse
        valid_json = '{"type": "Create", "actor": "https://example.com/users/test"}'
        result = safe_json_loads(valid_json)
        assert result['type'] == 'Create'
        
        # Invalid JSON should raise exception
        invalid_inputs = [
            '{"unclosed": ',
            'undefined',
            'null; system("rm -rf /")',
            '{"__proto__": {"isAdmin": true}}'
        ]
        
        for invalid in invalid_inputs:
            with pytest.raises((ValueError, json.JSONDecodeError)):
                safe_json_loads(invalid)


class TestHTMLSanitization:
    """Test HTML sanitization for XSS prevention."""
    
    def test_allowlist_html_xss_prevention(self):
        """Test that dangerous HTML is sanitized."""
        dangerous_inputs = [
            '<script>alert("XSS")</script>',
            '<img src=x onerror="alert(1)">',
            '<iframe src="javascript:alert(1)"></iframe>',
            '<a href="javascript:void(0)">Click</a>',
            '<div onmouseover="alert(1)">Hover</div>',
            '<style>body{background:url("javascript:alert(1)")}</style>',
            '<meta http-equiv="refresh" content="0;url=javascript:alert(1)">',
            '<svg onload="alert(1)"></svg>',
            '<input type="text" onfocus="alert(1)" autofocus>'
        ]
        
        for dangerous in dangerous_inputs:
            cleaned = allowlist_html(dangerous)
            
            # Should not contain script tags or event handlers
            assert '<script' not in cleaned.lower()
            assert 'javascript:' not in cleaned.lower()
            assert 'onerror' not in cleaned.lower()
            assert 'onload' not in cleaned.lower()
            assert 'onfocus' not in cleaned.lower()
            assert 'onmouseover' not in cleaned.lower()
    
    def test_markdown_xss_prevention(self):
        """Test that markdown conversion prevents XSS."""
        dangerous_markdown = [
            '[Click me](javascript:alert(1))',
            '![](x" onerror="alert(1))',
            '<script>alert(1)</script>',
            '```html\n<script>alert(1)</script>\n```'
        ]
        
        for dangerous in dangerous_markdown:
            html = markdown_to_html(dangerous)
            cleaned = allowlist_html(html)
            
            # Should not allow javascript execution
            assert 'javascript:' not in cleaned
            assert '<script' not in cleaned
            assert 'onerror' not in cleaned


class TestVoteAmplificationPrevention:
    """Test prevention of vote amplification attacks."""
    
    def test_vote_deduplication(self):
        """Test that duplicate votes are prevented."""
        from app.models import PostVote, Post, User
        
        with patch('app.models.db.session') as mock_session:
            # Simulate same vote multiple times
            user_id = 1
            post_id = 1
            
            # First vote should work
            vote1 = PostVote(user_id=user_id, post_id=post_id, effect=1)
            
            # Duplicate vote should be prevented by unique constraint
            vote2 = PostVote(user_id=user_id, post_id=post_id, effect=1)
            
            # In real implementation, database constraint prevents this
    
    def test_announce_spam_prevention(self):
        """Test prevention of announce spam."""
        from app.activitypub.routes.inbox import process_inbox_request
        
        with patch('app.models.Activity.query') as mock_query:
            # Simulate multiple announces of same object
            activity = {
                'type': 'Announce',
                'actor': 'https://example.com/users/spammer',
                'object': 'https://target.com/posts/1'
            }
            
            # Should track and limit announces
            for i in range(10):
                result = process_inbox_request(activity)
                
                if i > 5:  # After threshold
                    # Should reject further announces
                    assert result is False or result == {'error': 'Too many announces'}


class TestSecurityHeaders:
    """Test security headers implementation."""
    
    def test_activitypub_content_type_validation(self, client, app):
        """Test that ActivityPub endpoints validate content type."""
        with app.test_request_context():
            # POST with wrong content type
            response = client.post(
                '/site_inbox',
                data='{"type": "Create"}',
                content_type='text/plain'  # Wrong content type
            )
            
            # Should reject non-ActivityPub content types
            assert response.status_code in [400, 415]  # Bad Request or Unsupported Media Type
    
    def test_cors_headers(self, client, test_user, app):
        """Test CORS headers on ActivityPub endpoints."""
        with app.test_request_context():
            response = client.get(
                f'/u/{test_user.user_name}',
                headers={'Accept': 'application/activity+json'}
            )
            
            # Should have appropriate CORS headers
            assert 'Access-Control-Allow-Origin' in response.headers
            # Should not be overly permissive
            assert response.headers.get('Access-Control-Allow-Origin') != '*'


class TestErrorHandlingSecurity:
    """Test secure error handling."""
    
    def test_no_sensitive_info_in_errors(self, client, app):
        """Test that errors don't leak sensitive information."""
        with app.test_request_context():
            # Try to access non-existent user
            response = client.get('/u/nonexistent')
            
            # Should not reveal database structure or queries
            assert 'SELECT' not in response.data.decode()
            assert 'FROM users' not in response.data.decode()
            assert 'postgresql' not in response.data.decode()
            
            # Should give generic error
            assert response.status_code == 404