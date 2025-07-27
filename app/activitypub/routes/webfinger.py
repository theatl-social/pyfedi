"""
WebFinger and host-meta endpoints for actor discovery

This module implements RFC 7033 WebFinger protocol for discovering
information about users and communities on the server.

Endpoints:
    - /.well-known/webfinger - Actor discovery
    - /.well-known/host-meta - Host metadata
"""

from __future__ import annotations
from typing import Dict, Any, Optional, TypedDict, Literal
from urllib.parse import urlparse
from flask import request, jsonify, current_app

from app import db, cache
from app.activitypub.routes import bp
from app.models import User, Community
from app.utils import is_activitypub_request

# Type definitions
type ResourceUri = str
type ActorName = str


class WebFingerLink(TypedDict):
    """WebFinger link object"""
    rel: str
    type: Optional[str]
    href: Optional[str]
    template: Optional[str]


class WebFingerResponse(TypedDict):
    """WebFinger response format"""
    subject: str
    aliases: list[str]
    links: list[WebFingerLink]


@bp.route('/.well-known/webfinger')
@cache.cached(timeout=600, query_string=True)
def webfinger() -> tuple[Dict[str, Any], int]:
    """
    WebFinger endpoint for discovering actors.
    
    Supports discovering both users and communities via acct: URIs.
    Compatible with Mastodon, Lemmy, and other ActivityPub implementations.
    
    Query Parameters:
        resource: The resource to look up (e.g., acct:user@domain.com)
        
    Returns:
        JSON response with actor information or error
        
    Example:
        GET /.well-known/webfinger?resource=acct:alice@example.com
    """
    resource = request.args.get('resource', '').strip()
    
    if not resource:
        return {'error': 'Resource parameter required'}, 400
    
    # Ensure resource is in correct format
    if not resource.startswith('acct:') and '@' in resource:
        resource = f'acct:{resource}'
    
    # Parse the resource
    try:
        if resource.startswith('acct:'):
            # Handle acct: URIs (e.g., acct:user@domain.com)
            account = resource[5:]  # Remove 'acct:' prefix
            parts = account.split('@')
            
            if len(parts) != 2:
                return {'error': 'Invalid acct: format'}, 400
                
            actor_name, domain = parts
            
            # Verify the domain matches our server
            if domain != current_app.config['SERVER_NAME']:
                return {'error': 'Domain does not match this server'}, 404
                
        elif resource.startswith('https://') or resource.startswith('http://'):
            # Handle URL-based resources
            parsed = urlparse(resource)
            domain = parsed.netloc
            
            if domain != current_app.config['SERVER_NAME']:
                return {'error': 'Domain does not match this server'}, 404
                
            # Extract actor name from path
            path_parts = parsed.path.strip('/').split('/')
            if len(path_parts) >= 2 and path_parts[0] in ['u', 'c']:
                actor_name = path_parts[1]
            else:
                return {'error': 'Invalid URL format'}, 400
        else:
            return {'error': 'Resource must be an acct: URI or HTTPS URL'}, 400
            
    except Exception as e:
        current_app.logger.error(f"Error parsing WebFinger resource: {e}")
        return {'error': 'Invalid resource format'}, 400
    
    # Look up the actor (user or community)
    actor: Optional[Union[User, Community]] = None
    actor_type: Optional[str] = None
    
    # Try user first
    user = User.query.filter_by(
        user_name=actor_name,
        ap_id=None,  # Local users only
        deleted=False,
        banned=False
    ).first()
    
    if user:
        actor = user
        actor_type = 'Person'
    else:
        # Try community
        community = Community.query.filter_by(
            name=actor_name,
            ap_id=None,  # Local communities only
            banned=False
        ).first()
        
        if community:
            actor = community
            actor_type = 'Group'
    
    if not actor:
        return {'error': 'Actor not found'}, 404
    
    # Build the response
    actor_url = actor.public_url()
    
    response = WebFingerResponse(
        subject=resource,
        aliases=[actor_url],
        links=[
            {
                'rel': 'http://webfinger.net/rel/profile-page',
                'type': 'text/html',
                'href': actor_url
            },
            {
                'rel': 'self',
                'type': 'application/activity+json',
                'href': actor_url
            }
        ]
    )
    
    # Add avatar if available
    if hasattr(actor, 'avatar') and actor.avatar:
        avatar_url = actor.avatar_url()
        if avatar_url:
            response['links'].append({
                'rel': 'http://webfinger.net/rel/avatar',
                'type': 'image/png',  # Adjust based on actual format
                'href': avatar_url
            })
    
    return jsonify(response), 200


@bp.route('/.well-known/host-meta')
@cache.cached(timeout=3600)
def host_meta() -> tuple[str, int, Dict[str, str]]:
    """
    Host-meta endpoint for server metadata.
    
    Provides WebFinger template for client discovery.
    Compatible with older federation implementations.
    
    Returns:
        XML response with host metadata
    """
    server_name = current_app.config['SERVER_NAME']
    
    xml_response = f'''<?xml version="1.0" encoding="UTF-8"?>
<XRD xmlns="http://docs.oasis-open.org/ns/xri/xrd-1.0">
    <Link rel="lrdd" type="application/xrd+xml" template="https://{server_name}/.well-known/webfinger?resource={{uri}}"/>
</XRD>'''
    
    headers = {
        'Content-Type': 'application/xrd+xml; charset=utf-8',
        'Cache-Control': 'public, max-age=3600'
    }
    
    return xml_response, 200, headers