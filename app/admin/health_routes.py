"""
Admin routes for instance health monitoring
"""
from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for
from flask_login import login_required
from app.admin.util import admin_required
from app.federation.health_monitor import InstanceHealthMonitor, InstanceHealth

bp = Blueprint('admin_health', __name__)


@bp.route('/health/instances')
@login_required
@admin_required
def instance_health():
    """View instance health dashboard"""
    monitor = InstanceHealthMonitor()
    health_data = monitor.get_all_instance_health()
    
    # Group by health status
    healthy = []
    degraded = []
    unhealthy = []
    dead = []
    
    for domain, data in health_data.items():
        entry = {'domain': domain, **data}
        
        if data['health'] == InstanceHealth.HEALTHY.value:
            healthy.append(entry)
        elif data['health'] == InstanceHealth.DEGRADED.value:
            degraded.append(entry)
        elif data['health'] == InstanceHealth.UNHEALTHY.value:
            unhealthy.append(entry)
        else:  # DEAD
            dead.append(entry)
    
    return render_template('admin/instance_health.html',
                           healthy=healthy,
                           degraded=degraded,
                           unhealthy=unhealthy,
                           dead=dead,
                           total=len(health_data))


@bp.route('/health/instances/<domain>')
@login_required
@admin_required
def instance_health_detail(domain):
    """View detailed health info for an instance"""
    monitor = InstanceHealthMonitor()
    health_data = monitor.get_all_instance_health()
    
    if domain not in health_data:
        flash(f'No health data for {domain}', 'warning')
        return redirect(url_for('admin_health.instance_health'))
    
    data = health_data[domain]
    metrics = monitor._get_metrics(domain)
    
    return render_template('admin/instance_health_detail.html',
                           domain=domain,
                           health=data,
                           metrics=metrics.to_dict())


@bp.route('/health/instances/<domain>/reset', methods=['POST'])
@login_required
@admin_required
def reset_instance_health(domain):
    """Reset health metrics for an instance"""
    monitor = InstanceHealthMonitor()
    monitor.reset_instance_health(domain)
    
    flash(f'Health metrics reset for {domain}', 'success')
    return redirect(url_for('admin_health.instance_health'))


@bp.route('/api/admin/health/instances')
@login_required
@admin_required
def api_instance_health():
    """API endpoint for instance health data"""
    monitor = InstanceHealthMonitor()
    health_data = monitor.get_all_instance_health()
    
    # Add summary statistics
    summary = {
        'total': len(health_data),
        'healthy': sum(1 for d in health_data.values() if d['health'] == 'healthy'),
        'degraded': sum(1 for d in health_data.values() if d['health'] == 'degraded'),
        'unhealthy': sum(1 for d in health_data.values() if d['health'] == 'unhealthy'),
        'dead': sum(1 for d in health_data.values() if d['health'] == 'dead'),
        'circuits_open': sum(1 for d in health_data.values() if d['circuit_state'] == 'open')
    }
    
    return jsonify({
        'instances': health_data,
        'summary': summary
    })