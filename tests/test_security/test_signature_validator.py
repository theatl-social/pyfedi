"""
Test cases for signature validation security
Tests protection against authentication bypass vulnerabilities
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from app.security.signature_validator import SignatureValidator, SecurityError
from app.activitypub.signature import VerificationError


class TestSignatureValidator:
    """Test signature validation security"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.validator = SignatureValidator()
        
        # Mock actor
        self.mock_actor = Mock()
        self.mock_actor.ap_profile_id = "https://example.com/users/alice"
        self.mock_actor.public_key = "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkq..."
        self.mock_actor.instance = Mock()
        self.mock_actor.instance.domain = "example.com"
        
        # Mock request
        self.mock_request = Mock()
        self.mock_request.headers = {}
        self.mock_request.get_json.return_value = {"type": "Like"}
        self.mock_request.user_agent.string = "Test/1.0"
        
    def test_unsigned_request_rejected_by_default(self):
        """Test unsigned requests are rejected when no signature present"""
        with patch('app.security.signature_validator.current_app') as mock_app:
            mock_app.config = {'ALLOW_UNSIGNED_ACTIVITIES': False}
            
            # No signature headers
            self.mock_request.headers = {}
            
            with pytest.raises(SecurityError, match="No valid signature found"):
                self.validator.verify_request(self.mock_request, self.mock_actor)
    
    def test_valid_http_signature_accepted(self):
        """Test valid HTTP signature is accepted"""
        self.mock_request.headers = {
            'Signature': 'keyId="...",algorithm="...",headers="...",signature="..."',
            'Date': datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
        }
        
        with patch('app.security.signature_validator.HttpSignature.verify_request') as mock_verify:
            mock_verify.return_value = None  # No exception means success
            
            verified, method = self.validator.verify_request(self.mock_request, self.mock_actor)
            
            assert verified is True
            assert method == 'http_signature'
            mock_verify.assert_called_once()
    
    def test_invalid_http_signature_rejected(self):
        """Test invalid HTTP signature is rejected"""
        self.mock_request.headers = {
            'Signature': 'keyId="...",algorithm="...",headers="...",signature="INVALID"'
        }
        
        with patch('app.security.signature_validator.HttpSignature.verify_request') as mock_verify:
            mock_verify.side_effect = VerificationError("Invalid signature")
            
            with pytest.raises(SecurityError, match="No valid signature found"):
                self.validator.verify_request(self.mock_request, self.mock_actor)
    
    def test_no_fallback_to_ld_signature_with_http_signature_present(self):
        """Test no fallback to LD signature when HTTP signature exists but fails"""
        self.mock_request.headers = {'Signature': 'invalid'}
        self.mock_request.get_json.return_value = {
            "type": "Like",
            "signature": {  # LD signature present
                "type": "RsaSignature2017",
                "creator": "https://example.com/users/alice#main-key",
                "created": "2023-01-01T00:00:00Z",
                "signatureValue": "..."
            }
        }
        
        with patch('app.security.signature_validator.HttpSignature.verify_request') as mock_http:
            mock_http.side_effect = VerificationError("Invalid HTTP sig")
            
            with patch('app.security.signature_validator.LDSignature.verify_signature') as mock_ld:
                # LD signature would be valid
                mock_ld.return_value = None
                
                # Should still fail - no fallback when HTTP sig present
                with pytest.raises(SecurityError):
                    self.validator.verify_request(self.mock_request, self.mock_actor)
                
                # LD signature should NOT be tried
                mock_ld.assert_not_called()
    
    def test_ld_signature_only_when_no_http_signature(self):
        """Test LD signature is used only when no HTTP signature present"""
        # No HTTP signature
        self.mock_request.headers = {}
        self.mock_request.get_json.return_value = {
            "type": "Like",
            "signature": {
                "type": "RsaSignature2017",
                "creator": "https://example.com/users/alice#main-key",
                "created": "2023-01-01T00:00:00Z",
                "signatureValue": "..."
            }
        }
        
        with patch('app.security.signature_validator.LDSignature.verify_signature') as mock_ld:
            mock_ld.return_value = None  # Success
            
            verified, method = self.validator.verify_request(self.mock_request, self.mock_actor)
            
            assert verified is True
            assert method == 'ld_signature'
            mock_ld.assert_called_once()
    
    def test_stale_date_header_rejected(self):
        """Test requests with old date headers are rejected (replay attack protection)"""
        # Set date header to 1 hour ago
        old_date = (datetime.utcnow() - timedelta(hours=1)).strftime('%a, %d %b %Y %H:%M:%S GMT')
        self.mock_request.headers = {
            'Signature': 'keyId="...",headers="date",...',
            'Date': old_date
        }
        
        # Even with valid signature, should fail due to old date
        with patch('app.security.signature_validator.HttpSignature.verify_request'):
            with pytest.raises(SecurityError):
                self.validator.verify_request(self.mock_request, self.mock_actor)
    
    def test_future_date_header_rejected(self):
        """Test requests with future date headers are rejected"""
        # Set date header to 1 hour in future
        future_date = (datetime.utcnow() + timedelta(hours=1)).strftime('%a, %d %b %Y %H:%M:%S GMT')
        self.mock_request.headers = {
            'Signature': 'keyId="...",headers="date",...',
            'Date': future_date
        }
        
        with patch('app.security.signature_validator.HttpSignature.verify_request'):
            with pytest.raises(SecurityError):
                self.validator.verify_request(self.mock_request, self.mock_actor)
    
    def test_allowlist_not_checked_by_default(self):
        """Test allowlist is not consulted when ALLOW_UNSIGNED_ACTIVITIES is False"""
        with patch('app.security.signature_validator.current_app') as mock_app:
            mock_app.config = {'ALLOW_UNSIGNED_ACTIVITIES': False}
            
            # Add actor to allowlist
            self.validator.UNSIGNED_ALLOWLIST[self.mock_actor.ap_profile_id] = {
                'allowed_types': ['Like'],
                'reason': 'Test'
            }
            
            # Should still fail
            with pytest.raises(SecurityError):
                self.validator.verify_request(self.mock_request, self.mock_actor)
    
    def test_allowlist_requires_exact_match(self):
        """Test allowlist requires exact actor and type match"""
        with patch('app.security.signature_validator.current_app') as mock_app:
            mock_app.config = {'ALLOW_UNSIGNED_ACTIVITIES': True}
            
            # Allow only Create activities from this actor
            self.validator.UNSIGNED_ALLOWLIST[self.mock_actor.ap_profile_id] = {
                'allowed_types': ['Create'],
                'reason': 'Test'
            }
            
            # But request is Like activity
            self.mock_request.get_json.return_value = {"type": "Like"}
            
            # Should fail - wrong activity type
            with pytest.raises(SecurityError):
                self.validator.verify_request(self.mock_request, self.mock_actor)
    
    def test_instance_failure_tracking(self):
        """Test signature failures are tracked per instance"""
        with patch('app.security.signature_validator.redis_client') as mock_redis:
            mock_redis.incr.return_value = 1
            
            self.mock_request.headers = {'Signature': 'invalid'}
            
            with patch('app.security.signature_validator.HttpSignature.verify_request') as mock_verify:
                mock_verify.side_effect = VerificationError("Bad sig")
                
                try:
                    self.validator.verify_request(self.mock_request, self.mock_actor)
                except SecurityError:
                    pass
                
                # Should track failure
                mock_redis.incr.assert_called_with('sig_failures:example.com')
                mock_redis.expire.assert_called_with('sig_failures:example.com', 3600)
    
    def test_excessive_failures_logged(self):
        """Test excessive signature failures trigger security alert"""
        with patch('app.security.signature_validator.redis_client') as mock_redis:
            # 101st failure
            mock_redis.incr.return_value = 101
            mock_redis.get.return_value = b'101'
            
            self.mock_request.headers = {'Signature': 'invalid'}
            
            with patch('app.security.signature_validator.HttpSignature.verify_request') as mock_verify:
                mock_verify.side_effect = VerificationError("Bad sig")
                
                with patch.object(self.validator, '_log_security_alert') as mock_alert:
                    try:
                        self.validator.verify_request(self.mock_request, self.mock_actor)
                    except SecurityError:
                        pass
                    
                    # Should log excessive failures
                    mock_alert.assert_any_call('INSTANCE_AUTO_BLOCKED', self.mock_actor, 
                                             'Too many signature failures from example.com')
    
    def test_ld_signature_validation_checks_fields(self):
        """Test LD signature validation checks required fields"""
        self.mock_request.headers = {}
        
        # Missing required fields
        invalid_signatures = [
            {},  # Empty
            {"type": "RsaSignature2017"},  # Missing other fields
            {"type": "InvalidType", "creator": "x", "created": "x", "signatureValue": "x"},  # Bad type
            {"creator": "x", "created": "x", "signatureValue": "x"},  # Missing type
        ]
        
        for bad_sig in invalid_signatures:
            self.mock_request.get_json.return_value = {
                "type": "Like",
                "signature": bad_sig
            }
            
            with pytest.raises(SecurityError):
                self.validator.verify_request(self.mock_request, self.mock_actor)
    
    def test_request_caching(self):
        """Test signature verification results are cached per request"""
        self.mock_request.headers = {
            'Signature': 'keyId="...",algorithm="...",signature="..."'
        }
        
        with patch('app.security.signature_validator.HttpSignature.verify_request') as mock_verify:
            mock_verify.return_value = None
            
            # First call
            result1 = self.validator.verify_request(self.mock_request, self.mock_actor)
            
            # Second call with same signature
            result2 = self.validator.verify_request(self.mock_request, self.mock_actor)
            
            # Should use cache, only verify once
            assert mock_verify.call_count == 1
            assert result1 == result2


class TestAuthenticationBypassScenarios:
    """Test specific authentication bypass scenarios from the vulnerability"""
    
    def setup_method(self):
        self.validator = SignatureValidator()
        
        self.mock_actor = Mock()
        self.mock_actor.ap_profile_id = "https://attacker.com/users/evil"
        self.mock_actor.public_key = "fake-key"
        self.mock_actor.instance = None
        
        self.mock_request = Mock()
        self.mock_request.headers = {}
        self.mock_request.user_agent.string = "Evil/1.0"
    
    def test_cannot_bypass_with_create_string_object(self):
        """Test the specific bypass vulnerability is fixed"""
        # The vulnerable code accepted Create with string object without verification
        self.mock_request.get_json.return_value = {
            "type": "Create",
            "actor": "https://attacker.com/users/evil",
            "object": "https://victim.com/posts/123"  # String object
        }
        
        # Should not be accepted without signature
        with pytest.raises(SecurityError):
            self.validator.verify_request(self.mock_request, self.mock_actor)
    
    def test_cannot_bypass_with_invalid_ld_signature(self):
        """Test invalid LD signatures are properly rejected"""
        self.mock_request.get_json.return_value = {
            "type": "Like",
            "actor": "https://attacker.com/users/evil",
            "object": "https://victim.com/posts/123",
            "signature": {
                "type": "RsaSignature2017",
                "creator": "https://different-actor.com/users/other#main-key",  # Wrong creator!
                "created": "2023-01-01T00:00:00Z",
                "signatureValue": "fake-signature"
            }
        }
        
        with patch('app.security.signature_validator.LDSignature.verify_signature') as mock_ld:
            mock_ld.side_effect = VerificationError("Invalid signature")
            
            with pytest.raises(SecurityError):
                self.validator.verify_request(self.mock_request, self.mock_actor)
    
    def test_cannot_spoof_signature_header(self):
        """Test spoofed signature headers are rejected"""
        # Attacker tries to spoof signature from different actor
        self.mock_request.headers = {
            'Signature': 'keyId="https://legitimate.com/users/alice#main-key",signature="fake"'
        }
        
        with patch('app.security.signature_validator.HttpSignature.verify_request') as mock_verify:
            # Signature verification would fail with attacker's key
            mock_verify.side_effect = VerificationError("Key mismatch")
            
            with pytest.raises(SecurityError):
                self.validator.verify_request(self.mock_request, self.mock_actor)
    
    def test_no_unsigned_activities_without_explicit_config(self):
        """Test unsigned activities are never accepted without explicit configuration"""
        test_activities = [
            {"type": "Create", "object": {"type": "Note"}},
            {"type": "Update", "object": {"type": "Person"}},
            {"type": "Delete", "object": "https://example.com/notes/1"},
            {"type": "Like", "object": "https://example.com/posts/1"},
            {"type": "Announce", "object": "https://example.com/posts/1"}
        ]
        
        for activity in test_activities:
            activity["actor"] = self.mock_actor.ap_profile_id
            self.mock_request.get_json.return_value = activity
            
            with pytest.raises(SecurityError):
                self.validator.verify_request(self.mock_request, self.mock_actor)