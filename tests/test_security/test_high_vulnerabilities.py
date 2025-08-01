"""
Test cases for HIGH severity vulnerability fixes
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import redis
import time
from datetime import datetime, timedelta
from app.security.actor_limits import ActorCreationLimiter
from app.security.relay_protection import RelayProtection
from app.security.media_proxy_security import SecureMediaProxy, SSRFSafeAdapter
from app.security.permission_validator import PermissionValidator, Permission
from app.security.error_handler import SecureErrorHandler
import requests


class TestActorCreationLimits:
    """Test DoS prevention via actor creation limits"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_redis = Mock(spec=redis.Redis)
        self.limiter = ActorCreationLimiter()
        self.limiter.redis_client = self.mock_redis
    
    def test_actor_creation_within_limits_allowed(self):
        """Test actor creation is allowed within limits"""
        self.mock_redis.get.side_effect = [b'5', b'20', b'50']  # hourly, daily, global
        
        allowed, reason = self.limiter.can_create_actor('example.com', 'https://example.com/users/new')
        
        assert allowed is True
        assert reason is None
    
    def test_hourly_limit_exceeded_blocks_creation(self):
        """Test hourly limit prevents actor creation"""
        self.mock_redis.get.side_effect = [b'11', b'20', b'50']  # Exceeds hourly
        
        allowed, reason = self.limiter.can_create_actor('example.com', 'https://example.com/users/new')
        
        assert allowed is False
        assert 'hourly limit' in reason
    
    def test_daily_limit_exceeded_blocks_creation(self):
        """Test daily limit prevents actor creation"""
        self.mock_redis.get.side_effect = [b'5', b'51', b'50']  # Exceeds daily
        
        allowed, reason = self.limiter.can_create_actor('example.com', 'https://example.com/users/new')
        
        assert allowed is False
        assert 'daily limit' in reason
    
    def test_global_limit_protects_system(self):
        """Test global limit prevents system overload"""
        self.mock_redis.get.side_effect = [b'5', b'20', b'101']  # Exceeds global
        
        allowed, reason = self.limiter.can_create_actor('example.com', 'https://example.com/users/new')
        
        assert allowed is False
        assert 'temporarily unavailable' in reason
    
    def test_suspicious_instance_blocked(self):
        """Test suspicious instances are blocked"""
        self.mock_redis.get.side_effect = [b'5', b'20', b'50']
        self.mock_redis.exists.return_value = True  # Instance is blocked
        
        allowed, reason = self.limiter.can_create_actor('suspicious.com', 'https://suspicious.com/users/new')
        
        assert allowed is False
        assert 'temporarily blocked' in reason
    
    def test_duplicate_actor_prevented(self):
        """Test duplicate actors are not created"""
        self.mock_redis.get.side_effect = [b'5', b'20', b'50']
        self.mock_redis.exists.return_value = False
        
        with patch('app.security.actor_limits.User.query') as mock_query:
            mock_query.filter_by.return_value.first.return_value = Mock()  # Actor exists
            
            allowed, reason = self.limiter.can_create_actor('example.com', 'https://example.com/users/existing')
            
            assert allowed is False
            assert 'already exists' in reason
    
    def test_rate_limit_tracking(self):
        """Test rate limits are properly tracked"""
        self.limiter.record_actor_creation('example.com', 'https://example.com/users/new')
        
        # Verify Redis calls
        assert self.mock_redis.incr.call_count == 3  # hourly, daily, global
        assert self.mock_redis.expire.call_count == 3
        
        # Check TTLs
        expire_calls = self.mock_redis.expire.call_args_list
        ttls = [call[0][1] for call in expire_calls]
        assert 3600 in ttls  # 1 hour
        assert 86400 in ttls  # 24 hours


class TestRelayProtection:
    """Test vote amplification prevention"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_redis = Mock(spec=redis.Redis)
        self.protector = RelayProtection()
        self.protector.redis_client = self.mock_redis
        
        self.relay_actor = Mock()
        self.relay_actor.ap_profile_id = 'https://relay.example.com/actor'
        self.relay_actor.instance = Mock(software='activityrelay')
        
        self.normal_actor = Mock()
        self.normal_actor.ap_profile_id = 'https://example.com/users/alice'
        self.normal_actor.instance = Mock(software='mastodon')
    
    def test_relay_detection_by_software(self):
        """Test relay detection by software type"""
        assert self.protector.is_relay_actor(self.relay_actor) is True
        assert self.protector.is_relay_actor(self.normal_actor) is False
    
    def test_relay_detection_by_url_pattern(self):
        """Test relay detection by URL patterns"""
        relay_patterns = [
            'https://example.com/relay',
            'https://example.com/actor',
            'https://relay.social/inbox'
        ]
        
        for url in relay_patterns:
            actor = Mock()
            actor.ap_profile_id = url
            actor.instance = None
            assert self.protector.is_relay_actor(actor) is True
    
    def test_relay_cannot_amplify_votes(self):
        """Test relays cannot amplify vote activities"""
        announce = {
            'type': 'Announce',
            'actor': 'https://relay.example.com/actor',
            'object': {
                'type': 'Like',
                'actor': 'https://example.com/users/alice',
                'object': 'https://our-instance.com/posts/123'
            }
        }
        
        valid, reason = self.protector.validate_announced_activity(announce, self.relay_actor)
        
        assert valid is False
        assert 'cannot amplify votes' in reason
    
    def test_relay_cannot_amplify_moderation(self):
        """Test relays cannot amplify moderation activities"""
        announce = {
            'type': 'Announce',
            'actor': 'https://relay.example.com/actor',
            'object': {
                'type': 'Flag',
                'actor': 'https://example.com/users/mod',
                'object': 'https://bad-actor.com/users/spam'
            }
        }
        
        valid, reason = self.protector.validate_announced_activity(announce, self.relay_actor)
        
        assert valid is False
        assert 'cannot amplify moderation' in reason
    
    def test_announce_depth_limit(self):
        """Test deeply nested announces are rejected"""
        # Create deeply nested announce
        announce = {
            'type': 'Announce',
            'object': {
                'type': 'Announce',
                'object': {
                    'type': 'Announce',
                    'object': {
                        'type': 'Like',
                        'object': 'https://example.com/posts/1'
                    }
                }
            }
        }
        
        valid, reason = self.protector.validate_announced_activity(announce, self.normal_actor)
        
        assert valid is False
        assert 'depth exceeds limit' in reason
    
    def test_relay_rate_limiting(self):
        """Test relay announce rate limiting"""
        self.mock_redis.incr.return_value = 101  # Over limit
        
        announce = {
            'type': 'Announce',
            'object': 'https://example.com/posts/123'
        }
        
        valid, reason = self.protector._validate_relay_announce(announce, self.relay_actor)
        
        assert valid is False
        assert 'rate limit exceeded' in reason
    
    def test_vote_rate_limiting_per_actor(self):
        """Test vote rate limiting per original actor"""
        self.mock_redis.incr.return_value = 101  # Over limit
        
        vote = {
            'type': 'Like',
            'actor': 'https://example.com/users/alice',
            'object': 'https://our-instance.com/posts/123'
        }
        
        valid = self.protector._check_vote_rate('https://example.com/users/alice')
        assert valid is False


class TestMediaProxySecurity:
    """Test SSRF prevention in media proxy"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_app = Mock()
        self.mock_app.config = {
            'MEDIA_PROXY_SECRET': 'test-secret',
            'SERVER_NAME': 'our-instance.com'
        }
        
        with patch('app.security.media_proxy_security.current_app', self.mock_app):
            self.proxy = SecureMediaProxy()
    
    def test_valid_media_url_generates_proxy_url(self):
        """Test valid media URLs get proxy URLs"""
        media_url = 'https://example.com/image.jpg'
        
        with patch('time.time', return_value=1234567890):
            proxy_url = self.proxy.generate_proxy_url(media_url)
        
        assert proxy_url is not None
        assert '/proxy/media/' in proxy_url
        assert media_url in proxy_url
    
    def test_private_ip_media_rejected(self):
        """Test media from private IPs is rejected"""
        private_urls = [
            'http://192.168.1.1/image.jpg',
            'http://10.0.0.1/image.jpg',
            'http://localhost/image.jpg',
            'http://127.0.0.1/image.jpg'
        ]
        
        for url in private_urls:
            proxy_url = self.proxy.generate_proxy_url(url)
            assert proxy_url is None
    
    def test_signature_validation(self):
        """Test proxy URL signature validation"""
        media_url = 'https://example.com/image.jpg'
        
        # Generate valid signature
        timestamp = int(time.time())
        signature = self.proxy._generate_signature(media_url, timestamp)
        
        # Validate
        valid, error = self.proxy.validate_proxy_request(signature, str(timestamp), media_url)
        assert valid is True
        assert error is None
        
        # Test invalid signature
        valid, error = self.proxy.validate_proxy_request('invalid', str(timestamp), media_url)
        assert valid is False
        assert 'Invalid signature' in error
    
    def test_expired_proxy_url_rejected(self):
        """Test expired proxy URLs are rejected"""
        media_url = 'https://example.com/image.jpg'
        old_timestamp = int(time.time()) - 90000  # 25 hours ago
        signature = self.proxy._generate_signature(media_url, old_timestamp)
        
        valid, error = self.proxy.validate_proxy_request(signature, str(old_timestamp), media_url)
        
        assert valid is False
        assert 'Expired' in error
    
    def test_content_type_validation(self):
        """Test only allowed content types are proxied"""
        # This would be tested with actual HTTP requests
        # Here we just verify the allowed types are set
        assert 'image/jpeg' in self.proxy.ALLOWED_CONTENT_TYPES
        assert 'text/html' not in self.proxy.ALLOWED_CONTENT_TYPES
        assert 'application/javascript' not in self.proxy.ALLOWED_CONTENT_TYPES
    
    def test_ssrf_adapter_blocks_private_ips(self):
        """Test SSRFSafeAdapter blocks private IPs after redirect"""
        adapter = SSRFSafeAdapter()
        
        # Mock request to private IP
        mock_request = Mock()
        mock_request.url = 'http://evil.com/redirect'  # This would redirect to private IP
        
        with patch('socket.gethostbyname', return_value='192.168.1.1'):
            with pytest.raises(requests.exceptions.ConnectionError, match='private IP'):
                adapter.send(mock_request)


class TestPermissionValidation:
    """Test privilege escalation prevention"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.validator = PermissionValidator()
        
        self.admin = Mock()
        self.admin.id = 1
        self.admin.is_site_admin = True
        
        self.moderator = Mock()
        self.moderator.id = 2
        self.moderator.is_site_admin = False
        
        self.member = Mock()
        self.member.id = 3
        self.member.is_site_admin = False
        
        self.community = Mock()
        self.community.id = 1
    
    def test_admin_has_all_permissions(self):
        """Test site admin has all permissions"""
        permissions = self.validator.get_user_permissions(self.admin, self.community)
        assert len(permissions) == len(Permission)
    
    def test_member_cannot_moderate(self):
        """Test regular members cannot moderate"""
        with patch('app.security.permission_validator.CommunityMember.query') as mock_query:
            mock_membership = Mock()
            mock_membership.is_admin = False
            mock_membership.is_moderator = False
            mock_membership.is_banned = False
            mock_query.filter_by.return_value.first.return_value = mock_membership
            
            allowed, reason = self.validator.validate_action(
                self.member, 'Block', Mock(), self.community
            )
            
            assert allowed is False
            assert 'No permission' in reason
    
    def test_cannot_modify_others_content(self):
        """Test users cannot modify others' content"""
        post = Mock()
        post.author_id = 999  # Different user
        
        with patch('app.security.permission_validator.CommunityMember.query') as mock_query:
            mock_membership = Mock()
            mock_membership.is_moderator = False
            mock_query.filter_by.return_value.first.return_value = mock_membership
            
            allowed, reason = self.validator.validate_action(
                self.member, 'Update', post, self.community
            )
            
            assert allowed is False
            assert 'own content' in reason
    
    def test_group_activity_validation(self):
        """Test group activity attribution validation"""
        # Valid group activity
        group_activity = {
            'type': 'Create',
            'actor': 'https://example.com/c/community',
            'attributedTo': 'https://example.com/users/mod',
            'object': {'type': 'Note'}
        }
        
        actor = Mock()
        actor.ap_profile_id = 'https://example.com/users/mod'
        
        valid, reason = self.validator.validate_group_action(group_activity, actor)
        assert valid is True
        
        # Mismatched actor
        actor.ap_profile_id = 'https://example.com/users/different'
        valid, reason = self.validator.validate_group_action(group_activity, actor)
        assert valid is False
        assert 'Actor mismatch' in reason
    
    def test_cannot_remove_last_admin(self):
        """Test cannot remove last admin from community"""
        with patch('app.security.permission_validator.CommunityMember.query') as mock_query:
            # User is admin
            mock_membership = Mock()
            mock_membership.is_admin = True
            
            # Only 1 admin total
            mock_query.filter_by.return_value.first.return_value = mock_membership
            mock_query.filter_by.return_value.count.return_value = 1
            
            allowed, reason = self.validator._validate_remove_moderator(
                self.admin, self.admin, self.community
            )
            
            assert allowed is False
            assert 'last admin' in reason


class TestSecureErrorHandling:
    """Test information disclosure prevention"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_app = Mock()
        self.mock_app.config = {'DEBUG': False, 'LOG_ERRORS': True}
        
        with patch('app.security.error_handler.current_app', self.mock_app):
            self.handler = SecureErrorHandler()
    
    def test_database_errors_sanitized(self):
        """Test database information is not leaked"""
        errors = [
            Exception("Table 'users' doesn't exist"),
            Exception("Column 'password' not found"),
            Exception("postgres://user:pass@localhost/db connection failed"),
            Exception("Duplicate entry 'admin@example.com' for key 'email'")
        ]
        
        for error in errors:
            response, status = self.handler.handle_error(error)
            
            # Should not contain sensitive info
            assert 'users' not in response['error']
            assert 'password' not in response['error']
            assert 'postgres://' not in response['error']
            assert 'admin@example.com' not in response['error']
            assert response['error'] in self.handler.ERROR_MESSAGES.values()
    
    def test_file_paths_removed(self):
        """Test file paths are not exposed"""
        error = Exception("File not found: /home/user/app/config/secret.key")
        
        response, status = self.handler.handle_error(error)
        
        assert '/home/user' not in response['error']
        assert 'secret.key' not in response['error']
    
    def test_consistent_error_messages(self):
        """Test error messages are consistent"""
        # Different auth errors should return same message
        auth_errors = [
            Exception("Invalid password for user 'admin'"),
            Exception("User 'admin' not found"),
            Exception("Authentication token expired"),
            Exception("Invalid credentials")
        ]
        
        messages = []
        for error in auth_errors:
            response, _ = self.handler.handle_error(error, 401)
            messages.append(response['error'])
        
        # All should return same message
        assert len(set(messages)) == 1
        assert messages[0] == self.handler.ERROR_MESSAGES['authentication']
    
    def test_activitypub_errors_handled(self):
        """Test ActivityPub errors are properly handled"""
        ap_errors = [
            (Exception("Signature verification failed"), 401),
            (Exception("Actor not found"), 404),
            (Exception("No permission to update"), 403),
            (Exception("Rate limit exceeded"), 429)
        ]
        
        for error, expected_status in ap_errors:
            response, status = self.handler.handle_activitypub_error(error)
            assert status == expected_status
            assert 'error' in response
            # Should not leak details
            assert 'verification failed' not in response['error'].lower()
    
    def test_stack_trace_sanitization(self):
        """Test stack traces are sanitized in logs"""
        sensitive_trace = """
        File "/home/user/app/auth.py", line 42, in authenticate
            if password == 'super_secret_password':
        ValueError: Invalid password for user at 0x7f8b8c0d5f40
        """
        
        sanitized = self.handler._sanitize_output(sensitive_trace)
        
        assert '/home/user' not in sanitized
        assert 'super_secret_password' not in sanitized
        assert '0x7f8b8c0d5f40' not in sanitized
        assert '[REDACTED]' in sanitized


class TestIntegration:
    """Integration tests for HIGH vulnerability fixes"""
    
    def test_actor_creation_full_flow(self):
        """Test full actor creation flow with limits"""
        # Would test the actual integration with routes
        pass
    
    def test_relay_announce_processing(self):
        """Test processing announces from relays"""
        # Would test with actual ActivityPub processing
        pass
    
    def test_media_proxy_request_flow(self):
        """Test complete media proxy request flow"""
        # Would test with actual Flask request context
        pass
    
    def test_permission_checks_in_routes(self):
        """Test permission validation in actual routes"""
        # Would test with actual route handlers
        pass
    
    def test_error_handling_in_production(self):
        """Test error handling in production mode"""
        # Would test with production configuration
        pass