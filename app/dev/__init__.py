from flask import Blueprint

bp = Blueprint('dev', __name__)

from app.dev import routes
