"""
Secure ActivityPub routes with enhanced security checks
"""
from flask import Blueprint, request, jsonify
from typing import Dict, Any
import logging
from app.security.json_validator import SafeJSONParser, validate_activitypub_object
from app.security.signature_validator import SignatureValidator, SecurityError
from app.security.uri_validator import validate_uri
from app.utils import rate_limiter
from app.activitypub import process_inbox_request
from app.models import User

logger = logging.getLogger(__name__)


def create_secure_activitypub_bp() -> Blueprint:
    """Create secure ActivityPub blueprint with enhanced security"""
    bp = Blueprint('activitypub_secure', __name__)
    
    @bp.route('/inbox', methods=['POST'])
    @bp.route('/c/<community>/inbox', methods=['POST'])
    @bp.route('/u/<username>/inbox', methods=['POST'])
    @rate_limiter.limit("50/minute")
    def shared_inbox_secure(community=None, username=None):
        """
        Secure inbox handler with comprehensive security checks
        
        Security measures:
        1. Rate limiting
        2. Safe JSON parsing with size/depth limits
        3. Signature verification (no unsafe fallbacks)
        4. URI validation for SSRF prevention
        5. Activity type validation
        6. Comprehensive error handling
        """
        try:
            # Check rate limiting
            if not rate_limiter.is_allowed(request.remote_addr):
                logger.warning(f"Rate limit exceeded for {request.remote_addr}")
                return jsonify({'error': 'Rate limit exceeded'}), 429
            
            # Safe JSON parsing
            parser = SafeJSONParser()
            try:
                activity = parser.parse(request.data)
            except ValueError as e:
                logger.warning(f"JSON parsing failed: {e}")
                if "too large" in str(e).lower():
                    return jsonify({'error': 'Payload too large'}), 413
                return jsonify({'error': 'Invalid JSON'}), 400
            
            # Validate ActivityPub object structure
            try:
                validate_activitypub_object(activity)
            except ValueError as e:
                logger.warning(f"Invalid ActivityPub object: {e}")
                return jsonify({'error': f'Invalid ActivityPub object: {e}'}), 400
            
            # Get actor
            actor_id = activity.get('actor')
            if not actor_id:
                return jsonify({'error': 'Missing actor'}), 400
            
            # Validate actor URI
            try:
                if isinstance(actor_id, str):
                    validate_uri(actor_id, context='activitypub')
                elif isinstance(actor_id, dict) and 'id' in actor_id:
                    validate_uri(actor_id['id'], context='activitypub')
            except ValueError as e:
                logger.warning(f"Invalid actor URI: {e}")
                return jsonify({'error': 'Invalid actor URI'}), 400
            
            # Fetch actor from database
            actor = User.query.filter_by(ap_profile_id=actor_id).first()
            if not actor:
                # Actor not in database - might need to fetch
                logger.info(f"Unknown actor: {actor_id}")
                # In production, would trigger actor fetch via Celery
                return jsonify({'error': 'Unknown actor'}), 404
            
            # Verify signature - no unsafe fallbacks
            validator = SignatureValidator()
            try:
                verified, method = validator.verify_request(request, actor)
                if not verified:
                    return jsonify({'error': 'Signature verification failed'}), 401
            except SecurityError as e:
                logger.warning(f"Security error: {e}")
                return jsonify({'error': 'Invalid signature'}), 401
            
            # Validate object URI if present
            obj = activity.get('object')
            if obj and isinstance(obj, str):
                try:
                    validate_uri(obj, context='activitypub')
                except ValueError as e:
                    logger.warning(f"Invalid object URI: {e}")
                    return jsonify({'error': 'Invalid object URI'}), 400
            
            # Log successful verification
            logger.info(f"Verified {activity.get('type')} from {actor_id} via {method}")
            
            # Process the activity
            result, status_code = process_inbox_request(activity, actor)
            
            return jsonify(result), status_code
            
        except Exception as e:
            # Log but don't expose internal errors
            logger.error(f"Unexpected error in inbox handler: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500
    
    @bp.errorhandler(413)
    def payload_too_large(e):
        """Handle payload too large errors"""
        return jsonify({'error': 'Payload too large'}), 413
    
    @bp.errorhandler(429)
    def too_many_requests(e):
        """Handle rate limit errors"""
        return jsonify({'error': 'Too many requests'}), 429
    
    return bp


def log_security_event(event_type: str, details: Dict[str, Any]):
    """Log security events for monitoring"""
    logger.warning(f"SECURITY_EVENT: {event_type} - {details}")
    # In production, send to security monitoring system
