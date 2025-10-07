from flask import Blueprint, current_app, jsonify
from flask_smorest import Blueprint as ApiBlueprint
from flask_limiter import RateLimitExceeded
from sqlalchemy.orm.exc import NoResultFound
import sentry_sdk

# Non-documented routes in swagger UI
bp = Blueprint('api_alpha', __name__)

# Different blueprints to organize different api namespaces
site_bp = ApiBlueprint(
    "Site",
    __name__,
    url_prefix="/api/alpha",
    description="",
)

misc_bp = ApiBlueprint(
    "Misc",
    __name__,
    url_prefix="/api/alpha",
    description="",
)

comm_bp = ApiBlueprint(
    "Community",
    __name__,
    url_prefix="/api/alpha",
    description="",
)

feed_bp = ApiBlueprint(
    "Feed",
    __name__,
    url_prefix="/api/alpha",
    description="",
)

topic_bp = ApiBlueprint(
    "Topic",
    __name__,
    url_prefix="/api/alpha",
    description="",
)

user_bp = ApiBlueprint(
    "User",
    __name__,
    url_prefix="/api/alpha",
    description=""
)

reply_bp = ApiBlueprint(
    "Comment",
    __name__,
    url_prefix="/api/alpha",
    description=""
)

post_bp = ApiBlueprint(
    "Post",
    __name__,
    url_prefix="/api/alpha",
    description=""
)

private_message_bp = ApiBlueprint(
    "Private Message",
    __name__,
    url_prefix="/api/alpha",
    description=""
)

upload_bp = ApiBlueprint(
    "Upload",
    __name__,
    url_prefix="/api/alpha",
    description=""
)


def shared_error_handler(e):
    """Shared error handler for all API blueprints"""
    if isinstance(e, RateLimitExceeded):
        response = {"code": 429, "message": str(e), "status": "Bad Request"}
        return jsonify(response), 429
    elif isinstance(e, NoResultFound):
        response = {"code": 429, "message": str(e), "status": "Bad credentials"}
        return jsonify(response), 400
    else:
        if str(e) != 'incorrect_login' and str(e) != 'No object found.':
            current_app.logger.exception("API exception")
            if current_app.config['SENTRY_DSN']:
                sentry_sdk.capture_exception(e)
        response = {"code": 400, "message": str(e), "status": "Bad Request"}
        return jsonify(response), 400


# Register the shared error handler for all blueprints
blueprints = [site_bp, misc_bp, comm_bp, feed_bp, topic_bp, user_bp, reply_bp, post_bp, private_message_bp, upload_bp]
for blueprint in blueprints:
    blueprint.errorhandler(Exception)(shared_error_handler)

from app.api.alpha import routes
