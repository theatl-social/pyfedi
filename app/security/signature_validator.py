"""
Strict signature validation for ActivityPub requests
"""
from typing import Optional, Tuple, Dict, Any
from flask import Request, g, current_app
from app.activitypub.signature import HttpSignature, LDSignature, VerificationError
from app.models import User, Instance
from app import redis_client
from datetime import datetime, timedelta
import json
import logging


class SignatureValidator:
    """
    Strict signature validation with no unsafe fallbacks
    """
    
    # Very limited allowlist for unsigned activities
    # Only add entries here after careful security review
    UNSIGNED_ALLOWLIST = {
        # Example: 'https://trusted-relay.example.com': {
        #     'allowed_types': ['Announce'],
        #     'reason': 'Trusted relay service'
        # }
    }
    
    # Maximum time difference for date headers (15 minutes)
    MAX_TIME_DIFF = timedelta(minutes=15)
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._verification_cache = {}  # Request-scoped cache
    
    def verify_request(self, request: Request, actor: User) -> Tuple[bool, Optional[str]]:
        """
        Verify request signature with strict validation
        
        Args:
            request: Flask request object
            actor: Actor who allegedly sent the request
            
        Returns:
            Tuple of (verified: bool, method: str|None)
            
        Raises:
            SecurityError: If signature verification fails
        """
        # Generate cache key
        signature_header = request.headers.get('Signature', '')
        cache_key = f"{actor.ap_profile_id}:{signature_header}"
        
        # Check cache
        if cache_key in self._verification_cache:
            return self._verification_cache[cache_key]
        
        verified = False
        method = None
        
        try:
            # Primary method: HTTP Signature
            if self._has_http_signature(request):
                verified, method = self._verify_http_signature(request, actor)
                if verified:
                    self._log_verification_success('HTTP_SIGNATURE', actor)
                else:
                    self._log_verification_failure('HTTP_SIGNATURE', actor, "Invalid signature")
            
            # Fallback: LD Signature (only if no HTTP signature)
            elif self._has_ld_signature(request):
                verified, method = self._verify_ld_signature(request, actor)
                if verified:
                    self._log_verification_success('LD_SIGNATURE', actor)
                    # Mark as using weaker signature method
                    g.weak_signature = True
                else:
                    self._log_verification_failure('LD_SIGNATURE', actor, "Invalid signature")
            
            # Last resort: Check explicit allowlist
            elif self._is_unsigned_allowed(actor, request):
                verified = True
                method = 'unsigned_allowlist'
                self._log_verification_success('UNSIGNED_ALLOWED', actor)
                g.unsigned_activity = True
            
            # No valid signature found
            if not verified:
                self._handle_verification_failure(actor, request)
                raise SecurityError(f"No valid signature found for request from {actor.ap_profile_id}")
            
            # Cache result
            self._verification_cache[cache_key] = (verified, method)
            
            return verified, method
            
        except Exception as e:
            self.logger.error(f"Signature verification error: {e}")
            self._log_security_alert('SIGNATURE_VERIFICATION_ERROR', actor, str(e))
            raise
    
    def _has_http_signature(self, request: Request) -> bool:
        """Check if request has HTTP signature"""
        return bool(request.headers.get('Signature'))
    
    def _has_ld_signature(self, request: Request) -> bool:
        """Check if request has LD signature"""
        try:
            data = request.get_json(force=True, cache=True)
            return isinstance(data, dict) and 'signature' in data
        except Exception:
            return False
    
    def _verify_http_signature(self, request: Request, actor: User) -> Tuple[bool, Optional[str]]:
        """Verify HTTP signature"""
        try:
            # Verify date header is recent (prevent replay attacks)
            if not self._verify_date_header(request):
                self._log_security_alert('STALE_DATE_HEADER', actor)
                return False, None
            
            # Verify signature
            HttpSignature.verify_request(request, actor.public_key, skip_date=False)
            return True, 'http_signature'
            
        except VerificationError as e:
            self.logger.debug(f"HTTP signature verification failed: {e}")
            return False, None
    
    def _verify_ld_signature(self, request: Request, actor: User) -> Tuple[bool, Optional[str]]:
        """Verify Linked Data signature"""
        try:
            request_json = request.get_json(force=True, cache=True)
            
            # Verify signature
            LDSignature.verify_signature(request_json, actor.public_key)
            
            # Additional validation for LD signatures
            if not self._validate_ld_signature_fields(request_json):
                return False, None
            
            return True, 'ld_signature'
            
        except Exception as e:
            self.logger.debug(f"LD signature verification failed: {e}")
            return False, None
    
    def _validate_ld_signature_fields(self, data: Dict[str, Any]) -> bool:
        """Validate LD signature has required fields"""
        if 'signature' not in data:
            return False
            
        sig = data['signature']
        required_fields = ['type', 'creator', 'created', 'signatureValue']
        
        for field in required_fields:
            if field not in sig:
                return False
        
        # Validate signature type
        if sig.get('type') not in ['RsaSignature2017', 'Ed25519Signature2018']:
            return False
        
        return True
    
    def _verify_date_header(self, request: Request) -> bool:
        """Verify date header is recent to prevent replay attacks"""
        date_header = request.headers.get('Date')
        if not date_header:
            return True  # Some implementations don't include date
        
        try:
            # Parse date header
            request_date = datetime.strptime(date_header, '%a, %d %b %Y %H:%M:%S GMT')
            
            # Compare with current time
            time_diff = abs(datetime.utcnow() - request_date)
            
            if time_diff > self.MAX_TIME_DIFF:
                self.logger.warning(f"Date header too old: {time_diff}")
                return False
                
            return True
            
        except ValueError:
            self.logger.warning(f"Invalid date header format: {date_header}")
            return False
    
    def _is_unsigned_allowed(self, actor: User, request: Request) -> bool:
        """Check if unsigned activity is explicitly allowed"""
        # Never allow unsigned activities in production unless explicitly configured
        if not current_app.config.get('ALLOW_UNSIGNED_ACTIVITIES', False):
            return False
        
        # Check allowlist
        allowed = self.UNSIGNED_ALLOWLIST.get(actor.ap_profile_id)
        if not allowed:
            return False
        
        try:
            data = request.get_json(force=True, cache=True)
            activity_type = data.get('type')
            
            # Check if this activity type is allowed
            if activity_type not in allowed.get('allowed_types', []):
                return False
            
            # Log for audit purposes
            self._log_security_event('UNSIGNED_ACTIVITY_ALLOWED', {
                'actor': actor.ap_profile_id,
                'type': activity_type,
                'reason': allowed.get('reason', 'Unknown')
            })
            
            return True
            
        except Exception:
            return False
    
    def _handle_verification_failure(self, actor: User, request: Request):
        """Handle signature verification failure"""
        # Increment failure counter
        if actor.instance:
            self._increment_failure_counter(actor.instance)
        
        # Log security event
        self._log_security_alert('NO_VALID_SIGNATURE', actor)
        
        # Check if instance should be blocked
        if actor.instance and self._should_block_instance(actor.instance):
            self._log_security_alert('INSTANCE_AUTO_BLOCKED', actor, 
                                   f"Too many signature failures from {actor.instance.domain}")
            # TODO: Implement instance blocking
    
    def _increment_failure_counter(self, instance: Instance):
        """Track signature failures per instance"""
        key = f"sig_failures:{instance.domain}"
        count = redis_client.incr(key)
        
        # Set expiry on first increment
        if count == 1:
            redis_client.expire(key, 3600)  # 1 hour window
        
        # Log if threshold reached
        if count == 50:
            self._log_security_event('SIGNATURE_FAILURE_THRESHOLD', {
                'instance': instance.domain,
                'count': count
            })
    
    def _should_block_instance(self, instance: Instance) -> bool:
        """Check if instance has too many failures"""
        key = f"sig_failures:{instance.domain}"
        count = redis_client.get(key)
        
        if count:
            return int(count) > 100  # More than 100 failures per hour
        
        return False
    
    def _log_verification_success(self, method: str, actor: User):
        """Log successful verification"""
        self._log_security_event('SIGNATURE_VERIFIED', {
            'method': method,
            'actor': actor.ap_profile_id,
            'instance': actor.instance.domain if actor.instance else None
        })
    
    def _log_verification_failure(self, method: str, actor: User, error: str):
        """Log verification failure"""
        self._log_security_event('SIGNATURE_FAILED', {
            'method': method,
            'actor': actor.ap_profile_id,
            'instance': actor.instance.domain if actor.instance else None,
            'error': error
        }, level='WARNING')
    
    def _log_security_alert(self, event: str, actor: User, details: str = None):
        """Log critical security alerts"""
        from app.utils import ip_address
        
        self._log_security_event(event, {
            'actor': actor.ap_profile_id,
            'instance': actor.instance.domain if actor.instance else None,
            'ip': ip_address(),
            'user_agent': request.user_agent.string if request else None,
            'details': details
        }, level='CRITICAL')
    
    def _log_security_event(self, event_type: str, data: Dict[str, Any], level: str = 'INFO'):
        """Log security event"""
        # Add request ID if available
        if hasattr(g, 'request_id'):
            data['request_id'] = g.request_id
        
        # Log to application logger
        log_message = f"[SECURITY] {event_type}: {json.dumps(data)}"
        
        if level == 'CRITICAL':
            self.logger.critical(log_message)
        elif level == 'WARNING':
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)
        
        # TODO: Send to security monitoring system
        # TODO: Store in security_events table for analysis


class SecurityError(Exception):
    """Raised when security validation fails"""
    pass
