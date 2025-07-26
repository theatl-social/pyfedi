"""
Secure error handling to prevent information disclosure
"""
from flask import jsonify, current_app
from typing import Dict, Any, Optional
import logging
import traceback
from werkzeug.exceptions import HTTPException
import re

logger = logging.getLogger(__name__)


class SecureErrorHandler:
    """Handle errors securely without leaking sensitive information"""
    
    # Patterns that might indicate sensitive information
    SENSITIVE_PATTERNS = [
        re.compile(r'password', re.I),
        re.compile(r'secret', re.I),
        re.compile(r'token', re.I),
        re.compile(r'api[_-]?key', re.I),
        re.compile(r'private[_-]?key', re.I),
        re.compile(r'/home/\w+', re.I),  # File paths
        re.compile(r'[A-Za-z]:\\\\', re.I),  # Windows paths
        re.compile(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'),  # IP addresses
        re.compile(r'postgres://.*@'),  # Database URLs
        re.compile(r'mysql://.*@'),
        re.compile(r'redis://.*@'),
        re.compile(r'Table [\'\"]?\w+[\'\"]?'),  # Table names
        re.compile(r'Column [\'\"]?\w+[\'\"]?'),  # Column names
        re.compile(r'at 0x[0-9a-fA-F]+>'),  # Memory addresses
    ]
    
    # Generic error messages for different scenarios
    ERROR_MESSAGES = {
        'validation': "Invalid request data",
        'authentication': "Authentication failed",
        'authorization': "Access denied",
        'not_found': "Resource not found",
        'rate_limit': "Too many requests",
        'server_error': "Internal server error",
        'bad_request': "Bad request",
        'conflict': "Request conflicts with current state",
        'gone': "Resource no longer available",
        'unprocessable': "Unable to process request",
        'timeout': "Request timeout",
        'service_unavailable': "Service temporarily unavailable"
    }
    
    def __init__(self):
        self.debug_mode = current_app.config.get('DEBUG', False)
        self.log_errors = current_app.config.get('LOG_ERRORS', True)
    
    def handle_error(self, error: Exception, status_code: Optional[int] = None) -> tuple[Dict[str, Any], int]:
        """
        Handle an error and return safe response
        
        Returns:
            (response_dict, status_code)
        """
        # Determine status code
        if isinstance(error, HTTPException):
            status_code = error.code or 500
        elif not status_code:
            status_code = self._guess_status_code(error)
        
        # Log the actual error
        if self.log_errors:
            self._log_error(error, status_code)
        
        # Generate safe error message
        safe_message = self._get_safe_message(error, status_code)
        
        # Build response
        response = {
            'error': safe_message,
            'status': status_code
        }
        
        # Add request ID if available
        request_id = self._get_request_id()
        if request_id:
            response['request_id'] = request_id
        
        # Only include details in debug mode
        if self.debug_mode and current_app.config.get('TESTING', False):
            response['debug'] = {
                'type': type(error).__name__,
                'message': str(error)
            }
        
        return response, status_code
    
    def handle_activitypub_error(self, error: Exception, activity: Optional[Dict[str, Any]] = None) -> tuple[Dict[str, Any], int]:
        """Handle ActivityPub-specific errors"""
        # Log with activity context
        if activity:
            logger.error(f"ActivityPub error processing {activity.get('type', 'unknown')}: {error}")
        
        # Determine error type
        error_str = str(error).lower()
        
        if 'signature' in error_str or 'verification' in error_str:
            return {'error': 'Invalid signature'}, 401
        elif 'actor' in error_str and 'not found' in error_str:
            return {'error': 'Actor not found'}, 404
        elif 'permission' in error_str or 'authorized' in error_str:
            return {'error': 'Unauthorized'}, 403
        elif 'rate' in error_str and 'limit' in error_str:
            return {'error': 'Rate limit exceeded'}, 429
        elif 'json' in error_str or 'parse' in error_str:
            return {'error': 'Invalid request format'}, 400
        else:
            return {'error': 'Could not process activity'}, 422
    
    def _get_safe_message(self, error: Exception, status_code: int) -> str:
        """Get a safe error message that doesn't leak information"""
        # Check for known error types
        error_str = str(error).lower()
        
        # Map to generic messages based on content
        if 'password' in error_str or 'credential' in error_str:
            return self.ERROR_MESSAGES['authentication']
        elif 'permission' in error_str or 'forbidden' in error_str:
            return self.ERROR_MESSAGES['authorization']
        elif 'not found' in error_str or 'does not exist' in error_str:
            return self.ERROR_MESSAGES['not_found']
        elif 'validation' in error_str or 'invalid' in error_str:
            return self.ERROR_MESSAGES['validation']
        elif 'rate' in error_str and 'limit' in error_str:
            return self.ERROR_MESSAGES['rate_limit']
        elif 'timeout' in error_str:
            return self.ERROR_MESSAGES['timeout']
        elif 'conflict' in error_str or 'duplicate' in error_str:
            return self.ERROR_MESSAGES['conflict']
        
        # Map by status code
        if status_code == 400:
            return self.ERROR_MESSAGES['bad_request']
        elif status_code == 401:
            return self.ERROR_MESSAGES['authentication']
        elif status_code == 403:
            return self.ERROR_MESSAGES['authorization']
        elif status_code == 404:
            return self.ERROR_MESSAGES['not_found']
        elif status_code == 409:
            return self.ERROR_MESSAGES['conflict']
        elif status_code == 410:
            return self.ERROR_MESSAGES['gone']
        elif status_code == 422:
            return self.ERROR_MESSAGES['unprocessable']
        elif status_code == 429:
            return self.ERROR_MESSAGES['rate_limit']
        elif status_code == 503:
            return self.ERROR_MESSAGES['service_unavailable']
        elif status_code >= 500:
            return self.ERROR_MESSAGES['server_error']
        
        return self.ERROR_MESSAGES['bad_request']
    
    def _guess_status_code(self, error: Exception) -> int:
        """Guess appropriate status code from error"""
        error_str = str(error).lower()
        
        if 'not found' in error_str:
            return 404
        elif 'permission' in error_str or 'forbidden' in error_str:
            return 403
        elif 'unauthorized' in error_str or 'authentication' in error_str:
            return 401
        elif 'validation' in error_str or 'invalid' in error_str:
            return 400
        elif 'conflict' in error_str or 'duplicate' in error_str:
            return 409
        elif 'timeout' in error_str:
            return 504
        else:
            return 500
    
    def _log_error(self, error: Exception, status_code: int):
        """Log error details securely"""
        # Get stack trace
        tb = traceback.format_exc()
        
        # Sanitize stack trace
        sanitized_tb = self._sanitize_output(tb)
        
        # Log based on severity
        if status_code >= 500:
            logger.error(f"Server error ({status_code}): {error}\n{sanitized_tb}")
        elif status_code >= 400:
            logger.warning(f"Client error ({status_code}): {error}")
        else:
            logger.info(f"Handled error ({status_code}): {error}")
    
    def _sanitize_output(self, text: str) -> str:
        """Remove sensitive information from text"""
        if not text:
            return text
        
        # Replace sensitive patterns
        for pattern in self.SENSITIVE_PATTERNS:
            text = pattern.sub('[REDACTED]', text)
        
        # Replace specific values
        # Database passwords
        text = re.sub(r'password[\'\"]\s*:\s*[\'\"][^\'\"]+[\'\"]', 'password: [REDACTED]', text, flags=re.I)
        # API keys
        text = re.sub(r'[a-fA-F0-9]{32,}', '[REDACTED]', text)
        
        return text
    
    def _get_request_id(self) -> Optional[str]:
        """Get request ID for tracking"""
        try:
            from flask import g
            return getattr(g, 'request_id', None)
        except Exception:
            return None
    
    def create_error_response(self, message: str, status_code: int,
                              details: Optional[Dict[str, Any]] = None) -> tuple[Dict[str, Any], int]:
        """Create a standardized error response"""
        response = {
            'error': message,
            'status': status_code
        }
        
        request_id = self._get_request_id()
        if request_id:
            response['request_id'] = request_id
        
        # Only add details if they're safe
        if details and self.debug_mode:
            safe_details = {}
            for key, value in details.items():
                if not any(pattern.search(str(value)) for pattern in self.SENSITIVE_PATTERNS):
                    safe_details[key] = value
            if safe_details:
                response['details'] = safe_details
        
        return response, status_code


# Flask error handlers
def register_error_handlers(app):
    """Register error handlers with Flask app"""
    handler = SecureErrorHandler()
    
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify(handler.handle_error(error, 400)[0]), 400
    
    @app.errorhandler(401)
    def unauthorized(error):
        return jsonify(handler.handle_error(error, 401)[0]), 401
    
    @app.errorhandler(403)
    def forbidden(error):
        return jsonify(handler.handle_error(error, 403)[0]), 403
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify(handler.handle_error(error, 404)[0]), 404
    
    @app.errorhandler(429)
    def too_many_requests(error):
        return jsonify(handler.handle_error(error, 429)[0]), 429
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify(handler.handle_error(error, 500)[0]), 500
    
    @app.errorhandler(Exception)
    def unhandled_exception(error):
        return jsonify(handler.handle_error(error)[0]), 500
