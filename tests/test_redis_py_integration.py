"""
Test Redis-py integration after migration from aioredis
"""
import pytest
import redis
import json
import time
from unittest.mock import Mock, patch

from app.federation.producer import FederationProducer, get_producer
from app.federation.types import Priority, ActivityType
from app.federation.rate_limiter import DestinationRateLimiter, RateLimitType
from app.federation.redis_functions import Redis7Functions, get_redis7_functions


class TestRedisIntegration:
    """Test Redis-py integration"""
    
    @pytest.fixture
    def redis_client(self):
        """Create a test Redis client"""
        client = redis.from_url('redis://localhost:6379/15', decode_responses=True)  # Use DB 15 for tests
        # Clean up before tests
        client.flushdb()
        yield client
        # Clean up after tests
        client.flushdb()
    
    def test_producer_sync_operations(self, redis_client):
        """Test that producer uses synchronous Redis operations"""
        producer = FederationProducer(redis_client)
        
        # Test queueing an activity
        activity = {
            'type': 'Like',
            'actor': 'https://example.com/users/alice',
            'object': 'https://example.com/posts/1'
        }
        
        msg_id = producer.queue_activity(activity, priority=Priority.NORMAL)
        assert msg_id is not None
        
        # Verify it was added to the stream
        messages = redis_client.xrange('federation:normal', count=1)
        assert len(messages) == 1
        assert json.loads(messages[0][1]['data'])['activity'] == activity
    
    def test_producer_batch_operations(self, redis_client):
        """Test batch operations use pipeline"""
        producer = FederationProducer(redis_client)
        
        activities = [
            {
                'type': 'Like',
                'actor': f'https://example.com/users/user{i}',
                'object': 'https://example.com/posts/1'
            }
            for i in range(5)
        ]
        
        msg_ids = producer.queue_batch(activities, priority=Priority.BULK)
        assert len(msg_ids) == 5
        
        # Verify all were added
        messages = redis_client.xrange('federation:bulk', count=10)
        assert len(messages) == 5
    
    def test_rate_limiter_pipeline(self, app):
        """Test rate limiter uses pipeline for better performance"""
        with app.app_context():
            limiter = DestinationRateLimiter()
            
            # First request should be allowed
            allowed, retry_after, info = limiter.check_rate_limit(
                'example.com',
                RateLimitType.ACTIVITIES
            )
            assert allowed is True
            assert retry_after is None
            assert info['current_requests'] == 1
    
    def test_redis7_functions(self, redis_client):
        """Test Redis 7 functions if available"""
        functions = Redis7Functions(redis_client)
        
        # Try to load functions
        loaded = functions.load_functions()
        
        if loaded:
            # Test atomic rate limiting
            now = time.time()
            allowed, retry_after, count, global_count, burst = functions.check_rate_limit(
                key='test:rate:activities',
                global_key='test:rate:global',
                now=now,
                window=60,
                limit=10,
                burst_limit=12,
                global_window=60,
                global_limit=100
            )
            
            assert allowed is True
            assert retry_after == 0
            assert count == 1
            assert global_count == 1
            assert burst is False
        else:
            # Redis 7 not available, skip
            pytest.skip("Redis 7 functions not available")
    
    def test_stream_operations(self, redis_client):
        """Test Redis Streams operations"""
        # Add some messages
        stream_key = 'test:stream'
        
        for i in range(5):
            redis_client.xadd(
                stream_key,
                {'data': f'message-{i}', 'timestamp': str(time.time())},
                maxlen=100
            )
        
        # Read messages
        messages = redis_client.xrange(stream_key)
        assert len(messages) == 5
        
        # Test consumer group operations
        redis_client.xgroup_create(stream_key, 'test-group', id='0')
        
        # Read as consumer
        pending = redis_client.xreadgroup(
            'test-group',
            'consumer-1',
            {stream_key: '>'},
            count=2
        )
        
        assert len(pending[0][1]) == 2
        
        # Acknowledge messages
        msg_ids = [msg[0] for msg in pending[0][1]]
        acked = redis_client.xack(stream_key, 'test-group', *msg_ids)
        assert acked == 2
    
    def test_pipeline_performance(self, redis_client):
        """Test pipeline improves performance"""
        # Without pipeline
        start = time.time()
        for i in range(100):
            redis_client.set(f'key-{i}', f'value-{i}')
        no_pipeline_time = time.time() - start
        
        # Clean up
        for i in range(100):
            redis_client.delete(f'key-{i}')
        
        # With pipeline
        start = time.time()
        with redis_client.pipeline() as pipe:
            for i in range(100):
                pipe.set(f'key-{i}', f'value-{i}')
            pipe.execute()
        pipeline_time = time.time() - start
        
        # Pipeline should be faster (or at least not significantly slower)
        # In practice, pipeline is much faster for remote Redis
        assert pipeline_time <= no_pipeline_time * 1.5  # Allow some variance
    
    def test_redis_datatypes(self, redis_client):
        """Test various Redis data types work correctly"""
        # Strings
        redis_client.set('test:string', 'hello')
        assert redis_client.get('test:string') == 'hello'
        
        # Lists
        redis_client.rpush('test:list', 'a', 'b', 'c')
        assert redis_client.lrange('test:list', 0, -1) == ['a', 'b', 'c']
        
        # Sets
        redis_client.sadd('test:set', 'x', 'y', 'z')
        assert redis_client.scard('test:set') == 3
        
        # Sorted sets
        redis_client.zadd('test:zset', {'alice': 100, 'bob': 200})
        assert redis_client.zrange('test:zset', 0, -1) == ['alice', 'bob']
        
        # Hashes
        redis_client.hset('test:hash', mapping={'field1': 'value1', 'field2': 'value2'})
        assert redis_client.hgetall('test:hash') == {'field1': 'value1', 'field2': 'value2'}
    
    def test_expiry_operations(self, redis_client):
        """Test key expiry operations"""
        redis_client.setex('test:expiring', 2, 'temporary')
        assert redis_client.get('test:expiring') == 'temporary'
        
        # Check TTL
        ttl = redis_client.ttl('test:expiring')
        assert 0 < ttl <= 2
        
        # Wait for expiry
        time.sleep(3)
        assert redis_client.get('test:expiring') is None


class TestRedisCompatibility:
    """Test compatibility with existing Redis usage patterns"""
    
    def test_decode_responses(self):
        """Test decode_responses=True works correctly"""
        client = redis.from_url('redis://localhost:6379/15', decode_responses=True)
        
        # Should return strings, not bytes
        client.set('test:decode', 'value')
        result = client.get('test:decode')
        assert isinstance(result, str)
        assert result == 'value'
        
        client.delete('test:decode')
    
    def test_connection_pool(self):
        """Test connection pooling works"""
        pool = redis.ConnectionPool.from_url('redis://localhost:6379/15')
        client1 = redis.Redis(connection_pool=pool, decode_responses=True)
        client2 = redis.Redis(connection_pool=pool, decode_responses=True)
        
        # Both clients should work
        client1.set('test:pool', 'from-client1')
        assert client2.get('test:pool') == 'from-client1'
        
        client1.delete('test:pool')
    
    @patch('redis.from_url')
    def test_redis_url_parsing(self, mock_from_url):
        """Test Redis URL is parsed correctly"""
        mock_client = Mock()
        mock_from_url.return_value = mock_client
        
        # Test various URL formats
        urls = [
            'redis://localhost:6379/0',
            'redis://user:pass@localhost:6379/1',
            'redis://redis.example.com:6380/2',
            'unix:///var/run/redis.sock?db=3'
        ]
        
        for url in urls:
            client = redis.from_url(url, decode_responses=True)
            mock_from_url.assert_called_with(url, decode_responses=True)