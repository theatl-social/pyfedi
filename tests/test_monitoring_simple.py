"""
Simple unit tests for Phase 3 monitoring and rate limiting functionality
Tests the core monitoring operations without full Flask app setup
"""

import json
import time
import unittest
from unittest.mock import MagicMock, patch


class TestAdvancedRateLimiter(unittest.TestCase):
    """Test advanced rate limiting functionality"""

    def test_parse_rate_limit_formats(self):
        """Test parsing different rate limit formats"""
        from app.api.admin.monitoring import AdvancedRateLimiter

        limiter = AdvancedRateLimiter()

        # Test various formats
        count, window = limiter.parse_rate_limit("10/hour")
        self.assertEqual(count, 10)
        self.assertEqual(window, 3600)

        count, window = limiter.parse_rate_limit("100/minute")
        self.assertEqual(count, 100)
        self.assertEqual(window, 60)

        count, window = limiter.parse_rate_limit("5/second")
        self.assertEqual(count, 5)
        self.assertEqual(window, 1)

        # Test invalid format (should use default)
        count, window = limiter.parse_rate_limit("invalid")
        self.assertEqual(count, 10)
        self.assertEqual(window, 3600)

    def test_get_rate_limit_key_generation(self):
        """Test rate limit key generation"""
        from app.api.admin.monitoring import AdvancedRateLimiter

        limiter = AdvancedRateLimiter()

        key = limiter.get_rate_limit_key("private_registration", "test_client")
        expected = "piefed:ratelimit:private_registration:test_client"
        self.assertEqual(key, expected)

    def test_fallback_rate_limiting(self):
        """Test fallback rate limiting without Redis"""
        from app.api.admin.monitoring import AdvancedRateLimiter

        limiter = AdvancedRateLimiter()

        # Mock g object for in-memory cache
        with patch("app.api.admin.monitoring.g") as mock_g:
            mock_g.rate_limit_cache = {}

            # First request should be allowed
            result = limiter._check_rate_limit_fallback(
                "private_registration", "test_client"
            )
            self.assertTrue(result["allowed"])
            self.assertEqual(result["remaining"], 9)  # 10/hour - 1
            self.assertTrue(result["fallback"])

    @patch("app.api.admin.monitoring.redis_client")
    def test_redis_rate_limiting_allowed(self, mock_redis):
        """Test Redis-backed rate limiting when allowed"""
        from app.api.admin.monitoring import AdvancedRateLimiter

        limiter = AdvancedRateLimiter()

        # Mock Redis responses
        mock_redis.zremrangebyscore.return_value = None
        mock_redis.zcard.return_value = 5  # Current count
        mock_redis.zadd.return_value = 1
        mock_redis.expire.return_value = True

        result = limiter.check_rate_limit("private_registration", "test_client")

        self.assertTrue(result["allowed"])
        self.assertEqual(result["limit"], 10)
        self.assertEqual(result["remaining"], 4)  # 10 - 5 - 1

        # Verify Redis calls
        mock_redis.zremrangebyscore.assert_called_once()
        mock_redis.zadd.assert_called_once()

    @patch("app.api.admin.monitoring.redis_client")
    def test_redis_rate_limiting_exceeded(self, mock_redis):
        """Test Redis-backed rate limiting when exceeded"""
        from app.api.admin.monitoring import AdvancedRateLimiter

        limiter = AdvancedRateLimiter()

        # Mock Redis responses for rate limit exceeded
        mock_redis.zremrangebyscore.return_value = None
        mock_redis.zcard.return_value = 10  # At limit
        mock_redis.zrange.return_value = [
            (b"timestamp", 1640995200)
        ]  # Mock oldest request

        result = limiter.check_rate_limit("private_registration", "test_client")

        self.assertFalse(result["allowed"])
        self.assertEqual(result["limit"], 10)
        self.assertEqual(result["remaining"], 0)
        self.assertGreater(result["retry_after"], 0)

    def test_client_identifier_generation(self):
        """Test client identifier generation from request"""
        from app.api.admin.monitoring import AdvancedRateLimiter

        limiter = AdvancedRateLimiter()

        # Mock request object with secret
        mock_request = MagicMock()
        mock_request.headers = {"X-PieFed-Secret": "test_secret_123"}

        identifier = limiter.get_client_identifier(mock_request)
        self.assertTrue(identifier.startswith("secret:"))
        self.assertEqual(len(identifier), 23)  # 'secret:' + 16 char hash

    def test_client_identifier_fallback_to_ip(self):
        """Test client identifier fallback to IP when no secret"""
        from app.api.admin.monitoring import AdvancedRateLimiter

        limiter = AdvancedRateLimiter()

        # Mock request object without secret
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.environ = {
            "HTTP_X_FORWARDED_FOR": "192.168.1.100, proxy.example.com"
        }
        mock_request.remote_addr = "10.0.0.1"

        identifier = limiter.get_client_identifier(mock_request)
        self.assertEqual(
            identifier, "ip:192.168.1.100"
        )  # Should use first IP from forwarded header


class TestAdminAPIMonitor(unittest.TestCase):
    """Test admin API monitoring functionality"""

    def test_record_request_basic(self):
        """Test basic request recording"""
        from app.api.admin.monitoring import AdminAPIMonitor

        monitor = AdminAPIMonitor()

        # Record a request
        monitor.record_request("private_register", "POST", 201, 150, "192.168.1.100")

        # Check metrics were recorded
        self.assertEqual(monitor.metrics["requests_total_private_register_POST"], 1)
        self.assertEqual(monitor.metrics["requests_status_201"], 1)

        # Check timings were recorded
        self.assertEqual(len(monitor.timings["duration_private_register_POST"]), 1)
        self.assertEqual(monitor.timings["duration_private_register_POST"][0], 150)

    def test_get_performance_stats(self):
        """Test performance statistics generation"""
        from app.api.admin.monitoring import AdminAPIMonitor

        monitor = AdminAPIMonitor()

        # Record some sample requests
        monitor.record_request("private_register", "POST", 201, 100)
        monitor.record_request("private_register", "POST", 201, 150)
        monitor.record_request("user_lookup", "GET", 200, 50)
        monitor.record_request("user_lookup", "GET", 404, 25)

        stats = monitor.get_performance_stats()

        # Check total requests
        self.assertEqual(stats["total_requests"], 4)

        # Check error rate (1 error out of 4 requests = 25%)
        self.assertEqual(stats["error_rate"], 25.0)

        # Check response times
        self.assertIn("duration_private_register_POST", stats["average_response_times"])
        self.assertEqual(
            stats["average_response_times"]["duration_private_register_POST"]["avg_ms"],
            125,
        )
        self.assertEqual(
            stats["average_response_times"]["duration_private_register_POST"]["min_ms"],
            100,
        )
        self.assertEqual(
            stats["average_response_times"]["duration_private_register_POST"]["max_ms"],
            150,
        )

    @patch("app.api.admin.monitoring.redis_client")
    @patch("app.api.admin.monitoring.current_app")
    def test_redis_metrics_storage(self, mock_app, mock_redis):
        """Test storing metrics in Redis"""
        from app.api.admin.monitoring import AdminAPIMonitor

        monitor = AdminAPIMonitor()

        # Mock Redis operations
        mock_redis.setex.return_value = True
        mock_redis.hincrby.return_value = 1
        mock_redis.expire.return_value = True
        mock_redis.incr.return_value = 1

        # Record a request (should trigger Redis storage)
        monitor.record_request("private_register", "POST", 201, 100, "192.168.1.1")

        # Verify Redis was called
        self.assertTrue(mock_redis.setex.called)
        self.assertTrue(mock_redis.hincrby.called)

    @patch("app.api.admin.monitoring.redis_client", None)
    def test_fallback_without_redis(self):
        """Test monitoring works without Redis"""
        from app.api.admin.monitoring import AdminAPIMonitor

        monitor = AdminAPIMonitor()

        # Should work without Redis
        monitor.record_request("test", "GET", 200, 50)

        stats = monitor.get_performance_stats()
        self.assertEqual(stats["total_requests"], 1)

    def test_get_redis_key_caching(self):
        """Test Redis key generation and caching"""
        from app.api.admin.monitoring import AdminAPIMonitor

        monitor = AdminAPIMonitor()

        # Should generate consistent keys
        key1 = monitor.get_redis_key("request", "test_id")
        key2 = monitor.get_redis_key("request", "test_id")

        expected = "piefed:admin_api:request:test_id"
        self.assertEqual(key1, expected)
        self.assertEqual(key2, expected)


class TestMonitoringDecorators(unittest.TestCase):
    """Test monitoring decorators and utilities"""

    def test_track_admin_request_decorator(self):
        """Test request tracking decorator"""
        from app.api.admin.monitoring import admin_monitor, track_admin_request

        # Create a mock function
        @track_admin_request("test_endpoint", "POST")
        def mock_endpoint():
            time.sleep(0.01)  # Small delay for timing
            return {"success": True}, 201

        # Mock request context
        with patch("app.api.admin.monitoring.request") as mock_request:
            mock_request.environ = {"HTTP_X_FORWARDED_FOR": "192.168.1.1"}

            # Call the decorated function
            result = mock_endpoint()

            # Verify response
            self.assertEqual(result, ({"success": True}, 201))

            # Verify metrics were recorded
            self.assertGreater(
                admin_monitor.metrics["requests_total_test_endpoint_POST"], 0
            )

    @patch("app.api.admin.monitoring.current_app")
    def test_check_advanced_rate_limit_allowed(self, mock_app):
        """Test advanced rate limit check when allowed"""
        from app.api.admin.monitoring import check_advanced_rate_limit, rate_limiter

        # Mock rate limiter to allow request
        with patch.object(
            rate_limiter, "get_client_identifier"
        ) as mock_identifier, patch.object(
            rate_limiter, "check_rate_limit"
        ) as mock_check:

            mock_identifier.return_value = "test_client"
            mock_check.return_value = {
                "allowed": True,
                "limit": 10,
                "remaining": 5,
                "reset_time": int(time.time()) + 3600,
                "retry_after": 0,
            }

            # Should not raise exception
            result = check_advanced_rate_limit("private_registration")
            self.assertTrue(result["allowed"])

    @patch("app.api.admin.monitoring.current_app")
    def test_check_advanced_rate_limit_exceeded(self, mock_app):
        """Test advanced rate limit check when exceeded"""
        from werkzeug.exceptions import TooManyRequests

        from app.api.admin.monitoring import check_advanced_rate_limit, rate_limiter

        # Mock rate limiter to deny request
        with patch.object(
            rate_limiter, "get_client_identifier"
        ) as mock_identifier, patch.object(
            rate_limiter, "check_rate_limit"
        ) as mock_check:

            mock_identifier.return_value = "test_client"
            mock_check.return_value = {
                "allowed": False,
                "limit": 10,
                "remaining": 0,
                "reset_time": int(time.time()) + 3600,
                "retry_after": 300,
            }

            # Should raise TooManyRequests exception
            with self.assertRaises(TooManyRequests):
                check_advanced_rate_limit("private_registration")


class TestIntegration(unittest.TestCase):
    """Integration tests for monitoring components"""

    def test_monitoring_system_initialization(self):
        """Test that monitoring system initializes properly"""
        from app.api.admin.monitoring import admin_monitor, rate_limiter

        # Check that global instances exist
        self.assertIsNotNone(admin_monitor)
        self.assertIsNotNone(rate_limiter)

        # Check default configuration
        self.assertIn("private_registration", rate_limiter.default_limits)
        self.assertEqual(rate_limiter.default_limits["private_registration"], "10/hour")


if __name__ == "__main__":
    unittest.main()
