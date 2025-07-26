"""
URI validation to prevent SSRF and other URI-based attacks
"""
import ipaddress
import re
from typing import Optional, List, Set
from urllib.parse import urlparse, urljoin
from flask import current_app
import socket
import logging


class URIValidator:
    """
    Validate URIs to prevent:
    - SSRF (Server-Side Request Forgery)
    - Local file access
    - Private network access
    - Malicious redirects
    """
    
    # Allowed schemes for ActivityPub
    ALLOWED_SCHEMES = {'http', 'https'}
    
    # Blocked schemes that could be dangerous
    BLOCKED_SCHEMES = {
        'file', 'ftp', 'ftps', 'gopher', 'javascript', 
        'data', 'vbscript', 'about', 'ssh', 'telnet',
        'ldap', 'ldaps', 'dict', 'tftp', 'sftp'
    }
    
    # Commonly blocked ports
    BLOCKED_PORTS = {
        21,    # FTP
        22,    # SSH
        23,    # Telnet
        25,    # SMTP
        110,   # POP3
        135,   # Windows RPC
        139,   # NetBIOS
        445,   # SMB
        1433,  # MSSQL
        1521,  # Oracle
        3306,  # MySQL
        3389,  # RDP
        5432,  # PostgreSQL
        5900,  # VNC
        6379,  # Redis
        8020,  # Hadoop
        9200,  # Elasticsearch
        11211, # Memcached
        27017, # MongoDB
    }
    
    # Private IP ranges (RFC 1918 and others)
    PRIVATE_IP_RANGES = [
        ipaddress.ip_network('10.0.0.0/8'),
        ipaddress.ip_network('172.16.0.0/12'),
        ipaddress.ip_network('192.168.0.0/16'),
        ipaddress.ip_network('127.0.0.0/8'),      # Loopback
        ipaddress.ip_network('169.254.0.0/16'),   # Link-local
        ipaddress.ip_network('fc00::/7'),         # IPv6 private
        ipaddress.ip_network('::1/128'),          # IPv6 loopback
        ipaddress.ip_network('fe80::/10'),        # IPv6 link-local
    ]
    
    # Maximum URI length
    MAX_URI_LENGTH = 2048
    
    # Suspicious patterns in URIs
    SUSPICIOUS_PATTERNS = [
        re.compile(r'%00'),                       # Null byte
        re.compile(r'\.\.'),                      # Directory traversal
        re.compile(r'%2e%2e', re.IGNORECASE),    # Encoded directory traversal
        re.compile(r'%252e%252e', re.IGNORECASE), # Double encoded
        re.compile(r'[\r\n]'),                    # CRLF injection
        re.compile(r'%0[da]', re.IGNORECASE),    # Encoded CRLF
    ]
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._dns_cache = {}  # Cache DNS lookups
        self._load_config()
    
    def _load_config(self):
        """Load configuration from Flask app"""
        # Allow customization via config
        self.allowed_schemes = set(current_app.config.get('URI_ALLOWED_SCHEMES', self.ALLOWED_SCHEMES))
        self.blocked_ports = set(current_app.config.get('URI_BLOCKED_PORTS', self.BLOCKED_PORTS))
        self.max_uri_length = current_app.config.get('MAX_URI_LENGTH', self.MAX_URI_LENGTH)
        
        # Additional blocked hosts from config
        self.blocked_hosts = set(current_app.config.get('URI_BLOCKED_HOSTS', []))
        self.blocked_hosts.update(['localhost', '0.0.0.0', '::1'])
    
    def validate(self, uri: str, context: str = 'general') -> str:
        """
        Validate a URI for safety
        
        Args:
            uri: The URI to validate
            context: Context for validation (e.g., 'activitypub', 'media', 'redirect')
            
        Returns:
            Normalized safe URI
            
        Raises:
            ValueError: If URI is invalid or unsafe
        """
        if not uri:
            raise ValueError("Empty URI")
        
        # Length check
        if len(uri) > self.max_uri_length:
            raise ValueError(f"URI too long: {len(uri)} > {self.max_uri_length}")
        
        # Check for suspicious patterns
        for pattern in self.SUSPICIOUS_PATTERNS:
            if pattern.search(uri):
                raise ValueError(f"URI contains suspicious pattern")
        
        # Parse URI
        try:
            parsed = urlparse(uri)
        except Exception as e:
            raise ValueError(f"Invalid URI format: {e}")
        
        # Scheme validation
        if not parsed.scheme:
            raise ValueError("URI missing scheme")
        
        if parsed.scheme.lower() not in self.allowed_schemes:
            raise ValueError(f"Disallowed URI scheme: {parsed.scheme}")
        
        # Host validation
        if not parsed.hostname:
            raise ValueError("URI missing hostname")
        
        # Normalize and validate hostname
        hostname = parsed.hostname.lower()
        
        # Check blocked hosts
        if hostname in self.blocked_hosts:
            raise ValueError(f"Blocked hostname: {hostname}")
        
        # Port validation
        port = parsed.port
        if port is None:
            port = 443 if parsed.scheme == 'https' else 80
        
        if port in self.blocked_ports:
            raise ValueError(f"Blocked port: {port}")
        
        # Check for IP address
        try:
            ip = ipaddress.ip_address(hostname)
            # It's an IP address, validate it
            if self._is_private_ip(ip):
                raise ValueError(f"Private IP address not allowed: {ip}")
        except ValueError:
            # Not an IP, it's a hostname - resolve and check
            if not self._validate_hostname(hostname):
                raise ValueError(f"Invalid hostname: {hostname}")
            
            # DNS resolution check (with caching)
            resolved_ips = self._resolve_hostname(hostname)
            for ip in resolved_ips:
                if self._is_private_ip(ip):
                    raise ValueError(f"Hostname resolves to private IP: {hostname} -> {ip}")
        
        # Context-specific validation
        if context == 'activitypub':
            self._validate_activitypub_uri(parsed)
        elif context == 'media':
            self._validate_media_uri(parsed)
        elif context == 'redirect':
            self._validate_redirect_uri(parsed)
        
        # Return normalized URI
        return uri
    
    def _is_private_ip(self, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        """Check if IP is in private range"""
        for private_range in self.PRIVATE_IP_RANGES:
            if ip in private_range:
                return True
        return False
    
    def _validate_hostname(self, hostname: str) -> bool:
        """Validate hostname format"""
        # Basic hostname validation
        if len(hostname) > 253:
            return False
        
        # Check each label
        labels = hostname.split('.')
        for label in labels:
            if not label or len(label) > 63:
                return False
            if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$', label):
                return False
        
        return True
    
    def _resolve_hostname(self, hostname: str) -> List[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        """Resolve hostname to IP addresses with caching"""
        # Check cache
        if hostname in self._dns_cache:
            return self._dns_cache[hostname]
        
        try:
            # Resolve hostname
            addr_info = socket.getaddrinfo(hostname, None)
            ips = []
            
            for family, _, _, _, sockaddr in addr_info:
                ip_str = sockaddr[0]
                try:
                    ip = ipaddress.ip_address(ip_str)
                    if ip not in ips:
                        ips.append(ip)
                except ValueError:
                    continue
            
            # Cache result (with TTL)
            self._dns_cache[hostname] = ips
            # TODO: Implement cache expiry
            
            return ips
            
        except socket.gaierror:
            self.logger.warning(f"Failed to resolve hostname: {hostname}")
            return []
    
    def _validate_activitypub_uri(self, parsed):
        """Additional validation for ActivityPub URIs"""
        # ActivityPub URIs should use HTTPS in production
        if current_app.config.get('REQUIRE_HTTPS_ACTIVITYPUB', True):
            if parsed.scheme != 'https':
                raise ValueError("ActivityPub URIs must use HTTPS")
        
        # Check for common ActivityPub paths
        path = parsed.path
        if path:
            # Disallow certain paths that might be internal
            internal_paths = ['/admin', '/api/internal', '/.well-known/security.txt']
            for internal_path in internal_paths:
                if path.startswith(internal_path):
                    raise ValueError(f"Internal path not allowed: {path}")
    
    def _validate_media_uri(self, parsed):
        """Additional validation for media URIs"""
        # Media URIs might have different rules
        # For example, could check file extensions
        pass
    
    def _validate_redirect_uri(self, parsed):
        """Additional validation for redirect URIs"""
        # Prevent open redirects
        # Only allow redirects to same origin or allowlisted domains
        pass
    
    def normalize_uri(self, uri: str) -> str:
        """Normalize a URI for consistent comparison"""
        try:
            parsed = urlparse(uri)
            
            # Normalize scheme and hostname to lowercase
            scheme = parsed.scheme.lower()
            hostname = parsed.hostname.lower() if parsed.hostname else ''
            
            # Reconstruct normalized URI
            normalized = f"{scheme}://{hostname}"
            
            if parsed.port and parsed.port != (443 if scheme == 'https' else 80):
                normalized += f":{parsed.port}"
            
            if parsed.path:
                normalized += parsed.path
            
            if parsed.query:
                normalized += f"?{parsed.query}"
            
            if parsed.fragment:
                normalized += f"#{parsed.fragment}"
            
            return normalized
            
        except Exception:
            return uri
    
    def is_same_origin(self, uri1: str, uri2: str) -> bool:
        """Check if two URIs have the same origin"""
        try:
            parsed1 = urlparse(uri1)
            parsed2 = urlparse(uri2)
            
            return (
                parsed1.scheme == parsed2.scheme and
                parsed1.hostname == parsed2.hostname and
                parsed1.port == parsed2.port
            )
        except Exception:
            return False
    
    def validate_batch(self, uris: List[str], context: str = 'general') -> List[tuple[str, Optional[str]]]:
        """
        Validate multiple URIs
        
        Returns:
            List of (uri, error) tuples. Error is None if valid.
        """
        results = []
        
        for uri in uris:
            try:
                self.validate(uri, context)
                results.append((uri, None))
            except ValueError as e:
                results.append((uri, str(e)))
        
        return results


# Convenience function for one-off validation
def validate_uri(uri: str, context: str = 'general') -> str:
    """Validate a URI using the default validator"""
    validator = URIValidator()
    return validator.validate(uri, context)