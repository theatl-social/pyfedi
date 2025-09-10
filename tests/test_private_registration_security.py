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


class TestRateLimiting:
    """Test rate limiting functionality"""
    
    @patch.dict('os.environ', {
        'PRIVATE_REGISTRATION_RATE_LIMIT': '3',
        'PRIVATE_REGISTRATION_ENABLED': 'true',
        'PRIVATE_REGISTRATION_SECRET': 'test-rate-limit-secret'
    })
    def test_rate_limit_enforcement(self, test_app):
        """Test that rate limiting is properly enforced"""
        client = test_app.test_client()
        
        headers = {
            'X-PieFed-Secret': 'test-rate-limit-secret',
            'Content-Type': 'application/json',
            'X-Forwarded-For': '127.0.0.1'
        }
        
        # Make requests up to the limit (should succeed)
        for i in range(3):
            user_data = {
                'username': f'ratetest{i}',
                'email': f'ratetest{i}@example.com',
                'auto_activate': True
            }
            
            response = client.post(
                '/api/alpha/admin/private_register',
                headers=headers,
                data=json.dumps(user_data)
            )
            
            assert response.status_code == 201, f"Request {i+1} should succeed"
        
        # Next request should be rate limited
        user_data = {
            'username': 'ratetest_overflow',
            'email': 'ratetest_overflow@example.com',
            'auto_activate': True
        }
        
        response = client.post(
            '/api/alpha/admin/private_register',
            headers=headers,
            data=json.dumps(user_data)
        )
        
        assert response.status_code == 429
        data = response.get_json()
        assert data['success'] is False
        assert data['error'] == 'rate_limited'
    
    def test_rate_limit_per_ip(self, test_app):
        """Test that rate limiting is applied per IP address"""
        client = test_app.test_client()
        
        headers_ip1 = {
            'X-PieFed-Secret': 'test-rate-limit-secret',
            'Content-Type': 'application/json',
            'X-Forwarded-For': '127.0.0.1'
        }
        
        headers_ip2 = {
            'X-PieFed-Secret': 'test-rate-limit-secret', 
            'Content-Type': 'application/json',
            'X-Forwarded-For': '10.0.0.1'
        }
        
        # Use up rate limit for IP1
        for i in range(3):
            user_data = {
                'username': f'ip1test{i}',
                'email': f'ip1test{i}@example.com',
                'auto_activate': True
            }
            
            response = client.post(
                '/api/alpha/admin/private_register',
                headers=headers_ip1,
                data=json.dumps(user_data)
            )
            
            assert response.status_code == 201
        
        # IP1 should be rate limited
        response = client.post(
            '/api/alpha/admin/private_register',
            headers=headers_ip1,
            data=json.dumps({'username': 'ip1overflow', 'email': 'ip1overflow@example.com'})
        )
        assert response.status_code == 429
        
        # IP2 should still work
        response = client.post(
            '/api/alpha/admin/private_register',
            headers=headers_ip2,
            data=json.dumps({'username': 'ip2test', 'email': 'ip2test@example.com'})
        )
        assert response.status_code == 201


class TestIPSecurity:
    """Test IP whitelist security features"""
    
    @patch.dict('os.environ', {
        'PRIVATE_REGISTRATION_ALLOWED_IPS': '127.0.0.1,10.0.0.0/8',
        'PRIVATE_REGISTRATION_ENABLED': 'true', 
        'PRIVATE_REGISTRATION_SECRET': 'test-ip-security-secret'
    })
    def test_allowed_ip_ranges(self, test_app):
        """Test various IP ranges in whitelist"""
        client = test_app.test_client()
        
        # Test cases: (IP, should_succeed)
        test_cases = [
            ('127.0.0.1', True),        # Exact match
            ('10.0.0.1', True),         # In range  
            ('10.255.255.255', True),   # Edge of range
            ('192.168.1.1', False),     # Not in range
            ('172.16.0.1', False),      # Not in range  
            ('11.0.0.1', False),        # Outside range
        ]
        
        for test_ip, should_succeed in test_cases:
            headers = {
                'X-PieFed-Secret': 'test-ip-security-secret',
                'Content-Type': 'application/json',
                'X-Forwarded-For': test_ip
            }
            
            user_data = {
                'username': f'iptest_{test_ip.replace(".", "_")}',
                'email': f'iptest_{test_ip.replace(".", "_")}@example.com',
                'auto_activate': True
            }
            
            response = client.post(
                '/api/alpha/admin/private_register',
                headers=headers,
                data=json.dumps(user_data)
            )
            
            if should_succeed:
                assert response.status_code == 201, f"IP {test_ip} should be allowed"
            else:
                assert response.status_code == 403, f"IP {test_ip} should be blocked"
                data = response.get_json()
                assert data['error'] == 'ip_unauthorized'
    
    def test_x_forwarded_for_parsing(self, test_app):
        """Test proper parsing of X-Forwarded-For header with multiple IPs"""
        client = test_app.test_client()
        
        # Test with multiple forwarded IPs (should use first one)
        headers = {
            'X-PieFed-Secret': 'test-ip-security-secret',
            'Content-Type': 'application/json',
            'X-Forwarded-For': '127.0.0.1, 192.168.1.1, 10.0.0.1'  # First IP is allowed
        }
        
        user_data = {
            'username': 'forwarded_test',
            'email': 'forwarded_test@example.com',
            'auto_activate': True
        }
        
        response = client.post(
            '/api/alpha/admin/private_register',
            headers=headers,
            data=json.dumps(user_data)
        )
        
        # Should succeed because first IP (127.0.0.1) is allowed
        assert response.status_code == 201
    
    def test_no_ip_restrictions(self, test_app):
        """Test behavior when no IP restrictions are configured"""
        with patch.dict('os.environ', {
            'PRIVATE_REGISTRATION_ALLOWED_IPS': '',  # No restrictions
            'PRIVATE_REGISTRATION_ENABLED': 'true',
            'PRIVATE_REGISTRATION_SECRET': 'test-no-ip-secret'
        }):
            client = test_app.test_client()
            
            # Should allow any IP when no restrictions
            headers = {
                'X-PieFed-Secret': 'test-no-ip-secret',
                'Content-Type': 'application/json',
                'X-Forwarded-For': '192.168.1.100'  # Random IP
            }
            
            user_data = {
                'username': 'anyip_test',
                'email': 'anyip_test@example.com',
                'auto_activate': True
            }
            
            response = client.post(
                '/api/alpha/admin/private_register',
                headers=headers,
                data=json.dumps(user_data)
            )
            
            assert response.status_code == 201


class TestConcurrentRequests:
    """Test handling of concurrent requests"""
    
    def test_concurrent_registrations(self, test_app):
        """Test multiple concurrent registration requests"""
        client = test_app.test_client()
        
        headers = {
            'X-PieFed-Secret': 'test-concurrent-secret',
            'Content-Type': 'application/json',
            'X-Forwarded-For': '127.0.0.1'
        }
        
        def register_user(user_id):
            """Helper function to register a user"""
            user_data = {
                'username': f'concurrent_user_{user_id}',
                'email': f'concurrent_user_{user_id}@example.com',
                'auto_activate': True
            }
            
            response = client.post(
                '/api/alpha/admin/private_register',
                headers=headers,
                data=json.dumps(user_data)
            )
            
            return response.status_code, user_id
        
        # Start 5 concurrent registration requests
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(register_user, i) for i in range(5)]
            results = [future.result() for future in as_completed(futures)]
        
        # All should succeed (different usernames/emails)
        success_count = sum(1 for status, _ in results if status == 201)
        assert success_count == 5, f"Expected 5 successful registrations, got {success_count}"
    
    def test_concurrent_duplicate_registrations(self, test_app):
        """Test concurrent attempts to register the same user"""
        client = test_app.test_client()
        
        headers = {
            'X-PieFed-Secret': 'test-concurrent-dup-secret',
            'Content-Type': 'application/json',
            'X-Forwarded-For': '127.0.0.1'
        }
        
        # Same user data for all requests
        user_data = {
            'username': 'duplicate_concurrent',
            'email': 'duplicate_concurrent@example.com',
            'auto_activate': True
        }
        
        def register_duplicate():
            """Try to register the same user"""
            response = client.post(
                '/api/alpha/admin/private_register',
                headers=headers,
                data=json.dumps(user_data)
            )
            return response.status_code
        
        # Start 3 concurrent registration requests for same user
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(register_duplicate) for _ in range(3)]
            results = [future.result() for future in as_completed(futures)]
        
        # Only one should succeed (201), others should fail (400)
        success_count = sum(1 for status in results if status == 201)
        failure_count = sum(1 for status in results if status == 400)
        
        assert success_count == 1, f"Expected 1 successful registration, got {success_count}"
        assert failure_count == 2, f"Expected 2 failed registrations, got {failure_count}"


class TestAttackScenarios:
    """Test various attack scenarios"""
    
    def test_secret_brute_force_protection(self, test_app):
        """Test protection against secret brute force attempts"""
        client = test_app.test_client()
        
        headers_base = {
            'Content-Type': 'application/json',
            'X-Forwarded-For': '127.0.0.1'
        }
        
        user_data = {
            'username': 'brute_force_test',
            'email': 'brute_force_test@example.com',
            'auto_activate': True
        }
        
        # Try multiple wrong secrets rapidly
        wrong_secrets = ['wrong1', 'wrong2', 'wrong3', 'admin123', 'password']
        
        for secret in wrong_secrets:
            headers = headers_base.copy()
            headers['X-PieFed-Secret'] = secret
            
            response = client.post(
                '/api/alpha/admin/private_register',
                headers=headers,
                data=json.dumps(user_data)
            )
            
            # Should always return 401 for wrong secret
            assert response.status_code == 401
            data = response.get_json()
            assert data['error'] == 'invalid_secret'
    
    def test_large_payload_handling(self, test_app):
        """Test handling of unusually large payloads"""
        client = test_app.test_client()
        
        headers = {
            'X-PieFed-Secret': 'test-large-payload-secret',
            'Content-Type': 'application/json',
            'X-Forwarded-For': '127.0.0.1'
        }
        
        # Create large bio (beyond typical limits)
        large_bio = 'A' * 10000  # 10KB bio
        
        user_data = {
            'username': 'large_payload_test',
            'email': 'large_payload_test@example.com',
            'bio': large_bio,
            'auto_activate': True
        }
        
        response = client.post(
            '/api/alpha/admin/private_register',
            headers=headers,
            data=json.dumps(user_data)
        )
        
        # Should handle gracefully (either succeed or fail with validation error)
        assert response.status_code in [201, 400]
        
        if response.status_code == 400:
            data = response.get_json()
            assert data['error'] == 'validation_failed'
    
    def test_malicious_headers(self, test_app):
        """Test handling of malicious or malformed headers"""
        client = test_app.test_client()
        
        user_data = {
            'username': 'malicious_header_test',
            'email': 'malicious_header_test@example.com',
            'auto_activate': True
        }
        
        # Test various malicious header scenarios
        malicious_headers = [
            # SQL injection attempt in secret
            {'X-PieFed-Secret': "'; DROP TABLE users; --"},
            # XSS attempt in forwarded IP
            {'X-PieFed-Secret': 'test-secret', 'X-Forwarded-For': '<script>alert("xss")</script>'},
            # Very long secret
            {'X-PieFed-Secret': 'A' * 1000},
            # Binary data in secret
            {'X-PieFed-Secret': '\x00\x01\x02'},
        ]
        
        for malicious_header in malicious_headers:
            headers = {
                'Content-Type': 'application/json',
                'X-Forwarded-For': '127.0.0.1'  # Default safe IP
            }
            headers.update(malicious_header)
            
            response = client.post(
                '/api/alpha/admin/private_register',
                headers=headers,
                data=json.dumps(user_data)
            )
            
            # Should handle malicious headers gracefully
            assert response.status_code in [400, 401, 403]
            
            # Should not cause server errors
            assert response.status_code != 500