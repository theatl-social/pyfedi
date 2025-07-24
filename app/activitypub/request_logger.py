"""
ActivityPub Request Status Logger

This module provides comprehensive logging for incoming ActivityPub requests,
tracking their status through each phase of processing from initial receipt
to processing completion.
"""

import os
import uuid
import traceback
from datetime import datetime
from typing import Optional, Dict, Any
from flask import current_app, request, g
from sqlalchemy import text
from app import db
from app.models import utcnow


def is_logging_enabled() -> bool:
    """Check if AP request logging is enabled via environment variable"""
    return os.environ.get('ENABLE_AP_REQUEST_LOGGING', '0') == '1'


class APRequestLogger:
    """Logger for tracking ActivityPub request processing status"""
    
    def __init__(self, request_json: Optional[Dict] = None):
        """Initialize the logger with a unique request ID"""
        self.request_id = str(uuid.uuid4())
        self.activity_id = None
        self.post_object_uri = None
        self.enabled = is_logging_enabled()
        
        # If logging is disabled, skip extraction
        if not self.enabled:
            return
        
        # Extract key information from request if available
        if request_json:
            try:
                self.activity_id = request_json.get('id')
                if 'object' in request_json:
                    obj = request_json['object']
                    if isinstance(obj, dict):
                        self.post_object_uri = obj.get('id')
                    elif isinstance(obj, str):
                        self.post_object_uri = obj
            except Exception as e:
                self.log_checkpoint('init', 'error', f'Failed to extract request info: {str(e)}')
    
    def log_checkpoint(self, checkpoint: str, status: str, details: str = None):
        """
        Log a checkpoint in the request processing
        
        Args:
            checkpoint: The processing phase (e.g., 'initial_receipt', 'json_parse', 'signature_verify')
            status: The status ('ok', 'error', 'warning', 'ignored')
            details: Optional additional details about this checkpoint
        """
        # Skip logging if disabled
        if not self.enabled:
            return
            
        try:
            # Safely truncate details if too long
            if details and len(details) > 2000:
                details = details[:1997] + '...'
            
            # Use raw SQL to avoid SQLAlchemy model dependencies
            insert_sql = text("""
                INSERT INTO ap_request_status 
                (request_id, timestamp, checkpoint, status, activity_id, post_object_uri, details)
                VALUES (:request_id, :timestamp, :checkpoint, :status, :activity_id, :post_object_uri, :details)
            """)
            
            db.session.execute(insert_sql, {
                'request_id': self.request_id,
                'timestamp': utcnow(),
                'checkpoint': checkpoint[:64],  # Ensure it fits in VARCHAR(64)
                'status': status[:32],          # Ensure it fits in VARCHAR(32)
                'activity_id': self.activity_id,
                'post_object_uri': self.post_object_uri,
                'details': details
            })
            db.session.commit()
            
        except Exception as e:
            # If logging fails, try to log the failure itself
            try:
                current_app.logger.error(f'APRequestLogger failed: {str(e)} for request {self.request_id}')
            except:
                pass  # If even that fails, silently continue
    
    def log_error(self, checkpoint: str, error: Exception, additional_context: str = None):
        """
        Log an error that occurred during processing
        
        Args:
            checkpoint: The processing phase where the error occurred
            error: The exception that was raised
            additional_context: Optional additional context about the error
        """
        # Skip logging if disabled
        if not self.enabled:
            return
            
        error_details = f"Error: {str(error)}"
        if additional_context:
            error_details = f"{additional_context} - {error_details}"
        
        # Add stack trace for debugging
        try:
            stack_trace = traceback.format_exc()
            if stack_trace and stack_trace != 'NoneType: None\n':
                error_details += f"\nStack trace: {stack_trace}"
        except:
            pass
        
        self.log_checkpoint(checkpoint, 'error', error_details)

    def store_request_body(self, request_obj, parsed_json: Optional[Dict] = None):
        """
        Store the raw POST body and headers for this request
        
        Args:
            request_obj: Flask request object
            parsed_json: Parsed JSON content if successful
        """
        # Skip if logging is disabled
        if not self.enabled:
            return
            
        try:
            from app.models import APRequestBody
            from app.utils import ip_address
            
            # Get raw body data
            body_data = request_obj.get_data(as_text=True)
            
            # Extract headers (excluding sensitive ones)
            headers_dict = {}
            excluded_headers = {'authorization', 'cookie', 'x-api-key'}
            for key, value in request_obj.headers:
                if key.lower() not in excluded_headers:
                    headers_dict[key] = value
            
            # Create APRequestBody record
            body_record = APRequestBody(
                request_id=self.request_id,
                headers=headers_dict,
                body=body_data,
                parsed_json=parsed_json,
                content_type=request_obj.content_type,
                content_length=request_obj.content_length,
                remote_addr=ip_address(),
                user_agent=request_obj.headers.get('User-Agent')
            )
            
            db.session.add(body_record)
            db.session.commit()
            
            self.log_checkpoint('request_body_stored', 'ok', 
                              f'Stored {len(body_data)} bytes of POST data')
            
        except Exception as e:
            self.log_checkpoint('request_body_stored', 'error', 
                              f'Failed to store request body: {str(e)}')
    
    def log_null_check_failure(self, checkpoint: str, field_name: str, expected_type: str = None):
        """
        Log when a required field is None/null or missing
        
        Args:
            checkpoint: The processing phase where the null check failed
            field_name: The name of the field that was null/missing
            expected_type: Optional expected type of the field
        """
        # Skip logging if disabled
        if not self.enabled:
            return
            
        details = f"Null/missing field: {field_name}"
        if expected_type:
            details += f" (expected {expected_type})"
        
        self.log_checkpoint(checkpoint, 'error', details)
    
    def log_validation_failure(self, checkpoint: str, validation_error: str):
        """
        Log validation failures
        
        Args:
            checkpoint: The processing phase where validation failed
            validation_error: Description of what validation failed
        """
        # Skip logging if disabled
        if not self.enabled:
            return
            
        self.log_checkpoint(checkpoint, 'error', f"Validation failed: {validation_error}")
    
    def safe_extract_field(self, data: Dict, field_path: str, checkpoint: str) -> Any:
        """
        Safely extract a field from nested dictionary data with logging
        
        Args:
            data: The dictionary to extract from
            field_path: Dot-separated path to field (e.g., 'object.id')
            checkpoint: Current processing checkpoint for logging
        
        Returns:
            The field value if found, None otherwise
        """
        try:
            if not isinstance(data, dict):
                self.log_null_check_failure(checkpoint, field_path, 'dict')
                return None
            
            keys = field_path.split('.')
            current = data
            
            for key in keys:
                if not isinstance(current, dict) or key not in current:
                    self.log_null_check_failure(checkpoint, field_path)
                    return None
                current = current[key]
            
            if current is None:
                self.log_null_check_failure(checkpoint, field_path)
                return None
            
            return current
            
        except Exception as e:
            self.log_error(checkpoint, e, f"Failed to extract field {field_path}")
            return None
    
    def update_activity_info(self, activity_id: str = None, post_object_uri: str = None):
        """
        Update the activity ID and/or post object URI for this request
        
        Args:
            activity_id: The ActivityPub activity ID
            post_object_uri: The URI of the post/object being processed
        """
        # Skip if logging disabled
        if not self.enabled:
            return
            
        if activity_id:
            self.activity_id = activity_id
        if post_object_uri:
            self.post_object_uri = post_object_uri


def create_request_logger(request_json: Optional[Dict] = None) -> Optional[APRequestLogger]:
    """
    Factory function to create a request logger
    
    Args:
        request_json: Optional request JSON to extract info from
    
    Returns:
        APRequestLogger instance if logging is enabled, None otherwise
    """
    if not is_logging_enabled():
        return None
    
    try:
        return APRequestLogger(request_json)
    except Exception as e:
        # If logger creation fails, return None and log to Flask logger
        try:
            from flask import current_app
            current_app.logger.error(f'Failed to create AP request logger: {str(e)}')
        except:
            pass
        return None


def log_request_completion(logger: Optional[APRequestLogger], success: bool = True, final_message: str = None):
    """
    Log the completion of request processing
    
    Args:
        logger: The APRequestLogger instance (can be None if logging disabled)
        success: Whether processing completed successfully
        final_message: Optional final message to log
    """
    if logger is None or not logger.enabled:
        return
        
    status = 'ok' if success else 'error'
    checkpoint = 'process_inbox_request'
    
    if final_message:
        logger.log_checkpoint(checkpoint, status, final_message)
    else:
        message = 'Request processing completed successfully' if success else 'Request processing failed'
        logger.log_checkpoint(checkpoint, status, message)


def get_request_status_summary(request_id: str) -> Dict:
    """
    Get a summary of the processing status for a request
    
    Args:
        request_id: The UUID of the request to summarize
    
    Returns:
        Dictionary with status summary
    """
    if not is_logging_enabled():
        return {'error': 'AP request logging is disabled'}
        
    try:
        query_sql = text("""
            SELECT checkpoint, status, timestamp, details
            FROM ap_request_status 
            WHERE request_id = :request_id 
            ORDER BY timestamp ASC
        """)
        
        result = db.session.execute(query_sql, {'request_id': request_id})
        rows = result.fetchall()
        
        summary = {
            'request_id': request_id,
            'total_checkpoints': len(rows),
            'completed': False,
            'has_errors': False,
            'checkpoints': []
        }
        
        for row in rows:
            checkpoint_info = {
                'checkpoint': row.checkpoint,
                'status': row.status,
                'timestamp': row.timestamp.isoformat() if row.timestamp else None,
                'details': row.details
            }
            summary['checkpoints'].append(checkpoint_info)
            
            if row.status == 'error':
                summary['has_errors'] = True
            
            if row.checkpoint == 'process_inbox_request' and row.status == 'ok':
                summary['completed'] = True
        
        return summary
        
    except Exception as e:
        return {
            'request_id': request_id,
            'error': f'Failed to get status summary: {str(e)}'
        }
