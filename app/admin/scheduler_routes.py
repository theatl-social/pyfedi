"""
Admin routes for task scheduler management.

This module provides web interface and API endpoints for managing
scheduled tasks in the PeachPie federation system.
"""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required
from flask_babel import _
from typing import Dict, Any
import json
from datetime import datetime

from app.utils import user_access_required
from app.federation.scheduler import TaskScheduler, ScheduleType, TaskStatus

bp = Blueprint('admin_scheduler', __name__)


@bp.route('/scheduled-tasks')
@login_required
@user_access_required('change instance settings')
def scheduled_tasks():
    """Display scheduled tasks dashboard"""
    return render_template(
        'admin/scheduled_tasks.html',
        title=_('Scheduled Tasks'),
        active_child='admin_scheduler'
    )


@bp.route('/scheduled-tasks/new')
@login_required
@user_access_required('change instance settings')
def new_scheduled_task():
    """Display form to create new scheduled task"""
    return render_template(
        'admin/scheduled_task_form.html',
        title=_('New Scheduled Task'),
        task=None,
        schedule_types=ScheduleType,
        task_types=[
            'maintenance',
            'federation',
            'cleanup',
            'analytics',
            'notification'
        ]
    )


@bp.route('/scheduled-tasks/<task_id>')
@login_required
@user_access_required('change instance settings')
def scheduled_task_detail(task_id: str):
    """Display scheduled task details"""
    return render_template(
        'admin/scheduled_task_detail.html',
        title=_('Scheduled Task Details'),
        task_id=task_id
    )


@bp.route('/scheduled-tasks/<task_id>/edit')
@login_required
@user_access_required('change instance settings')
def edit_scheduled_task(task_id: str):
    """Display form to edit scheduled task"""
    return render_template(
        'admin/scheduled_task_form.html',
        title=_('Edit Scheduled Task'),
        task_id=task_id,
        schedule_types=ScheduleType,
        task_types=[
            'maintenance',
            'federation',
            'cleanup',
            'analytics',
            'notification'
        ]
    )


# API endpoints
@bp.route('/api/scheduled-tasks', methods=['GET'])
@login_required
@user_access_required('change instance settings')
async def api_list_scheduled_tasks():
    """API endpoint to list scheduled tasks"""
    from app import current_app
    
    scheduler = TaskScheduler(
        redis_url=current_app.config['REDIS_URL']
    )
    
    try:
        await scheduler.start()
        
        # Get filter parameters
        status = request.args.get('status')
        task_type = request.args.get('task_type')
        
        # Convert status string to enum if provided
        if status:
            try:
                status = TaskStatus(status)
            except ValueError:
                status = None
        
        tasks = await scheduler.list_tasks(status=status, task_type=task_type)
        
        # Convert tasks to JSON-serializable format
        tasks_data = []
        for task in tasks:
            task_dict = task.to_dict()
            task_dict['status'] = task.status.value
            task_dict['schedule_type'] = task.schedule_type.value
            tasks_data.append(task_dict)
        
        return jsonify({
            'tasks': tasks_data,
            'total': len(tasks_data)
        })
        
    finally:
        await scheduler.stop()


@bp.route('/api/scheduled-tasks/<task_id>', methods=['GET'])
@login_required
@user_access_required('change instance settings')
async def api_get_scheduled_task(task_id: str):
    """API endpoint to get a specific scheduled task"""
    from app import current_app
    
    scheduler = TaskScheduler(
        redis_url=current_app.config['REDIS_URL']
    )
    
    try:
        await scheduler.start()
        task = await scheduler.get_task(task_id)
        
        if not task:
            return jsonify({'error': 'Task not found'}), 404
        
        task_dict = task.to_dict()
        task_dict['status'] = task.status.value
        task_dict['schedule_type'] = task.schedule_type.value
        
        return jsonify(task_dict)
        
    finally:
        await scheduler.stop()


@bp.route('/api/scheduled-tasks', methods=['POST'])
@login_required
@user_access_required('change instance settings')
async def api_create_scheduled_task():
    """API endpoint to create a new scheduled task"""
    from app import current_app
    
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['name', 'task_type', 'schedule', 'schedule_type']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    scheduler = TaskScheduler(
        redis_url=current_app.config['REDIS_URL']
    )
    
    try:
        await scheduler.start()
        
        # Parse payload if provided as string
        payload = data.get('payload', {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return jsonify({'error': 'Invalid JSON in payload'}), 400
        
        task = await scheduler.schedule_task(
            name=data['name'],
            task_type=data['task_type'],
            schedule=data['schedule'],
            payload=payload,
            schedule_type=ScheduleType(data['schedule_type']),
            timezone=data.get('timezone', 'UTC'),
            max_retries=data.get('max_retries', 3),
            enabled=data.get('enabled', True)
        )
        
        task_dict = task.to_dict()
        task_dict['status'] = task.status.value
        task_dict['schedule_type'] = task.schedule_type.value
        
        return jsonify(task_dict), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400
        
    finally:
        await scheduler.stop()


@bp.route('/api/scheduled-tasks/<task_id>', methods=['PUT'])
@login_required
@user_access_required('change instance settings')
async def api_update_scheduled_task(task_id: str):
    """API endpoint to update a scheduled task"""
    from app import current_app
    
    data = request.get_json()
    
    scheduler = TaskScheduler(
        redis_url=current_app.config['REDIS_URL']
    )
    
    try:
        await scheduler.start()
        
        # Parse payload if provided as string
        if 'payload' in data and isinstance(data['payload'], str):
            try:
                data['payload'] = json.loads(data['payload'])
            except json.JSONDecodeError:
                return jsonify({'error': 'Invalid JSON in payload'}), 400
        
        # Convert string enums to enum values
        if 'schedule_type' in data:
            data['schedule_type'] = ScheduleType(data['schedule_type'])
        if 'status' in data:
            data['status'] = TaskStatus(data['status'])
        
        task = await scheduler.update_task(task_id, **data)
        
        if not task:
            return jsonify({'error': 'Task not found'}), 404
        
        task_dict = task.to_dict()
        task_dict['status'] = task.status.value
        task_dict['schedule_type'] = task.schedule_type.value
        
        return jsonify(task_dict)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400
        
    finally:
        await scheduler.stop()


@bp.route('/api/scheduled-tasks/<task_id>', methods=['DELETE'])
@login_required
@user_access_required('change instance settings')
async def api_delete_scheduled_task(task_id: str):
    """API endpoint to delete a scheduled task"""
    from app import current_app
    
    scheduler = TaskScheduler(
        redis_url=current_app.config['REDIS_URL']
    )
    
    try:
        await scheduler.start()
        success = await scheduler.delete_task(task_id)
        
        if not success:
            return jsonify({'error': 'Task not found'}), 404
        
        return '', 204
        
    finally:
        await scheduler.stop()


@bp.route('/api/scheduled-tasks/<task_id>/pause', methods=['POST'])
@login_required
@user_access_required('change instance settings')
async def api_pause_scheduled_task(task_id: str):
    """API endpoint to pause a scheduled task"""
    from app import current_app
    
    scheduler = TaskScheduler(
        redis_url=current_app.config['REDIS_URL']
    )
    
    try:
        await scheduler.start()
        success = await scheduler.pause_task(task_id)
        
        if not success:
            return jsonify({'error': 'Task not found'}), 404
        
        return jsonify({'message': 'Task paused successfully'})
        
    finally:
        await scheduler.stop()


@bp.route('/api/scheduled-tasks/<task_id>/resume', methods=['POST'])
@login_required
@user_access_required('change instance settings')
async def api_resume_scheduled_task(task_id: str):
    """API endpoint to resume a scheduled task"""
    from app import current_app
    
    scheduler = TaskScheduler(
        redis_url=current_app.config['REDIS_URL']
    )
    
    try:
        await scheduler.start()
        success = await scheduler.resume_task(task_id)
        
        if not success:
            return jsonify({'error': 'Task not found'}), 404
        
        return jsonify({'message': 'Task resumed successfully'})
        
    finally:
        await scheduler.stop()


@bp.route('/api/scheduled-tasks/<task_id>/run', methods=['POST'])
@login_required
@user_access_required('change instance settings')
async def api_run_scheduled_task_now(task_id: str):
    """API endpoint to run a scheduled task immediately"""
    from app import current_app
    
    scheduler = TaskScheduler(
        redis_url=current_app.config['REDIS_URL']
    )
    
    try:
        await scheduler.start()
        task = await scheduler.get_task(task_id)
        
        if not task:
            return jsonify({'error': 'Task not found'}), 404
        
        # Execute the task
        await scheduler._execute_task(task)
        
        return jsonify({'message': 'Task executed successfully'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400
        
    finally:
        await scheduler.stop()


@bp.route('/api/scheduler/stats', methods=['GET'])
@login_required
@user_access_required('change instance settings')
async def api_scheduler_stats():
    """API endpoint to get scheduler statistics"""
    from app import current_app
    
    scheduler = TaskScheduler(
        redis_url=current_app.config['REDIS_URL']
    )
    
    try:
        await scheduler.start()
        stats = await scheduler.get_scheduler_stats()
        return jsonify(stats)
        
    finally:
        await scheduler.stop()