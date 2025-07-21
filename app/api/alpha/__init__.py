from flask import Blueprint
from flask_smorest import Blueprint as ApiBlueprint

bp = Blueprint('api_alpha', __name__)
api_bp = ApiBlueprint(
    "alpha_api",
    __name__,
    url_prefix="/api/alpha",
    description="Testing flask_smorest with piefed.",
)

from app.api.alpha import routes
