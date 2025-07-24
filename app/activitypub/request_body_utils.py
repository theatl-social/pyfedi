"""
ActivityPub Request Body Utilities

Helper functions for querying and analyzing stored request bodies
"""

from typing import List, Dict, Any, Optional
from sqlalchemy import text, desc
from app import db
from app.models import APRequestStatus, APRequestBody


def get_recent_requests(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent ActivityPub requests with their status"""
    query = text("""
        SELECT 
            rb.request_id,
            rb.timestamp as received_at,
            rb.remote_addr,
            rb.content_type,
            rb.content_length,
            rb.parsed_json->>'type' as activity_type,
            rb.parsed_json->>'actor' as actor,
            rb.parsed_json->>'id' as activity_id,
            (SELECT status.status 
             FROM ap_request_status status 
             WHERE status.request_id = rb.request_id 
             ORDER BY status.timestamp DESC 
             LIMIT 1) as latest_status,
            (SELECT COUNT(*) 
             FROM ap_request_status status 
             WHERE status.request_id = rb.request_id 
             AND status.status = 'error') as error_count
        FROM ap_request_body rb
        ORDER BY rb.timestamp DESC
        LIMIT :limit
    """)
    
    result = db.session.execute(query, {'limit': limit})
    return [dict(row._mapping) for row in result]


def get_request_details(request_id: str) -> Optional[Dict[str, Any]]:
    """Get full details for a specific request including timeline"""
    
    # Get body data
    body = APRequestBody.query.filter_by(request_id=request_id).first()
    if not body:
        return None
    
    # Get status timeline
    statuses = APRequestStatus.query.filter_by(request_id=request_id)\
        .order_by(APRequestStatus.timestamp.asc()).all()
    
    return {
        'request_id': request_id,
        'received_at': body.timestamp.isoformat() if body.timestamp else None,
        'remote_addr': body.remote_addr,
        'user_agent': body.user_agent,
        'content_type': body.content_type,
        'content_length': body.content_length,
        'headers': body.headers,
        'raw_body': body.body,
        'parsed_json': body.parsed_json,
        'timeline': [
            {
                'checkpoint': status.checkpoint,
                'status': status.status,
                'timestamp': status.timestamp.isoformat() if status.timestamp else None,
                'details': status.details
            }
            for status in statuses
        ]
    }


def get_failed_requests(hours: int = 24, limit: int = 50) -> List[Dict[str, Any]]:
    """Get requests that failed within the specified time period"""
    query = text("""
        SELECT DISTINCT
            rb.request_id,
            rb.timestamp as received_at,
            rb.remote_addr,
            rb.parsed_json->>'type' as activity_type,
            rb.parsed_json->>'actor' as actor,
            rb.parsed_json->>'id' as activity_id
        FROM ap_request_body rb
        JOIN ap_request_status rs ON rb.request_id = rs.request_id
        WHERE rs.status = 'error'
        AND rb.timestamp > NOW() - INTERVAL ':hours hours'
        ORDER BY rb.timestamp DESC
        LIMIT :limit
    """)
    
    result = db.session.execute(query, {'hours': hours, 'limit': limit})
    return [dict(row._mapping) for row in result]


def get_activity_type_stats(hours: int = 24) -> List[Dict[str, Any]]:
    """Get statistics by activity type"""
    query = text("""
        SELECT 
            rb.parsed_json->>'type' as activity_type,
            COUNT(*) as total_requests,
            COUNT(CASE WHEN EXISTS (
                SELECT 1 FROM ap_request_status rs 
                WHERE rs.request_id = rb.request_id 
                AND rs.status = 'error'
            ) THEN 1 END) as failed_requests,
            AVG((
                SELECT COUNT(*) FROM ap_request_status rs 
                WHERE rs.request_id = rb.request_id
            )) as avg_checkpoints
        FROM ap_request_body rb
        WHERE rb.timestamp > NOW() - INTERVAL ':hours hours'
        GROUP BY rb.parsed_json->>'type'
        ORDER BY total_requests DESC
    """)
    
    result = db.session.execute(query, {'hours': hours})
    return [dict(row._mapping) for row in result]
