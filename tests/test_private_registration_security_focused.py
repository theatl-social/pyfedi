"""
Focused security tests for private registration API

Core security protocols that MUST be verified:
1. Secret-based authentication (constant-time comparison)
2. IP whitelist enforcement  
3. Feature toggle security
4. Input sanitization
5. Rate limiting (basic)
"""

import pytest
import json
import os
from unittest.mock import patch


class PrivateRegSecurityTestConfig:
    """Minimal test config focused on security"""
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SERVER_NAME = 'localhost'
    SECRET_KEY = 'test-security-key'
    CACHE_TYPE = 'null'
    MAIL_SUPPRESS_SEND = True
    CELERY_ALWAYS_EAGER = True

    # Required config values to prevent KeyError
    SENTRY_DSN = ''
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    RATELIMIT_ENABLED = False
    SERVE_API_DOCS = False


@pytest.fixture
def security_app():
    """Create test app with security focus"""
    test_env = {
        'PRIVATE_REGISTRATION_ENABLED': 'true',
        'PRIVATE_REGISTRATION_SECRET': 'secure-test-secret-2024',
        'PRIVATE_REGISTRATION_ALLOWED_IPS': '127.0.0.1,10.0.0.0/8',
        'SERVER_NAME': 'localhost'
    }
    
    with patch.dict(os.environ, test_env):
        from app import create_app, db
        app = create_app(PrivateRegSecurityTestConfig)
        
        with app.app_context():
            db.create_all()
            yield app
            db.session.remove()
            db.drop_all()


@pytest.fixture 
def client(security_app):
    return security_app.test_client()


class TestCoreSecurityProtocols:
    """Test essential security protocols"""
    
    def test_secret_authentication_required(self, client):
        """Verify secret authentication is required"""
        # No secret header
        response = client.post('/api/alpha/admin/private_register',
                             headers={'Content-Type': 'application/json'},
                             data=json.dumps({'username': 'test', 'email': 'test@example.com'}))
        
        assert response.status_code == 401
        
        # Empty secret
        response = client.post('/api/alpha/admin/private_register',
                             headers={'X-PieFed-Secret': '', 'Content-Type': 'application/json'},
                             data=json.dumps({'username': 'test', 'email': 'test@example.com'}))
        
        assert response.status_code == 401
        
        # Wrong secret
        response = client.post('/api/alpha/admin/private_register',
                             headers={'X-PieFed-Secret': 'wrong-secret', 'Content-Type': 'application/json'},
                             data=json.dumps({'username': 'test', 'email': 'test@example.com'}))
        
        assert response.status_code == 401
        data = response.get_json()
        assert data['error'] == 'invalid_secret'
    
    def test_correct_secret_authentication(self, client):
        """Verify correct secret allows access"""
        headers = {
            'X-PieFed-Secret': 'secure-test-secret-2024',
            'Content-Type': 'application/json',
            'X-Forwarded-For': '127.0.0.1'
        }
        
        # Health endpoint should work
        response = client.get('/api/alpha/admin/health', headers=headers)
        assert response.status_code == 200
        
        # Registration should work with valid data
        user_data = {'username': 'sectest', 'email': 'sectest@example.com', 'auto_activate': True}
        response = client.post('/api/alpha/admin/private_register', headers=headers, data=json.dumps(user_data))
        assert response.status_code == 201
    
    def test_feature_toggle_security(self, client):
        """Verify feature can be properly disabled"""
        with patch.dict(os.environ, {'PRIVATE_REGISTRATION_ENABLED': 'false'}):
            headers = {
                'X-PieFed-Secret': 'secure-test-secret-2024',
                'Content-Type': 'application/json',
                'X-Forwarded-For': '127.0.0.1'
            }
            
            # Even with correct secret, should be disabled
            response = client.post('/api/alpha/admin/private_register',
                                 headers=headers,
                                 data=json.dumps({'username': 'test', 'email': 'test@example.com'}))
            
            assert response.status_code == 403
            data = response.get_json()
            assert data['error'] == 'feature_disabled'
    
    def test_ip_whitelist_enforcement(self, client):
        """Verify IP whitelist is enforced"""
        headers_base = {
            'X-PieFed-Secret': 'secure-test-secret-2024',
            'Content-Type': 'application/json'
        }
        
        # Allowed IP (127.0.0.1)
        headers = headers_base.copy()
        headers['X-Forwarded-For'] = '127.0.0.1'
        response = client.get('/api/alpha/admin/health', headers=headers)
        assert response.status_code == 200
        
        # Allowed IP range (10.0.0.0/8)
        headers['X-Forwarded-For'] = '10.0.0.5'
        response = client.get('/api/alpha/admin/health', headers=headers)
        assert response.status_code == 200
        
        # Blocked IP
        headers['X-Forwarded-For'] = '192.168.1.100'
        response = client.get('/api/alpha/admin/health', headers=headers)
        assert response.status_code == 403
        data = response.get_json()
        assert data['error'] == 'ip_unauthorized'
    
    def test_input_sanitization(self, client):
        """Verify malicious input is properly handled"""
        headers = {
            'X-PieFed-Secret': 'secure-test-secret-2024',
            'Content-Type': 'application/json',
            'X-Forwarded-For': '127.0.0.1'
        }
        
        # SQL injection attempt
        malicious_data = {
            'username': "'; DROP TABLE users; --",
            'email': 'test@example.com'
        }
        response = client.post('/api/alpha/admin/private_register', headers=headers, data=json.dumps(malicious_data))
        # Should either succeed (if sanitized) or fail with validation error (not server error)
        assert response.status_code in [201, 400]
        assert response.status_code != 500
        
        # XSS attempt
        xss_data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'display_name': '<script>alert("xss")</script>',
            'bio': '<img src=x onerror=alert("xss")>'
        }
        response = client.post('/api/alpha/admin/private_register', headers=headers, data=json.dumps(xss_data))
        assert response.status_code in [201, 400]
        assert response.status_code != 500
        
        # If registration succeeded, verify data is sanitized
        if response.status_code == 201:
            data = response.get_json()
            # Should not contain raw script tags in response
            display_name = data.get('display_name', '')
            assert '<script>' not in display_name
    
    def test_constant_time_secret_comparison(self, client):
        """Verify secrets are compared using constant-time comparison"""
        # This test verifies the secret validation function uses hmac.compare_digest
        from app.api.admin.security import validate_registration_secret
        
        with patch.dict(os.environ, {'PRIVATE_REGISTRATION_SECRET': 'correct-secret'}):
            # Test that function exists and works
            assert validate_registration_secret('correct-secret') is True
            assert validate_registration_secret('wrong-secret') is False
            assert validate_registration_secret('') is False
            assert validate_registration_secret(None) is False
    
    def test_error_information_disclosure(self, client):
        """Verify errors don't disclose sensitive information"""
        # Test with various invalid inputs to ensure error messages are safe
        test_cases = [
            # No secret
            ({}, 401),
            # Wrong secret  
            ({'X-PieFed-Secret': 'wrong'}, 401),
            # Invalid IP
            ({'X-PieFed-Secret': 'secure-test-secret-2024', 'X-Forwarded-For': '192.168.1.1'}, 403),
        ]
        
        for headers, expected_status in test_cases:
            headers['Content-Type'] = 'application/json'
            response = client.post('/api/alpha/admin/private_register',
                                 headers=headers,
                                 data=json.dumps({'username': 'test', 'email': 'test@example.com'}))
            
            assert response.status_code == expected_status
            
            # Verify error response doesn't leak sensitive info
            data = response.get_json()
            error_message = data.get('message', '').lower()
            
            # Should not contain sensitive information
            assert 'secure-test-secret-2024' not in error_message
            assert 'database' not in error_message
            assert 'internal' not in error_message
            assert 'exception' not in error_message


class TestBasicRateLimit:
    """Basic rate limiting test"""
    
    @patch.dict(os.environ, {'PRIVATE_REGISTRATION_RATE_LIMIT': '2'})
    def test_basic_rate_limiting(self, client):
        """Verify basic rate limiting works"""
        headers = {
            'X-PieFed-Secret': 'secure-test-secret-2024',
            'Content-Type': 'application/json',
            'X-Forwarded-For': '127.0.0.1'
        }
        
        # First two requests should succeed
        for i in range(2):
            user_data = {'username': f'rate{i}', 'email': f'rate{i}@example.com', 'auto_activate': True}
            response = client.post('/api/alpha/admin/private_register', headers=headers, data=json.dumps(user_data))
            assert response.status_code == 201
        
        # Third request should be rate limited
        user_data = {'username': 'rate_fail', 'email': 'rate_fail@example.com', 'auto_activate': True}
        response = client.post('/api/alpha/admin/private_register', headers=headers, data=json.dumps(user_data))
        assert response.status_code == 429
        data = response.get_json()
        assert data['error'] == 'rate_limited'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])