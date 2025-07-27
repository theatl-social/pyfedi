from flask import Blueprint

bp = Blueprint('admin', __name__)

from app.admin import routes
from app.admin import health_routes
from app.admin import rate_limit_routes
from app.admin import scheduler_routes

# Register sub-blueprints
bp.register_blueprint(health_routes.bp, url_prefix='/health')
bp.register_blueprint(rate_limit_routes.bp, url_prefix='/rate-limits')
bp.register_blueprint(scheduler_routes.bp, url_prefix='/scheduler')
