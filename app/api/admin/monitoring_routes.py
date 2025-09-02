"""
Monitoring and metrics routes for admin API Phase 3
"""
from flask import current_app, jsonify, g
from datetime import datetime, timedelta
from app.api.alpha import admin_bp
from app.api.admin.security import require_private_registration_auth
from app.api.admin.monitoring import admin_monitor, rate_limiter, track_admin_request
from app.models import utcnow
from app import redis_client


@admin_bp.route('/metrics', methods=['GET'])
@admin_bp.doc(
    summary="Get API performance metrics",
    description="""
    Prometheus-compatible metrics endpoint for monitoring API performance.
    Includes request counts, response times, error rates, and system health.
    """,
    security=[{"PrivateRegistrationSecret": []}]
)
@require_private_registration_auth
@track_admin_request('metrics')
def get_metrics():
    """Get comprehensive API metrics"""
    try:
        # Get performance stats from monitor
        perf_stats = admin_monitor.get_performance_stats()
        redis_stats = admin_monitor.get_redis_stats()
        
        # Get current timestamp
        timestamp = utcnow()
        
        # Compile comprehensive metrics
        metrics = {
            'timestamp': timestamp.isoformat(),
            'performance': perf_stats,
            'redis': redis_stats,
            'rate_limiting': {
                'enabled': bool(redis_client),
                'default_limits': rate_limiter.default_limits,
                'fallback_mode': not redis_client
            },
            'system': {
                'uptime_seconds': 0,  # TODO: Track application uptime
                'memory_usage': 'unknown',  # TODO: Add memory monitoring
                'active_connections': redis_stats.get('redis_info', {}).get('connected_clients', 0)
            }
        }
        
        # Add Prometheus format if requested
        accept_header = current_app.config.get('HTTP_ACCEPT', '')
        if 'text/plain' in accept_header:
            prometheus_metrics = _format_prometheus_metrics(metrics)
            return prometheus_metrics, 200, {'Content-Type': 'text/plain; version=0.0.4'}
        
        return metrics, 200
        
    except Exception as e:
        current_app.logger.error(f"Failed to generate metrics: {e}")
        return {
            'success': False,
            'error': 'metrics_failed',
            'message': 'Failed to retrieve metrics',
            'details': {'error': str(e)}
        }, 500


@admin_bp.route('/monitoring/health', methods=['GET'])
@admin_bp.doc(
    summary="Comprehensive health check",
    description="""
    Detailed health check including all system dependencies.
    Validates database, Redis, rate limiting, and API functionality.
    """,
    security=[{"PrivateRegistrationSecret": []}]
)
@require_private_registration_auth
@track_admin_request('health')
def comprehensive_health_check():
    """Comprehensive health check with dependency validation"""
    health_status = {
        'timestamp': utcnow().isoformat(),
        'status': 'healthy',
        'checks': {}
    }
    
    overall_healthy = True
    
    # Database health check
    try:
        from app import db
        db.session.execute('SELECT 1')
        health_status['checks']['database'] = {
            'status': 'healthy',
            'response_time_ms': 0,  # TODO: Measure actual response time
            'message': 'Database connection OK'
        }
    except Exception as e:
        health_status['checks']['database'] = {
            'status': 'unhealthy', 
            'error': str(e),
            'message': 'Database connection failed'
        }
        overall_healthy = False
    
    # Redis health check
    if redis_client:
        try:
            start_time = datetime.now()
            redis_client.ping()
            response_time = int((datetime.now() - start_time).total_seconds() * 1000)
            
            health_status['checks']['redis'] = {
                'status': 'healthy',
                'response_time_ms': response_time,
                'message': 'Redis connection OK',
                'info': redis_client.info('memory')
            }
        except Exception as e:
            health_status['checks']['redis'] = {
                'status': 'unhealthy',
                'error': str(e), 
                'message': 'Redis connection failed'
            }
            overall_healthy = False
    else:
        health_status['checks']['redis'] = {
            'status': 'disabled',
            'message': 'Redis not configured'
        }
    
    # Rate limiting health check
    try:
        test_identifier = f"health_check_{int(datetime.now().timestamp())}"
        rate_status = rate_limiter.check_rate_limit('statistics', test_identifier)
        
        health_status['checks']['rate_limiting'] = {
            'status': 'healthy',
            'message': 'Rate limiting functional',
            'fallback_mode': rate_status.get('fallback', False)
        }
    except Exception as e:
        health_status['checks']['rate_limiting'] = {
            'status': 'degraded',
            'error': str(e),
            'message': 'Rate limiting issues detected'
        }
    
    # API functionality check
    try:
        from app.utils import is_private_registration_enabled
        config_check = is_private_registration_enabled()
        
        health_status['checks']['api'] = {
            'status': 'healthy',
            'message': 'API functionality OK',
            'private_registration_enabled': config_check
        }
    except Exception as e:
        health_status['checks']['api'] = {
            'status': 'unhealthy',
            'error': str(e),
            'message': 'API functionality check failed'
        }
        overall_healthy = False
    
    # Set overall status
    health_status['status'] = 'healthy' if overall_healthy else 'unhealthy'
    
    # Return appropriate HTTP status
    status_code = 200 if overall_healthy else 503
    return health_status, status_code


@admin_bp.route('/monitoring/rate-limits', methods=['GET'])
@admin_bp.doc(
    summary="Get rate limiting status",
    description="""
    Current rate limiting configuration and usage statistics.
    Shows limits, current usage, and reset times for the requesting client.
    """,
    security=[{"PrivateRegistrationSecret": []}]
)
@require_private_registration_auth
@track_admin_request('rate_limits')
def get_rate_limit_status():
    """Get current rate limiting status"""
    try:
        identifier = rate_limiter.get_client_identifier()
        
        # Check all operation types for current client
        rate_statuses = {}
        for operation_type in rate_limiter.default_limits.keys():
            status = rate_limiter.check_rate_limit(operation_type, identifier)
            rate_statuses[operation_type] = status
        
        response = {
            'client_identifier': identifier,
            'rate_limits': rate_statuses,
            'global_config': {
                'redis_enabled': bool(redis_client),
                'fallback_mode': not redis_client,
                'default_limits': rate_limiter.default_limits
            },
            'timestamp': utcnow().isoformat()
        }
        
        return response, 200
        
    except Exception as e:
        current_app.logger.error(f"Failed to get rate limit status: {e}")
        return {
            'success': False,
            'error': 'rate_limit_check_failed',
            'message': 'Failed to check rate limit status',
            'details': {'error': str(e)}
        }, 500


@admin_bp.route('/monitoring/audit', methods=['GET'])
@admin_bp.doc(
    summary="Get audit trail",
    description="""
    Retrieve audit trail of admin API operations.
    Includes timestamps, operations performed, and outcomes.
    """,
    security=[{"PrivateRegistrationSecret": []}]
)
@require_private_registration_auth
@track_admin_request('audit')
def get_audit_trail():
    """Get audit trail from Redis logs"""
    try:
        if not redis_client:
            return {
                'audit_logs': [],
                'message': 'Audit logging requires Redis',
                'redis_available': False
            }, 200
        
        # Get recent audit entries from Redis
        current_time = datetime.utcnow()
        
        # Look back 24 hours for audit entries
        audit_logs = []
        for hours_back in range(24):
            check_time = current_time - timedelta(hours=hours_back)
            hour_key = f"piefed:admin_api:hourly:{check_time.strftime('%Y%m%d%H')}"
            
            try:
                hourly_data = redis_client.hgetall(hour_key)
                if hourly_data:
                    # Convert Redis data to audit format
                    hour_audit = {
                        'hour': check_time.strftime('%Y-%m-%d %H:00'),
                        'operations': {}
                    }
                    
                    for key, value in hourly_data.items():
                        if isinstance(key, bytes):
                            key = key.decode('utf-8')
                        if isinstance(value, bytes):
                            value = int(value.decode('utf-8'))
                        hour_audit['operations'][key] = value
                    
                    if hour_audit['operations']:  # Only include hours with activity
                        audit_logs.append(hour_audit)
            except Exception as e:
                current_app.logger.warning(f"Failed to read audit data for {hour_key}: {e}")
        
        return {
            'audit_logs': audit_logs,
            'total_hours': len(audit_logs),
            'redis_available': True,
            'timestamp': current_time.isoformat()
        }, 200
        
    except Exception as e:
        current_app.logger.error(f"Failed to retrieve audit trail: {e}")
        return {
            'success': False,
            'error': 'audit_retrieval_failed', 
            'message': 'Failed to retrieve audit trail',
            'details': {'error': str(e)}
        }, 500


def _format_prometheus_metrics(metrics_data):
    """Format metrics in Prometheus exposition format"""
    prometheus_lines = []
    
    # Request metrics
    perf = metrics_data.get('performance', {})
    
    # Total requests
    total_requests = perf.get('total_requests', 0)
    prometheus_lines.append('# HELP piefed_admin_api_requests_total Total API requests')
    prometheus_lines.append('# TYPE piefed_admin_api_requests_total counter')
    prometheus_lines.append(f'piefed_admin_api_requests_total {total_requests}')
    
    # Error rate
    error_rate = perf.get('error_rate', 0)
    prometheus_lines.append('# HELP piefed_admin_api_error_rate Error rate percentage')
    prometheus_lines.append('# TYPE piefed_admin_api_error_rate gauge')
    prometheus_lines.append(f'piefed_admin_api_error_rate {error_rate}')
    
    # Response times per endpoint
    for endpoint_method, timing_info in perf.get('average_response_times', {}).items():
        avg_ms = timing_info.get('avg_ms', 0)
        endpoint_safe = endpoint_method.replace('/', '_').replace('-', '_')
        
        prometheus_lines.append('# HELP piefed_admin_api_response_time_ms Response time in milliseconds')
        prometheus_lines.append('# TYPE piefed_admin_api_response_time_ms gauge')
        prometheus_lines.append(f'piefed_admin_api_response_time_ms{{endpoint="{endpoint_safe}"}} {avg_ms}')
    
    # Redis metrics
    redis_info = metrics_data.get('redis', {})
    if redis_info.get('redis_available'):
        connected_clients = redis_info.get('redis_info', {}).get('connected_clients', 0)
        prometheus_lines.append('# HELP piefed_admin_api_redis_clients Connected Redis clients')
        prometheus_lines.append('# TYPE piefed_admin_api_redis_clients gauge')
        prometheus_lines.append(f'piefed_admin_api_redis_clients {connected_clients}')
    
    return '\n'.join(prometheus_lines) + '\n'