"""
Monitoring Dashboard Routes

Provides web interface and API endpoints for monitoring the federation system.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, TypedDict
from datetime import datetime, timedelta
from flask import render_template, jsonify, request, abort, g
from flask_login import login_required, current_user
import redis
import json

from app import db, cache
from app.monitoring import bp
from app.utils import is_admin, get_redis_connection
from app.models import ActivityPubLog, User, Instance, FederationError
from app.federation.processor import FederationStreamProcessor
from app.federation.retry_manager import RetryManager
from app.federation.lifecycle_manager import LifecycleManager
from app.constants import APLOG_SUCCESS, APLOG_FAILURE, APLOG_DUPLICATE


class QueueStats(TypedDict):
    """Queue statistics structure"""
    name: str
    pending: int
    processing: int
    retry: int
    dlq: int
    consumers: int


class InstanceHealth(TypedDict):
    """Instance health information"""
    domain: str
    status: str
    last_success: Optional[datetime]
    last_failure: Optional[datetime]
    failure_count: int
    success_rate: float


class SystemMetrics(TypedDict):
    """System metrics"""
    redis_memory: Dict[str, Any]
    database_connections: int
    active_workers: int
    uptime: float


@bp.before_request
def require_admin() -> None:
    """Require admin access for all monitoring routes."""
    if not current_user.is_authenticated or not is_admin(current_user.id):
        abort(403)


@bp.route('/')
@login_required
def dashboard() -> str:
    """
    Main monitoring dashboard view.
    
    Returns:
        Rendered dashboard template
    """
    return render_template('monitoring/dashboard.html')


@bp.route('/api/stats')
@login_required
def api_stats() -> tuple[Dict[str, Any], int]:
    """
    Get current system statistics.
    
    Returns:
        JSON response with system stats
    """
    redis_client = get_redis_connection()
    
    # Get queue statistics
    queues = ['urgent', 'normal', 'bulk']
    queue_stats: List[QueueStats] = []
    
    for queue in queues:
        stream_key = f"federation:stream:{queue}"
        retry_key = f"federation:retry:{queue}"
        dlq_key = f"federation:dlq"
        
        # Get pending messages
        try:
            pending_info = redis_client.xpending(stream_key, f"{stream_key}:group")
            pending_count = pending_info['pending'] if pending_info else 0
        except:
            pending_count = 0
        
        # Get retry queue size
        retry_count = redis_client.zcard(retry_key)
        
        # Get DLQ count for this queue
        dlq_count = redis_client.llen(f"{dlq_key}:{queue}")
        
        # Get consumer info
        try:
            groups = redis_client.xinfo_groups(stream_key)
            consumers = groups[0]['consumers'] if groups else 0
        except:
            consumers = 0
        
        queue_stats.append(QueueStats(
            name=queue,
            pending=pending_count,
            processing=0,  # Would need to track this separately
            retry=retry_count,
            dlq=dlq_count,
            consumers=consumers
        ))
    
    # Get recent activity stats
    hour_ago = datetime.utcnow() - timedelta(hours=1)
    recent_activities = ActivityPubLog.query.filter(
        ActivityPubLog.timestamp >= hour_ago
    ).all()
    
    success_count = sum(1 for a in recent_activities if a.result == APLOG_SUCCESS)
    failure_count = sum(1 for a in recent_activities if a.result == APLOG_FAILURE)
    duplicate_count = sum(1 for a in recent_activities if a.result == APLOG_DUPLICATE)
    
    # Get system metrics
    redis_info = redis_client.info()
    redis_memory = {
        'used_memory_human': redis_info.get('used_memory_human', 'N/A'),
        'used_memory_rss_human': redis_info.get('used_memory_rss_human', 'N/A'),
        'used_memory_peak_human': redis_info.get('used_memory_peak_human', 'N/A'),
        'total_connections_received': redis_info.get('total_connections_received', 0),
        'connected_clients': redis_info.get('connected_clients', 0)
    }
    
    return jsonify({
        'queues': queue_stats,
        'activity': {
            'last_hour': {
                'total': len(recent_activities),
                'success': success_count,
                'failure': failure_count,
                'duplicate': duplicate_count
            }
        },
        'system': {
            'redis_memory': redis_memory,
            'database_connections': db.session.bind.pool.size(),
            'timestamp': datetime.utcnow().isoformat()
        }
    })


@bp.route('/api/instances')
@login_required
def api_instances() -> tuple[List[Dict[str, Any]], int]:
    """
    Get health status of federated instances.
    
    Returns:
        JSON array of instance health data
    """
    # Get all instances with recent activity
    instances = Instance.query.filter(
        Instance.last_seen > datetime.utcnow() - timedelta(days=7)
    ).all()
    
    instance_health: List[InstanceHealth] = []
    
    for instance in instances:
        # Calculate success rate from recent activities
        recent_logs = ActivityPubLog.query.filter(
            ActivityPubLog.instance_id == instance.id,
            ActivityPubLog.timestamp > datetime.utcnow() - timedelta(hours=24)
        ).all()
        
        success = sum(1 for log in recent_logs if log.result == APLOG_SUCCESS)
        total = len(recent_logs)
        success_rate = (success / total * 100) if total > 0 else 0
        
        # Get federation errors
        recent_errors = FederationError.query.filter(
            FederationError.instance_id == instance.id,
            FederationError.created_at > datetime.utcnow() - timedelta(hours=24)
        ).count()
        
        instance_health.append({
            'domain': instance.domain,
            'status': 'healthy' if success_rate > 90 else 'degraded' if success_rate > 50 else 'unhealthy',
            'last_seen': instance.last_seen.isoformat() if instance.last_seen else None,
            'failure_count': recent_errors,
            'success_rate': round(success_rate, 2),
            'software': instance.software,
            'version': instance.version
        })
    
    return jsonify(sorted(instance_health, key=lambda x: x['success_rate']))


@bp.route('/api/errors')
@login_required
def api_errors() -> tuple[List[Dict[str, Any]], int]:
    """
    Get recent federation errors.
    
    Returns:
        JSON array of recent errors
    """
    limit = request.args.get('limit', 50, type=int)
    
    errors = FederationError.query.order_by(
        FederationError.created_at.desc()
    ).limit(limit).all()
    
    error_list = []
    for error in errors:
        error_list.append({
            'id': error.id,
            'timestamp': error.created_at.isoformat(),
            'instance': error.instance.domain if error.instance else 'Unknown',
            'activity_type': error.activity_type,
            'error_type': error.error_type,
            'error_message': error.error_message,
            'retry_count': error.retry_count
        })
    
    return jsonify(error_list)


@bp.route('/api/activity/<activity_id>')
@login_required
def api_activity_detail(activity_id: str) -> tuple[Dict[str, Any], int]:
    """
    Get detailed information about a specific activity.
    
    Args:
        activity_id: Activity ID to look up
        
    Returns:
        JSON with activity details
    """
    activity = ActivityPubLog.query.filter_by(
        activity_id=activity_id
    ).first()
    
    if not activity:
        abort(404)
    
    return jsonify({
        'id': activity.id,
        'activity_id': activity.activity_id,
        'timestamp': activity.timestamp.isoformat(),
        'type': activity.activity_type,
        'result': activity.result,
        'instance': activity.instance.domain if activity.instance else None,
        'exception_message': activity.exception_message,
        'activity_json': json.loads(activity.activity_json) if activity.activity_json else None
    })


@bp.route('/api/retry-queue')
@login_required
def api_retry_queue() -> tuple[List[Dict[str, Any]], int]:
    """
    Get items in retry queue.
    
    Returns:
        JSON array of retry queue items
    """
    redis_client = get_redis_connection()
    retry_items = []
    
    for queue in ['urgent', 'normal', 'bulk']:
        retry_key = f"federation:retry:{queue}"
        
        # Get items with scores (retry timestamps)
        items = redis_client.zrange(retry_key, 0, 50, withscores=True)
        
        for item_data, retry_at in items:
            try:
                item = json.loads(item_data)
                retry_items.append({
                    'queue': queue,
                    'activity_id': item.get('id', 'Unknown'),
                    'activity_type': item.get('type', 'Unknown'),
                    'retry_at': datetime.fromtimestamp(retry_at).isoformat(),
                    'destination': item.get('destination', 'Unknown'),
                    'retry_count': item.get('_retry_count', 0)
                })
            except:
                continue
    
    return jsonify(sorted(retry_items, key=lambda x: x['retry_at']))


@bp.route('/api/dlq')
@login_required
def api_dlq() -> tuple[List[Dict[str, Any]], int]:
    """
    Get items in Dead Letter Queue.
    
    Returns:
        JSON array of DLQ items
    """
    redis_client = get_redis_connection()
    dlq_items = []
    
    for queue in ['urgent', 'normal', 'bulk']:
        dlq_key = f"federation:dlq:{queue}"
        
        # Get up to 50 items from each DLQ
        items = redis_client.lrange(dlq_key, 0, 50)
        
        for item_data in items:
            try:
                item = json.loads(item_data)
                dlq_items.append({
                    'queue': queue,
                    'activity_id': item.get('id', 'Unknown'),
                    'activity_type': item.get('type', 'Unknown'),
                    'destination': item.get('destination', 'Unknown'),
                    'failed_at': item.get('_failed_at', 'Unknown'),
                    'retry_count': item.get('_retry_count', 0),
                    'last_error': item.get('_last_error', 'Unknown')
                })
            except:
                continue
    
    return jsonify(dlq_items)


@bp.route('/api/memory-status')
@login_required
def api_memory_status() -> tuple[Dict[str, Any], int]:
    """
    Get Redis memory status and lifecycle stats.
    
    Returns:
        JSON with memory statistics
    """
    lifecycle_mgr = LifecycleManager(get_redis_connection())
    memory_status = lifecycle_mgr.get_memory_status()
    
    # Add stream sizes
    redis_client = get_redis_connection()
    stream_sizes = {}
    for queue in ['urgent', 'normal', 'bulk']:
        stream_key = f"federation:stream:{queue}"
        try:
            info = redis_client.xinfo_stream(stream_key)
            stream_sizes[queue] = {
                'length': info['length'],
                'first_entry': info['first-entry'][0] if info['first-entry'] else None,
                'last_entry': info['last-entry'][0] if info['last-entry'] else None
            }
        except:
            stream_sizes[queue] = {'length': 0}
    
    memory_status['streams'] = stream_sizes
    
    return jsonify(memory_status)


@bp.route('/api/task/<task_id>')
@login_required
def api_task_status(task_id: str) -> tuple[Dict[str, Any], int]:
    """
    Get status of a specific task/activity.
    
    Args:
        task_id: Activity ID to check
        
    Returns:
        JSON with task status and details
    """
    redis_client = get_redis_connection()
    
    # Check if task is in any stream
    for queue in ['urgent', 'normal', 'bulk']:
        stream_key = f"federation:stream:{queue}"
        
        # Check pending messages
        try:
            pending = redis_client.xpending_range(
                stream_key, 
                f"{stream_key}:group",
                "-", "+", 1000
            )
            for msg in pending:
                # Get message content
                messages = redis_client.xrange(stream_key, msg['message_id'], msg['message_id'])
                if messages:
                    content = json.loads(messages[0][1].get(b'data', b'{}'))
                    if content.get('id') == task_id:
                        return jsonify({
                            'status': 'processing',
                            'queue': queue,
                            'consumer': msg['consumer'].decode(),
                            'idle_time_ms': msg['time_since_delivered'],
                            'delivery_count': msg['times_delivered'],
                            'activity': content
                        })
        except:
            pass
        
        # Check retry queue
        retry_key = f"federation:retry:{queue}"
        retry_items = redis_client.zrange(retry_key, 0, -1, withscores=True)
        for item_data, retry_at in retry_items:
            try:
                item = json.loads(item_data)
                if item.get('id') == task_id:
                    return jsonify({
                        'status': 'retry',
                        'queue': queue,
                        'retry_at': datetime.fromtimestamp(retry_at).isoformat(),
                        'retry_count': item.get('_retry_count', 0),
                        'last_error': item.get('_last_error'),
                        'activity': item
                    })
            except:
                continue
        
        # Check DLQ
        dlq_key = f"federation:dlq:{queue}"
        dlq_items = redis_client.lrange(dlq_key, 0, -1)
        for item_data in dlq_items:
            try:
                item = json.loads(item_data)
                if item.get('id') == task_id:
                    return jsonify({
                        'status': 'failed',
                        'queue': queue,
                        'failed_at': item.get('_failed_at'),
                        'retry_count': item.get('_retry_count', 0),
                        'last_error': item.get('_last_error'),
                        'activity': item
                    })
            except:
                continue
    
    # Check if task was completed (in ActivityPubLog)
    activity_log = ActivityPubLog.query.filter_by(
        activity_id=task_id
    ).order_by(ActivityPubLog.timestamp.desc()).first()
    
    if activity_log:
        return jsonify({
            'status': 'completed',
            'result': 'success' if activity_log.result == APLOG_SUCCESS else 'failure',
            'timestamp': activity_log.timestamp.isoformat(),
            'instance': activity_log.instance.domain if activity_log.instance else None,
            'exception': activity_log.exception_message,
            'activity_type': activity_log.activity_type
        })
    
    # Task not found
    return jsonify({
        'status': 'not_found',
        'message': f'Task {task_id} not found in any queue or log'
    }), 404


@bp.route('/api/task', methods=['POST'])
@login_required
def api_submit_task() -> tuple[Dict[str, Any], int]:
    """
    Submit a new federation task for testing/debugging.
    
    Request body should contain:
        - activity: The ActivityPub activity object
        - destination: Target inbox URL
        - priority: Queue priority (urgent/normal/bulk)
        
    Returns:
        JSON with task submission status
    """
    if not current_user.is_authenticated or not is_admin(current_user.id):
        abort(403)
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    activity = data.get('activity')
    destination = data.get('destination')
    priority = data.get('priority', 'normal')
    
    if not activity or not destination:
        return jsonify({'error': 'Missing required fields: activity, destination'}), 400
    
    if priority not in ['urgent', 'normal', 'bulk']:
        return jsonify({'error': 'Invalid priority. Must be: urgent, normal, or bulk'}), 400
    
    # Get federation producer
    from app.federation.producer import get_producer
    producer = get_producer()
    
    try:
        # Queue the activity
        success = producer.queue_activity(
            activity=activity,
            destination=destination,
            priority=priority
        )
        
        if success:
            return jsonify({
                'status': 'queued',
                'activity_id': activity.get('id'),
                'queue': priority,
                'destination': destination
            })
        else:
            return jsonify({'error': 'Failed to queue activity'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500