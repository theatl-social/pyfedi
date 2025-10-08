"""
Startup validation utilities for PieFed

This module contains functions that run at application startup to validate
and fix data integrity issues, especially for user accounts.
"""

from flask import current_app
from app import db
from app.models import User
from app.utils import finalize_user_setup


def validate_and_fix_user_activitypub_setup():
    """
    Find and fix any local user accounts that are missing ActivityPub setup.

    This handles cases where users were created (e.g., via private registration API)
    but didn't get their ActivityPub keys and URLs configured.

    Returns:
        dict: Summary of users found and fixed
    """
    try:
        # Find local users that are:
        # 1. Verified (activated)
        # 2. Not deleted or banned
        # 3. Missing ActivityPub private key (indicator of incomplete setup)
        incomplete_users = User.query.filter(
            User.instance_id == 1,  # Local users only
            User.verified == True,  # Only activated users
            User.banned == False,
            User.deleted == False,
            User.private_key == None  # Missing ActivityPub setup
        ).all()

        if not incomplete_users:
            current_app.logger.info("No users with incomplete ActivityPub setup found")
            return {
                'users_checked': User.query.filter_by(instance_id=1, deleted=False).count(),
                'users_fixed': 0,
                'users_found': []
            }

        fixed_users = []
        for user in incomplete_users:
            try:
                current_app.logger.info(
                    f"Fixing ActivityPub setup for user {user.id} ({user.user_name})"
                )

                # Run the complete setup process
                finalize_user_setup(user)

                fixed_users.append({
                    'id': user.id,
                    'username': user.user_name,
                    'email': user.email
                })

                current_app.logger.info(
                    f"Successfully fixed ActivityPub setup for user {user.id} ({user.user_name})"
                )

            except Exception as user_error:
                current_app.logger.error(
                    f"Failed to fix ActivityPub setup for user {user.id} ({user.user_name}): {user_error}"
                )

        return {
            'users_checked': User.query.filter_by(instance_id=1, deleted=False).count(),
            'users_fixed': len(fixed_users),
            'users_found': fixed_users
        }

    except Exception as e:
        current_app.logger.error(f"Error during user ActivityPub validation: {e}")
        return {
            'error': str(e),
            'users_fixed': 0
        }


def run_startup_validations():
    """
    Run all startup validations.

    This function is called when the application starts to ensure data integrity.
    """
    current_app.logger.info("Running startup validations...")

    try:
        # Validate and fix user ActivityPub setup
        activitypub_result = validate_and_fix_user_activitypub_setup()

        if activitypub_result.get('users_fixed', 0) > 0:
            current_app.logger.info(
                f"Fixed ActivityPub setup for {activitypub_result['users_fixed']} user(s)"
            )

        if 'error' in activitypub_result:
            current_app.logger.error(
                f"Error during ActivityPub validation: {activitypub_result['error']}"
            )

        current_app.logger.info("Startup validations completed")

        return {
            'activitypub_validation': activitypub_result
        }
    finally:
        # Clean up the database session to prevent stale objects
        # from polluting the session for subsequent requests
        db.session.remove()
