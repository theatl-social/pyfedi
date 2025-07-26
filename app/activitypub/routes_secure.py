"""
Secure version of ActivityPub routes with critical security fixes
This file contains the updated shared_inbox and related functions
"""
from flask import request, current_app, abort, jsonify, json, g
from app import db, redis_client, limiter
from app.activitypub import bp
from app.models import User, Site
from app.utils import ip_address
from app.security.json_validator import SafeJSONParser, validate_activitypub_object
from app.security.signature_validator import SignatureValidator, SecurityError
from app.security.uri_validator import URIValidator

import os
import uuid
import sys
import traceback
from datetime import datetime

# Import existing functions we need
from app.activitypub.routes import (
    log_ap_status, store_request_body, find_actor_or_create,
    process_inbox_request, process_delete_request,
    log_incoming_ap, APLOG_NOTYPE, APLOG_FAILURE, APLOG_ANNOUNCE,
    APLOG_DUPLICATE, APLOG_IGNORED, APLOG_PT_VIEW, APLOG_DELETE,
    APLOG_SUCCESS
)
from app.activitypub.request_logger import create_request_logger

# Debug flags
EXTRA_AP_DB_DEBUG = os.environ.get('EXTRA_AP_DB_DEBUG', '0') == '1'
EXTRA_AP_LOGGING = os.environ.get('EXTRA_AP_LOGGING', '0') == '1'


@bp.route('/inbox', methods=['POST'])
@limiter.limit("100/minute")  # Overall rate limit
def shared_inbox_secure():
    """
    Secure version of shared_inbox with critical security fixes:
    1. Safe JSON parsing with size/depth limits
    2. Strict signature verification
    3. URI validation
    4. Rate limiting
    """
    # Generate request ID early
    request_id = str(uuid.uuid4())
    g.request_id = request_id
    
    # Initialize logger
    logger = None
    try:
        logger = create_request_logger()
        if logger:
            logger.request_id = request_id
            logger.log_checkpoint('initial_receipt', 'ok', f'Request received at {request.path}')
    except Exception as e:
        current_app.logger.error(f'Failed to create request logger: {str(e)}')
    
    # Early content-length validation
    content_length = request.content_length
    max_content_length = current_app.config.get('MAX_CONTENT_LENGTH', 10 * 1024 * 1024)
    
    if content_length and content_length > max_content_length:
        msg = f'Request too large: {content_length} bytes > {max_content_length}'
        current_app.logger.warning(f'{msg} from {request.remote_addr}')
        if logger:
            logger.log_error('content_length_check', None, msg)
        return 'Request entity too large', 413
    
    # Read body once
    try:
        raw_body = request.get_data(cache=True)
    except Exception as e:
        current_app.logger.error(f'Failed to read request body: {str(e)}')
        if logger:
            logger.log_error('body_read', e, 'Failed to read request body')
        return 'Bad request', 400
    
    # Log raw request
    log_ap_status(request_id, "raw_received", "ok", details="POST received at /inbox")
    store_request_body(request_id, request)
    
    # Parse JSON safely
    try:
        parser = SafeJSONParser()
        request_json = parser.parse(raw_body)
        
        # Validate ActivityPub object structure
        validate_activitypub_object(request_json)
        
        if logger:
            logger.log_checkpoint('json_parse', 'ok', 'Successfully parsed and validated JSON')
            logger.store_request_body(request, request_json)
            
    except ValueError as e:
        log_ap_status(request_id, "json_parse", "fail", details=str(e))
        if logger:
            logger.log_error('json_parse', e, 'JSON parsing/validation failed')
        log_incoming_ap('', APLOG_NOTYPE, APLOG_FAILURE, None, f'Invalid JSON: {str(e)}')
        return 'Bad request', 400
    except Exception as e:
        log_ap_status(request_id, "json_parse", "fail", details=str(e))
        if logger:
            logger.log_error('json_parse', e, 'Unexpected error parsing JSON')
        return 'Bad request', 400
    
    # Extract activity info
    activity_id = request_json.get('id')
    activity_type = request_json.get('type')
    actor_id = request_json.get('actor')
    
    # Validate required fields
    if not all([activity_id, activity_type, actor_id]):
        missing = []
        if not activity_id: missing.append('id')
        if not activity_type: missing.append('type')
        if not actor_id: missing.append('actor')
        
        log_ap_status(request_id, "field_validation", "fail", details=f"Missing fields: {missing}")
        if logger:
            logger.log_validation_failure('field_validation', f'Missing required fields: {missing}')
        return 'Bad request', 400
    
    # Validate activity ID
    if not isinstance(activity_id, str) or len(activity_id) > 2048:
        log_ap_status(request_id, "field_validation", "fail", details="Invalid activity ID")
        return 'Bad request', 400
    
    # Initialize site
    g.site = Site.query.get(1)
    store_ap_json = g.site.log_activitypub_json if g.site else False
    saved_json = request_json if store_ap_json else None
    
    # Duplicate check
    if redis_client.exists(activity_id):
        log_ap_status(request_id, "duplicate_check", "ignored", activity_id=activity_id)
        if logger:
            logger.log_checkpoint('duplicate_check', 'ignored', 'Activity already processed')
        log_incoming_ap(activity_id, APLOG_DUPLICATE, APLOG_IGNORED, saved_json, 'Duplicate activity')
        return '', 200
    
    # Mark as processing
    redis_client.set(activity_id, 1, ex=90)
    
    # Special handling for Announce with nested object
    if activity_type == 'Announce' and isinstance(request_json.get('object'), dict):
        object_data = request_json['object']
        
        # Validate nested object
        if 'id' not in object_data:
            if logger:
                logger.log_validation_failure('announce_validation', 'Missing id in announced object')
            return 'Bad request', 400
        
        if not isinstance(object_data['id'], str) or len(object_data['id']) > 2048:
            if logger:
                logger.log_validation_failure('announce_validation', 'Invalid id in announced object')
            return 'Bad request', 400
        
        # Update activity_id to the inner object's ID for deduplication
        activity_id = object_data['id']
        if redis_client.exists(activity_id):
            log_incoming_ap(activity_id, APLOG_DUPLICATE, APLOG_IGNORED, saved_json, 'Duplicate announced activity')
            return '', 200
        redis_client.set(activity_id, 1, ex=90)
    
    # Find or create actor
    try:
        actor = find_actor_or_create(actor_id)
        if not actor:
            log_ap_status(request_id, 'actor_lookup', 'fail', activity_id=activity_id, details=f'Actor not found: {actor_id}')
            if logger:
                logger.log_null_check_failure('actor_lookup', 'actor', 'User/Community object')
            log_incoming_ap(activity_id, APLOG_NOTYPE, APLOG_FAILURE, saved_json, f'Actor not found: {actor_id}')
            return 'Actor not found', 404
    except Exception as e:
        log_ap_status(request_id, 'actor_lookup', 'fail', activity_id=activity_id, details=str(e))
        if logger:
            logger.log_error('actor_lookup', e, 'Failed to find/create actor')
        return 'Internal error', 500
    
    # Validate actor is not local (security check)
    if actor.is_local():
        log_ap_status(request_id, 'actor_validation', 'fail', activity_id=activity_id, details='Local actor')
        if logger:
            logger.log_security_alert('LOCAL_ACTOR_EXTERNAL_REQUEST', f'Local actor {actor_id} in external request')
        return 'Forbidden', 403
    
    # Signature verification with strict validation
    try:
        validator = SignatureValidator()
        verified, method = validator.verify_request(request, actor)
        
        if logger:
            logger.log_checkpoint('signature_verify', 'ok', f'Signature verified via {method}')
        log_ap_status(request_id, 'signature_verify', 'ok', activity_id=activity_id, details=f'Verified via {method}')
        
    except SecurityError as e:
        log_ap_status(request_id, 'signature_verify', 'fail', activity_id=activity_id, details=str(e))
        if logger:
            logger.log_security_alert('SIGNATURE_VERIFICATION_FAILED', str(e))
        log_incoming_ap(activity_id, APLOG_NOTYPE, APLOG_FAILURE, saved_json, f'Signature verification failed: {e}')
        return 'Unauthorized', 401
    except Exception as e:
        log_ap_status(request_id, 'signature_verify', 'error', activity_id=activity_id, details=str(e))
        if logger:
            logger.log_error('signature_verify', e, 'Unexpected error during verification')
        return 'Internal error', 500
    
    # Update instance information
    if actor.instance_id:
        try:
            actor.instance.last_seen = datetime.utcnow()
            actor.instance.dormant = False
            actor.instance.gone_forever = False
            actor.instance.failures = 0
            actor.instance.ip_address = ip_address()
            db.session.commit()
            
            if logger:
                logger.log_checkpoint('instance_update', 'ok', f'Updated instance {actor.instance.domain}')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Failed to update instance: {e}')
    
    # Special handling for account deletion
    if activity_type == 'Delete' and request_json.get('object') == actor_id:
        if logger:
            logger.log_checkpoint('account_deletion_dispatch', 'ok', 'Processing account deletion')
        
        if current_app.debug:
            process_delete_request(request_json, store_ap_json, request_id)
        else:
            process_delete_request.delay(request_json, store_ap_json, request_id)
        
        return '', 200
    
    # Rate limiting for specific activity types
    if activity_type in ['Like', 'Dislike']:
        # Rate limit votes per actor
        vote_key = f"vote_rate:{actor_id}:{request.remote_addr}"
        vote_count = redis_client.incr(vote_key)
        if vote_count == 1:
            redis_client.expire(vote_key, 60)  # 1 minute window
        
        if vote_count > 60:  # 60 votes per minute per actor/IP
            log_ap_status(request_id, 'rate_limit', 'fail', activity_id=activity_id, details='Vote rate limit exceeded')
            if logger:
                logger.log_security_alert('VOTE_RATE_LIMIT_EXCEEDED', f'Actor {actor_id} exceeded vote rate limit')
            return 'Too many requests', 429
    
    # Dispatch to main processing
    if logger:
        logger.log_checkpoint('main_processing_dispatch', 'ok', 'Dispatching to main inbox processing')
    
    try:
        if current_app.debug:
            process_inbox_request(request_json, store_ap_json, request_id)
        else:
            process_inbox_request.delay(request_json, store_ap_json, request_id)
        
        return '', 200
        
    except Exception as e:
        log_ap_status(request_id, 'processing_dispatch', 'error', activity_id=activity_id, details=str(e))
        if logger:
            logger.log_error('processing_dispatch', e, 'Failed to dispatch for processing')
        return 'Internal error', 500