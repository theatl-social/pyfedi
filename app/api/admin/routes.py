"""
Admin API routes with full OpenAPI documentation
"""
from flask import request, current_app, jsonify
from marshmallow import ValidationError
from werkzeug.exceptions import BadRequest, Unauthorized, Forbidden, TooManyRequests
from app.api.alpha import admin_bp
from app.api.alpha.schema import (
    AdminPrivateRegistrationRequest,
    AdminPrivateRegistrationResponse,
    AdminPrivateRegistrationError,
    AdminUserValidationRequest,
    AdminUserValidationResponse,
    AdminUserListRequest,
    AdminUserListResponse,
    AdminUserLookupRequest,
    AdminUserLookupResponse,
    AdminHealthResponse,
    # Phase 2 schemas
    AdminUserUpdateRequest,
    AdminUserUpdateResponse,
    AdminUserActionRequest,
    AdminUserActionResponse,
    AdminBulkUserRequest,
    AdminBulkUserResponse,
    AdminUserStatsResponse,
    AdminRegistrationStatsRequest,
    AdminRegistrationStatsResponse,
    AdminUserExportRequest,
    AdminUserExportResponse
)
from app.api.admin.security import require_private_registration_auth
from app.api.admin.monitoring import track_admin_request, check_advanced_rate_limit
from app.api.admin.private_registration import (
    create_private_user,
    validate_user_availability,
    get_user_by_lookup,
    list_users
)
from app.api.admin.user_management import (
    update_user,
    perform_user_action,
    bulk_user_operations,
    get_user_statistics,
    get_registration_statistics,
    export_user_data
)
from app.utils import is_private_registration_enabled
from datetime import datetime


@admin_bp.route('/private_register', methods=['POST'])
@admin_bp.doc(
    summary="Create user via private registration",
    description="""
    Create a new user account using private registration with secret authentication.
    
    This endpoint requires:
    - X-PieFed-Secret header with valid secret
    - Optional IP whitelist validation
    - Rate limiting protection
    
    Features:
    - Automatic password generation if not provided
    - Optional email verification bypass
    - Comprehensive input validation
    - Audit logging of all attempts
    """,
    security=[{"PrivateRegistrationSecret": []}]
)
@admin_bp.arguments(AdminPrivateRegistrationRequest, location="json")
@admin_bp.response(201, AdminPrivateRegistrationResponse, 
                   description="User created successfully")
@admin_bp.alt_response(400, AdminPrivateRegistrationError, 
                       description="Validation error or user already exists")
@admin_bp.alt_response(401, AdminPrivateRegistrationError, 
                       description="Invalid secret")
@admin_bp.alt_response(403, AdminPrivateRegistrationError, 
                       description="Feature disabled or IP not authorized")
@admin_bp.alt_response(429, AdminPrivateRegistrationError, 
                       description="Rate limit exceeded")
@require_private_registration_auth
@track_admin_request('private_register', 'POST')
def create_private_user_endpoint(json_data):
    """Create a new user via private registration"""
    # Apply advanced rate limiting
    check_advanced_rate_limit('private_registration')
    
    try:
        result = create_private_user(json_data)
        return result, 201
        
    except ValidationError as e:
        error_response = {
            'success': False,
            'error': 'validation_failed',
            'message': 'User validation failed',
            'details': getattr(e, 'details', {})
        }
        return error_response, 400
        
    except Exception as e:
        current_app.logger.error(f"Private registration error: {str(e)}")
        error_response = {
            'success': False,
            'error': 'user_creation_failed',
            'message': 'Failed to create user',
            'details': {'error': str(e)}
        }
        return error_response, 400


@admin_bp.route('/user/validate', methods=['POST'])
@admin_bp.doc(
    summary="Validate username and email availability",
    description="""
    Check if proposed username and email are available for registration.
    Returns availability status and alternative username suggestions if needed.
    """,
    security=[{"PrivateRegistrationSecret": []}]
)
@admin_bp.arguments(AdminUserValidationRequest, location="json")
@admin_bp.response(200, AdminUserValidationResponse,
                   description="Validation result")
@admin_bp.alt_response(401, AdminPrivateRegistrationError,
                       description="Invalid secret")
@admin_bp.alt_response(403, AdminPrivateRegistrationError,
                       description="Feature disabled or IP not authorized")
@require_private_registration_auth
def validate_user_endpoint(json_data):
    """Validate username and email availability"""
    username = json_data.get('username')
    email = json_data.get('email')
    
    result = validate_user_availability(username, email)
    return result, 200


@admin_bp.route('/users', methods=['GET'])
@admin_bp.doc(
    summary="List users with filtering and pagination",
    description="""
    Retrieve a paginated list of users with optional filtering.
    
    Supports filtering by:
    - Local vs remote users
    - Verification status
    - Active/banned status
    - Username/email search
    - Activity within timeframe
    
    Supports sorting by various fields with pagination.
    """,
    security=[{"PrivateRegistrationSecret": []}]
)
@admin_bp.arguments(AdminUserListRequest, location="query")
@admin_bp.response(200, AdminUserListResponse,
                   description="User list with pagination")
@admin_bp.alt_response(401, AdminPrivateRegistrationError,
                       description="Invalid secret")
@admin_bp.alt_response(403, AdminPrivateRegistrationError,
                       description="Feature disabled or IP not authorized")
@require_private_registration_auth
def list_users_endpoint(query_args):
    """List users with filtering and pagination"""
    result = list_users(
        local_only=query_args.get('local_only', True),
        verified=query_args.get('verified'),
        active=query_args.get('active'),
        search=query_args.get('search'),
        sort=query_args.get('sort', 'created_desc'),
        page=query_args.get('page', 1),
        limit=query_args.get('limit', 50),
        last_seen_days=query_args.get('last_seen_days')
    )
    return result, 200


@admin_bp.route('/user/lookup', methods=['GET'])
@admin_bp.doc(
    summary="Look up specific user",
    description="""
    Find a specific user by username, email, or ID.
    Returns detailed user information if found.
    """,
    security=[{"PrivateRegistrationSecret": []}]
)
@admin_bp.arguments(AdminUserLookupRequest, location="query")
@admin_bp.response(200, AdminUserLookupResponse,
                   description="User lookup result")
@admin_bp.alt_response(401, AdminPrivateRegistrationError,
                       description="Invalid secret")
@admin_bp.alt_response(403, AdminPrivateRegistrationError,
                       description="Feature disabled or IP not authorized")
@require_private_registration_auth
def lookup_user_endpoint(query_args):
    """Look up user by username, email, or ID"""
    result = get_user_by_lookup(
        username=query_args.get('username'),
        email=query_args.get('email'),
        user_id=query_args.get('id')
    )
    return result, 200


@admin_bp.route('/health', methods=['GET'])
@admin_bp.doc(
    summary="Admin API health check",
    description="""
    Check the health and configuration of the admin API system.
    Returns status of private registration feature and basic statistics.
    """,
    security=[{"PrivateRegistrationSecret": []}]
)
@admin_bp.response(200, AdminHealthResponse,
                   description="Health check result")
@admin_bp.alt_response(401, AdminPrivateRegistrationError,
                       description="Invalid secret")
@require_private_registration_auth
def health_check_endpoint():
    """Health check for admin API"""
    from app.utils import (
        get_private_registration_allowed_ips,
        get_private_registration_rate_limit
    )
    
    # Basic health info
    health_info = {
        'private_registration': {
            'enabled': is_private_registration_enabled(),
            'rate_limit_configured': bool(get_private_registration_rate_limit()),
            'ip_whitelist_configured': bool(get_private_registration_allowed_ips()),
            'stats_24h': {
                'total_attempts': 0,  # TODO: Implement stats collection
                'successful': 0,
                'failed': 0,
                'success_rate': 0.0
            }
        },
        'database': 'healthy',  # TODO: Add actual DB health check
        'timestamp': datetime.utcnow().isoformat()
    }
    
    return health_info, 200


# Error handlers for admin blueprint
@admin_bp.errorhandler(Unauthorized)
def handle_unauthorized(error):
    return {
        'success': False,
        'error': 'invalid_secret',
        'message': 'Invalid authentication secret',
        'details': {}
    }, 401


@admin_bp.errorhandler(Forbidden)
def handle_forbidden(error):
    return {
        'success': False,
        'error': 'feature_disabled' if 'disabled' in str(error) else 'ip_unauthorized',
        'message': str(error),
        'details': {}
    }, 403


@admin_bp.errorhandler(TooManyRequests)
def handle_rate_limit(error):
    return {
        'success': False,
        'error': 'rate_limited',
        'message': 'Rate limit exceeded',
        'details': {}
    }, 429


@admin_bp.errorhandler(BadRequest)
def handle_bad_request(error):
    return {
        'success': False,
        'error': 'bad_request',
        'message': 'Invalid request format',
        'details': {}
    }, 400


# Phase 2: User Management Endpoints

@admin_bp.route('/user/<int:user_id>', methods=['PUT'])
@admin_bp.doc(
    summary="Update user profile",
    description="""
    Update user profile information including display name, bio, email, and settings.
    Only provided fields will be updated. Email must be unique.
    """,
    security=[{"PrivateRegistrationSecret": []}]
)
@admin_bp.arguments(AdminUserUpdateRequest, location="json")
@admin_bp.response(200, AdminUserUpdateResponse, description="User updated successfully")
@admin_bp.alt_response(400, AdminPrivateRegistrationError, description="Validation error")
@admin_bp.alt_response(401, AdminPrivateRegistrationError, description="Invalid secret")
@admin_bp.alt_response(404, AdminPrivateRegistrationError, description="User not found")
@require_private_registration_auth
def update_user_endpoint(json_data, user_id):
    """Update user profile information"""
    try:
        result = update_user(user_id, json_data)
        return result, 200
    except ValueError as e:
        return {
            'success': False,
            'error': 'validation_failed',
            'message': str(e),
            'details': {}
        }, 400 if 'not found' not in str(e) else 404


@admin_bp.route('/user/<int:user_id>/disable', methods=['POST'])
@admin_bp.doc(
    summary="Disable user account",
    description="""
    Disable a user account. Disabled users cannot log in or perform actions.
    Reason is optional but recommended for audit purposes.
    """,
    security=[{"PrivateRegistrationSecret": []}]
)
@admin_bp.arguments(AdminUserActionRequest, location="json")
@admin_bp.response(200, AdminUserActionResponse, description="User disabled successfully")
@admin_bp.alt_response(400, AdminPrivateRegistrationError, description="User already disabled or other error")
@require_private_registration_auth
def disable_user_endpoint(json_data, user_id):
    """Disable user account"""
    try:
        result = perform_user_action(
            user_id, 'disable',
            reason=json_data.get('reason'),
            expires_at=json_data.get('expires_at'),
            notify_user=json_data.get('notify_user', False)
        )
        return result, 200
    except ValueError as e:
        return {
            'success': False,
            'error': 'action_failed',
            'message': str(e),
            'details': {}
        }, 400


@admin_bp.route('/user/<int:user_id>/enable', methods=['POST'])
@admin_bp.doc(
    summary="Enable user account",
    description="Re-enable a previously disabled user account.",
    security=[{"PrivateRegistrationSecret": []}]
)
@admin_bp.response(200, AdminUserActionResponse, description="User enabled successfully")
@admin_bp.alt_response(400, AdminPrivateRegistrationError, description="User already enabled or other error")
@require_private_registration_auth
def enable_user_endpoint(user_id):
    """Enable user account"""
    try:
        result = perform_user_action(user_id, 'enable')
        return result, 200
    except ValueError as e:
        return {
            'success': False,
            'error': 'action_failed',
            'message': str(e),
            'details': {}
        }, 400


@admin_bp.route('/user/<int:user_id>/ban', methods=['POST'])
@admin_bp.doc(
    summary="Ban user account",
    description="""
    Ban a user account. Banned users cannot access the platform.
    Reason is strongly recommended for audit and legal purposes.
    """,
    security=[{"PrivateRegistrationSecret": []}]
)
@admin_bp.arguments(AdminUserActionRequest, location="json")
@admin_bp.response(200, AdminUserActionResponse, description="User banned successfully")
@admin_bp.alt_response(400, AdminPrivateRegistrationError, description="User already banned or other error")
@require_private_registration_auth
def ban_user_endpoint(json_data, user_id):
    """Ban user account"""
    try:
        result = perform_user_action(
            user_id, 'ban',
            reason=json_data.get('reason'),
            expires_at=json_data.get('expires_at'),
            notify_user=json_data.get('notify_user', False)
        )
        return result, 200
    except ValueError as e:
        return {
            'success': False,
            'error': 'action_failed',
            'message': str(e),
            'details': {}
        }, 400


@admin_bp.route('/user/<int:user_id>/unban', methods=['POST'])
@admin_bp.doc(
    summary="Unban user account",
    description="Remove ban from a previously banned user account.",
    security=[{"PrivateRegistrationSecret": []}]
)
@admin_bp.response(200, AdminUserActionResponse, description="User unbanned successfully")
@admin_bp.alt_response(400, AdminPrivateRegistrationError, description="User not banned or other error")
@require_private_registration_auth
def unban_user_endpoint(user_id):
    """Unban user account"""
    try:
        result = perform_user_action(user_id, 'unban')
        return result, 200
    except ValueError as e:
        return {
            'success': False,
            'error': 'action_failed',
            'message': str(e),
            'details': {}
        }, 400


@admin_bp.route('/user/<int:user_id>', methods=['DELETE'])
@admin_bp.doc(
    summary="Delete user account",
    description="""
    Soft delete a user account. The user data is anonymized but preserved for data integrity.
    This action is irreversible.
    """,
    security=[{"PrivateRegistrationSecret": []}]
)
@admin_bp.arguments(AdminUserActionRequest, location="json")
@admin_bp.response(200, AdminUserActionResponse, description="User deleted successfully")
@admin_bp.alt_response(400, AdminPrivateRegistrationError, description="User already deleted or other error")
@require_private_registration_auth
def delete_user_endpoint(json_data, user_id):
    """Soft delete user account"""
    try:
        result = perform_user_action(
            user_id, 'delete',
            reason=json_data.get('reason'),
            notify_user=json_data.get('notify_user', False)
        )
        return result, 200
    except ValueError as e:
        return {
            'success': False,
            'error': 'action_failed',
            'message': str(e),
            'details': {}
        }, 400


@admin_bp.route('/users/bulk', methods=['POST'])
@admin_bp.doc(
    summary="Bulk user operations",
    description="""
    Perform operations on multiple users at once. Supports disable, enable, ban, unban, delete.
    Maximum 100 users per request. Results include per-user success/failure status.
    """,
    security=[{"PrivateRegistrationSecret": []}]
)
@admin_bp.arguments(AdminBulkUserRequest, location="json")
@admin_bp.response(200, AdminBulkUserResponse, description="Bulk operation completed")
@admin_bp.alt_response(400, AdminPrivateRegistrationError, description="Invalid request or too many users")
@require_private_registration_auth
@track_admin_request('users_bulk', 'POST')
def bulk_user_operations_endpoint(json_data):
    """Perform bulk operations on users"""
    # Apply strict rate limiting for bulk operations
    check_advanced_rate_limit('bulk_operations')
    
    try:
        result = bulk_user_operations(
            operation=json_data['operation'],
            user_ids=json_data['user_ids'],
            reason=json_data.get('reason'),
            notify_users=json_data.get('notify_users', False)
        )
        return result, 200
    except ValueError as e:
        return {
            'success': False,
            'error': 'bulk_operation_failed',
            'message': str(e),
            'details': {}
        }, 400


@admin_bp.route('/stats/users', methods=['GET'])
@admin_bp.doc(
    summary="Get user statistics",
    description="""
    Comprehensive user statistics including totals, activity, and registration metrics.
    Provides insights into user base composition and engagement.
    """,
    security=[{"PrivateRegistrationSecret": []}]
)
@admin_bp.response(200, AdminUserStatsResponse, description="User statistics")
@require_private_registration_auth
@track_admin_request('stats_users', 'GET')
def user_statistics_endpoint():
    """Get comprehensive user statistics"""
    # Apply rate limiting for statistics
    check_advanced_rate_limit('statistics')
    
    try:
        result = get_user_statistics()
        return result, 200
    except Exception as e:
        current_app.logger.error(f"Error getting user statistics: {str(e)}")
        return {
            'success': False,
            'error': 'stats_failed',
            'message': 'Failed to retrieve user statistics',
            'details': {}
        }, 500


@admin_bp.route('/stats/registrations', methods=['GET'])
@admin_bp.doc(
    summary="Get registration statistics",
    description="""
    Detailed registration analytics over time with daily/hourly breakdowns.
    Useful for understanding growth patterns and peak registration times.
    """,
    security=[{"PrivateRegistrationSecret": []}]
)
@admin_bp.arguments(AdminRegistrationStatsRequest, location="query")
@admin_bp.response(200, AdminRegistrationStatsResponse, description="Registration statistics")
@require_private_registration_auth
def registration_statistics_endpoint(query_args):
    """Get detailed registration statistics"""
    try:
        result = get_registration_statistics(
            days=query_args.get('days', 30),
            include_hourly=query_args.get('include_hourly', False)
        )
        return result, 200
    except Exception as e:
        current_app.logger.error(f"Error getting registration statistics: {str(e)}")
        return {
            'success': False,
            'error': 'stats_failed',
            'message': 'Failed to retrieve registration statistics',
            'details': {}
        }, 500


@admin_bp.route('/users/export', methods=['POST'])
@admin_bp.doc(
    summary="Export user data",
    description="""
    Export user data in CSV or JSON format with customizable fields and filters.
    Returns a temporary download URL that expires after 24 hours.
    """,
    security=[{"PrivateRegistrationSecret": []}]
)
@admin_bp.arguments(AdminUserExportRequest, location="json")
@admin_bp.response(200, AdminUserExportResponse, description="Export prepared successfully")
@admin_bp.alt_response(400, AdminPrivateRegistrationError, description="Invalid export request")
@require_private_registration_auth
def export_users_endpoint(json_data):
    """Export user data"""
    try:
        result = export_user_data(
            format_type=json_data.get('format', 'csv'),
            export_fields=json_data.get('export_fields'),
            filters=json_data.get('filters')
        )
        return result, 200
    except Exception as e:
        current_app.logger.error(f"Error exporting user data: {str(e)}")
        return {
            'success': False,
            'error': 'export_failed',
            'message': 'Failed to export user data',
            'details': {'error': str(e)}
        }, 500