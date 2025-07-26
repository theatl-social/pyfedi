# Security module for PyFedi/PeachPie
"""
This module contains security-related utilities and validators
to protect against common vulnerabilities.
"""

from .json_validator import SafeJSONParser
from .signature_validator import SignatureValidator
from .uri_validator import URIValidator
from .actor_limits import ActorCreationLimiter
from .relay_protection import RelayProtection
from .media_proxy_security import SecureMediaProxy
from .permission_validator import PermissionValidator
from .error_handler import SecureErrorHandler

__all__ = [
    'SafeJSONParser', 
    'SignatureValidator', 
    'URIValidator',
    'ActorCreationLimiter',
    'RelayProtection',
    'SecureMediaProxy',
    'PermissionValidator',
    'SecureErrorHandler'
]
