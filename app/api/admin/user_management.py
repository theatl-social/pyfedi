"""
User management implementation for admin API Phase 2
"""

from datetime import datetime, timedelta

from flask import current_app, g
from sqlalchemy import and_

from app import db
from app.api.admin.security import sanitize_user_input
from app.models import User, utcnow


def update_user(user_id, update_data):
    """
    Update user profile information.

    Args:
        user_id (int): User ID to update
        update_data (dict): Fields to update

    Returns:
        dict: Update result

    Raises:
        ValueError: If user not found or validation fails
    """
    # Sanitize input data
    update_data = sanitize_user_input(update_data)

    # Find user
    user = User.query.filter_by(id=user_id, deleted=False).first()
    if not user:
        raise ValueError(f"User {user_id} not found")

    # Validate email uniqueness if changing
    if "email" in update_data:
        existing = User.query.filter(
            and_(
                User.email == update_data["email"],
                User.id != user_id,
                User.deleted is False,
            )
        ).first()
        if existing:
            raise ValueError(f"Email '{update_data['email']}' is already in use")

    # Track updated fields
    updated_fields = []

    try:
        # Update allowed fields
        if "display_name" in update_data:
            user.title = update_data["display_name"]
            updated_fields.append("display_name")

        if "bio" in update_data:
            user.about = update_data["bio"]
            updated_fields.append("bio")

        if "timezone" in update_data:
            user.timezone = update_data["timezone"]
            updated_fields.append("timezone")

        if "email" in update_data:
            user.email = update_data["email"]
            updated_fields.append("email")

        if "verified" in update_data:
            user.verified = update_data["verified"]
            updated_fields.append("verified")

        if "newsletter" in update_data:
            user.newsletter = update_data["newsletter"]
            updated_fields.append("newsletter")

        if "searchable" in update_data:
            user.searchable = update_data["searchable"]
            updated_fields.append("searchable")

        db.session.commit()

        # Log update (handle testing context gracefully)
        try:
            current_app.logger.info(
                f"User {user_id} updated by admin. Fields: {updated_fields}"
            )
        except RuntimeError:
            pass  # No logging outside Flask context

        return {
            "success": True,
            "user_id": user_id,
            "message": f"User updated successfully. Fields modified: {', '.join(updated_fields)}",
            "updated_fields": updated_fields,
        }

    except Exception as e:
        db.session.rollback()
        try:
            current_app.logger.error(f"Failed to update user {user_id}: {str(e)}")
        except RuntimeError:
            pass  # No logging outside Flask context
        raise ValueError(f"Failed to update user: {str(e)}")


def perform_user_action(
    user_id, action, reason=None, expires_at=None, notify_user=False
):
    """
    Perform administrative action on user (ban, disable, etc).

    Args:
        user_id (int): User ID
        action (str): Action to perform
        reason (str): Reason for action
        expires_at (datetime): Optional expiry
        notify_user (bool): Send notification

    Returns:
        dict: Action result
    """
    user = User.query.filter_by(id=user_id, deleted=False).first()
    if not user:
        raise ValueError(f"User {user_id} not found")

    # Handle Flask context gracefully for testing
    try:
        admin_user = getattr(g, "admin_user", "system")
    except RuntimeError:
        admin_user = "system"  # For testing outside Flask context
    timestamp = utcnow()

    try:
        if action == "ban":
            if user.banned:
                raise ValueError("User is already banned")
            user.banned = True
            message = f"User banned. Reason: {reason}" if reason else "User banned"

        elif action == "unban":
            if not user.banned:
                raise ValueError("User is not banned")
            user.banned = False
            message = "User unbanned"

        elif action == "disable":
            if not user.verified:
                raise ValueError("User is already disabled")
            user.verified = False
            message = f"User disabled. Reason: {reason}" if reason else "User disabled"

        elif action == "enable":
            if user.verified:
                raise ValueError("User is already enabled")

            # Check if user was created via private registration without auto_activate
            # In this case, we need to call finalize_user_setup() to set up AP keys
            needs_finalization = not user.ap_profile_id or not user.private_key

            user.verified = True

            # Finalize user setup if needed (AP keys, profile URLs)
            if needs_finalization:
                from app.utils import finalize_user_setup

                finalize_user_setup(user)
                message = "User enabled and finalized (AP keys generated)"
            else:
                message = "User enabled"

        elif action == "delete":
            user.deleted = True
            user.user_name = f"deleted_{user.id}_{int(timestamp.timestamp())}"
            user.email = f"deleted_{user.id}@deleted.local"
            message = (
                f"User soft deleted. Reason: {reason}"
                if reason
                else "User soft deleted"
            )

        else:
            raise ValueError(f"Unknown action: {action}")

        db.session.commit()

        # Log the action
        try:
            current_app.logger.info(
                f"User {user_id} {action} by {admin_user}. Reason: {reason}"
            )
        except RuntimeError:
            pass  # No logging outside Flask context

        # TODO: Send notification email if requested
        if notify_user:
            try:
                current_app.logger.info(
                    f"Notification email requested for user {user_id} but not implemented"
                )
            except RuntimeError:
                pass  # No logging outside Flask context

        return {
            "success": True,
            "user_id": user_id,
            "action": action,
            "message": message,
            "performed_by": str(admin_user),
            "timestamp": timestamp.isoformat(),
        }

    except Exception as e:
        db.session.rollback()
        try:
            current_app.logger.error(f"Failed to {action} user {user_id}: {str(e)}")
        except RuntimeError:
            pass  # No logging outside Flask context
        raise ValueError(f"Failed to {action} user: {str(e)}")


def bulk_user_operations(operation, user_ids, reason=None, notify_users=False):
    """
    Perform bulk operations on multiple users.

    Args:
        operation (str): Operation to perform
        user_ids (list): List of user IDs
        reason (str): Reason for operation
        notify_users (bool): Send notifications

    Returns:
        dict: Bulk operation result
    """
    if not user_ids or len(user_ids) == 0:
        raise ValueError("User IDs list cannot be empty")
    if len(user_ids) > 100:
        raise ValueError(
            "Cannot perform bulk operations on more than 100 users at once"
        )

    results = []
    successful = 0
    failed = 0

    for user_id in user_ids:
        try:
            result = perform_user_action(
                user_id, operation, reason, notify_user=notify_users
            )
            results.append(
                {"user_id": user_id, "success": True, "message": result["message"]}
            )
            successful += 1
        except Exception as e:
            results.append({"user_id": user_id, "success": False, "error": str(e)})
            failed += 1

    return {
        "success": failed == 0,  # Success if no failures
        "operation": operation,
        "total_requested": len(user_ids),
        "successful": successful,
        "failed": failed,
        "results": results,
        "message": f"Bulk {operation} completed: {successful} successful, {failed} failed",
    }


def get_user_statistics():
    """
    Get comprehensive user statistics.

    Returns:
        dict: User statistics
    """
    now = utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # Base statistics
    total_users = User.query.filter_by(deleted=False).count()
    local_users = User.query.filter_by(deleted=False, instance_id=1).count()
    remote_users = total_users - local_users
    verified_users = User.query.filter_by(deleted=False, verified=True).count()
    banned_users = User.query.filter_by(deleted=False, banned=True).count()

    # Activity statistics
    active_24h = User.query.filter(
        and_(User.deleted is False, User.last_seen >= day_ago)
    ).count()

    active_7d = User.query.filter(
        and_(User.deleted is False, User.last_seen >= week_ago)
    ).count()

    active_30d = User.query.filter(
        and_(User.deleted is False, User.last_seen >= month_ago)
    ).count()

    # Registration statistics
    registrations_today = User.query.filter(
        and_(User.deleted is False, User.created >= day_ago)
    ).count()

    registrations_7d = User.query.filter(
        and_(User.deleted is False, User.created >= week_ago)
    ).count()

    registrations_30d = User.query.filter(
        and_(User.deleted is False, User.created >= month_ago)
    ).count()

    return {
        "total_users": total_users,
        "local_users": local_users,
        "remote_users": remote_users,
        "verified_users": verified_users,
        "banned_users": banned_users,
        "active_24h": active_24h,
        "active_7d": active_7d,
        "active_30d": active_30d,
        "registrations_today": registrations_today,
        "registrations_7d": registrations_7d,
        "registrations_30d": registrations_30d,
        "timestamp": now.isoformat(),
    }


def get_registration_statistics(days=30, include_hourly=False):
    """
    Get detailed registration statistics over time.

    Args:
        days (int): Number of days to analyze
        include_hourly (bool): Include hourly breakdown

    Returns:
        dict: Registration statistics
    """
    now = utcnow()
    start_date = now - timedelta(days=days)

    # Total registrations in period
    total_registrations = User.query.filter(
        and_(User.deleted is False, User.created >= start_date)
    ).count()

    # TODO: Track private vs public registrations
    # For now, assume all are public since we don't have tracking yet
    private_registrations = 0
    public_registrations = total_registrations

    # Daily breakdown
    daily_breakdown = []
    current_date = start_date.date()
    end_date = now.date()

    while current_date <= end_date:
        day_start = datetime.combine(current_date, datetime.min.time())
        day_end = day_start + timedelta(days=1)

        count = User.query.filter(
            and_(
                User.deleted is False, User.created >= day_start, User.created < day_end
            )
        ).count()

        daily_breakdown.append(
            {"date": current_date.isoformat(), "registrations": count}
        )

        current_date += timedelta(days=1)

    # Hourly breakdown (last 24 hours if requested)
    hourly_breakdown = []
    if include_hourly:
        for hour in range(24):
            hour_start = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            hour_end = hour_start + timedelta(hours=1)

            count = User.query.filter(
                and_(
                    User.deleted is False,
                    User.created >= hour_start,
                    User.created < hour_end,
                )
            ).count()

            hourly_breakdown.append({"hour": hour, "registrations": count})

    return {
        "period_days": days,
        "total_registrations": total_registrations,
        "private_registrations": private_registrations,
        "public_registrations": public_registrations,
        "daily_breakdown": daily_breakdown,
        "hourly_breakdown": hourly_breakdown,
        "timestamp": now.isoformat(),
    }


def export_user_data(format_type="csv", export_fields=None, filters=None):
    """
    Export user data in various formats.

    Args:
        format_type (str): Export format ('csv' or 'json')
        fields (list): Fields to include
        filters (dict): Filters to apply

    Returns:
        dict: Export result with download info
    """
    # Default fields
    if not export_fields:
        export_fields = [
            "id",
            "username",
            "email",
            "display_name",
            "created_at",
            "last_seen",
            "is_verified",
            "is_banned",
            "is_local",
        ]

    # Build query with filters
    from app.api.admin.private_registration import list_users

    # Use existing list_users function to apply filters
    filters = filters or {}
    user_list = list_users(
        local_only=filters.get("local_only", True),
        verified=filters.get("verified"),
        active=filters.get("active"),
        search=filters.get("search"),
        sort=filters.get("sort", "created_desc"),
        page=1,
        limit=10000,  # Large limit for export
    )

    users_data = user_list["users"]
    total_records = len(users_data)

    # TODO: Generate actual file and return download URL
    # For now, return placeholder response
    return {
        "success": True,
        "format": format_type,
        "total_records": total_records,
        "download_url": f"/api/alpha/admin/download/users_{int(utcnow().timestamp())}.{format_type}",
        "expires_at": (utcnow() + timedelta(hours=24)).isoformat(),
        "message": f"Export prepared: {total_records} records in {format_type} format",
    }
