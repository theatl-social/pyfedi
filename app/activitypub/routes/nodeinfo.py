"""
NodeInfo endpoints for server metadata

This module implements the NodeInfo protocol for sharing server metadata
with other federated instances. Supports both NodeInfo 2.0 and 2.1 standards.

Endpoints:
    - /.well-known/nodeinfo - NodeInfo discovery
    - /nodeinfo/2.0 - NodeInfo 2.0 format
    - /nodeinfo/2.1 - NodeInfo 2.1 format
"""

from __future__ import annotations
from typing import Dict, Any, List, TypedDict, Optional
from flask import jsonify, current_app

from app import db, cache
from app.activitypub.routes import bp
from app.activitypub.util import (
    users_total, active_half_year, active_month,
    local_posts, local_comments, local_communities
)
from app.models import BannedInstances, Instance
from app.utils import get_setting

# Type definitions
class NodeInfoLink(TypedDict):
    """NodeInfo discovery link"""
    rel: str
    href: str


class NodeInfoUsage(TypedDict):
    """Usage statistics"""
    users: Dict[str, int]
    localPosts: int
    localComments: int


class NodeInfoSoftware(TypedDict):
    """Software information"""
    name: str
    version: str
    repository: Optional[str]
    homepage: Optional[str]


class NodeInfoMetadata(TypedDict, total=False):
    """Server metadata"""
    nodeName: str
    nodeDescription: str
    nodeAdmins: List[str]
    federated_instances: Optional[Dict[str, List[str]]]


class NodeInfo20Response(TypedDict):
    """NodeInfo 2.0 response format"""
    version: str
    software: NodeInfoSoftware
    protocols: List[str]
    services: Dict[str, List[str]]
    usage: NodeInfoUsage
    openRegistrations: bool
    metadata: NodeInfoMetadata


class NodeInfo21Response(NodeInfo20Response):
    """NodeInfo 2.1 response format (extends 2.0)"""
    localPosts: int  # Moved from usage in 2.1
    localComments: int  # Moved from usage in 2.1


@bp.route('/.well-known/nodeinfo')
@cache.cached(timeout=3600)
def nodeinfo() -> tuple[Dict[str, Any], int]:
    """
    NodeInfo discovery endpoint.
    
    Provides links to available NodeInfo endpoints. This allows other
    instances to discover which versions of NodeInfo we support.
    
    Returns:
        JSON response with links to NodeInfo endpoints
        
    Example Response:
        {
            "links": [
                {
                    "rel": "http://nodeinfo.diaspora.software/ns/schema/2.0",
                    "href": "https://example.com/nodeinfo/2.0"
                },
                {
                    "rel": "http://nodeinfo.diaspora.software/ns/schema/2.1",
                    "href": "https://example.com/nodeinfo/2.1"
                }
            ]
        }
    """
    server_name = current_app.config['SERVER_NAME']
    
    links = [
        NodeInfoLink(
            rel="http://nodeinfo.diaspora.software/ns/schema/2.0",
            href=f"https://{server_name}/nodeinfo/2.0"
        ),
        NodeInfoLink(
            rel="http://nodeinfo.diaspora.software/ns/schema/2.1",
            href=f"https://{server_name}/nodeinfo/2.1"
        )
    ]
    
    return jsonify({"links": links}), 200


@bp.route('/nodeinfo/2.0')
@bp.route('/nodeinfo/2.0.json')
@cache.cached(timeout=300)
def nodeinfo2() -> tuple[Dict[str, Any], int]:
    """
    NodeInfo 2.0 endpoint.
    
    Provides server metadata in NodeInfo 2.0 format. This includes
    software information, usage statistics, and federation status.
    
    Returns:
        JSON response with server information
        
    Example Response:
        {
            "version": "2.0",
            "software": {
                "name": "pyfedi",
                "version": "0.1.0"
            },
            "protocols": ["activitypub"],
            "services": {"inbound": [], "outbound": []},
            "usage": {
                "users": {"total": 100, "activeMonth": 50, "activeHalfyear": 75},
                "localPosts": 1000,
                "localComments": 5000
            },
            "openRegistrations": true,
            "metadata": {
                "nodeName": "Example Instance",
                "nodeDescription": "A PyFedi instance"
            }
        }
    """
    # Get server settings
    registration_open = get_setting('registration_open', True)
    node_name = get_setting('name', 'PyFedi Instance')
    node_description = get_setting('description', 'A federated community platform')
    
    # Build response
    response = NodeInfo20Response(
        version="2.0",
        software={
            "name": "pyfedi",
            "version": current_app.config.get('VERSION', '0.1.0'),
            "repository": "https://github.com/PieFed/pyfedi",
            "homepage": "https://piefed.com"
        },
        protocols=["activitypub"],
        services={
            "inbound": [],
            "outbound": []
        },
        usage={
            "users": {
                "total": users_total(),
                "activeMonth": active_month(),
                "activeHalfyear": active_half_year()
            },
            "localPosts": local_posts(),
            "localComments": local_comments()
        },
        openRegistrations=registration_open,
        metadata={
            "nodeName": node_name,
            "nodeDescription": node_description
        }
    )
    
    # Add admin information if available
    admin_emails = get_setting('admin_emails', [])
    if admin_emails:
        response['metadata']['nodeAdmins'] = admin_emails
    
    return jsonify(response), 200


@bp.route('/nodeinfo/2.1')
@bp.route('/nodeinfo/2.1.json')
@cache.cached(timeout=300)
def nodeinfo21() -> tuple[Dict[str, Any], int]:
    """
    NodeInfo 2.1 endpoint.
    
    Provides server metadata in NodeInfo 2.1 format. This extends 2.0
    with additional fields and slightly different structure.
    
    Key differences from 2.0:
        - localPosts and localComments moved to top level
        - Additional metadata fields supported
        
    Returns:
        JSON response with server information
    """
    # Get base data from 2.0
    base_response, _ = nodeinfo2()
    base_data = base_response.get_json()
    
    # Transform to 2.1 format
    response = NodeInfo21Response(
        version="2.1",
        software=base_data['software'],
        protocols=base_data['protocols'],
        services=base_data['services'],
        usage={
            "users": base_data['usage']['users']
        },
        localPosts=base_data['usage']['localPosts'],
        localComments=base_data['usage']['localComments'],
        openRegistrations=base_data['openRegistrations'],
        metadata=base_data['metadata']
    )
    
    # Add federated instances information
    if get_setting('show_federation_info', True):
        linked_instances = Instance.query.filter(
            Instance.dormant == False,
            Instance.gone_forever == False
        ).count()
        
        blocked_count = BannedInstances.query.count()
        
        response['metadata']['federated_instances'] = {
            'linked': linked_instances,
            'blocked': blocked_count
        }
    
    return jsonify(response), 200


def get_server_capabilities() -> Dict[str, Any]:
    """
    Get detailed server capabilities for extended NodeInfo.
    
    This function collects additional server capabilities that might
    be useful for other instances to know about.
    
    Returns:
        Dictionary of server capabilities
        
    Example:
        >>> caps = get_server_capabilities()
        >>> print(caps['features'])
        ['groups', 'markdown', 'polls', 'emoji_reactions']
    """
    capabilities = {
        'features': [
            'groups',  # Community support
            'markdown',  # Markdown formatting
            'polls',  # Poll support
            'emoji_reactions',  # Custom emoji reactions
            'moderation',  # Moderation tools
            'reports',  # Reporting system
        ],
        'limits': {
            'max_post_length': get_setting('max_post_length', 50000),
            'max_comment_length': get_setting('max_comment_length', 10000),
            'max_media_size': get_setting('max_media_size', 10485760),  # 10MB
            'allowed_media_types': [
                'image/jpeg',
                'image/png',
                'image/gif',
                'image/webp',
                'video/mp4',
                'video/webm'
            ]
        },
        'federation': {
            'enabled': True,
            'protocols': ['activitypub'],
            'software_families': [
                'lemmy',
                'mastodon',
                'piefed',
                'kbin',
                'peertube'
            ]
        }
    }
    
    return capabilities