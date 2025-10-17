"""
LDAP utilities for user synchronization
"""
from __future__ import annotations

import logging
from typing import Optional

from flask import current_app
from ldap3 import Server, Connection, ALL, SUBTREE, MODIFY_REPLACE
from ldap3.core.exceptions import LDAPException, LDAPBindError

logger = logging.getLogger(__name__)


def _bind_user(dn: str, password: str) -> Optional[Connection]:
    """
    Create and return an LDAP connection using configuration from Flask app.
    Returns None if LDAP is not configured or connection fails.
    """
    if not current_app.config.get('LDAP_SERVER'):
        logger.info("LDAP_SERVER not configured, skipping LDAP operations")
        return None

    try:
        # Create server object
        server = Server(
            current_app.config['LDAP_SERVER'],
            port=current_app.config.get('LDAP_PORT', 389),
            use_ssl=current_app.config.get('LDAP_USE_SSL', False),
            get_info=ALL
        )

        # Create connection
        conn = Connection(
            server,
            user=dn,
            password=password,
            auto_bind=True
        )

        # Enable TLS if configured
        if current_app.config.get('LDAP_USE_TLS', False):
            conn.start_tls()

        return conn

    except LDAPBindError as e:
        logger.error(f"LDAP bind failed: {e}")
        return None
    except LDAPException as e:
        logger.error(f"LDAP connection error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error connecting to LDAP: {e}")
        return None


def sync_user_to_ldap(username: str, email: str, password: str) -> bool:
    """
    Synchronize user data to LDAP server.

    Args:
        username: User's username
        email: User's email address
        password: User's plain text password

    Returns:
        bool: True if sync was successful or skipped, False if failed
    """
    if not current_app.config.get('LDAP_WRITE_ENABLE'):
        logger.info("LDAP_WRITE_ENABLE set to false, skipping LDAP writing operations")
        return True

    username = username.lower()

    # Skip if no password provided
    if not password or not password.strip():
        logger.info(f"No password provided for user {username}, skipping LDAP sync")
        return True

    conn = _bind_user(current_app.config.get('LDAP_WRITE_BIND_DN'), current_app.config.get('LDAP_WRITE_BIND_PASSWORD'))
    if not conn:
        return True

    try:
        base_dn = current_app.config.get('LDAP_BASE_DN', '')
        user_filter = current_app.config.get('LDAP_WRITE_USER_FILTER', '(uid={username})').format(username=username)

        username_attr = current_app.config.get('LDAP_WRITE_ATTR_USERNAME', 'uid')
        email_attr = current_app.config.get('LDAP_WRITE_ATTR_EMAIL', 'mail')
        password_attr = current_app.config.get('LDAP_WRITE_ATTR_PASSWORD', 'userPassword')

        # Search for existing user
        conn.search(
            search_base=base_dn,
            search_filter=user_filter,
            search_scope=SUBTREE,
            attributes=[username_attr, email_attr, password_attr]
        )

        if conn.entries:
            # User exists, update their attributes
            user_dn = conn.entries[0].entry_dn
            changes = {}

            # Update email if different
            current_email = getattr(conn.entries[0], email_attr, None)
            if current_email != email:
                changes[email_attr] = [(MODIFY_REPLACE, [email])]

            # Always update password (assume it's hashed appropriately by LDAP server)
            changes[password_attr] = [(MODIFY_REPLACE, [password])]

            if changes:
                success = conn.modify(user_dn, changes)
                if success:
                    logger.info(f"Successfully updated LDAP user {username}")
                    return True
                else:
                    logger.error(f"Failed to update LDAP user {username}: {conn.result}")
                    return False
            else:
                logger.info(f"No changes needed for LDAP user {username}")
                return True
        else:
            # User doesn't exist, create new entry
            user_dn = f"{username_attr}={username},{base_dn}"
            attributes = {
                username_attr: username,
                email_attr: email,
                password_attr: password,
                'cn': username,  # Common name (required)
                'sn': username,  # Surname (required for inetOrgPerson)
                'objectClass': ['inetOrgPerson']
            }

            success = conn.add(user_dn, attributes=attributes)
            if success:
                logger.info(f"Successfully created LDAP user {username}")
                return True
            else:
                logger.error(f"Failed to create LDAP user {username}: {conn.result}")
                return False

    except LDAPException as e:
        logger.error(f"LDAP error syncing user {username}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error syncing user {username} to LDAP: {e}")
        return False
    finally:
        if conn:
            conn.unbind()


def login_with_ldap(user_name: str, password: str) -> str | bool:
    if not current_app.config.get('LDAP_READ_ENABLE'):
        logger.info("LDAP_READ_ENABLE set to false, skipping LDAP reading operations")
        return False

    base_dn = current_app.config.get('LDAP_BASE_DN', '')
    user_name_attr = current_app.config.get('LDAP_READ_ATTR_USERNAME', 'uid')

    full_dn = f"{user_name_attr}={user_name},{base_dn}"

    conn = _bind_user(full_dn, password)
    if not conn:
        return False

    try:
        user_filter = current_app.config.get('LDAP_READ_USER_FILTER', '(uid={username})').format(username=user_name)
        email_attr = current_app.config.get('LDAP_READ_ATTR_EMAIL', 'mail')

        conn.search(
            search_base=base_dn,
            search_filter=user_filter,
            search_scope=SUBTREE,
            attributes=[email_attr]
        )

        if conn.entries:
            email = getattr(conn.entries[0], email_attr)
            return email.value

        return False

    except LDAPException as e:
        logger.error(f"LDAP error logging user {username} in: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error logging user {username} in with LDAP: {e}")
        return False
    finally:
        if conn:
            conn.unbind()


def test_ldap_connection() -> bool:
    """
    Test LDAP connection and return True if successful.
    """
    conn = _bind_user(
        current_app.config.get('LDAP_WRITE_BIND_DN'),
        current_app.config.get('LDAP_WRITE_BIND_PASSWORD')
    )
    if conn:
        conn.unbind()
        return True
    return False
