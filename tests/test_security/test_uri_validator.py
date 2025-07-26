"""
Test cases for URI validation security
Tests protection against SSRF and other URI-based attacks
"""
import pytest
from unittest.mock import Mock, patch
import ipaddress
from app.security.uri_validator import URIValidator, validate_uri


class TestURIValidator:
    """Test URI validation security"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_app = Mock()
        self.mock_app.config = {
            'URI_ALLOWED_SCHEMES': {'http', 'https'},
            'URI_BLOCKED_PORTS': {22, 23, 25, 445, 3389},
            'MAX_URI_LENGTH': 2048,
            'URI_BLOCKED_HOSTS': set()
        }
        
        with patch('app.security.uri_validator.current_app', self.mock_app):
            self.validator = URIValidator()
    
    def test_valid_https_uri_accepted(self):
        """Test valid HTTPS URIs are accepted"""
        valid_uris = [
            "https://example.com/users/alice",
            "https://mastodon.social/@user",
            "https://lemmy.ml/c/technology",
            "https://sub.domain.example.com:8443/path?query=1#fragment"
        ]
        
        for uri in valid_uris:
            result = self.validator.validate(uri)
            assert result == uri
    
    def test_empty_uri_rejected(self):
        """Test empty URI is rejected"""
        with pytest.raises(ValueError, match="Empty URI"):
            self.validator.validate("")
        
        with pytest.raises(ValueError, match="Empty URI"):
            self.validator.validate(None)
    
    def test_oversized_uri_rejected(self):
        """Test oversized URIs are rejected"""
        long_uri = "https://example.com/" + "x" * 3000
        
        with pytest.raises(ValueError, match="URI too long"):
            self.validator.validate(long_uri)
    
    def test_dangerous_schemes_rejected(self):
        """Test dangerous URI schemes are rejected"""
        dangerous_uris = [
            "file:///etc/passwd",
            "file://C:/Windows/System32/config/sam",
            "ftp://example.com/file",
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "vbscript:msgbox('XSS')",
            "about:blank",
            "gopher://example.com",
            "ssh://root@example.com",
            "telnet://example.com",
            "ldap://example.com/cn=admin",
            "dict://example.com/",
            "tftp://example.com/boot",
            "sftp://example.com/"
        ]
        
        for uri in dangerous_uris:
            with pytest.raises(ValueError, match="Disallowed URI scheme"):
                self.validator.validate(uri)
    
    def test_missing_scheme_rejected(self):
        """Test URIs without scheme are rejected"""
        with pytest.raises(ValueError, match="URI missing scheme"):
            self.validator.validate("example.com/path")
        
        with pytest.raises(ValueError, match="URI missing scheme"):
            self.validator.validate("//example.com/path")
    
    def test_missing_hostname_rejected(self):
        """Test URIs without hostname are rejected"""
        with pytest.raises(ValueError, match="URI missing hostname"):
            self.validator.validate("https://")
        
        with pytest.raises(ValueError, match="URI missing hostname"):
            self.validator.validate("https:///path")
    
    def test_localhost_variants_rejected(self):
        """Test localhost and variants are rejected"""
        localhost_variants = [
            "http://localhost/admin",
            "http://LOCALHOST/admin",  # Case variations
            "http://127.0.0.1/internal",
            "http://127.0.0.2/internal",  # Any 127.x.x.x
            "http://127.255.255.255/",
            "http://0.0.0.0/",
            "http://[::1]/",  # IPv6 localhost
            "http://[0000:0000:0000:0000:0000:0000:0000:0001]/",  # Full IPv6
        ]
        
        for uri in localhost_variants:
            with pytest.raises(ValueError, match="Blocked hostname|Private IP"):
                self.validator.validate(uri)
    
    def test_private_ip_ranges_rejected(self):
        """Test private IP ranges are rejected"""
        private_ips = [
            # RFC 1918 private ranges
            "http://10.0.0.1/",
            "http://10.255.255.255/",
            "http://172.16.0.1/",
            "http://172.31.255.255/",
            "http://192.168.0.1/",
            "http://192.168.255.255/",
            # Link-local
            "http://169.254.0.1/",
            "http://169.254.255.255/",
            # IPv6 private
            "http://[fc00::1]/",
            "http://[fdff:ffff:ffff:ffff:ffff:ffff:ffff:ffff]/",
            "http://[fe80::1]/",  # Link-local
        ]
        
        for uri in private_ips:
            with pytest.raises(ValueError, match="Private IP address not allowed"):
                self.validator.validate(uri)
    
    def test_blocked_ports_rejected(self):
        """Test blocked ports are rejected"""
        blocked_port_uris = [
            "http://example.com:21/",    # FTP
            "http://example.com:22/",    # SSH  
            "http://example.com:23/",    # Telnet
            "http://example.com:25/",    # SMTP
            "http://example.com:445/",   # SMB
            "http://example.com:3389/",  # RDP
            "http://example.com:6379/",  # Redis
            "http://example.com:11211/", # Memcached
        ]
        
        for uri in blocked_port_uris:
            with pytest.raises(ValueError, match="Blocked port"):
                self.validator.validate(uri)
    
    def test_dns_rebinding_protection(self):
        """Test protection against DNS rebinding attacks"""
        # Mock DNS resolution to return private IP
        def mock_getaddrinfo(host, port):
            if host == "evil.example.com":
                # Resolves to private IP
                return [(None, None, None, None, ('192.168.1.1', 0))]
            return [(None, None, None, None, ('93.184.216.34', 0))]  # Public IP
        
        with patch('socket.getaddrinfo', mock_getaddrinfo):
            # Should reject domain that resolves to private IP
            with pytest.raises(ValueError, match="resolves to private IP"):
                self.validator.validate("https://evil.example.com/")
            
            # Should accept domain that resolves to public IP
            result = self.validator.validate("https://good.example.com/")
            assert result == "https://good.example.com/"
    
    def test_suspicious_patterns_rejected(self):
        """Test URIs with suspicious patterns are rejected"""
        suspicious_uris = [
            "https://example.com/path%00",  # Null byte
            "https://example.com/../etc/passwd",  # Directory traversal
            "https://example.com/..%2f..%2fetc%2fpasswd",  # Encoded traversal
            "https://example.com/%2e%2e%2f%2e%2e%2f",  # Encoded dots
            "https://example.com/%252e%252e%252f",  # Double encoded
            "https://example.com/path\r\nSet-Cookie: evil=1",  # CRLF injection
            "https://example.com/path%0d%0aSet-Cookie:%20evil=1",  # Encoded CRLF
        ]
        
        for uri in suspicious_uris:
            with pytest.raises(ValueError, match="suspicious pattern"):
                self.validator.validate(uri)
    
    def test_hostname_validation(self):
        """Test hostname validation rules"""
        # Valid hostnames
        valid_hostnames = [
            "https://example.com/",
            "https://sub.example.com/",
            "https://deeply.nested.sub.example.com/",
            "https://example-with-dash.com/",
            "https://123.example.com/",  # Can start with number
            "https://example123.com/",
        ]
        
        for uri in valid_hostnames:
            result = self.validator.validate(uri)
            assert result == uri
        
        # Invalid hostnames
        invalid_hostnames = [
            "https://-example.com/",  # Starts with dash
            "https://example-.com/",  # Ends with dash
            "https://exam ple.com/",  # Space in hostname
            "https://example..com/",  # Double dot
            "https://.example.com/",  # Starts with dot
            "https://example.com./",  # Ends with dot (technically valid but suspicious)
        ]
        
        for uri in invalid_hostnames:
            with pytest.raises(ValueError):
                self.validator.validate(uri)
    
    def test_activitypub_context_validation(self):
        """Test ActivityPub-specific URI validation"""
        with patch('app.security.uri_validator.current_app') as mock_app:
            mock_app.config = {
                'URI_ALLOWED_SCHEMES': {'https'},
                'URI_BLOCKED_PORTS': set(),
                'MAX_URI_LENGTH': 2048,
                'URI_BLOCKED_HOSTS': set(),
                'REQUIRE_HTTPS_ACTIVITYPUB': True
            }
            
            validator = URIValidator()
            
            # HTTP not allowed for ActivityPub
            with pytest.raises(ValueError, match="ActivityPub URIs must use HTTPS"):
                validator.validate("http://example.com/users/alice", context='activitypub')
            
            # HTTPS is fine
            result = validator.validate("https://example.com/users/alice", context='activitypub')
            assert result == "https://example.com/users/alice"
            
            # Internal paths rejected
            with pytest.raises(ValueError, match="Internal path not allowed"):
                validator.validate("https://example.com/admin/users", context='activitypub')
    
    def test_uri_normalization(self):
        """Test URI normalization"""
        # Test cases: (input, expected)
        test_cases = [
            ("https://EXAMPLE.COM/Path", "https://example.com/Path"),
            ("https://example.com:443/path", "https://example.com/path"),  # Default port removed
            ("http://example.com:80/path", "http://example.com/path"),  # Default port removed
            ("https://example.com:8443/path", "https://example.com:8443/path"),  # Non-default kept
            ("https://example.com/path?query=1", "https://example.com/path?query=1"),
            ("https://example.com/path#fragment", "https://example.com/path#fragment"),
        ]
        
        for input_uri, expected in test_cases:
            normalized = self.validator.normalize_uri(input_uri)
            assert normalized == expected
    
    def test_same_origin_check(self):
        """Test same origin validation"""
        origin = "https://example.com"
        
        # Same origin
        assert self.validator.is_same_origin(origin, "https://example.com/path")
        assert self.validator.is_same_origin(origin, "https://example.com:443/path")
        
        # Different origin
        assert not self.validator.is_same_origin(origin, "http://example.com/path")  # Different scheme
        assert not self.validator.is_same_origin(origin, "https://other.com/path")  # Different host
        assert not self.validator.is_same_origin(origin, "https://example.com:8443/path")  # Different port
        assert not self.validator.is_same_origin(origin, "https://sub.example.com/path")  # Different subdomain
    
    def test_batch_validation(self):
        """Test batch URI validation"""
        uris = [
            "https://valid.com/",
            "file:///etc/passwd",  # Invalid
            "https://another-valid.com/",
            "http://192.168.1.1/",  # Invalid
            "https://third-valid.com/"
        ]
        
        results = self.validator.validate_batch(uris)
        
        assert results[0] == ("https://valid.com/", None)
        assert results[1][0] == "file:///etc/passwd"
        assert "Disallowed URI scheme" in results[1][1]
        assert results[2] == ("https://another-valid.com/", None)
        assert results[3][0] == "http://192.168.1.1/"
        assert "Private IP" in results[3][1]
        assert results[4] == ("https://third-valid.com/", None)


class TestSSRFAttackVectors:
    """Test specific SSRF attack vectors"""
    
    def setup_method(self):
        self.mock_app = Mock()
        self.mock_app.config = {
            'URI_ALLOWED_SCHEMES': {'http', 'https'},
            'URI_BLOCKED_PORTS': {22, 6379, 11211},
            'MAX_URI_LENGTH': 2048,
            'URI_BLOCKED_HOSTS': set()
        }
    
    def test_cloud_metadata_endpoints_blocked(self):
        """Test cloud metadata endpoints are blocked"""
        with patch('app.security.uri_validator.current_app', self.mock_app):
            validator = URIValidator()
            
            # AWS metadata
            with pytest.raises(ValueError, match="Private IP"):
                validator.validate("http://169.254.169.254/latest/meta-data/")
            
            # Google Cloud metadata
            with pytest.raises(ValueError, match="Blocked hostname"):
                validator.validate("http://metadata.google.internal/")
            
            # Azure metadata
            with pytest.raises(ValueError, match="Private IP"):
                validator.validate("http://169.254.169.254/metadata/instance")
    
    def test_bypass_attempts_blocked(self):
        """Test various SSRF bypass attempts are blocked"""
        with patch('app.security.uri_validator.current_app', self.mock_app):
            validator = URIValidator()
            
            bypass_attempts = [
                # Decimal IP
                "http://2130706433/",  # 127.0.0.1 in decimal
                # Hex IP  
                "http://0x7f000001/",  # 127.0.0.1 in hex
                # Octal IP
                "http://0177.0.0.01/",  # 127.0.0.1 in octal
                # Mixed encoding
                "http://127.0.0.1:6379/",  # Redis port
                # URL encoding
                "http://127.0.0.1%2f/",
                # Unicode tricks
                "https://example.com@127.0.0.1/",  # @ trick
                "https://127.0.0.1#@example.com/",  # Fragment trick
            ]
            
            for uri in bypass_attempts:
                with pytest.raises(ValueError):
                    validator.validate(uri)
    
    def test_redirect_chains_not_followed(self):
        """Test validator doesn't follow redirects (prevents SSRF via redirect)"""
        with patch('app.security.uri_validator.current_app', self.mock_app):
            validator = URIValidator()
            
            # Validator should only validate the initial URI, not follow redirects
            # This URI might redirect to internal resources
            result = validator.validate("https://bit.ly/shortened")
            assert result == "https://bit.ly/shortened"  # Validates only the provided URI