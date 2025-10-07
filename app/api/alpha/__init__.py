from flask import Blueprint, current_app, jsonify, request
from flask_smorest import Blueprint as ApiBlueprint
from flask_limiter import RateLimitExceeded
from sqlalchemy.orm.exc import NoResultFound
from marshmallow import ValidationError
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
    elif isinstance(e, ValidationError):
        # Enhance validation error messages with provided values so we can compare what was provided with what is required
        enhanced_messages = {}
        
        for field, messages in e.messages.items():
            enhanced_messages[field] = []
            provided_value = _get_provided_value(field)
            
            for message in messages:
                if provided_value is not None:
                    enhanced_message = f"{message} (provided: '{provided_value}')"
                else:
                    enhanced_message = message
                enhanced_messages[field].append(enhanced_message)
        
        # Create an enhanced exception message that includes provided values
        enhanced_exception_msg = f"ValidationError: {enhanced_messages}"
        
        # Log using the standard logging mechanism
        current_app.logger.exception(f"API validation error: {enhanced_exception_msg}")
        if current_app.config['SENTRY_DSN']:
            sentry_sdk.capture_exception(e)
        
        response = {"code": 400, "message": "Validation failed", "errors": enhanced_messages, "status": "Unprocessable Entity"}
        return jsonify(response), 422
    else:
        if str(e) != 'incorrect_login' and str(e) != 'No object found.':
            current_app.logger.exception("API exception")
            if current_app.config['SENTRY_DSN']:
                sentry_sdk.capture_exception(e)
        response = {"code": 400, "message": str(e), "status": "Bad Request"}
        return jsonify(response), 400


def _get_provided_value(field):
    """Helper function to extract the provided value for a field from request data"""
    try:
        # Check different request data sources
        if request.json and field in request.json:
            return request.json[field]
        elif request.form and field in request.form:
            return request.form[field]
        elif request.args and field in request.args:
            return request.args[field]
        return None
    except Exception:
        return None


# Register the shared error handler for all blueprints
blueprints = [site_bp, misc_bp, comm_bp, feed_bp, topic_bp, user_bp, reply_bp, post_bp, private_message_bp, upload_bp]
for blueprint in blueprints:
    blueprint.errorhandler(Exception)(shared_error_handler)

from app.api.alpha import routes
