from flask import Blueprint, current_app, jsonify, request
from flask_smorest import Blueprint as ApiBlueprint
from flask_limiter import RateLimitExceeded
from sqlalchemy.orm.exc import NoResultFound
import sentry_sdk
from werkzeug.exceptions import UnprocessableEntity

# Non-documented routes in swagger UI
bp = Blueprint("api_alpha", __name__)

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

user_bp = ApiBlueprint("User", __name__, url_prefix="/api/alpha", description="")

reply_bp = ApiBlueprint("Comment", __name__, url_prefix="/api/alpha", description="")

post_bp = ApiBlueprint("Post", __name__, url_prefix="/api/alpha", description="")

private_message_bp = ApiBlueprint(
    "Private Message", __name__, url_prefix="/api/alpha", description=""
)

upload_bp = ApiBlueprint("Upload", __name__, url_prefix="/api/alpha", description="")

admin_bp = ApiBlueprint("Admin", __name__, url_prefix="/api/alpha", description="")

# The fork's private-registration admin API gets its OWN blueprint rather than
# sharing upstream's `admin_bp`. That sharing is what broke it:
#
# This fork defined `admin_bp` with url_prefix="/api/alpha/admin". Upstream
# v1.6.9 independently added its own blueprint, same name "Admin", with the
# generic url_prefix="/api/alpha" — its two registration-application routes
# spell "/admin/..." in their decorators instead. Conflict resolution in
# 4c611576 kept upstream's line, and every fork route (whose decorators are
# bare, e.g. "/private_register", on the assumption the prefix supplies
# "/admin") silently moved from /api/alpha/admin/private_register to
# /api/alpha/private_register. Combined with the dropped imports in the same
# commit, the API 404'd in production for five months.
#
# A separate blueprint makes that class of collision impossible: upstream can
# rename or re-prefix `admin_bp` freely without moving the fork's endpoints,
# and the fork's own route decorators stay untouched. Upstream's
# /api/alpha/admin/registration_application/* paths are unaffected.
private_admin_bp = ApiBlueprint(
    "PrivateAdmin",
    __name__,
    url_prefix="/api/alpha/admin",
    description="Administrative endpoints for user management and private registration",
)


def shared_error_handler(e):
    """Shared error handler for all API blueprints"""
    if isinstance(e, RateLimitExceeded):
        response = {"code": 429, "message": str(e), "status": "Bad Request"}
        return jsonify(response), 429
    elif isinstance(e, NoResultFound):
        response = {"code": 400, "message": str(e), "status": "Not found"}
        return jsonify(response), 400
    elif isinstance(e, BlockingIOError):
        response = {"code": 400, "message": str(e), "status": "Bad credentials"}
        return jsonify(response), 400
    elif isinstance(e, UnprocessableEntity):
        # Log using the standard logging mechanism
        if current_app.config["SENTRY_DSN"]:
            sentry_sdk.capture_exception(e)

        response = {
            "code": 400,
            "message": "Validation failed",
            "status": str(e.data["messages"]),
        }
        return jsonify(response), 400
    else:
        if str(e) != "incorrect_login" and str(e) != "No object found.":
            current_app.logger.exception("API exception")
            if current_app.config["SENTRY_DSN"]:
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
blueprints = [
    site_bp,
    misc_bp,
    comm_bp,
    feed_bp,
    topic_bp,
    user_bp,
    reply_bp,
    post_bp,
    private_message_bp,
    upload_bp,
    admin_bp,
    private_admin_bp,
]
for blueprint in blueprints:
    blueprint.errorhandler(Exception)(shared_error_handler)

from app.api.alpha import routes

# These two imports are load-bearing, not decorative. Flask only registers a
# route when its @admin_bp.route decorator actually executes, which requires the
# module to be imported — nothing else in the tree imports either of these.
#
# They were dropped during conflict resolution in 4c611576 ("Merge upstream
# PieFed v1.6.9", 2026-03-06) and stayed missing for five months and six
# upstream merges. The whole private-registration admin API (19 endpoints) was
# live code that 404'd. It went unnoticed because CLAUDE.md's post-merge
# checklist verified `ls app/api/admin/private_registration.py` — the file
# existed the entire time — and because the tests that would have caught it were
# in the CI exclusion list.
#
# The endpoints are gated in depth (app/api/admin/security.py:74): the
# PRIVATE_REGISTRATION_ENABLED feature flag defaults to false, then an IP
# allowlist, then the X-PieFed-Secret header, then a rate limit.
#
# tests/test_admin_api_routes_registered.py asserts these routes exist.
from app.api.admin import routes as admin_routes  # noqa: E402, F401
from app.api.admin import monitoring_routes  # noqa: E402, F401
