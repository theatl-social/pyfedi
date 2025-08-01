"""
Test suite for Redis Streams federation implementation
"""
import pytest
import redis
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from app.federation.tasks import (
    FederationTask, FederationTaskType, TaskPriority,
    FederationTaskProcessor, FederationMonitor
)
from app.federation.stream_utils import (
    get_stream_name, get_task_id, ensure_consumer_group,
    add_to_stream, read_from_stream
)
from app import create_app, db
from app.models import Instance, User, Community, Post


class TestRedisStreamsBasics:
    """Test basic Redis Streams functionality"""
    
    @pytest.fixture
    def app(self):
        """Create test application"""
        app = create_app('testing')
        with app.app_context():
            db.create_all()
            yield app
            db.session.remove()
            db.drop_all()
    
    @pytest.fixture
    def redis_client(self, app):
        """Get Redis client"""
        return redis.from_url(app.config['REDIS_URL'])
    
    def test_stream_creation(self, redis_client):
        """Test creating streams for different priorities"""
        # Add tasks to different priority streams
        for priority in TaskPriority:
            stream_name = get_stream_name(priority)
            task_id = get_task_id()
            
            data = {
                'task_id': task_id,
                'type': 'test',
                'priority': priority.value,
                'created_at': datetime.utcnow().isoformat()
            }
            
            msg_id = redis_client.xadd(stream_name, data)
            assert msg_id is not None
            
            # Read back
            messages = redis_client.xrange(stream_name, count=1)
            assert len(messages) == 1
            assert messages[0][1]['task_id'] == task_id.encode()
    
    def test_consumer_group_creation(self, redis_client):
        """Test consumer group creation"""
        stream_name = get_stream_name(TaskPriority.MEDIUM)
        group_name = 'test-group'
        
        # Ensure stream exists
        redis_client.xadd(stream_name, {'test': 'data'})
        
        # Create consumer group
        ensure_consumer_group(redis_client, stream_name, group_name)
        
        # Verify group exists
        groups = redis_client.xinfo_groups(stream_name)
        assert any(g['name'] == group_name.encode() for g in groups)
    
    def test_task_serialization(self):
        """Test FederationTask serialization"""
        task = FederationTask(
            type=FederationTaskType.SEND_ACTIVITY,
            payload={
                'activity': {'type': 'Like', 'id': 'test-123'},
                'recipients': ['https://example.com/inbox']
            },
            priority=TaskPriority.HIGH,
            source='test',
            retry_count=0
        )
        
        # Serialize
        data = task.to_redis()
        assert data['type'] == 'send_activity'
        assert data['priority'] == 'high'
        assert 'payload' in data
        
        # Deserialize
        task2 = FederationTask.from_redis(data)
        assert task2.type == FederationTaskType.SEND_ACTIVITY
        assert task2.priority == TaskPriority.HIGH
        assert task2.payload['activity']['type'] == 'Like'


class TestFederationTaskProcessor:
    """Test task processing logic"""
    
    @pytest.fixture
    def processor(self, app):
        """Create task processor"""
        with app.app_context():
            return FederationTaskProcessor(
                worker_id='test-worker',
                redis_url=app.config['REDIS_URL']
            )
    
    @pytest.fixture
    def sample_instance(self, app):
        """Create test instance"""
        with app.app_context():
            instance = Instance(
                domain='example.com',
                software='mastodon',
                inbox='https://example.com/inbox',
                shared_inbox='https://example.com/inbox'
            )
            db.session.add(instance)
            db.session.commit()
            return instance
    
    def test_send_activity_success(self, processor, sample_instance):
        """Test successful activity delivery"""
        with patch('app.activitypub.signature.post_request') as mock_post:
            mock_post.return_value = True
            
            task = FederationTask(
                type=FederationTaskType.SEND_ACTIVITY,
                payload={
                    'activity': {
                        'type': 'Like',
                        'id': 'https://local.test/activities/1',
                        'actor': 'https://local.test/users/alice',
                        'object': 'https://example.com/posts/1'
                    },
                    'recipients': ['https://example.com/inbox']
                }
            )
            
            result = processor.process_task(task)
            assert result is True
            mock_post.assert_called_once()
    
    def test_send_activity_failure_retry(self, processor, sample_instance):
        """Test activity delivery failure with retry"""
        with patch('app.activitypub.signature.post_request') as mock_post:
            mock_post.return_value = False
            
            task = FederationTask(
                type=FederationTaskType.SEND_ACTIVITY,
                payload={
                    'activity': {'type': 'Like'},
                    'recipients': ['https://example.com/inbox']
                },
                retry_count=0
            )
            
            # Process should fail but schedule retry
            with patch.object(processor, '_schedule_retry') as mock_retry:
                result = processor.process_task(task)
                assert result is False
                mock_retry.assert_called_once()
    
    def test_process_incoming_activity(self, processor):
        """Test processing incoming activities"""
        with patch('app.activitypub.routes.activities.process_inbox_request') as mock_process:
            mock_process.return_value = True
            
            task = FederationTask(
                type=FederationTaskType.PROCESS_INCOMING,
                payload={
                    'activity': {
                        'type': 'Create',
                        'actor': 'https://example.com/users/bob',
                        'object': {
                            'type': 'Note',
                            'content': 'Hello world!'
                        }
                    },
                    'instance': 'example.com'
                }
            )
            
            result = processor.process_task(task)
            assert result is True
            mock_process.assert_called_once()
    
    def test_dead_letter_queue(self, processor):
        """Test DLQ for permanently failed tasks"""
        task = FederationTask(
            type=FederationTaskType.SEND_ACTIVITY,
            payload={'activity': {}, 'recipients': []},
            retry_count=10  # Exceeds max retries
        )
        
        with patch.object(processor.dlq_handler, 'add_to_dlq') as mock_dlq:
            with patch('app.activitypub.signature.post_request', return_value=False):
                processor.process_task(task)
                mock_dlq.assert_called_once()


class TestRedisStreamsIntegration:
    """Integration tests for Redis Streams federation"""
    
    @pytest.fixture
    def setup_federation(self, app):
        """Set up federation test environment"""
        with app.app_context():
            # Create instances
            local = Instance(
                domain='local.test',
                software='peachpie'
            )
            remote = Instance(
                domain='remote.test',
                software='mastodon',
                inbox='https://remote.test/inbox'
            )
            db.session.add_all([local, remote])
            
            # Create users
            alice = User(
                user_name='alice',
                email='alice@local.test',
                instance_id=local.id,
                ap_profile_id='https://local.test/users/alice'
            )
            bob = User(
                user_name='bob',
                email='bob@remote.test',
                instance_id=remote.id,
                ap_profile_id='https://remote.test/users/bob'
            )
            db.session.add_all([alice, bob])
            
            db.session.commit()
            return {'alice': alice, 'bob': bob, 'local': local, 'remote': remote}
    
    def test_end_to_end_federation(self, app, setup_federation):
        """Test complete federation flow"""
        with app.app_context():
            alice = setup_federation['alice']
            
            # Simulate creating a post
            post = Post(
                user_id=alice.id,
                title='Test Post',
                body='This is a test',
                ap_id='https://local.test/posts/1'
            )
            db.session.add(post)
            db.session.commit()
            
            # Queue federation task
            from app.federation.tasks import queue_federation_task
            task = FederationTask(
                type=FederationTaskType.SEND_ACTIVITY,
                payload={
                    'activity': {
                        'type': 'Create',
                        'actor': alice.ap_profile_id,
                        'object': {
                            'type': 'Article',
                            'id': post.ap_id,
                            'attributedTo': alice.ap_profile_id,
                            'name': post.title,
                            'content': post.body
                        }
                    },
                    'recipients': ['https://remote.test/inbox']
                },
                priority=TaskPriority.MEDIUM
            )
            
            result = queue_federation_task(task)
            assert result is not None
    
    def test_concurrent_processing(self, app):
        """Test concurrent task processing"""
        with app.app_context():
            # Queue multiple tasks
            tasks = []
            for i in range(10):
                task = FederationTask(
                    type=FederationTaskType.SEND_ACTIVITY,
                    payload={
                        'activity': {'type': 'Like', 'id': f'like-{i}'},
                        'recipients': [f'https://example{i}.com/inbox']
                    }
                )
                tasks.append(task)
            
            # Process concurrently
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=3) as executor:
                from app.federation.tasks import queue_federation_task
                futures = [executor.submit(queue_federation_task, task) for task in tasks]
                
                # Verify all queued successfully
                for future in futures:
                    assert future.result() is not None


class TestMonitoring:
    """Test monitoring and metrics"""
    
    @pytest.fixture
    def monitor(self, app):
        """Create federation monitor"""
        with app.app_context():
            return FederationMonitor(redis_url=app.config['REDIS_URL'])
    
    def test_stream_metrics(self, monitor):
        """Test stream metrics collection"""
        metrics = monitor.get_stream_metrics()
        
        assert 'streams' in metrics
        assert 'total_pending' in metrics
        assert 'processing_rate' in metrics
        
        # Check individual stream metrics
        for priority in TaskPriority:
            stream_key = f'stream:{priority.value}'
            assert stream_key in metrics['streams']
            assert 'length' in metrics['streams'][stream_key]
            assert 'oldest_id' in metrics['streams'][stream_key]
    
    def test_worker_health(self, monitor):
        """Test worker health monitoring"""
        # Register worker heartbeat
        monitor.redis_client.hset(
            'federation:workers',
            'test-worker',
            json.dumps({
                'last_heartbeat': datetime.utcnow().isoformat(),
                'tasks_processed': 100,
                'status': 'healthy'
            })
        )
        
        health = monitor.get_worker_health()
        assert 'test-worker' in health
        assert health['test-worker']['status'] == 'healthy'
    
    def test_error_tracking(self, monitor):
        """Test error tracking"""
        # Simulate errors
        for i in range(5):
            monitor.record_error('test_error', f'Error {i}')
        
        errors = monitor.get_recent_errors()
        assert len(errors) >= 5
        assert errors[0]['type'] == 'test_error'


def test_redis_streams_performance():
    """Performance test for Redis Streams"""
    app = create_app('testing')
    
    with app.app_context():
        redis_client = redis.from_url(app.config['REDIS_URL'])
        stream_name = 'test:performance'
        
        # Queue 1000 tasks
        start_time = datetime.utcnow()
        for i in range(1000):
            redis_client.xadd(stream_name, {
                'task_id': f'task-{i}',
                'data': json.dumps({'index': i})
            })
        
        queue_time = (datetime.utcnow() - start_time).total_seconds()
        
        # Read all tasks
        start_time = datetime.utcnow()
        messages = redis_client.xrange(stream_name, count=1000)
        read_time = (datetime.utcnow() - start_time).total_seconds()
        
        # Clean up
        redis_client.delete(stream_name)
        
        # Performance assertions
        assert queue_time < 1.0  # Should queue 1000 tasks in under 1 second
        assert read_time < 0.5   # Should read 1000 tasks in under 0.5 seconds
        assert len(messages) == 1000


if __name__ == '__main__':
    pytest.main([__file__, '-v'])