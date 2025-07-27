"""
Inbox endpoints for receiving ActivityPub activities

This module handles incoming ActivityPub activities sent to our inbox endpoints.
Maintains full compatibility with PyFedi, Lemmy, Mastodon, and other implementations.

The key compatibility fix is in handling Follow Accept/Reject responses - different
software expects different formats.

Endpoints:
    - /inbox - Shared inbox for all actors
    - /site_inbox - Site-wide inbox
    - /u/<actor>/inbox - User-specific inbox
    - /c/<actor>/inbox - Community-specific inbox
"""

from __future__ import annotations
from typing import Dict, Any, Optional, Literal, Tuple
import json
from datetime import datetime
from flask import request, abort, g, current_app
from sqlalchemy import text

from app import db, cache
from app.activitypub.routes import bp
from app.activitypub.signature import HttpSignature, VerificationError
from app.activitypub.util import (
    find_actor_or_create, find_community, ensure_domains_match,
    verify_object_from_source, post_to_activity
)
from app.activitypub.routes.helpers import (
    format_follow_response, log_ap_status, store_request_body,
    generate_request_id, get_request_id
)
from app.models import (
    User, Community, CommunityMember, CommunityJoinRequest,
    Instance, Post, PostReply, utcnow
)
from app.utils import gibberish, get_setting, instance_banned
from app.security.json_validator import SafeJSONParser

# Type aliases
type ActivityType = Literal[
    "Create", "Update", "Delete", "Follow", "Accept", "Reject",
    "Like", "Dislike", "Announce", "Undo", "Add", "Remove",
    "Block", "Flag", "Move"
]
type InboxResponse = Tuple[str, int]


@bp.route('/inbox', methods=['POST'])
def shared_inbox() -> InboxResponse:
    """
    Shared inbox endpoint for receiving activities.
    
    This is the main inbox that receives activities for all actors
    on this instance. It validates signatures and routes activities
    to appropriate handlers.
    
    Returns:
        204 No Content on success
        400/401/500 on various errors
        
    Security:
        - Validates HTTP signatures
        - Checks for banned instances
        - Validates JSON structure
        - Verifies actor domains match
    """
    return _process_inbox(shared=True)


@bp.route('/site_inbox', methods=['POST'])
def site_inbox() -> InboxResponse:
    """
    Site-wide inbox for instance-level activities.
    
    Handles activities directed at the instance itself rather
    than specific actors (e.g., instance blocks).
    
    Returns:
        204 No Content on success
    """
    return _process_inbox(site=True)


@bp.route('/u/<actor>/inbox', methods=['POST'])
def user_inbox(actor: str) -> InboxResponse:
    """
    User-specific inbox endpoint.
    
    Args:
        actor: Username receiving the activity
        
    Returns:
        204 No Content on success
    """
    return _process_inbox(user_name=actor)


@bp.route('/c/<actor>/inbox', methods=['POST'])
def community_inbox(actor: str) -> InboxResponse:
    """
    Community-specific inbox endpoint.
    
    Args:
        actor: Community name receiving the activity
        
    Returns:
        204 No Content on success
    """
    return _process_inbox(community_name=actor)


def _process_inbox(
    shared: bool = False,
    site: bool = False,
    user_name: Optional[str] = None,
    community_name: Optional[str] = None
) -> InboxResponse:
    """
    Process incoming ActivityPub activity.
    
    This is the main entry point for all inbox processing. It handles:
    - Request validation and parsing
    - Signature verification
    - Instance ban checking
    - Activity routing to handlers
    
    Args:
        shared: True if this is the shared inbox
        site: True if this is the site inbox
        user_name: Target user name if user inbox
        community_name: Target community name if community inbox
        
    Returns:
        HTTP response tuple
    """
    # Generate request ID for tracking
    request_id = generate_request_id()
    g.request_id = request_id
    
    # Log initial request
    log_ap_status(request_id, 'inbox_received', 'processing')
    
    try:
        # Parse JSON with safety checks
        parser = SafeJSONParser(
            max_size=1_000_000,  # 1MB limit
            max_depth=10,
            max_keys=1000
        )
        
        activity = parser.parse(request.data)
        
        # Store request for debugging
        store_request_body(request_id, request, activity)
        
        # Extract basic activity info
        activity_type = activity.get('type')
        activity_id = activity.get('id', 'no-id')
        actor_id = activity.get('actor')
        
        if not activity_type or not actor_id:
            log_ap_status(request_id, 'validation', 'failed', 
                         details='Missing type or actor')
            return 'Bad Request: Missing required fields', 400
        
        # Verify actor domain matches activity domain
        if not ensure_domains_match(actor_id, activity_id):
            log_ap_status(request_id, 'validation', 'failed',
                         details='Domain mismatch')
            return 'Bad Request: Domain mismatch', 400
        
        # Check for banned instances
        actor_domain = actor_id.split('/')[2]
        if instance_banned(actor_domain):
            log_ap_status(request_id, 'validation', 'banned',
                         details=f'Instance {actor_domain} is banned')
            return '', 204  # Silently drop
        
        # Verify HTTP signature
        if not _verify_signature(request, activity):
            log_ap_status(request_id, 'signature', 'failed')
            return 'Unauthorized: Invalid signature', 401
        
        # Route to activity handler
        result = _handle_activity(activity, request_id)
        
        if result:
            log_ap_status(request_id, 'processing', 'success',
                         activity_id=activity_id)
            return '', 204
        else:
            log_ap_status(request_id, 'processing', 'failed',
                         activity_id=activity_id)
            return 'Internal Server Error', 500
            
    except json.JSONDecodeError as e:
        log_ap_status(request_id, 'parsing', 'failed',
                     details=str(e))
        return 'Bad Request: Invalid JSON', 400
    except Exception as e:
        current_app.logger.error(f"Inbox processing error: {e}")
        log_ap_status(request_id, 'processing', 'error',
                     details=str(e))
        return 'Internal Server Error', 500


def _verify_signature(request: request, activity: Dict[str, Any]) -> bool:
    """
    Verify HTTP signature on incoming request.
    
    Args:
        request: Flask request object
        activity: Parsed activity data
        
    Returns:
        True if signature is valid or not required
    """
    # Some activities don't require signatures
    if activity.get('type') in ['Delete'] and _is_self_delete(activity):
        return True
    
    if 'signature' not in request.headers:
        # Check if instance allows unsigned activities
        if not get_setting('require_signatures', True):
            return True
        return False
    
    try:
        # Get actor's public key
        actor = find_actor_or_create(activity['actor'])
        if not actor or not actor.public_key:
            return False
        
        # Verify signature
        HttpSignature.verify_request(
            request,
            actor.public_key,
            skip_date=True  # Be lenient with date headers
        )
        return True
        
    except VerificationError as e:
        current_app.logger.warning(f"Signature verification failed: {e}")
        return False


def _is_self_delete(activity: Dict[str, Any]) -> bool:
    """Check if this is an actor deleting themselves."""
    return (activity.get('type') == 'Delete' and 
            activity.get('actor') == activity.get('object'))


def _handle_activity(activity: Dict[str, Any], request_id: str) -> bool:
    """
    Route activity to appropriate handler.
    
    Args:
        activity: The activity to handle
        request_id: Request tracking ID
        
    Returns:
        True if handled successfully
    """
    activity_type = activity['type']
    
    handlers = {
        'Create': _handle_create,
        'Update': _handle_update,
        'Delete': _handle_delete,
        'Follow': _handle_follow,
        'Accept': _handle_accept,
        'Reject': _handle_reject,
        'Undo': _handle_undo,
        'Like': _handle_like,
        'Dislike': _handle_dislike,
        'Announce': _handle_announce,
        'Add': _handle_add,
        'Remove': _handle_remove,
        'Block': _handle_block,
        'Flag': _handle_flag,
    }
    
    handler = handlers.get(activity_type)
    if not handler:
        current_app.logger.warning(f"No handler for activity type: {activity_type}")
        return True  # Accept but ignore unknown activities
    
    try:
        return handler(activity, request_id)
    except Exception as e:
        current_app.logger.error(f"Handler error for {activity_type}: {e}")
        return False


def _handle_follow(activity: Dict[str, Any], request_id: str) -> bool:
    """
    Handle Follow activity with cross-platform compatibility.
    
    This is where the key compatibility fix happens - we format
    Accept/Reject responses differently based on the requesting instance.
    
    Args:
        activity: Follow activity
        request_id: Request tracking ID
        
    Returns:
        True if handled successfully
    """
    actor_url = activity['actor']
    object_url = activity['object']
    follow_id = activity.get('id')
    
    # Find the actor wanting to follow
    actor = find_actor_or_create(actor_url)
    if not actor:
        return False
    
    # Determine if following user or community
    target_user = User.query.filter_by(ap_profile_id=object_url).first()
    target_community = Community.query.filter_by(ap_profile_id=object_url).first()
    
    if target_user:
        # Following a user - auto-accept for now
        # TODO: Implement follow requests for locked accounts
        _send_follow_response(activity, 'Accept', actor.instance)
        return True
        
    elif target_community:
        # Following a community
        if target_community.restricted_to_mods:
            # Restricted community - create join request
            existing = CommunityJoinRequest.query.filter_by(
                user_id=actor.id,
                community_id=target_community.id
            ).first()
            
            if not existing:
                join_request = CommunityJoinRequest(
                    user_id=actor.id,
                    community_id=target_community.id
                )
                db.session.add(join_request)
                db.session.commit()
            
            # Don't send immediate response for restricted communities
            return True
        else:
            # Open community - auto-accept
            existing = CommunityMember.query.filter_by(
                user_id=actor.id,
                community_id=target_community.id
            ).first()
            
            if not existing:
                member = CommunityMember(
                    user_id=actor.id,
                    community_id=target_community.id,
                    is_moderator=False,
                    is_owner=False,
                    is_banned=False,
                    created_at=utcnow()
                )
                db.session.add(member)
                db.session.commit()
            
            _send_follow_response(activity, 'Accept', actor.instance)
            return True
    
    return False


def _send_follow_response(
    follow_activity: Dict[str, Any],
    response_type: Literal['Accept', 'Reject'],
    recipient_instance: Optional[Instance] = None
) -> None:
    """
    Send Accept or Reject response to Follow activity.
    
    Uses format_follow_response() to ensure compatibility with
    different ActivityPub implementations.
    
    Args:
        follow_activity: The original Follow activity
        response_type: 'Accept' or 'Reject'
        recipient_instance: Instance of the follower
    """
    from app.activitypub.signature import send_post_request
    
    follow_id = follow_activity.get('id')
    follow_actor = follow_activity['actor']
    follow_object = follow_activity['object']
    
    # Generate response ID
    response_id = f"https://{current_app.config['SERVER_NAME']}/activities/{response_type.lower()}/{gibberish(15)}"
    
    # Get the actor sending the response
    if follow_object.startswith(f"https://{current_app.config['SERVER_NAME']}/u/"):
        # User is responding
        user_name = follow_object.split('/')[-1]
        user = User.query.filter_by(user_name=user_name).first()
        actor = user.ap_profile_id if user else follow_object
        private_key = user.private_key if user else None
    else:
        # Community is responding
        community_name = follow_object.split('/')[-1]
        community = Community.query.filter_by(name=community_name).first()
        actor = community.ap_profile_id if community else follow_object
        private_key = community.private_key if community else None
    
    if not private_key:
        current_app.logger.error(f"No private key for {actor}")
        return
    
    # Format response based on recipient software
    response = format_follow_response(
        follow_id=follow_id,
        follow_actor=follow_actor,
        follow_object=follow_object,
        response_type=response_type,
        response_id=response_id,
        actor=actor,
        recipient_instance=recipient_instance
    )
    
    # Send the response
    send_post_request(
        uri=follow_actor + '/inbox',
        body=response,
        private_key=private_key,
        key_id=f"{actor}#main-key"
    )


def _handle_accept(activity: Dict[str, Any], request_id: str) -> bool:
    """
    Handle Accept activity (usually accepting our Follow request).
    
    Args:
        activity: Accept activity
        request_id: Request tracking ID
        
    Returns:
        True if handled successfully
    """
    # Handle different Accept formats
    accepted_object = activity.get('object')
    
    if isinstance(accepted_object, str):
        # Simple format - just the Follow ID
        # This is what Lemmy and Mastodon send
        pass
    elif isinstance(accepted_object, dict):
        # Complex format - full Follow object
        # This is what PyFedi sends
        if accepted_object.get('type') == 'Follow':
            # Process the follow acceptance
            pass
    
    # TODO: Update follow status in database
    
    return True


def _handle_reject(activity: Dict[str, Any], request_id: str) -> bool:
    """
    Handle Reject activity (usually rejecting our Follow request).
    
    Args:
        activity: Reject activity
        request_id: Request tracking ID
        
    Returns:
        True if handled successfully
    """
    # Similar to Accept, handle both simple and complex formats
    rejected_object = activity.get('object')
    
    # TODO: Update follow status in database
    
    return True


def _handle_create(activity: Dict[str, Any], request_id: str) -> bool:
    """Handle Create activity (new posts, comments, etc)."""
    object_data = activity.get('object')
    if not object_data or not isinstance(object_data, dict):
        return False
    
    object_type = object_data.get('type')
    
    if object_type in ['Note', 'Article', 'Page', 'Question']:
        # Creating a post or comment
        from app.activitypub.util import create_post, create_post_reply
        
        in_reply_to = object_data.get('inReplyTo')
        if in_reply_to:
            # It's a comment
            return create_post_reply(activity) is not None
        else:
            # It's a post
            return create_post(activity) is not None
    
    return True


def _handle_update(activity: Dict[str, Any], request_id: str) -> bool:
    """Handle Update activity (edits to posts, profiles, etc)."""
    from app.activitypub.util import update_post_from_activity, update_post_reply_from_activity
    
    object_data = activity.get('object')
    if not object_data:
        return False
    
    # Verify the update is from the original author
    if not verify_object_from_source(object_data):
        return False
    
    object_type = object_data.get('type')
    
    if object_type in ['Note', 'Article', 'Page']:
        if object_data.get('inReplyTo'):
            return update_post_reply_from_activity(activity)
        else:
            return update_post_from_activity(activity)
    
    return True


def _handle_delete(activity: Dict[str, Any], request_id: str) -> bool:
    """Handle Delete activity."""
    from app.activitypub.util import delete_post_or_comment
    
    object_ref = activity.get('object')
    
    if isinstance(object_ref, str):
        # Simple delete with just ID
        return delete_post_or_comment(activity)
    elif isinstance(object_ref, dict):
        # Complex delete with tombstone
        return delete_post_or_comment(activity)
    
    return True


def _handle_like(activity: Dict[str, Any], request_id: str) -> bool:
    """Handle Like activity (upvotes)."""
    from app.activitypub.util import process_vote
    return process_vote(activity, vote_type='like')


def _handle_dislike(activity: Dict[str, Any], request_id: str) -> bool:
    """Handle Dislike activity (downvotes)."""
    from app.activitypub.util import process_vote
    return process_vote(activity, vote_type='dislike')


def _handle_announce(activity: Dict[str, Any], request_id: str) -> bool:
    """Handle Announce activity (boosts/shares)."""
    # PyFedi doesn't currently support boosts
    return True


def _handle_undo(activity: Dict[str, Any], request_id: str) -> bool:
    """Handle Undo activity."""
    object_data = activity.get('object')
    if not object_data:
        return False
    
    if isinstance(object_data, dict):
        undo_type = object_data.get('type')
        
        if undo_type == 'Follow':
            # Unfollow
            # TODO: Remove community membership
            return True
        elif undo_type in ['Like', 'Dislike']:
            # Remove vote
            from app.activitypub.util import undo_vote
            return undo_vote(activity)
    
    return True


def _handle_add(activity: Dict[str, Any], request_id: str) -> bool:
    """Handle Add activity (adding moderators, pinning posts, etc)."""
    # TODO: Implement Add activity handling
    return True


def _handle_remove(activity: Dict[str, Any], request_id: str) -> bool:
    """Handle Remove activity (removing moderators, unpinning, etc)."""
    # TODO: Implement Remove activity handling
    return True


def _handle_block(activity: Dict[str, Any], request_id: str) -> bool:
    """Handle Block activity (instance blocks)."""
    # TODO: Implement Block activity handling
    return True


def _handle_flag(activity: Dict[str, Any], request_id: str) -> bool:
    """Handle Flag activity (reports)."""
    from app.activitypub.util import process_report
    return process_report(activity)


def replay_inbox_request(request_json: Dict[str, Any]) -> bool:
    """
    Replay a previously received inbox request.
    
    Used for debugging and recovery. Processes the activity
    as if it was just received.
    
    Args:
        request_json: The activity JSON to replay
        
    Returns:
        True if processed successfully
    """
    request_id = generate_request_id()
    g.request_id = request_id
    
    log_ap_status(request_id, 'replay', 'started')
    
    try:
        result = _handle_activity(request_json, request_id)
        log_ap_status(request_id, 'replay', 'success' if result else 'failed')
        return result
    except Exception as e:
        log_ap_status(request_id, 'replay', 'error', details=str(e))
        return False