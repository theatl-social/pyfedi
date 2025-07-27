"""
Federation Monitoring Module

Provides web-based monitoring dashboard and API endpoints for
tracking the status of the Redis Streams federation system.

Components:
    - Dashboard routes for web UI
    - API endpoints for status data
    - Real-time statistics
    - Queue monitoring
    - Error tracking
"""

from flask import Blueprint

bp = Blueprint('monitoring', __name__, 
               template_folder='templates',
               static_folder='static',
               url_prefix='/monitoring')

from app.monitoring import routes