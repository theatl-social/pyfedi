"""
Admin routes for rate limit monitoring and management
"""
from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for
from flask_login import login_required
from app.admin.util import admin_required
from app.federation.rate_limiter import DestinationRateLimiter, RateLimitType

bp = Blueprint('admin_rate_limits', __name__)


@bp.route('/rate-limits')
@login_required
@admin_required
def rate_limits_overview():
    """View rate limiting overview"""
    limiter = DestinationRateLimiter()
    
    # Get all destinations being rate limited
    limited_destinations = limiter.get_all_limited_destinations()
    
    # Get rate limit configuration
    config = {}
    for limit_type in RateLimitType:
        limit_config = limiter.limits[limit_type]
        config[limit_type.value] = {
            'max_requests': limit_config.max_requests,
            'window_seconds': limit_config.window_seconds,
            'requests_per_minute': (limit_config.max_requests / limit_config.window_seconds) * 60
        }
    
    return render_template('admin/rate_limits.html',
                           limited_destinations=limited_destinations,
                           config=config)


@bp.route('/rate-limits/<destination>')
@login_required
@admin_required
def rate_limit_detail(destination):
    """View detailed rate limit info for a destination"""
    limiter = DestinationRateLimiter()
    status = limiter.get_rate_limit_status(destination)
    
    return render_template('admin/rate_limit_detail.html',
                           destination=destination,
                           status=status)


@bp.route('/rate-limits/<destination>/reset', methods=['POST'])
@login_required
@admin_required
def reset_rate_limits(destination):
    """Reset rate limits for a destination"""
    limiter = DestinationRateLimiter()
    limiter.reset_rate_limits(destination)
    
    flash(f'Rate limits reset for {destination}', 'success')
    return redirect(url_for('admin_rate_limits.rate_limits_overview'))


@bp.route('/api/admin/rate-limits')
@login_required
@admin_required
def api_rate_limits():
    """API endpoint for rate limit data"""
    limiter = DestinationRateLimiter()
    
    # Get destinations parameter
    destinations = request.args.get('destinations', '').split(',')
    if not destinations or destinations == ['']:
        # Return overview
        limited = limiter.get_all_limited_destinations()
        return jsonify({
            'limited_destinations': limited,
            'total_limited': len(limited)
        })
    
    # Return specific destination data
    result = {}
    for destination in destinations:
        if destination:
            result[destination] = limiter.get_rate_limit_status(destination)
    
    return jsonify(result)


@bp.route('/api/admin/rate-limits/config')
@login_required
@admin_required
def api_rate_limit_config():
    """Get rate limit configuration"""
    limiter = DestinationRateLimiter()
    
    config = {}
    for limit_type in RateLimitType:
        limit_config = limiter.limits[limit_type]
        config[limit_type.value] = {
            'max_requests': limit_config.max_requests,
            'window_seconds': limit_config.window_seconds,
            'burst_limit': limit_config.burst_limit,
            'burst_allowance': limit_config.burst_allowance
        }
    
    return jsonify(config)