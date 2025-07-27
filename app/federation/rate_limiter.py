"""
Per-destination rate limiting for federation
Prevents overwhelming remote instances with too many requests
"""
from typing import Optional, Tuple, Dict, List
from datetime import datetime, timedelta
from collections import defaultdict
import redis
import time
import logging
from flask import current_app
from dataclasses import dataclass
from enum import Enum


logger = logging.getLogger(__name__)


class RateLimitType(Enum):
    """Types of rate limits"""
    ACTIVITIES = "activities"  # General activity delivery
    FOLLOWS = "follows"       # Follow/unfollow requests
    VOTES = "votes"          # Like/dislike activities
    MEDIA = "media"          # Media fetches
    GLOBAL = "global"        # Overall limit per instance


@dataclass
class RateLimitConfig:
    """Configuration for a rate limit type"""
    window_seconds: int
    max_requests: int
    burst_allowance: float = 1.2  # Allow 20% burst
    
    @property
    def burst_limit(self) -> int:
        """Calculate burst limit"""
        return int(self.max_requests * self.burst_allowance)


class DestinationRateLimiter:
    """Rate limiter for federation destinations"""
    
    # Default rate limits per type
    DEFAULT_LIMITS = {
        RateLimitType.ACTIVITIES: RateLimitConfig(
            window_seconds=60,
            max_requests=100
        ),
        RateLimitType.FOLLOWS: RateLimitConfig(
            window_seconds=300,  # 5 minutes
            max_requests=20
        ),
        RateLimitType.VOTES: RateLimitConfig(
            window_seconds=60,
            max_requests=200  # Higher for votes
        ),
        RateLimitType.MEDIA: RateLimitConfig(
            window_seconds=60,
            max_requests=30
        ),
        RateLimitType.GLOBAL: RateLimitConfig(
            window_seconds=60,
            max_requests=300  # Overall limit
        )
    }
    
    def __init__(self):
        self.redis_client = redis.from_url(
            current_app.config.get('REDIS_URL', 'redis://localhost:6379/0')
        )
        
        # Load configuration with defaults
        self.limits = {}
        for limit_type in RateLimitType:
            config_key = f'RATE_LIMIT_{limit_type.value.upper()}'
            
            if config_key in current_app.config:
                # Parse config like "100/60" (100 requests per 60 seconds)
                limit_str = current_app.config[config_key]
                try:
                    requests, seconds = map(int, limit_str.split('/'))
                    self.limits[limit_type] = RateLimitConfig(
                        window_seconds=seconds,
                        max_requests=requests
                    )
                except ValueError:
                    logger.warning(f"Invalid rate limit config: {config_key}={limit_str}")
                    self.limits[limit_type] = self.DEFAULT_LIMITS[limit_type]
            else:
                self.limits[limit_type] = self.DEFAULT_LIMITS[limit_type]
    
    def check_rate_limit(
        self, 
        destination: str, 
        limit_type: RateLimitType = RateLimitType.ACTIVITIES
    ) -> Tuple[bool, Optional[int], Dict[str, any]]:
        """
        Check if request is allowed under rate limit
        
        Args:
            destination: Remote instance domain
            limit_type: Type of rate limit to check
            
        Returns:
            (allowed, retry_after_seconds, info)
        """
        config = self.limits[limit_type]
        now = time.time()
        
        # Use sliding window with Redis sorted sets
        key = f"rate_limit:{limit_type.value}:{destination}"
        window_start = now - config.window_seconds
        
        # Remove old entries
        self.redis_client.zremrangebyscore(key, 0, window_start)
        
        # Count requests in window
        request_count = self.redis_client.zcard(key)
        
        # Check global limit as well
        global_key = f"rate_limit:{RateLimitType.GLOBAL.value}:{destination}"
        global_config = self.limits[RateLimitType.GLOBAL]
        global_window_start = now - global_config.window_seconds
        
        self.redis_client.zremrangebyscore(global_key, 0, global_window_start)
        global_count = self.redis_client.zcard(global_key)
        
        # Check if under limits
        under_specific_limit = request_count < config.max_requests
        under_global_limit = global_count < global_config.max_requests
        
        # Allow burst if recent rate is low
        allow_burst = False
        if not under_specific_limit and request_count < config.burst_limit:
            # Check if we've been under 50% usage for half the window
            half_window_start = now - (config.window_seconds / 2)
            recent_count = self.redis_client.zcount(key, half_window_start, now)
            if recent_count < (config.max_requests / 4):  # Under 25% in recent half
                allow_burst = True
                logger.info(f"Allowing burst for {destination} ({limit_type.value})")
        
        allowed = (under_specific_limit or allow_burst) and under_global_limit
        
        if allowed:
            # Add request to windows
            self.redis_client.zadd(key, {str(now): now})
            self.redis_client.expire(key, config.window_seconds * 2)
            
            self.redis_client.zadd(global_key, {str(now): now})
            self.redis_client.expire(global_key, global_config.window_seconds * 2)
            
            retry_after = None
        else:
            # Calculate when we can retry
            if not under_specific_limit:
                oldest = self.redis_client.zrange(key, 0, 0, withscores=True)
                if oldest:
                    retry_after = int(config.window_seconds - (now - oldest[0][1]) + 1)
                else:
                    retry_after = config.window_seconds
            else:
                # Global limit hit
                oldest = self.redis_client.zrange(global_key, 0, 0, withscores=True)
                if oldest:
                    retry_after = int(global_config.window_seconds - (now - oldest[0][1]) + 1)
                else:
                    retry_after = global_config.window_seconds
        
        info = {
            'type': limit_type.value,
            'current_requests': request_count,
            'limit': config.max_requests,
            'window_seconds': config.window_seconds,
            'global_requests': global_count,
            'global_limit': global_config.max_requests,
            'burst_allowed': allow_burst
        }
        
        return allowed, retry_after, info
    
    def record_response_time(self, destination: str, response_time: float):
        """
        Record response time for adaptive rate limiting
        
        Slower instances get lower rate limits
        """
        key = f"rate_limit:response_times:{destination}"
        
        # Keep last 100 response times
        self.redis_client.lpush(key, response_time)
        self.redis_client.ltrim(key, 0, 99)
        self.redis_client.expire(key, 3600)  # Keep for 1 hour
        
        # Calculate average
        times = self.redis_client.lrange(key, 0, -1)
        if len(times) >= 10:  # Need enough samples
            avg_time = sum(float(t) for t in times) / len(times)
            
            # Adjust rate limits based on response time
            if avg_time > 5.0:  # Very slow
                self._adjust_rate_limit(destination, 0.5)  # Half rate
            elif avg_time > 2.0:  # Slow
                self._adjust_rate_limit(destination, 0.75)  # 75% rate
            elif avg_time < 0.5:  # Fast
                self._adjust_rate_limit(destination, 1.25)  # 125% rate
    
    def _adjust_rate_limit(self, destination: str, factor: float):
        """Temporarily adjust rate limits for a destination"""
        key = f"rate_limit:adjustment:{destination}"
        self.redis_client.setex(key, 3600, factor)  # Adjust for 1 hour
    
    def get_rate_limit_status(self, destination: str) -> Dict[str, Dict]:
        """Get current rate limit status for a destination"""
        status = {}
        now = time.time()
        
        for limit_type in RateLimitType:
            config = self.limits[limit_type]
            key = f"rate_limit:{limit_type.value}:{destination}"
            window_start = now - config.window_seconds
            
            # Clean old entries
            self.redis_client.zremrangebyscore(key, 0, window_start)
            
            # Get current count
            current = self.redis_client.zcard(key)
            
            # Get adjustment factor
            adj_key = f"rate_limit:adjustment:{destination}"
            adjustment = self.redis_client.get(adj_key)
            adjustment = float(adjustment) if adjustment else 1.0
            
            adjusted_limit = int(config.max_requests * adjustment)
            
            status[limit_type.value] = {
                'current': current,
                'limit': adjusted_limit,
                'original_limit': config.max_requests,
                'window_seconds': config.window_seconds,
                'remaining': max(0, adjusted_limit - current),
                'adjustment_factor': adjustment
            }
        
        # Add response time stats
        rt_key = f"rate_limit:response_times:{destination}"
        response_times = self.redis_client.lrange(rt_key, 0, 9)  # Last 10
        if response_times:
            times = [float(t) for t in response_times]
            status['response_times'] = {
                'average': sum(times) / len(times),
                'min': min(times),
                'max': max(times),
                'samples': len(times)
            }
        
        return status
    
    def reset_rate_limits(self, destination: str):
        """Reset all rate limits for a destination"""
        patterns = [
            f"rate_limit:*:{destination}",
            f"rate_limit:adjustment:{destination}",
            f"rate_limit:response_times:{destination}"
        ]
        
        for pattern in patterns:
            for key in self.redis_client.scan_iter(match=pattern):
                self.redis_client.delete(key)
        
        logger.info(f"Reset rate limits for {destination}")
    
    def get_all_limited_destinations(self) -> List[Dict[str, any]]:
        """Get all destinations currently being rate limited"""
        limited = []
        now = time.time()
        
        # Scan for all rate limit keys
        for key in self.redis_client.scan_iter(match="rate_limit:*:*"):
            if b':adjustment:' in key or b':response_times:' in key:
                continue
                
            parts = key.decode().split(':')
            if len(parts) == 3:
                _, limit_type, destination = parts
                
                # Check if at limit
                config = self.limits.get(RateLimitType(limit_type))
                if config:
                    window_start = now - config.window_seconds
                    self.redis_client.zremrangebyscore(key, 0, window_start)
                    count = self.redis_client.zcard(key)
                    
                    if count >= config.max_requests * 0.8:  # 80% or more
                        limited.append({
                            'destination': destination,
                            'type': limit_type,
                            'current': count,
                            'limit': config.max_requests,
                            'percentage': (count / config.max_requests) * 100
                        })
        
        return sorted(limited, key=lambda x: x['percentage'], reverse=True)


# Utility functions

def check_rate_limit(destination: str, activity_type: str = None) -> Tuple[bool, Optional[int]]:
    """Check if we can send to a destination"""
    limiter = DestinationRateLimiter()
    
    # Map activity type to rate limit type
    if activity_type in ['Like', 'Dislike']:
        limit_type = RateLimitType.VOTES
    elif activity_type in ['Follow', 'Undo']:
        limit_type = RateLimitType.FOLLOWS
    elif activity_type == 'Image':
        limit_type = RateLimitType.MEDIA
    else:
        limit_type = RateLimitType.ACTIVITIES
    
    allowed, retry_after, _ = limiter.check_rate_limit(destination, limit_type)
    return allowed, retry_after


def record_destination_response_time(destination: str, response_time: float):
    """Record response time for adaptive rate limiting"""
    limiter = DestinationRateLimiter()
    limiter.record_response_time(destination, response_time)