"""
Helper functions for ActivityPub routes

This module contains shared utilities used across ActivityPub route handlers,
including response formatting, request logging, and common operations.

All functions are fully typed for better IDE support and runtime validation.
"""

from __future__ import annotations
from typing import Dict, Any, Optional, TypedDict, Literal, Union
from datetime import datetime
import json
import uuid
from flask import Request, g, current_app

from app import db, cache
from app.models import Instance, APRequestStatus, APRequestBody
from app.activitypub.signature import default_context

# Type aliases
type ActivityId = str
type ActorUrl = str
type JsonDict = Dict[str, Any]
type HttpStatusCode = int
type RequestId = str


class FollowResponseData(TypedDict):
    """Type definition for Follow Accept/Reject responses"""
    context: Union[str, list[str], Dict[str, Any]]
    actor: str
    to: list[str]
    object: Union[str, Dict[str, Any]]
    type: Literal["Accept", "Reject"]
    id: str


def format_follow_response(
    follow_id: ActivityId,
    follow_actor: ActorUrl,
    follow_object: ActorUrl,
    response_type: Literal["Accept", "Reject"],
    response_id: ActivityId,
    actor: ActorUrl,
    recipient_instance: Optional[Instance] = None
) -> FollowResponseData:
    """
    Format Accept/Reject responses for Follow activities with compatibility for different software.
    
    Args:
        follow_id: The ID of the original Follow activity
        follow_actor: The actor who sent the Follow
        follow_object: The object being followed
        response_type: Either "Accept" or "Reject"
        response_id: The ID for the response activity
        actor: The actor sending the response
        recipient_instance: The Instance object of the recipient (optional)
    
    Returns:
        Formatted Accept/Reject activity dict
        
    Example:
        >>> response = format_follow_response(
        ...     follow_id="https://example.com/activities/follow/123",
        ...     follow_actor="https://example.com/users/alice",
        ...     follow_object="https://our.site/c/community",
        ...     response_type="Accept",
        ...     response_id="https://our.site/activities/accept/456",
        ...     actor="https://our.site/c/community"
        ... )
    """
    # For PyFedi/PieFed instances, use the full object format for better compatibility
    if recipient_instance and recipient_instance.software and recipient_instance.software.lower() in ['pyfedi', 'piefed']:
        return FollowResponseData(
            context=default_context(),
            actor=actor,
            to=[follow_actor],
            object={
                "actor": follow_actor,
                "to": None,
                "object": follow_object,
                "type": "Follow",
                "id": follow_id
            },
            type=response_type,
            id=response_id
        )
    else:
        # For Lemmy, Mastodon, and other software, use the simpler format
        return FollowResponseData(
            context=default_context(),
            actor=actor,
            to=[follow_actor],
            object=follow_id,
            type=response_type,
            id=response_id
        )


def log_ap_status(
    request_id: RequestId,
    checkpoint: str,
    status: str,
    activity_id: Optional[ActivityId] = None,
    post_object_uri: Optional[str] = None,
    details: Optional[str] = None
) -> None:
    """
    Log ActivityPub request status checkpoint to database.
    
    This function provides resilient status logging for debugging and monitoring
    ActivityPub request processing.
    
    Args:
        request_id: Unique request identifier
        checkpoint: Processing stage name
        status: Status at this checkpoint
        activity_id: Optional ActivityPub activity ID
        post_object_uri: Optional post object URI
        details: Optional additional details
    """
    try:
        status_entry = APRequestStatus(
            request_id=request_id,
            timestamp=datetime.utcnow(),
            checkpoint=checkpoint,
            status=status,
            activity_id=activity_id[:256] if activity_id else None,
            post_object_uri=post_object_uri[:512] if post_object_uri else None,
            details=details[:1024] if details else None
        )
        db.session.add(status_entry)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.warning(f"Failed to log AP status: {str(e)}")


def store_request_body(
    request_id: RequestId,
    request_obj: Request,
    parsed_json: Optional[JsonDict] = None
) -> bool:
    """
    Store the request body and parsed JSON for an ActivityPub request.
    
    This function captures request data for debugging and replay capabilities.
    
    Args:
        request_id: Unique request identifier
        request_obj: Flask request object
        parsed_json: Pre-parsed JSON data (optional)
        
    Returns:
        True if storage was successful, False otherwise
    """
    try:
        # Get raw body
        body_bytes = request_obj.get_data(as_text=False)
        
        # Parse JSON if not provided
        if parsed_json is None:
            try:
                parsed_json = json.loads(body_bytes)
            except json.JSONDecodeError:
                parsed_json = None
        
        # Store in database
        body_entry = APRequestBody(
            request_id=request_id,
            timestamp=datetime.utcnow(),
            raw_body=body_bytes,
            parsed_json=parsed_json,
            content_type=request_obj.content_type,
            content_length=len(body_bytes)
        )
        
        db.session.add(body_entry)
        db.session.commit()
        return True
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to store request body: {str(e)}")
        return False


def generate_request_id() -> RequestId:
    """
    Generate a unique request ID for tracking.
    
    Returns:
        UUID string for request identification
    """
    return str(uuid.uuid4())


def get_request_id() -> RequestId:
    """
    Get the current request ID from Flask globals.
    
    Returns:
        Current request ID or generates new one if not set
    """
    if not hasattr(g, 'request_id'):
        g.request_id = generate_request_id()
    return g.request_id


def is_activitypub_request(request: Request) -> bool:
    """
    Check if the request is an ActivityPub request based on Accept header.
    
    Args:
        request: Flask request object
        
    Returns:
        True if this is an ActivityPub request
    """
    accept_header = request.headers.get('Accept', '')
    activitypub_types = [
        'application/activity+json',
        'application/ld+json',
        'application/json'
    ]
    
    return any(mime_type in accept_header for mime_type in activitypub_types)


def make_activitypub_response(
    data: JsonDict,
    status_code: HttpStatusCode = 200
) -> tuple[str, HttpStatusCode, Dict[str, str]]:
    """
    Create a properly formatted ActivityPub JSON response.
    
    Args:
        data: Response data dictionary
        status_code: HTTP status code
        
    Returns:
        Tuple of (json_string, status_code, headers)
    """
    headers = {
        'Content-Type': 'application/activity+json',
        'X-Request-Id': get_request_id()
    }
    
    return json.dumps(data), status_code, headers


def get_instance_by_domain(domain: str) -> Optional[Instance]:
    """
    Get an Instance object by domain name.
    
    Args:
        domain: Instance domain
        
    Returns:
        Instance object or None if not found
    """
    return Instance.query.filter_by(domain=domain).first()


def verify_instance_compatibility(
    instance: Instance,
    activity_type: str
) -> bool:
    """
    Verify if an instance supports a specific activity type.
    
    Args:
        instance: Instance to check
        activity_type: ActivityPub activity type
        
    Returns:
        True if the instance supports the activity type
    """
    # For now, assume all instances support all activities
    # This can be extended based on nodeinfo capabilities
    return True