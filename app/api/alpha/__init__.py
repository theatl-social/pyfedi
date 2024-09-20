from flask import Blueprint

bp = Blueprint('api_alpha', __name__)

from app.api.alpha import routes
