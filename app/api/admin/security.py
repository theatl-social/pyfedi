"""
Security utilities for admin API endpoints
"""

import hmac
import ipaddress
import secrets
from functools import wraps

from flask import current_app, g, request
from werkzeug.exceptions import Forbidden, Unauthorized

from app.utils import (
    get_private_registration_allowed_ips,
    get_private_registration_secret,
    is_private_registration_enabled,
)


def validate_registration_secret(provided_secret):
    """
    Validate private registration secret using constant-time comparison.

    Args:
        provided_secret (str): Secret provided in request header

    Returns:
        bool: True if valid, False otherwise
    """
    expected = get_private_registration_secret()
    if not expected or not provided_secret:
        return False
    return hmac.compare_digest(expected, provided_secret)


def is_ip_whitelisted(client_ip):
    """
    Check if client IP is in allowed IP ranges.

    Args:
        client_ip (str): Client IP address

    Returns:
        bool: True if allowed, False otherwise
    """
    allowed_ranges = get_private_registration_allowed_ips()
    if not allowed_ranges:
        return True  # No IP restrictions configured

    try:
        client_ip_obj = ipaddress.ip_address(client_ip)
        for ip_range in allowed_ranges:
            if client_ip_obj in ipaddress.ip_network(ip_range):
                return True
        return False
    except (ipaddress.AddressValueError, ValueError):
        current_app.logger.warning(f"Invalid IP address or range: {client_ip}")
        return False


def generate_secure_password(length=16):
    """
    Generate cryptographically secure password.

    Args:
        length (int): Password length (default 16)

    Returns:
        str: Secure random password
    """
    return secrets.token_urlsafe(length)


def validate_private_registration_request():
    """
    Validate private registration request with full security checks.

    Raises:
        Forbidden: If feature is disabled or IP not authorized
        Unauthorized: If secret is invalid
        TooManyRequests: If rate limited
    """
    # 1. Feature toggle check
    if not is_private_registration_enabled():
        raise Forbidden("Private registration is disabled")

    # 2. IP whitelist validation
    client_ip = request.environ.get("HTTP_X_FORWARDED_FOR", request.remote_addr)
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    if not is_ip_whitelisted(client_ip):
        current_app.logger.warning(f"Unauthorized IP attempted private registration: {client_ip}")
        raise Forbidden("IP not authorized for private registration")

    # 3. Secret validation
    provided_secret = request.headers.get("X-PieFed-Secret")
    if not validate_registration_secret(provided_secret):
        current_app.logger.warning(f"Invalid secret attempted from IP: {client_ip}")
        raise Unauthorized("Invalid authentication secret")

    # Store validated IP for logging
    g.client_ip = client_ip


def require_private_registration_auth(f):
    """
    Decorator to require private registration authentication.

    Usage:
        @require_private_registration_auth
        def my_admin_endpoint():
            # endpoint logic
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        validate_private_registration_request()
        return f(*args, **kwargs)

    return decorated_function


def log_registration_attempt(username, email, success, error_reason=None, user_id=None):
    """
    Log registration attempt for security audit.

    Args:
        username (str): Attempted username
        email (str): Attempted email
        success (bool): Whether registration succeeded
        error_reason (str): Error reason if failed
        user_id (int): Created user ID if successful
    """
    client_ip = getattr(g, "client_ip", request.remote_addr)
    user_agent = request.headers.get("User-Agent", "")

    # Log to application logger
    log_data = {
        "ip": client_ip,
        "username": username,
        "email": email,
        "success": success,
        "error": error_reason,
        "user_id": user_id,
        "user_agent": user_agent[:100] if user_agent else None,  # Truncate long user agents
    }

    if success:
        current_app.logger.info(f"PRIVATE_REG_SUCCESS: {log_data}")
    else:
        current_app.logger.warning(f"PRIVATE_REG_FAILURE: {log_data}")


def generate_username_suggestions(base_username, max_suggestions=3):
    """
    Generate alternative username suggestions if the requested one is taken.

    Args:
        base_username (str): Base username to generate suggestions from
        max_suggestions (int): Maximum number of suggestions

    Returns:
        list: List of suggested usernames
    """
    from app.models import User

    suggestions = []

    for i in range(1, max_suggestions + 10):  # Try more to ensure we get enough
        if len(suggestions) >= max_suggestions:
            break

        suggestion = f"{base_username}{i}"
        if not User.query.filter_by(user_name=suggestion).first():
            suggestions.append(suggestion)

    # Also try with current year if we need more suggestions
    if len(suggestions) < max_suggestions:
        from datetime import datetime

        year = datetime.now().year
        suggestion = f"{base_username}{year}"
        if not User.query.filter_by(user_name=suggestion).first():
            suggestions.append(suggestion)

    return suggestions[:max_suggestions]


def sanitize_user_input(data):
    """
    Sanitize user input to prevent XSS and other attacks.

    Args:
        data (dict): Input data

    Returns:
        dict: Sanitized data
    """
    import html

    sanitized = {}
    for key, value in data.items():
        if isinstance(value, str):
            # HTML escape strings
            sanitized[key] = html.escape(value.strip())
        else:
            sanitized[key] = value

    return sanitized
