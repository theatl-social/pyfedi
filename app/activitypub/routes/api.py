"""
API endpoints for instance information and compatibility

This module provides API endpoints that maintain compatibility with
various ActivityPub implementations including Mastodon and Lemmy.

Endpoints:
    - /api/v1/instance - Mastodon-compatible instance info
    - /api/v1/instance/domain_blocks - Domain blocklist
    - /api/v3/site - Lemmy-compatible site info
    - /api/v3/federated_instances - Federation status
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, TypedDict
from flask import jsonify, request, current_app

from app import db, cache
from app.activitypub.routes import bp
from app.activitypub.util import lemmy_site_data
from app.models import BannedInstances, AllowedInstances, Instance, Site, IpBan, utcnow
from app.utils import get_setting, blocked_emails

# Type definitions
class MastodonInstanceInfo(TypedDict):
    """Mastodon-compatible instance information"""
    uri: str
    title: str
    short_description: str
    description: str
    version: str
    urls: Dict[str, str]
    stats: Dict[str, int]
    languages: List[str]
    contact_account: Optional[Dict[str, Any]]


class DomainBlock(TypedDict):
    """Domain block information"""
    domain: str
    digest: str
    severity: str
    comment: Optional[str]


class FederatedInstance(TypedDict):
    """Federated instance information"""
    id: int
    domain: str
    published: str
    updated: Optional[str]
    software: Optional[str]
    version: Optional[str]


@bp.route('/api/v1/instance')
@cache.cached(timeout=300)
def api_v1_instance() -> tuple[Dict[str, Any], int]:
    """
    Mastodon-compatible instance information endpoint.
    
    Provides instance metadata in a format compatible with Mastodon's
    API v1. Used by various clients and tools for instance discovery.
    
    Returns:
        JSON response with instance information
        
    Example Response:
        {
            "uri": "example.com",
            "title": "Example Instance",
            "short_description": "A federated instance",
            "description": "Welcome to our instance!",
            "version": "0.1.0 (compatible; PyFedi)",
            "urls": {"streaming_api": null},
            "stats": {
                "user_count": 100,
                "status_count": 1000,
                "domain_count": 50
            },
            "languages": ["en"],
            "contact_account": null
        }
    """
    site = Site.query.first()
    server_name = current_app.config['SERVER_NAME']
    
    # Get statistics
    from app.activitypub.util import users_total, local_posts
    
    user_count = users_total()
    post_count = local_posts()
    
    # Count known instances
    instance_count = Instance.query.filter(
        Instance.dormant == False,
        Instance.gone_forever == False
    ).count()
    
    response = MastodonInstanceInfo(
        uri=server_name,
        title=site.name if site else 'PyFedi Instance',
        short_description=site.description[:500] if site and site.description else 'A federated community platform',
        description=site.description if site and site.description else 'Welcome to PyFedi!',
        version=f"{current_app.config.get('VERSION', '0.1.0')} (compatible; PyFedi)",
        urls={
            "streaming_api": None  # PyFedi doesn't have streaming
        },
        stats={
            "user_count": user_count,
            "status_count": post_count,
            "domain_count": instance_count
        },
        languages=get_setting('languages', ['en']),
        contact_account=None  # TODO: Implement contact account
    )
    
    return jsonify(response), 200


@bp.route('/api/v1/instance/domain_blocks')
@cache.cached(timeout=3600)
def domain_blocks() -> tuple[List[Dict[str, Any]], int]:
    """
    Get the list of blocked domains (Mastodon-compatible).
    
    Returns public domain blocks for transparency. Can be disabled
    in settings for privacy.
    
    Returns:
        JSON array of domain blocks
        
    Example Response:
        [
            {
                "domain": "spam.example",
                "digest": "a1b2c3...",
                "severity": "suspend",
                "comment": "Spam instance"
            }
        ]
    """
    if not get_setting('show_blocklist', False):
        return jsonify([]), 200
    
    # Get blocked instances
    blocked = BannedInstances.query.order_by(BannedInstances.domain).all()
    
    blocks = []
    for instance in blocked:
        # Create a digest of the domain for privacy
        import hashlib
        digest = hashlib.sha256(instance.domain.encode()).hexdigest()[:12]
        
        block = DomainBlock(
            domain=instance.domain,
            digest=digest,
            severity='suspend',  # PyFedi always suspends blocked instances
            comment=instance.reason if get_setting('show_block_reasons', False) else None
        )
        blocks.append(block)
    
    return jsonify(blocks), 200


@bp.route('/api/is_ip_banned', methods=['POST'])
def api_is_ip_banned() -> tuple[Dict[str, bool], int]:
    """
    Check if an IP address is banned.
    
    Internal API endpoint for checking IP bans. Requires proper
    authentication in production.
    
    Request Body:
        {"ip": "192.168.1.1"}
        
    Returns:
        JSON response with ban status
        
    Example Response:
        {"banned": false}
    """
    data = request.get_json()
    if not data or 'ip' not in data:
        return jsonify({'error': 'IP address required'}), 400
    
    ip_address = data['ip']
    
    # Check if IP is banned
    ip_ban = IpBan.query.filter_by(ip_address=ip_address).first()
    
    if ip_ban:
        # Check if ban has expired
        if ip_ban.banned_until and ip_ban.banned_until < utcnow():
            # Ban has expired, remove it
            db.session.delete(ip_ban)
            db.session.commit()
            return jsonify({'banned': False}), 200
        else:
            return jsonify({'banned': True}), 200
    
    return jsonify({'banned': False}), 200


@bp.route('/api/is_email_banned', methods=['POST'])
def api_is_email_banned() -> tuple[Dict[str, bool], int]:
    """
    Check if an email address/domain is banned.
    
    Internal API endpoint for checking email bans during registration.
    
    Request Body:
        {"email": "user@example.com"}
        
    Returns:
        JSON response with ban status
        
    Example Response:
        {"banned": true}
    """
    data = request.get_json()
    if not data or 'email' not in data:
        return jsonify({'error': 'Email address required'}), 400
    
    email = data['email'].lower()
    
    # Check against blocked email patterns
    for blocked_pattern in blocked_emails():
        if blocked_pattern in email:
            return jsonify({'banned': True}), 200
    
    return jsonify({'banned': False}), 200


@bp.route('/api/v3/site')
@cache.cached(timeout=300)
def lemmy_site() -> tuple[Dict[str, Any], int]:
    """
    Lemmy-compatible site information endpoint.
    
    Provides site metadata in Lemmy's API v3 format for compatibility
    with Lemmy clients and tools.
    
    Returns:
        JSON response with site information in Lemmy format
        
    Note:
        This endpoint wraps the lemmy_site_data() utility function
        which generates the complex Lemmy response format.
    """
    return jsonify(lemmy_site_data()), 200


@bp.route('/api/v3/federated_instances')
@cache.cached(timeout=600)
def lemmy_federated_instances() -> tuple[Dict[str, Any], int]:
    """
    Lemmy-compatible federated instances endpoint.
    
    Lists linked, allowed, and blocked instances in Lemmy's format.
    Used by Lemmy-compatible clients to show federation status.
    
    Returns:
        JSON response with federation information
        
    Example Response:
        {
            "federated_instances": {
                "linked": [
                    {"id": 1, "domain": "example.com", "published": "2024-01-01T00:00:00Z"},
                    ...
                ],
                "allowed": [...],
                "blocked": [...]
            }
        }
    """
    # Get linked instances (active, not dormant/gone)
    linked = Instance.query.filter(
        Instance.id != 1,  # Exclude local instance
        Instance.dormant == False,
        Instance.gone_forever == False
    ).order_by(Instance.domain).all()
    
    linked_list = []
    for instance in linked:
        inst_data = FederatedInstance(
            id=instance.id,
            domain=instance.domain,
            published=instance.created_at.isoformat() + 'Z' if instance.created_at else '2024-01-01T00:00:00Z',
            updated=instance.updated_at.isoformat() + 'Z' if instance.updated_at else None,
            software=instance.software,
            version=instance.version
        )
        linked_list.append(inst_data)
    
    # Get allowed instances (if in allowlist mode)
    allowed_list = []
    if get_setting('allowlist_enabled', False):
        allowed = AllowedInstances.query.order_by(AllowedInstances.domain).all()
        for instance in allowed:
            allowed_list.append({
                'id': instance.id,
                'domain': instance.domain,
                'published': instance.created_at.isoformat() + 'Z' if hasattr(instance, 'created_at') else '2024-01-01T00:00:00Z'
            })
    
    # Get blocked instances
    blocked_list = []
    if get_setting('show_blocklist', False):
        blocked = BannedInstances.query.order_by(BannedInstances.domain).all()
        for instance in blocked:
            blocked_list.append({
                'id': instance.id,
                'domain': instance.domain,
                'published': instance.created_at.isoformat() + 'Z',
                'reason': instance.reason if get_setting('show_block_reasons', False) else None
            })
    
    response = {
        'federated_instances': {
            'linked': linked_list,
            'allowed': allowed_list if allowed_list else None,
            'blocked': blocked_list if blocked_list else None
        }
    }
    
    return jsonify(response), 200