"""
Redis 7 Functions for optimized federation operations

This module contains Redis Functions that take advantage of Redis 7's
new scripting capabilities for atomic operations.
"""
import redis
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Redis Function for atomic rate limiting with sliding window
RATE_LIMIT_FUNCTION = """
#!lua name=federation_rate_limiter

-- Sliding window rate limiter with burst support
redis.register_function('check_rate_limit', function(keys, args)
    local key = keys[1]
    local global_key = keys[2]
    local now = tonumber(args[1])
    local window = tonumber(args[2])
    local limit = tonumber(args[3])
    local burst_limit = tonumber(args[4])
    local global_window = tonumber(args[5])
    local global_limit = tonumber(args[6])
    
    -- Clean old entries
    redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
    redis.call('ZREMRANGEBYSCORE', global_key, 0, now - global_window)
    
    -- Count current requests
    local count = redis.call('ZCARD', key)
    local global_count = redis.call('ZCARD', global_key)
    
    -- Check limits
    local under_limit = count < limit
    local under_global = global_count < global_limit
    
    -- Check burst eligibility
    local allow_burst = false
    if not under_limit and count < burst_limit then
        local half_window = now - (window / 2)
        local recent_count = redis.call('ZCOUNT', key, half_window, now)
        if recent_count < (limit / 4) then
            allow_burst = true
        end
    end
    
    local allowed = (under_limit or allow_burst) and under_global
    
    if allowed then
        -- Add request
        redis.call('ZADD', key, now, tostring(now))
        redis.call('EXPIRE', key, window * 2)
        redis.call('ZADD', global_key, now, tostring(now))
        redis.call('EXPIRE', global_key, global_window * 2)
        
        return {1, 0, count + 1, global_count + 1, allow_burst and 1 or 0}
    else
        -- Calculate retry after
        local retry_after = 0
        if not under_limit then
            local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
            if #oldest > 0 then
                retry_after = math.ceil(window - (now - oldest[2]))
            else
                retry_after = window
            end
        else
            local oldest = redis.call('ZRANGE', global_key, 0, 0, 'WITHSCORES')
            if #oldest > 0 then
                retry_after = math.ceil(global_window - (now - oldest[2]))
            else
                retry_after = global_window
            end
        end
        
        return {0, retry_after, count, global_count, 0}
    end
end)

-- Batch increment for activity metrics
redis.register_function('increment_metrics', function(keys, args)
    local results = {}
    for i = 1, #keys do
        local key = keys[i]
        local increment = tonumber(args[i] or 1)
        local new_value = redis.call('INCRBY', key, increment)
        redis.call('EXPIRE', key, 86400)  -- 24 hour expiry
        table.insert(results, new_value)
    end
    return results
end)

-- Atomic stream trimming with count
redis.register_function('trim_stream', function(keys, args)
    local stream_key = keys[1]
    local max_len = tonumber(args[1])
    local approx = args[2] == '1'
    
    -- Get current length
    local info = redis.call('XINFO', 'STREAM', stream_key)
    local current_len = 0
    for i = 1, #info, 2 do
        if info[i] == 'length' then
            current_len = info[i + 1]
            break
        end
    end
    
    -- Trim if needed
    local trimmed = 0
    if current_len > max_len then
        if approx then
            redis.call('XTRIM', stream_key, 'MAXLEN', '~', max_len)
        else
            redis.call('XTRIM', stream_key, 'MAXLEN', max_len)
        end
        trimmed = current_len - max_len
    end
    
    return {current_len, trimmed}
end)
"""


class Redis7Functions:
    """Manager for Redis 7 Functions"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self._functions_loaded = False
    
    def load_functions(self) -> bool:
        """Load Redis Functions into the server"""
        try:
            # Check if functions already exist
            try:
                existing = self.redis.function_list()
                if any(f.get('name') == 'federation_rate_limiter' for f in existing):
                    logger.info("Redis Functions already loaded")
                    self._functions_loaded = True
                    return True
            except Exception:
                pass
            
            # Load the functions
            self.redis.function_load(RATE_LIMIT_FUNCTION, replace=True)
            self._functions_loaded = True
            logger.info("Successfully loaded Redis 7 Functions")
            return True
            
        except redis.ResponseError as e:
            if "unknown command" in str(e).lower():
                logger.warning("Redis Functions not supported (requires Redis 7+)")
                return False
            raise
        except Exception as e:
            logger.error(f"Failed to load Redis Functions: {e}")
            return False
    
    def check_rate_limit(
        self,
        key: str,
        global_key: str,
        now: float,
        window: int,
        limit: int,
        burst_limit: int,
        global_window: int,
        global_limit: int
    ) -> tuple[bool, int, int, int, bool]:
        """
        Check rate limit using Redis Function
        
        Returns:
            (allowed, retry_after, count, global_count, burst_used)
        """
        if not self._functions_loaded:
            raise RuntimeError("Redis Functions not loaded")
        
        result = self.redis.fcall(
            'check_rate_limit',
            2,  # number of keys
            key,
            global_key,
            str(now),
            str(window),
            str(limit),
            str(burst_limit),
            str(global_window),
            str(global_limit)
        )
        
        return (
            bool(result[0]),  # allowed
            int(result[1]),   # retry_after
            int(result[2]),   # count
            int(result[3]),   # global_count
            bool(result[4])   # burst_used
        )
    
    def increment_metrics(self, metrics: dict[str, int]) -> dict[str, int]:
        """Atomically increment multiple metrics"""
        if not self._functions_loaded:
            # Fallback to pipeline
            pipe = self.redis.pipeline()
            for key, increment in metrics.items():
                pipe.incrby(key, increment)
                pipe.expire(key, 86400)
            results = pipe.execute()
            return dict(zip(metrics.keys(), results[::2]))
        
        keys = list(metrics.keys())
        values = [str(metrics[k]) for k in keys]
        
        results = self.redis.fcall(
            'increment_metrics',
            len(keys),
            *keys,
            *values
        )
        
        return dict(zip(keys, results))
    
    def trim_stream(self, stream_key: str, max_len: int, approximate: bool = True) -> tuple[int, int]:
        """Trim a stream and return stats"""
        if not self._functions_loaded:
            # Fallback
            self.redis.xtrim(stream_key, maxlen=max_len, approximate=approximate)
            return (0, 0)
        
        result = self.redis.fcall(
            'trim_stream',
            1,
            stream_key,
            str(max_len),
            '1' if approximate else '0'
        )
        
        return (int(result[0]), int(result[1]))


def get_redis7_functions(redis_client: Optional[redis.Redis] = None) -> Optional[Redis7Functions]:
    """Get Redis7Functions instance if supported"""
    if redis_client is None:
        from flask import current_app
        redis_client = redis.from_url(
            current_app.config.get('REDIS_URL', 'redis://localhost:6379/0')
        )
    
    functions = Redis7Functions(redis_client)
    if functions.load_functions():
        return functions
    return None