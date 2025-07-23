"""
Admin interface for viewing ActivityPub request status logs
"""

from flask import render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import text, desc

from app import db
from app.activitypub import bp
from app.activitypub.request_logger import get_request_status_summary


@bp.route('/admin/ap_requests')
@login_required
def admin_ap_requests():
    """View ActivityPub request logs (admin only)"""
    if not current_user.is_admin():
        return "Access denied", 403
    
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Get recent incomplete requests from the view
    query_sql = text("""
        SELECT 
            request_id,
            timestamp,
            checkpoint,
            status,
            activity_id,
            post_object_uri,
            details
        FROM ap_request_status_incomplete
        ORDER BY timestamp DESC
        LIMIT :limit OFFSET :offset
    """)
    
    offset = (page - 1) * per_page
    result = db.session.execute(query_sql, {
        'limit': per_page,
        'offset': offset
    })
    
    incomplete_requests = []
    for row in result:
        incomplete_requests.append({
            'request_id': str(row.request_id),
            'timestamp': row.timestamp.isoformat() if row.timestamp else None,
            'checkpoint': row.checkpoint,
            'status': row.status,
            'activity_id': row.activity_id,
            'post_object_uri': row.post_object_uri,
            'details': row.details
        })
    
    # Get count for pagination
    count_sql = text("SELECT COUNT(*) FROM ap_request_status_incomplete")
    total_count = db.session.execute(count_sql).scalar()
    
    return render_template('admin/ap_request_status.html',
                         incomplete_requests=incomplete_requests,
                         page=page,
                         per_page=per_page,
                         total_count=total_count)


@bp.route('/admin/ap_request/<request_id>')
@login_required 
def admin_ap_request_detail(request_id):
    """View detailed status for a specific request (admin only)"""
    if not current_user.is_admin():
        return "Access denied", 403
    
    try:
        summary = get_request_status_summary(request_id)
        return jsonify(summary)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/admin/ap_stats')
@login_required
def admin_ap_stats():
    """View ActivityPub processing statistics (admin only)"""
    if not current_user.is_admin():
        return "Access denied", 403
        
    # Get stats from the last 24 hours
    stats_sql = text("""
        SELECT 
            checkpoint,
            status,
            COUNT(*) as count
        FROM ap_request_status 
        WHERE timestamp > NOW() - INTERVAL '24 hours'
        GROUP BY checkpoint, status
        ORDER BY checkpoint, status
    """)
    
    result = db.session.execute(stats_sql)
    stats = {}
    
    for row in result:
        checkpoint = row.checkpoint
        if checkpoint not in stats:
            stats[checkpoint] = {}
        stats[checkpoint][row.status] = row.count
    
    # Get completion rate
    completion_sql = text("""
        WITH completed_requests AS (
            SELECT request_id
            FROM ap_request_status
            WHERE checkpoint = 'process_inbox_request' 
            AND status = 'ok'
            AND timestamp > NOW() - INTERVAL '24 hours'
        ),
        total_requests AS (
            SELECT COUNT(DISTINCT request_id) as total
            FROM ap_request_status
            WHERE checkpoint = 'initial_receipt'
            AND timestamp > NOW() - INTERVAL '24 hours'
        )
        SELECT 
            (SELECT COUNT(*) FROM completed_requests) as completed,
            total_requests.total as total
        FROM total_requests
    """)
    
    completion_result = db.session.execute(completion_sql).fetchone()
    completion_rate = 0
    if completion_result and completion_result.total > 0:
        completion_rate = (completion_result.completed / completion_result.total) * 100
    
    return jsonify({
        'stats': stats,
        'completion_rate': completion_rate,
        'completed_requests': completion_result.completed if completion_result else 0,
        'total_requests': completion_result.total if completion_result else 0
    })
