from flask import Blueprint

bp = Blueprint("instance", __name__)

from app.instance import routes
