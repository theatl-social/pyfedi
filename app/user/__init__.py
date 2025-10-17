from flask import Blueprint, current_app

bp = Blueprint("user", __name__)

from app.user import routes, subscription, passkeys
