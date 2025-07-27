from flask import Blueprint

bp = Blueprint('admin', __name__)

from app.admin import routes
from app.admin import health_routes

# Register sub-blueprints
bp.register_blueprint(health_routes.bp, url_prefix='/health')
