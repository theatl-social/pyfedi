"""
Debug endpoints for ActivityPub development

This module provides debugging endpoints that are only available
in development mode. They help with troubleshooting federation
issues and inspecting ActivityPub request/response data.

Endpoints:
    - /debug/ap_requests - List recent ActivityPub requests
    - /debug/ap_request/<id> - View specific request details
    - /testredis - Test Redis connectivity

Security:
    These endpoints should NEVER be enabled in production!
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from flask import jsonify, render_template, current_app, abort, request

from app import db, cache
from app.activitypub.routes import bp
from app.models import APRequestStatus, APRequestBody
from app.utils import get_redis_connection, get_setting

# Type aliases
type RequestId = str
type JsonResponse = tuple[Dict[str, Any], int]


def _check_debug_enabled() -> None:
    """
    Ensure debug endpoints are only accessible in development.
    
    Raises:
        404: If not in debug mode or debug endpoints disabled
    """
    if not current_app.debug:
        abort(404)
    
    if not get_setting('enable_debug_endpoints', False):
        abort(404)


@bp.route('/testredis')
def testredis_get() -> JsonResponse:
    """
    Test Redis connectivity and basic operations.
    
    This endpoint verifies that Redis is properly configured and
    accessible. It performs basic set/get operations.
    
    Returns:
        JSON response with Redis test results
        
    Example Response:
        {
            "status": "success",
            "ping": "PONG",
            "set_test": true,
            "get_test": "test_value",
            "info": {
                "redis_version": "7.0.5",
                "connected_clients": 10,
                "used_memory_human": "1.5M"
            }
        }
    """
    _check_debug_enabled()
    
    try:
        redis_client = get_redis_connection()
        
        # Test basic connectivity
        ping_result = redis_client.ping()
        
        # Test set/get
        test_key = f"test:{datetime.now(timezone.utc).timestamp()}"
        test_value = "Hello from PyFedi!"
        
        redis_client.setex(test_key, 60, test_value)  # 60 second expiry
        retrieved_value = redis_client.get(test_key)
        
        # Get server info
        info = redis_client.info()
        
        # Clean up test key
        redis_client.delete(test_key)
        
        return jsonify({
            "status": "success",
            "ping": "PONG" if ping_result else "FAILED",
            "set_test": True,
            "get_test": retrieved_value.decode('utf-8') if retrieved_value else None,
            "info": {
                "redis_version": info.get('redis_version'),
                "connected_clients": info.get('connected_clients'),
                "used_memory_human": info.get('used_memory_human'),
                "uptime_in_days": info.get('uptime_in_days')
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
            "type": type(e).__name__
        }), 500


@bp.route('/debug/ap_requests')
def debug_ap_requests() -> str:
    """
    List recent ActivityPub requests with filtering options.
    
    Query Parameters:
        - status: Filter by status (success, failed, error)
        - checkpoint: Filter by checkpoint name
        - hours: Show requests from last N hours (default 24)
        - limit: Maximum results (default 100, max 500)
        
    Returns:
        HTML page with request list
        
    Example:
        GET /debug/ap_requests?status=failed&hours=6
    """
    _check_debug_enabled()
    
    # Get query parameters
    filter_status = request.args.get('status')
    filter_checkpoint = request.args.get('checkpoint')
    hours = request.args.get('hours', 24, type=int)
    limit = min(request.args.get('limit', 100, type=int), 500)
    
    # Build query
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    query = APRequestStatus.query.filter(
        APRequestStatus.timestamp >= cutoff
    )
    
    if filter_status:
        query = query.filter(APRequestStatus.status == filter_status)
    
    if filter_checkpoint:
        query = query.filter(APRequestStatus.checkpoint == filter_checkpoint)
    
    # Get results
    requests = query.order_by(
        APRequestStatus.timestamp.desc()
    ).limit(limit).all()
    
    # Group by request_id for easier viewing
    grouped_requests: Dict[str, List[APRequestStatus]] = {}
    for req in requests:
        if req.request_id not in grouped_requests:
            grouped_requests[req.request_id] = []
        grouped_requests[req.request_id].append(req)
    
    # Get unique checkpoints and statuses for filter dropdowns
    all_checkpoints = db.session.query(
        APRequestStatus.checkpoint
    ).distinct().all()
    
    all_statuses = db.session.query(
        APRequestStatus.status
    ).distinct().all()
    
    return render_template(
        'debug/ap_requests.html',
        grouped_requests=grouped_requests,
        filter_status=filter_status,
        filter_checkpoint=filter_checkpoint,
        hours=hours,
        limit=limit,
        all_checkpoints=[c[0] for c in all_checkpoints],
        all_statuses=[s[0] for s in all_statuses]
    )


@bp.route('/debug/ap_request/<request_id>')
def debug_ap_request(request_id: RequestId) -> str:
    """
    View detailed information about a specific ActivityPub request.
    
    Shows the complete request lifecycle including:
    - All status checkpoints
    - Request headers and body
    - Response data
    - Processing timeline
    
    Args:
        request_id: UUID of the request to inspect
        
    Returns:
        HTML page with request details
    """
    _check_debug_enabled()
    
    # Get all status entries for this request
    statuses = APRequestStatus.query.filter_by(
        request_id=request_id
    ).order_by(APRequestStatus.timestamp).all()
    
    if not statuses:
        abort(404)
    
    # Get request body if available
    body_data = APRequestBody.query.filter_by(
        request_id=request_id
    ).first()
    
    # Calculate processing timeline
    timeline = []
    start_time = None
    
    for status in statuses:
        if start_time is None:
            start_time = status.timestamp
            elapsed = 0
        else:
            elapsed = (status.timestamp - start_time).total_seconds() * 1000  # ms
        
        timeline.append({
            'checkpoint': status.checkpoint,
            'status': status.status,
            'timestamp': status.timestamp,
            'elapsed_ms': elapsed,
            'details': status.details,
            'activity_id': status.activity_id,
            'post_uri': status.post_object_uri
        })
    
    # Format request body for display
    formatted_body = None
    if body_data and body_data.parsed_json:
        import json
        formatted_body = json.dumps(
            body_data.parsed_json,
            indent=2,
            sort_keys=True
        )
    
    return render_template(
        'debug/ap_request_detail.html',
        request_id=request_id,
        timeline=timeline,
        body_data=body_data,
        formatted_body=formatted_body,
        total_time=(timeline[-1]['elapsed_ms'] if timeline else 0)
    )


@bp.route('/debug/ap_stats')
def debug_ap_stats() -> JsonResponse:
    """
    Get ActivityPub processing statistics.
    
    Returns aggregated statistics about ActivityPub processing
    including success rates, common errors, and performance metrics.
    
    Returns:
        JSON response with statistics
        
    Example Response:
        {
            "total_requests": 1523,
            "success_rate": 0.95,
            "avg_processing_time_ms": 127,
            "errors_by_type": {
                "signature_failed": 45,
                "json_parse_error": 12
            },
            "requests_by_hour": [...],
            "top_instances": [...]
        }
    """
    _check_debug_enabled()
    
    # Calculate time windows
    now = datetime., timezone()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)
    
    # Get basic counts
    total_24h = APRequestStatus.query.filter(
        APRequestStatus.timestamp >= last_24h
    ).count()
    
    success_24h = APRequestStatus.query.filter(
        APRequestStatus.timestamp >= last_24h,
        APRequestStatus.status == 'success'
    ).count()
    
    # Get error breakdown
    errors = db.session.query(
        APRequestStatus.status,
        APRequestStatus.checkpoint,
        db.func.count(APRequestStatus.id).label('count')
    ).filter(
        APRequestStatus.timestamp >= last_24h,
        APRequestStatus.status.in_(['failed', 'error'])
    ).group_by(
        APRequestStatus.status,
        APRequestStatus.checkpoint
    ).all()
    
    error_breakdown = {}
    for error in errors:
        key = f"{error.checkpoint}_{error.status}"
        error_breakdown[key] = error.count
    
    # Calculate average processing time
    # This would need a more complex query with proper time tracking
    avg_time = 150  # Placeholder
    
    return jsonify({
        "period": "24h",
        "total_requests": total_24h,
        "successful_requests": success_24h,
        "success_rate": round(success_24h / total_24h, 3) if total_24h > 0 else 0,
        "avg_processing_time_ms": avg_time,
        "errors_by_type": error_breakdown,
        "timestamp": now.isoformat()
    }), 200


@bp.route('/debug/federation_status')
def debug_federation_status() -> JsonResponse:
    """
    Get current federation status with other instances.
    
    Shows which instances are currently reachable, their software
    versions, and recent communication status.
    
    Returns:
        JSON response with instance federation status
    """
    _check_debug_enabled()
    
    from app.models import Instance
    
    # Get all known instances
    instances = Instance.query.filter(
        Instance.id != 1,  # Exclude local
        Instance.gone_forever == False
    ).all()
    
    instance_status = []
    
    for instance in instances:
        status = {
            "domain": instance.domain,
            "software": instance.software,
            "version": instance.version,
            "dormant": instance.dormant,
            "last_seen": instance.last_successful_send.isoformat() if instance.last_successful_send else None,
            "failures": instance.failures,
            "user_count": instance.user_count,
            "post_count": instance.post_count
        }
        instance_status.append(status)
    
    # Sort by most recently active
    instance_status.sort(
        key=lambda x: x['last_seen'] or '1970-01-01',
        reverse=True
    )
    
    return jsonify({
        "total_instances": len(instances),
        "active_instances": sum(1 for i in instances if not i.dormant),
        "dormant_instances": sum(1 for i in instances if i.dormant),
        "instances": instance_status[:100]  # Limit to 100 for performance
    }), 200