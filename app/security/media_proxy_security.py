"""
Secure media proxy to prevent SSRF attacks
"""
import hashlib
import hmac
import time
from typing import Optional, Tuple
from urllib.parse import urlparse
import requests
from flask import current_app, abort
import ipaddress
from app.security.uri_validator import URIValidator
import logging

logger = logging.getLogger(__name__)


class SecureMediaProxy:
    """Secure media proxy with SSRF protection"""
    
    ALLOWED_CONTENT_TYPES = {
        'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp',
        'video/mp4', 'video/webm', 'video/ogg',
        'audio/mpeg', 'audio/ogg', 'audio/wav', 'audio/webm'
    }
    
    MAX_CONTENT_SIZE = 50 * 1024 * 1024  # 50MB
    MAX_REDIRECTS = 2
    REQUEST_TIMEOUT = 10
    
    def __init__(self):
        self.uri_validator = URIValidator()
        self.secret_key = current_app.config.get('MEDIA_PROXY_SECRET', 'change-me')
        self.cache_duration = current_app.config.get('MEDIA_CACHE_DURATION', 3600)
    
    def generate_proxy_url(self, media_url: str) -> str:
        """Generate a signed proxy URL for media"""
        # Validate the URL first
        try:
            self.uri_validator.validate(media_url, context='media')
        except ValueError as e:
            logger.warning(f"Invalid media URL: {media_url} - {e}")
            return None
        
        # Generate signature
        timestamp = int(time.time())
        signature = self._generate_signature(media_url, timestamp)
        
        # Build proxy URL
        proxy_path = f"/proxy/media/{signature}/{timestamp}/{media_url}"
        return proxy_path
    
    def validate_proxy_request(self, signature: str, timestamp: str, url: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a proxy request
        
        Returns:
            (is_valid, error_message)
        """
        # Check timestamp
        try:
            ts = int(timestamp)
            if abs(time.time() - ts) > 86400:  # 24 hour expiry
                return False, "Expired proxy URL"
        except ValueError:
            return False, "Invalid timestamp"
        
        # Verify signature
        expected_sig = self._generate_signature(url, ts)
        if not hmac.compare_digest(signature, expected_sig):
            return False, "Invalid signature"
        
        # Validate URL
        try:
            self.uri_validator.validate(url, context='media')
        except ValueError as e:
            return False, f"Invalid URL: {e}"
        
        return True, None
    
    def fetch_media(self, url: str) -> Tuple[Optional[bytes], Optional[str], Optional[dict]]:
        """
        Safely fetch media from URL
        
        Returns:
            (content, content_type, headers)
        """
        # Final URL validation
        try:
            self.uri_validator.validate(url, context='media')
        except ValueError as e:
            logger.error(f"URL validation failed: {e}")
            abort(400)
        
        # Configure session with restrictions
        session = requests.Session()
        session.max_redirects = self.MAX_REDIRECTS
        
        # Custom adapter to block private IPs after redirects
        session.mount('http://', SSRFSafeAdapter())
        session.mount('https://', SSRFSafeAdapter())
        
        try:
            # Make request with timeout
            response = session.get(
                url,
                timeout=self.REQUEST_TIMEOUT,
                stream=True,
                headers={
                    'User-Agent': 'PyFedi/1.0 MediaProxy',
                    'Accept': ', '.join(self.ALLOWED_CONTENT_TYPES)
                }
            )
            
            # Check response
            response.raise_for_status()
            
            # Validate content type
            content_type = response.headers.get('Content-Type', '').lower().split(';')[0]
            if content_type not in self.ALLOWED_CONTENT_TYPES:
                logger.warning(f"Blocked content type: {content_type}")
                abort(415)  # Unsupported Media Type
            
            # Check content length
            content_length = response.headers.get('Content-Length')
            if content_length and int(content_length) > self.MAX_CONTENT_SIZE:
                logger.warning(f"Content too large: {content_length}")
                abort(413)  # Payload Too Large
            
            # Read content with size limit
            content = b''
            for chunk in response.iter_content(chunk_size=8192):
                content += chunk
                if len(content) > self.MAX_CONTENT_SIZE:
                    logger.warning("Content exceeded size limit during streaming")
                    abort(413)
            
            # Build safe headers
            safe_headers = {
                'Content-Type': content_type,
                'Content-Length': str(len(content)),
                'Cache-Control': f'public, max-age={self.cache_duration}'
            }
            
            return content, content_type, safe_headers
            
        except requests.exceptions.Timeout:
            logger.error(f"Timeout fetching media: {url}")
            abort(504)  # Gateway Timeout
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error fetching media: {url} - {e}")
            abort(502)  # Bad Gateway
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error fetching media: {url} - {e}")
            abort(e.response.status_code if e.response else 502)
        except Exception as e:
            logger.error(f"Unexpected error fetching media: {url} - {e}")
            abort(500)
        finally:
            session.close()
    
    def _generate_signature(self, url: str, timestamp: int) -> str:
        """Generate HMAC signature for URL"""
        message = f"{url}:{timestamp}".encode('utf-8')
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            message,
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def clean_media_url(self, url: str) -> Optional[str]:
        """Clean and validate a media URL"""
        if not url:
            return None
        
        # Remove any URL encoding issues
        try:
            # Basic validation
            parsed = urlparse(url)
            if parsed.scheme not in ['http', 'https']:
                return None
            
            # Reconstruct clean URL
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                clean_url += f"?{parsed.query}"
            
            # Validate
            self.uri_validator.validate(clean_url, context='media')
            return clean_url
            
        except Exception:
            return None


class SSRFSafeAdapter(requests.adapters.HTTPAdapter):
    """Custom adapter that blocks requests to private IPs"""
    
    def send(self, request, **kwargs):
        """Override send to check resolved IP"""
        # Parse the URL
        parsed = urlparse(request.url)
        hostname = parsed.hostname
        
        if not hostname:
            raise requests.exceptions.InvalidURL("No hostname in URL")
        
        # Resolve hostname to IP
        try:
            import socket
            # Get IP address
            ip_str = socket.gethostbyname(hostname)
            ip = ipaddress.ip_address(ip_str)
            
            # Check if IP is private
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                raise requests.exceptions.ConnectionError(
                    f"Blocked request to private IP: {ip_str}"
                )
            
        except socket.gaierror:
            # DNS resolution failed
            raise requests.exceptions.ConnectionError(f"DNS resolution failed for {hostname}")
        
        # Proceed with normal request
        return super().send(request, **kwargs)


# Media proxy route handler
def handle_media_proxy(signature: str, timestamp: str, url: str):
    """Handle a media proxy request"""
    proxy = SecureMediaProxy()
    
    # Validate request
    valid, error = proxy.validate_proxy_request(signature, timestamp, url)
    if not valid:
        logger.warning(f"Invalid proxy request: {error}")
        abort(403)
    
    # Fetch media
    content, content_type, headers = proxy.fetch_media(url)
    
    return content, headers
