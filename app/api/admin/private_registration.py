"""
Private registration implementation for admin API
"""

from flask import current_app
from marshmallow import ValidationError
from werkzeug.security import generate_password_hash

from app import db
from app.api.admin.security import (
    generate_secure_password,
    generate_username_suggestions,
    log_registration_attempt,
    sanitize_user_input,
)
from app.models import User, utcnow


def validate_user_availability(username, email):
    """
    Validate if username and email are available for registration.

    Args:
        username (str): Proposed username
        email (str): Proposed email

    Returns:
        dict: Validation result with availability and suggestions
    """
    result = {
        "username_available": True,
        "email_available": True,
        "username_suggestions": [],
        "validation_errors": {},
    }

    # Check username availability
    existing_user = User.query.filter_by(user_name=username).first()
    if existing_user:
        result["username_available"] = False
        result["username_suggestions"] = generate_username_suggestions(username)
        result["validation_errors"][
            "username"
        ] = f"Username '{username}' is already taken"

    # Check email availability
    existing_email = User.query.filter_by(email=email).first()
    if existing_email:
        result["email_available"] = False
        result["validation_errors"]["email"] = f"Email '{email}' is already registered"

    return result


def create_private_user(user_data):
    """
    Create a new user via private registration.

    Args:
        user_data (dict): User registration data

    Returns:
        dict: Registration result

    Raises:
        ValidationError: If validation fails
        Exception: If user creation fails
    """
    # Sanitize input data
    user_data = sanitize_user_input(user_data)

    # Extract required fields
    username = user_data.get("username")
    email = user_data.get("email")

    # Validate availability
    validation = validate_user_availability(username, email)
    if not validation["username_available"] or not validation["email_available"]:
        error_details = {"field_errors": validation["validation_errors"]}
        if not validation["username_available"]:
            error_details["username_suggestions"] = validation["username_suggestions"]

        log_registration_attempt(username, email, False, "validation_failed")
        raise ValidationError(
            "User validation failed", field_name="validation", details=error_details
        )

    # Generate password if not provided
    password = user_data.get("password")
    generated_password = None
    if not password:
        generated_password = generate_secure_password(16)
        password = generated_password

    # Extract optional fields with defaults
    display_name = user_data.get("display_name", username)
    bio = user_data.get("bio", "")
    timezone = user_data.get("timezone", "UTC")
    auto_activate = user_data.get("auto_activate", True)
    send_welcome_email = user_data.get("send_welcome_email", False)

    try:
        # Create new user
        new_user = User(
            user_name=username,
            email=email,
            title=display_name,
            about=bio,
            password=generate_password_hash(password),
            verified=auto_activate,  # Skip email verification if auto_activate is True
            created=utcnow(),
            instance_id=1,  # Local user
            indexed=True,
            banned=False,
            deleted=False,
            newsletter=False,
            searchable=True,
        )

        # Set timezone if provided
        if timezone != "UTC":
            new_user.timezone = timezone

        db.session.add(new_user)
        db.session.flush()  # Get the user ID

        user_id = new_user.id

        # Send welcome email if requested (implement this based on existing email system)
        if send_welcome_email:
            # TODO: Implement welcome email sending
            current_app.logger.info(
                f"Welcome email requested for user {user_id} but not yet implemented"
            )

        db.session.commit()

        # Log successful registration
        log_registration_attempt(username, email, True, user_id=user_id)

        # Prepare response
        response = {
            "success": True,
            "user_id": user_id,
            "username": username,
            "email": email,
            "display_name": display_name,
            "activation_required": not auto_activate,
            "message": "User created successfully",
        }

        # Include generated password if applicable
        if generated_password:
            response["generated_password"] = generated_password

        current_app.logger.info(
            f"Private registration successful: user_id={user_id}, username={username}"
        )

        return response

    except Exception as e:
        db.session.rollback()
        error_msg = f"User creation failed: {str(e)}"
        current_app.logger.error(error_msg)
        log_registration_attempt(username, email, False, "database_error")
        raise Exception(error_msg)


def get_user_by_lookup(username=None, email=None, user_id=None):
    """
    Look up a user by username, email, or ID.

    Args:
        username (str): Username to search for
        email (str): Email to search for
        user_id (int): User ID to search for

    Returns:
        dict: User lookup result
    """
    user = None

    if user_id:
        user = User.query.filter_by(id=user_id, deleted=False).first()
    elif email:
        user = User.query.filter_by(email=email, deleted=False).first()
    elif username:
        user = User.query.filter_by(user_name=username, deleted=False).first()

    if not user:
        return {"found": False, "user": None}

    # Build user info response
    user_info = {
        "id": user.id,
        "username": user.user_name,
        "email": user.email,
        "display_name": user.title or user.user_name,
        "created_at": user.created.isoformat() if user.created else None,
        "last_seen": user.last_seen.isoformat() if user.last_seen else None,
        "is_verified": user.verified,
        "is_banned": user.banned,
        "is_local": user.instance_id == 1,
        "post_count": user.post_count or 0,
        "comment_count": getattr(user, "comment_count", 0),
        "reputation": user.reputation or 0,
        "bio": user.about or "",
    }

    return {"found": True, "user": user_info}


def list_users(
    local_only=True,
    verified=None,
    active=None,
    search=None,
    sort="created_desc",
    page=1,
    limit=50,
    last_seen_days=None,
):
    """
    List users with filtering and pagination.

    Args:
        local_only (bool): Filter to local users only
        verified (bool): Filter by verification status
        active (bool): Filter by active/banned status
        search (str): Search in username/email
        sort (str): Sort order
        page (int): Page number
        limit (int): Results per page
        last_seen_days (int): Users active within N days

    Returns:
        dict: User list with pagination
    """
    from datetime import timedelta

    # Base query
    query = User.query.filter_by(deleted=False)

    # Apply filters
    if local_only:
        query = query.filter_by(instance_id=1)

    if verified is not None:
        query = query.filter_by(verified=verified)

    if active is not None:
        query = query.filter_by(banned=not active)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(User.user_name.ilike(search_term), User.email.ilike(search_term))
        )

    if last_seen_days:
        cutoff_date = utcnow() - timedelta(days=last_seen_days)
        query = query.filter(User.last_seen > cutoff_date)

    # Apply sorting
    if sort == "created_desc":
        query = query.order_by(User.created.desc())
    elif sort == "created_asc":
        query = query.order_by(User.created.asc())
    elif sort == "username_asc":
        query = query.order_by(User.user_name.asc())
    elif sort == "username_desc":
        query = query.order_by(User.user_name.desc())
    elif sort == "last_seen_desc":
        query = query.order_by(User.last_seen.desc().nullslast())
    elif sort == "last_seen_asc":
        query = query.order_by(User.last_seen.asc().nullsfirst())
    elif sort == "post_count_desc":
        query = query.order_by(User.post_count.desc().nullslast())
    else:
        # Default to created_desc
        query = query.order_by(User.created.desc())

    # Paginate
    paginated = query.paginate(
        page=page, per_page=min(limit, 100), error_out=False
    )  # Cap at 100

    # Build user list
    users = []
    for user in paginated.items:
        user_info = {
            "id": user.id,
            "username": user.user_name,
            "email": user.email,
            "display_name": user.title or user.user_name,
            "created_at": user.created.isoformat() if user.created else None,
            "last_seen": user.last_seen.isoformat() if user.last_seen else None,
            "is_verified": user.verified,
            "is_banned": user.banned,
            "is_local": user.instance_id == 1,
            "post_count": user.post_count or 0,
            "comment_count": getattr(user, "comment_count", 0),
            "reputation": user.reputation or 0,
        }
        users.append(user_info)

    # Build pagination info
    pagination = {
        "page": page,
        "limit": limit,
        "total": paginated.total,
        "total_pages": paginated.pages,
        "has_next": paginated.has_next,
        "has_prev": paginated.has_prev,
    }

    return {"users": users, "pagination": pagination}
