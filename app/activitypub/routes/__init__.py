"""
ActivityPub Routes Package

This package contains all ActivityPub protocol endpoints organized by functionality.
Each module handles a specific aspect of the ActivityPub protocol with full type safety.

Modules:
    - webfinger: WebFinger and host-meta endpoints for actor discovery
    - nodeinfo: NodeInfo endpoints for server metadata
    - actors: Actor profiles and collections (users, communities)
    - inbox: Inbox endpoints for receiving activities
    - outbox: Outbox endpoints for activity distribution
    - api: API endpoints for instance information
    - debug: Debug endpoints for development (disabled in production)
    - helpers: Shared utility functions

Example:
    >>> from app.activitypub.routes import register_routes
    >>> register_routes(app)
"""

from flask import Blueprint
from typing import Optional

# Create the main ActivityPub blueprint
bp = Blueprint('activitypub', __name__)

# Import all route modules to register them
from . import (
    webfinger,
    nodeinfo,
    actors,
    inbox,
    outbox,
    api,
    debug,
)


def register_routes(app) -> None:
    """
    Register all ActivityPub routes with the Flask application.
    
    Args:
        app: Flask application instance
    """
    app.register_blueprint(bp)