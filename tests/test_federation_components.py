"""
Comprehensive unit tests for refactored federation components.

This module tests all the new components we've built including:
- Health monitoring with circuit breaker
- Rate limiting per destination
- Task scheduler
- Maintenance processor
"""
import pytest
import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock, patch, call

from app.federation.health_monitor import InstanceHealthMonitor, HealthStatus
from app.federation.rate_limiter import DestinationRateLimiter, RateLimitType
from app.federation.scheduler import TaskScheduler, ScheduleType, TaskStatus, ScheduledTask
from app.federation.maintenance_processor import MaintenanceProcessor


class TestInstanceHealthMonitor:
    """Test the instance health monitoring system."""
    
    @pytest.mark.asyncio
    async def test_health_monitor_initialization(self, redis_client):
        """Test health monitor initializes with correct defaults."""
        monitor = InstanceHealthMonitor(
            redis_client,
            failure_threshold=5,
            recovery_threshold=3,
            check_interval=300
        )
        
        assert monitor.failure_threshold == 5
        assert monitor.recovery_threshold == 3
        assert monitor.check_interval == 300
    
    @pytest.mark.asyncio
    async def test_record_success(self, redis_client):
        """Test recording successful federation attempts."""
        monitor = InstanceHealthMonitor(redis_client)
        
        # Record success
        await monitor.record_success('example.com', response_time=0.5)
        
        # Verify Redis operations
        redis_client.hincrby.assert_called()
        redis_client.hset.assert_called()
        redis_client.lpush.assert_called()
        
        # Check response time was recorded
        call_args = redis_client.lpush.call_args[0]
        assert call_args[0] == 'health:response_times:example.com'
        assert '0.5' in call_args[1]
    
    @pytest.mark.asyncio
    async def test_record_failure(self, redis_client):
        """Test recording failed federation attempts."""
        monitor = InstanceHealthMonitor(redis_client)
        
        # Record failure
        await monitor.record_failure('example.com', error_type='timeout')
        
        # Verify failure count incremented
        redis_client.hincrby.assert_called_with(
            'health:metrics:example.com',
            'failure_count',
            1
        )
        
        # Verify error recorded
        redis_client.lpush.assert_called()
        call_args = redis_client.lpush.call_args[0]
        assert 'health:errors:example.com' in call_args[0]
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_logic(self, redis_client):
        """Test circuit breaker opens after threshold failures."""
        monitor = InstanceHealthMonitor(redis_client, failure_threshold=3)
        
        # Mock current metrics showing failures
        redis_client.hgetall.return_value = {
            b'failure_count': b'5',
            b'success_count': b'1',
            b'consecutive_failures': b'5',
            b'status': b'healthy'
        }
        
        # Check if we can send
        can_send, reason = await monitor.can_send_to_instance('example.com')
        
        assert can_send is False
        assert 'Circuit breaker open' in reason
        
        # Verify status was updated
        redis_client.hset.assert_called_with(
            'health:metrics:example.com',
            'status',
            'circuit_open'
        )
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery(self, redis_client):
        """Test circuit breaker recovery after successful attempts."""
        monitor = InstanceHealthMonitor(redis_client, recovery_threshold=3)
        
        # Mock metrics showing recovery
        redis_client.hgetall.return_value = {
            b'failure_count': b'10',
            b'success_count': b'20',
            b'consecutive_successes': b'3',
            b'status': b'circuit_open'
        }
        
        # Record success to trigger recovery check
        await monitor.record_success('example.com', 0.5)
        
        # Check recovery logic was triggered
        calls = redis_client.hset.call_args_list
        status_update = next((c for c in calls if 'status' in str(c)), None)
        assert status_update is not None
    
    @pytest.mark.asyncio
    async def test_get_instance_health(self, redis_client):
        """Test retrieving instance health statistics."""
        # Mock health data
        redis_client.hgetall.return_value = {
            b'failure_count': b'5',
            b'success_count': b'95',
            b'status': b'healthy',
            b'last_check': datetime.now(timezone.utc).isoformat().encode()
        }
        
        # Mock response times
        redis_client.lrange.return_value = [b'0.5', b'0.3', b'0.4']
        
        monitor = InstanceHealthMonitor(redis_client)
        health = await monitor.get_instance_health('example.com')
        
        assert health['domain'] == 'example.com'
        assert health['failure_count'] == 5
        assert health['success_count'] == 95
        assert health['success_rate'] == 95.0
        assert health['avg_response_time'] == 0.4


class TestDestinationRateLimiter:
    """Test the per-destination rate limiting system."""
    
    @pytest.mark.asyncio
    async def test_rate_limiter_initialization(self, redis_client):
        """Test rate limiter initializes with correct defaults."""
        limiter = DestinationRateLimiter(redis_client)
        
        # Check default limits
        assert RateLimitType.ACTIVITIES in limiter.limits
        assert limiter.limits[RateLimitType.ACTIVITIES]['max_requests'] == 100
        assert limiter.limits[RateLimitType.ACTIVITIES]['window_seconds'] == 60
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_allowed(self, redis_client):
        """Test rate limit check when under limit."""
        limiter = DestinationRateLimiter(redis_client)
        
        # Mock no recent requests
        redis_client.zcard.return_value = 10  # 10 requests in window
        
        allowed, retry_after, info = await limiter.check_rate_limit(
            'example.com',
            RateLimitType.ACTIVITIES
        )
        
        assert allowed is True
        assert retry_after is None
        assert info['current_requests'] == 10
        assert info['limit'] == 100
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded(self, redis_client):
        """Test rate limit check when limit exceeded."""
        limiter = DestinationRateLimiter(redis_client)
        
        # Mock at limit
        redis_client.zcard.return_value = 100
        
        allowed, retry_after, info = await limiter.check_rate_limit(
            'example.com',
            RateLimitType.ACTIVITIES
        )
        
        assert allowed is False
        assert retry_after > 0
        assert info['current_requests'] == 100
    
    @pytest.mark.asyncio
    async def test_burst_allowance(self, redis_client):
        """Test burst allowance for temporary spikes."""
        limiter = DestinationRateLimiter(redis_client)
        
        # Mock at limit but low recent usage
        redis_client.zcard.return_value = 100
        
        # Mock historical usage (for burst calculation)
        # First call for full window, second for half window
        redis_client.zcard.side_effect = [100, 20]
        
        allowed, retry_after, info = await limiter.check_rate_limit(
            'example.com',
            RateLimitType.ACTIVITIES
        )
        
        # Should allow burst since recent usage is low
        assert allowed is True
        assert 'burst_allowed' in info
        assert info['burst_allowed'] is True
    
    @pytest.mark.asyncio
    async def test_adaptive_rate_limiting(self, redis_client):
        """Test adaptive rate limiting based on response times."""
        limiter = DestinationRateLimiter(redis_client)
        
        # Record fast response times
        for _ in range(5):
            await limiter.record_response_time('fast.com', 0.2)
        
        # Record slow response times
        for _ in range(5):
            await limiter.record_response_time('slow.com', 3.0)
        
        # Check adjustments were stored
        assert redis_client.hset.call_count >= 2
        
        # Verify different adjustment factors
        calls = redis_client.hset.call_args_list
        fast_call = next(c for c in calls if 'fast.com' in str(c))
        slow_call = next(c for c in calls if 'slow.com' in str(c))
        
        assert fast_call != slow_call
    
    @pytest.mark.asyncio
    async def test_rate_limit_reset(self, redis_client):
        """Test resetting rate limits for a destination."""
        limiter = DestinationRateLimiter(redis_client)
        
        # Reset limits
        await limiter.reset_limits('example.com')
        
        # Verify all rate limit keys were deleted
        delete_calls = redis_client.delete.call_args_list
        assert len(delete_calls) >= len(RateLimitType)
    
    @pytest.mark.asyncio
    async def test_global_rate_limit(self, redis_client):
        """Test global rate limit across all request types."""
        limiter = DestinationRateLimiter(redis_client)
        
        # Mock different request type counts
        redis_client.zcard.side_effect = [50, 30, 20, 10, 0]  # Different types
        
        # Global limit should consider all types
        allowed, retry_after, info = await limiter.check_rate_limit(
            'example.com',
            RateLimitType.ACTIVITIES
        )
        
        # Multiple zcard calls for different limit types
        assert redis_client.zcard.call_count > 1


class TestTaskScheduler:
    """Test the task scheduling system."""
    
    @pytest.mark.asyncio
    async def test_scheduler_initialization(self, redis_client):
        """Test scheduler initializes correctly."""
        scheduler = TaskScheduler('redis://localhost')
        
        assert scheduler.task_key_prefix == 'scheduler:task:'
        assert scheduler.check_interval == 60
        assert scheduler.redis is None  # Not started yet
    
    @pytest.mark.asyncio
    async def test_schedule_cron_task(self, redis_client):
        """Test scheduling a cron-based task."""
        scheduler = TaskScheduler('redis://localhost')
        scheduler.redis = redis_client
        
        # Schedule daily task
        task = await scheduler.schedule_task(
            name='daily_cleanup',
            task_type='maintenance',
            schedule='0 2 * * *',  # 2 AM daily
            payload={'days_to_keep': 30},
            schedule_type=ScheduleType.CRON,
            timezone='UTC'
        )
        
        assert task.name == 'daily_cleanup'
        assert task.schedule_type == ScheduleType.CRON
        assert task.next_run is not None
        
        # Verify saved to Redis
        redis_client.set.assert_called()
        call_args = redis_client.set.call_args[0]
        assert 'scheduler:task:' in call_args[0]
    
    @pytest.mark.asyncio
    async def test_schedule_interval_task(self, redis_client):
        """Test scheduling an interval-based task."""
        scheduler = TaskScheduler('redis://localhost')
        scheduler.redis = redis_client
        
        # Schedule every 5 minutes
        task = await scheduler.schedule_task(
            name='health_check',
            task_type='monitoring',
            schedule='5m',
            payload={'targets': ['example.com']},
            schedule_type=ScheduleType.INTERVAL
        )
        
        assert task.schedule == '5m'
        assert task.next_run is not None
        
        # Next run should be ~5 minutes from now
        expected_next = datetime.now(timezone.utc) + timedelta(minutes=5)
        assert abs((task.next_run - expected_next).total_seconds()) < 2
    
    @pytest.mark.asyncio
    async def test_execute_due_task(self, redis_client):
        """Test executing a task that's due."""
        scheduler = TaskScheduler('redis://localhost')
        scheduler.redis = redis_client
        
        # Create a task that's due now
        task = ScheduledTask(
            id='test-1',
            name='test_task',
            task_type='maintenance',
            schedule_type=ScheduleType.ONE_TIME,
            schedule=datetime.now(timezone.utc).isoformat(),
            payload={'test': 'data'},
            status=TaskStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            next_run=datetime.now(timezone.utc) - timedelta(minutes=1)  # Past due
        )
        
        # Mock task retrieval
        redis_client.get.return_value = json.dumps(task.to_dict())
        redis_client.scan.return_value = (0, [b'scheduler:task:test-1'])
        
        # Execute task
        await scheduler._execute_task(task)
        
        # Verify task was added to stream
        redis_client.xadd.assert_called()
        call_args = redis_client.xadd.call_args[0]
        assert 'maintenance' in call_args[0]  # Stream name
        assert call_args[1]['task_name'] == 'test_task'
    
    @pytest.mark.asyncio
    async def test_pause_resume_task(self, redis_client):
        """Test pausing and resuming scheduled tasks."""
        scheduler = TaskScheduler('redis://localhost')
        scheduler.redis = redis_client
        
        # Mock existing task
        task_data = {
            'id': 'test-1',
            'name': 'test_task',
            'status': 'active',
            'enabled': True,
            'schedule_type': 'interval',
            'schedule': '1h',
            'task_type': 'maintenance',
            'payload': {},
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        redis_client.get.return_value = json.dumps(task_data)
        
        # Pause task
        success = await scheduler.pause_task('test-1')
        assert success is True
        
        # Verify status updated
        saved_data = json.loads(redis_client.set.call_args[0][1])
        assert saved_data['status'] == 'paused'
        assert saved_data['enabled'] is False
    
    @pytest.mark.asyncio
    async def test_task_failure_handling(self, redis_client):
        """Test handling of task execution failures."""
        scheduler = TaskScheduler('redis://localhost')
        scheduler.redis = redis_client
        
        # Create task that will fail
        task = ScheduledTask(
            id='fail-1',
            name='failing_task',
            task_type='invalid_type',  # This will cause failure
            schedule_type=ScheduleType.INTERVAL,
            schedule='1h',
            payload={},
            status=TaskStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            next_run=datetime.now(timezone.utc),
            max_retries=3,
            error_count=2  # Already failed twice
        )
        
        # Execute failing task
        redis_client.xadd.side_effect = Exception("Stream error")
        await scheduler._execute_task(task)
        
        # Verify error handling
        saved_data = json.loads(redis_client.set.call_args[0][1])
        assert saved_data['error_count'] == 3
        assert saved_data['status'] == 'failed'  # Disabled after max retries
        assert 'last_error' in saved_data


class TestMaintenanceProcessor:
    """Test the maintenance task processor."""
    
    @pytest.mark.asyncio
    async def test_processor_initialization(self, redis_client, async_session):
        """Test maintenance processor initialization."""
        processor = MaintenanceProcessor(
            redis_client,
            async_session,
            stream_name='test:maintenance'
        )
        
        assert processor.stream_name == 'test:maintenance'
        assert processor.consumer_group == 'maintenance-group'
        assert processor._running is False
    
    @pytest.mark.asyncio
    async def test_cleanup_old_activities(self, redis_client, async_session):
        """Test cleanup of old activity logs."""
        processor = MaintenanceProcessor(redis_client, async_session)
        
        # Mock database query results
        with patch.object(async_session, 'scalar', return_value=100):  # 100 old records
            with patch.object(async_session, 'execute') as mock_execute:
                # Mock ID query results
                mock_result = Mock()
                mock_result.__iter__ = Mock(return_value=iter([(1,), (2,), (3,)]))
                mock_execute.return_value = mock_result
                
                # Run cleanup
                await processor._cleanup_old_activities({
                    'days_to_keep': 30,
                    'batch_size': 10
                })
                
                # Verify delete operations
                assert mock_execute.call_count >= 2  # At least select and delete
    
    @pytest.mark.asyncio
    async def test_update_instance_stats(self, redis_client, async_session):
        """Test updating instance statistics."""
        processor = MaintenanceProcessor(redis_client, async_session)
        
        # Mock instance query
        mock_instance = Mock()
        mock_instance.id = 1
        mock_instance.domain = 'example.com'
        
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_instance]
        
        with patch.object(async_session, 'execute', return_value=mock_result):
            with patch.object(async_session, 'scalar', side_effect=[10, 50]):  # user count, post count
                with patch.object(async_session, 'commit'):
                    await processor._update_instance_stats({})
                    
                    # Verify stats were updated
                    assert mock_instance.user_count == 10
                    assert mock_instance.post_count == 50
    
    @pytest.mark.asyncio
    async def test_message_routing(self, redis_client, async_session):
        """Test routing of maintenance messages to handlers."""
        processor = MaintenanceProcessor(redis_client, async_session)
        
        # Mock message processing
        test_messages = [
            ('cleanup_old_activities', {'days_to_keep': 7}),
            ('update_instance_stats', {}),
            ('unknown_task', {})  # Should log warning
        ]
        
        for task_name, payload in test_messages:
            with patch.object(processor, f'_{task_name}', new_callable=AsyncMock) as mock_handler:
                await processor._process_message(
                    'msg-1',
                    {'task_name': task_name, 'payload': payload}
                )
                
                if task_name != 'unknown_task':
                    mock_handler.assert_called_once_with(payload)
                
                # Verify acknowledgment
                redis_client.xack.assert_called()


class TestIntegrationScenarios:
    """Test integration between components."""
    
    @pytest.mark.asyncio
    async def test_health_and_rate_limit_integration(self, redis_client):
        """Test health monitor affects rate limiting."""
        health_monitor = InstanceHealthMonitor(redis_client)
        rate_limiter = DestinationRateLimiter(redis_client)
        
        # Mark instance as unhealthy
        redis_client.hgetall.return_value = {
            b'status': b'degraded',
            b'failure_count': b'10',
            b'success_count': b'5'
        }
        
        # Check if unhealthy status affects rate limits
        can_send, reason = await health_monitor.can_send_to_instance('unhealthy.com')
        
        # Rate limiter should respect health status
        if not can_send:
            allowed, _, _ = await rate_limiter.check_rate_limit(
                'unhealthy.com',
                RateLimitType.ACTIVITIES
            )
            # Could implement logic to reduce limits for unhealthy instances
    
    @pytest.mark.asyncio
    async def test_scheduler_creates_maintenance_tasks(self, redis_client):
        """Test scheduler can create and execute maintenance tasks."""
        scheduler = TaskScheduler('redis://localhost')
        scheduler.redis = redis_client
        
        # Schedule a maintenance task
        task = await scheduler.schedule_task(
            name='test_maintenance',
            task_type='maintenance',
            schedule='*/10 * * * *',  # Every 10 minutes
            payload={'cleanup': True},
            schedule_type=ScheduleType.CRON
        )
        
        # Mock task execution
        redis_client.xadd.return_value = b'123456789-0'
        await scheduler._execute_task(task)
        
        # Verify task was queued to maintenance stream
        call_args = redis_client.xadd.call_args[0]
        assert 'maintenance' in call_args[0]
        assert call_args[1]['task_name'] == 'test_maintenance'