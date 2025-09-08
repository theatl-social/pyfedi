"""
Advanced monitoring and rate limiting for admin API Phase 3
"""

import hashlib
import json
import time
from collections import defaultdict
from datetime import datetime

from flask import current_app, g, request

from app import cache, redis_client
from app.models import utcnow


class AdminAPIMonitor:
    """Advanced monitoring for admin API operations"""

    def __init__(self):
        self.metrics = defaultdict(int)
        self.timings = defaultdict(list)

    @cache.memoize(timeout=60)
    def get_redis_key(self, key_type, identifier):
        """Generate consistent Redis keys for rate limiting"""
        return f"piefed:admin_api:{key_type}:{identifier}"

    def record_request(self, endpoint, method, status_code, duration_ms, client_ip=None):
        """Record API request metrics"""
        timestamp = utcnow()

        # Basic counters
        self.metrics[f"requests_total_{endpoint}_{method}"] += 1
        self.metrics[f"requests_status_{status_code}"] += 1

        # Performance tracking
        perf_key = f"duration_{endpoint}_{method}"
        self.timings[perf_key].append(duration_ms)

        # Keep only last 100 measurements for moving averages
        if len(self.timings[perf_key]) > 100:
            self.timings[perf_key] = self.timings[perf_key][-100:]

        # Store in Redis for persistence (with 24h expiry)
        if redis_client:
            try:
                metric_data = {
                    "endpoint": endpoint,
                    "method": method,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                    "timestamp": timestamp.isoformat(),
                    "hour": timestamp.strftime("%Y%m%d%H"),
                }

                # Store individual request (for debugging)
                redis_key = self.get_redis_key("request", f"{timestamp.timestamp()}")
                redis_client.setex(redis_key, 86400, json.dumps(metric_data))  # 24h expiry

                # Update hourly aggregates
                hour_key = self.get_redis_key("hourly", metric_data["hour"])
                redis_client.hincrby(hour_key, f"count_{endpoint}_{method}", 1)
                redis_client.hincrby(hour_key, f"status_{status_code}", 1)
                redis_client.expire(hour_key, 86400 * 7)  # 7 days

                # Update error rates
                if status_code >= 400:
                    error_key = self.get_redis_key("errors", timestamp.strftime("%Y%m%d%H%M"))
                    redis_client.incr(error_key)
                    redis_client.expire(error_key, 3600)  # 1 hour

            except Exception as e:
                current_app.logger.warning(f"Failed to store metrics in Redis: {e}")

    def get_performance_stats(self):
        """Get performance statistics"""
        stats = {
            "total_requests": sum(v for k, v in self.metrics.items() if k.startswith("requests_total_")),
            "error_rate": 0.0,
            "average_response_times": {},
            "endpoint_usage": {},
        }

        # Calculate error rate
        total_requests = stats["total_requests"]
        error_requests = sum(
            v for k, v in self.metrics.items() if k.startswith("requests_status_") and int(k.split("_")[-1]) >= 400
        )

        if total_requests > 0:
            stats["error_rate"] = (error_requests / total_requests) * 100

        # Calculate average response times
        for endpoint_method, timings in self.timings.items():
            if timings:
                stats["average_response_times"][endpoint_method] = {
                    "avg_ms": sum(timings) / len(timings),
                    "min_ms": min(timings),
                    "max_ms": max(timings),
                    "samples": len(timings),
                }

        # Endpoint usage stats
        for key, count in self.metrics.items():
            if key.startswith("requests_total_"):
                endpoint_method = key.replace("requests_total_", "")
                stats["endpoint_usage"][endpoint_method] = count

        return stats

    def get_redis_stats(self):
        """Get statistics from Redis if available"""
        if not redis_client:
            return {"redis_available": False}

        try:
            current_hour = datetime.utcnow().strftime("%Y%m%d%H")
            hour_key = self.get_redis_key("hourly", current_hour)

            hourly_data = redis_client.hgetall(hour_key)

            # Convert byte keys/values to strings/ints
            hourly_stats = {}
            for k, v in hourly_data.items():
                if isinstance(k, bytes):
                    k = k.decode("utf-8")
                if isinstance(v, bytes):
                    v = int(v.decode("utf-8"))
                hourly_stats[k] = v

            return {
                "redis_available": True,
                "current_hour_stats": hourly_stats,
                "redis_info": {
                    "used_memory": redis_client.info().get("used_memory_human", "unknown"),
                    "connected_clients": redis_client.info().get("connected_clients", 0),
                },
            }
        except Exception as e:
            current_app.logger.warning(f"Failed to get Redis stats: {e}")
            return {"redis_available": False, "error": str(e)}


class AdvancedRateLimiter:
    """Advanced rate limiting with Redis backend"""

    def __init__(self):
        self.default_limits = {
            "private_registration": "10/hour",
            "user_lookup": "100/hour",
            "user_modification": "50/hour",
            "bulk_operations": "5/hour",
            "statistics": "60/hour",
        }

    def get_rate_limit_key(self, limit_type, identifier):
        """Generate rate limit key"""
        return f"piefed:ratelimit:{limit_type}:{identifier}"

    def parse_rate_limit(self, limit_str):
        """Parse rate limit string like '10/hour' or '100/minute'"""
        try:
            count, period = limit_str.split("/")
            count = int(count)

            if period == "second":
                window_seconds = 1
            elif period == "minute":
                window_seconds = 60
            elif period == "hour":
                window_seconds = 3600
            elif period == "day":
                window_seconds = 86400
            else:
                window_seconds = 3600  # Default to hour

            return count, window_seconds
        except:
            return 10, 3600  # Default: 10 per hour

    def check_rate_limit(self, limit_type, identifier, custom_limit=None):
        """
        Check if rate limit is exceeded using sliding window.

        Args:
            limit_type (str): Type of operation
            identifier (str): Client identifier (IP, secret hash, etc.)
            custom_limit (str): Custom rate limit override

        Returns:
            dict: Rate limit status with remaining count and reset time
        """
        if not redis_client:
            # Fallback to in-memory tracking (less accurate)
            return self._check_rate_limit_fallback(limit_type, identifier)

        limit_str = custom_limit or self.default_limits.get(limit_type, "10/hour")
        max_requests, window_seconds = self.parse_rate_limit(limit_str)

        rate_key = self.get_rate_limit_key(limit_type, identifier)
        current_time = int(time.time())
        window_start = current_time - window_seconds

        try:
            # Remove old entries
            redis_client.zremrangebyscore(rate_key, 0, window_start)

            # Count current requests
            current_count = redis_client.zcard(rate_key)

            if current_count >= max_requests:
                # Get oldest request to calculate reset time
                oldest_requests = redis_client.zrange(rate_key, 0, 0, withscores=True)
                if oldest_requests:
                    oldest_time = int(oldest_requests[0][1])
                    reset_time = oldest_time + window_seconds
                else:
                    reset_time = current_time + window_seconds

                return {
                    "allowed": False,
                    "limit": max_requests,
                    "remaining": 0,
                    "reset_time": reset_time,
                    "retry_after": max(1, reset_time - current_time),
                }

            # Add current request
            redis_client.zadd(rate_key, {str(current_time): current_time})
            redis_client.expire(rate_key, window_seconds + 60)  # Extra buffer

            return {
                "allowed": True,
                "limit": max_requests,
                "remaining": max_requests - current_count - 1,
                "reset_time": current_time + window_seconds,
                "retry_after": 0,
            }

        except Exception as e:
            current_app.logger.warning(f"Redis rate limit check failed: {e}")
            # Allow request if Redis fails
            return {
                "allowed": True,
                "limit": max_requests,
                "remaining": max_requests - 1,
                "reset_time": current_time + window_seconds,
                "retry_after": 0,
                "fallback": True,
            }

    def _check_rate_limit_fallback(self, limit_type, identifier):
        """Fallback rate limiting without Redis"""
        # Simple in-memory fallback (not persistent across restarts)
        if not hasattr(g, "rate_limit_cache"):
            g.rate_limit_cache = {}

        limit_str = self.default_limits.get(limit_type, "10/hour")
        max_requests, window_seconds = self.parse_rate_limit(limit_str)

        current_time = int(time.time())
        cache_key = f"{limit_type}:{identifier}"

        if cache_key not in g.rate_limit_cache:
            g.rate_limit_cache[cache_key] = []

        # Remove old requests
        g.rate_limit_cache[cache_key] = [
            req_time for req_time in g.rate_limit_cache[cache_key] if req_time > current_time - window_seconds
        ]

        current_count = len(g.rate_limit_cache[cache_key])

        if current_count >= max_requests:
            return {
                "allowed": False,
                "limit": max_requests,
                "remaining": 0,
                "reset_time": current_time + window_seconds,
                "retry_after": window_seconds,
                "fallback": True,
            }

        # Add current request
        g.rate_limit_cache[cache_key].append(current_time)

        return {
            "allowed": True,
            "limit": max_requests,
            "remaining": max_requests - current_count - 1,
            "reset_time": current_time + window_seconds,
            "retry_after": 0,
            "fallback": True,
        }

    def get_client_identifier(self, request_obj=None):
        """Get client identifier for rate limiting"""
        if request_obj is None:
            request_obj = request

        # Use secret hash as primary identifier
        secret = request_obj.headers.get("X-PieFed-Secret")
        if secret:
            secret_hash = hashlib.sha256(secret.encode()).hexdigest()[:16]
            return f"secret:{secret_hash}"

        # Fallback to IP address
        client_ip = request_obj.environ.get("HTTP_X_FORWARDED_FOR", request_obj.remote_addr)
        if client_ip and "," in client_ip:
            client_ip = client_ip.split(",")[0].strip()

        return f"ip:{client_ip or 'unknown'}"


# Global instances
admin_monitor = AdminAPIMonitor()
rate_limiter = AdvancedRateLimiter()


def track_admin_request(endpoint, method="GET"):
    """Decorator to track admin API requests"""

    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            client_ip = request.environ.get("HTTP_X_FORWARDED_FOR", request.remote_addr)

            try:
                response = func(*args, **kwargs)
                status_code = response[1] if isinstance(response, tuple) else 200
                duration_ms = int((time.time() - start_time) * 1000)

                # Record metrics
                admin_monitor.record_request(endpoint, method, status_code, duration_ms, client_ip)

                return response

            except Exception:
                duration_ms = int((time.time() - start_time) * 1000)
                admin_monitor.record_request(endpoint, method, 500, duration_ms, client_ip)
                raise

        wrapper.__name__ = func.__name__
        return wrapper

    return decorator


def check_advanced_rate_limit(operation_type):
    """Check advanced rate limiting before processing request"""
    identifier = rate_limiter.get_client_identifier()
    rate_status = rate_limiter.check_rate_limit(operation_type, identifier)

    if not rate_status["allowed"]:
        from werkzeug.exceptions import TooManyRequests

        # Add rate limit headers for client
        response_data = {
            "success": False,
            "error": "rate_limited",
            "message": f"Rate limit exceeded for {operation_type}",
            "details": {
                "limit": rate_status["limit"],
                "remaining": rate_status["remaining"],
                "reset_time": rate_status["reset_time"],
                "retry_after": rate_status["retry_after"],
            },
        }

        # Log rate limit violation
        try:
            current_app.logger.warning(f"Rate limit exceeded: {identifier} for {operation_type}")
        except RuntimeError:
            pass

        raise TooManyRequests(description=json.dumps(response_data))

    # Store rate limit info in g for adding to response headers
    g.rate_limit_info = rate_status
    return rate_status
