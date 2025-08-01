"""
Instance health monitoring and circuit breaker for federation
Tracks instance health and prevents sending to unhealthy instances
"""
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta
from enum import Enum
import redis
import json
import logging
from flask import current_app
from sqlalchemy import func
from app import db
from app.models import Instance, ActivityPubLog


logger = logging.getLogger(__name__)


class InstanceHealth(Enum):
    """Instance health states"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    DEAD = "dead"


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


class HealthMetrics:
    """Health metrics for an instance"""
    
    def __init__(self):
        self.success_count = 0
        self.failure_count = 0
        self.timeout_count = 0
        self.last_success = None
        self.last_failure = None
        self.response_times = []
        self.consecutive_failures = 0
        
    def add_success(self, response_time: float):
        """Record successful request"""
        self.success_count += 1
        self.consecutive_failures = 0
        self.last_success = datetime.now(timezone.utc)
        self.response_times.append(response_time)
        # Keep only last 100 response times
        if len(self.response_times) > 100:
            self.response_times.pop(0)
    
    def add_failure(self):
        """Record failed request"""
        self.failure_count += 1
        self.consecutive_failures += 1
        self.last_failure = datetime.now(timezone.utc)
    
    def add_timeout(self):
        """Record timeout"""
        self.timeout_count += 1
        self.consecutive_failures += 1
        self.last_failure = datetime.now(timezone.utc)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        total = self.success_count + self.failure_count + self.timeout_count
        if total == 0:
            return 1.0
        return self.success_count / total
    
    @property
    def avg_response_time(self) -> float:
        """Calculate average response time"""
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        return {
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'timeout_count': self.timeout_count,
            'last_success': self.last_success.isoformat() if self.last_success else None,
            'last_failure': self.last_failure.isoformat() if self.last_failure else None,
            'response_times': self.response_times[-10:],  # Keep only recent
            'consecutive_failures': self.consecutive_failures
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'HealthMetrics':
        """Create from dictionary"""
        metrics = cls()
        metrics.success_count = data.get('success_count', 0)
        metrics.failure_count = data.get('failure_count', 0)
        metrics.timeout_count = data.get('timeout_count', 0)
        metrics.consecutive_failures = data.get('consecutive_failures', 0)
        metrics.response_times = data.get('response_times', [])
        
        if data.get('last_success'):
            metrics.last_success = datetime.fromisoformat(data['last_success'])
        if data.get('last_failure'):
            metrics.last_failure = datetime.fromisoformat(data['last_failure'])
            
        return metrics


class InstanceHealthMonitor:
    """Monitor instance health and manage circuit breakers"""
    
    # Configuration defaults
    DEFAULT_FAILURE_THRESHOLD = 5  # Consecutive failures to open circuit
    DEFAULT_SUCCESS_THRESHOLD = 3  # Successes needed to close circuit
    DEFAULT_TIMEOUT_SECONDS = 10
    DEFAULT_RECOVERY_TIMEOUT = 300  # 5 minutes
    DEFAULT_HALF_OPEN_REQUESTS = 3
    
    def __init__(self):
        self.redis_client = redis.from_url(
            current_app.config.get('REDIS_URL', 'redis://localhost:6379/0')
        )
        self.failure_threshold = current_app.config.get(
            'CIRCUIT_FAILURE_THRESHOLD',
            self.DEFAULT_FAILURE_THRESHOLD
        )
        self.success_threshold = current_app.config.get(
            'CIRCUIT_SUCCESS_THRESHOLD',
            self.DEFAULT_SUCCESS_THRESHOLD
        )
        self.recovery_timeout = current_app.config.get(
            'CIRCUIT_RECOVERY_TIMEOUT',
            self.DEFAULT_RECOVERY_TIMEOUT
        )
    
    def record_success(self, instance_domain: str, response_time: float):
        """Record successful request to instance"""
        metrics = self._get_metrics(instance_domain)
        metrics.add_success(response_time)
        
        # Update circuit state if needed
        circuit_state = self._get_circuit_state(instance_domain)
        
        if circuit_state == CircuitState.HALF_OPEN:
            # Check if we can close the circuit
            recent_successes = self._get_recent_success_count(instance_domain)
            if recent_successes >= self.success_threshold:
                self._set_circuit_state(instance_domain, CircuitState.CLOSED)
                logger.info(f"Circuit breaker closed for {instance_domain}")
        
        self._save_metrics(instance_domain, metrics)
        self._update_instance_health(instance_domain)
    
    def record_failure(self, instance_domain: str, error_type: str = 'generic'):
        """Record failed request to instance"""
        metrics = self._get_metrics(instance_domain)
        
        if error_type == 'timeout':
            metrics.add_timeout()
        else:
            metrics.add_failure()
        
        # Check if we should open the circuit
        if metrics.consecutive_failures >= self.failure_threshold:
            self._set_circuit_state(instance_domain, CircuitState.OPEN)
            self._set_circuit_open_time(instance_domain)
            logger.warning(f"Circuit breaker opened for {instance_domain} after {metrics.consecutive_failures} failures")
        
        self._save_metrics(instance_domain, metrics)
        self._update_instance_health(instance_domain)
    
    def can_send_to_instance(self, instance_domain: str) -> Tuple[bool, Optional[str]]:
        """
        Check if we can send to an instance
        
        Returns:
            (can_send, reason_if_blocked)
        """
        circuit_state = self._get_circuit_state(instance_domain)
        
        if circuit_state == CircuitState.CLOSED:
            return True, None
        
        elif circuit_state == CircuitState.OPEN:
            # Check if we should transition to half-open
            open_time = self._get_circuit_open_time(instance_domain)
            if open_time:
                elapsed = (datetime.now(timezone.utc) - open_time).total_seconds()
                if elapsed >= self.recovery_timeout:
                    self._set_circuit_state(instance_domain, CircuitState.HALF_OPEN)
                    logger.info(f"Circuit breaker half-open for {instance_domain}")
                    return True, None  # Allow test request
                else:
                    remaining = self.recovery_timeout - elapsed
                    return False, f"Circuit breaker open, retry in {int(remaining)}s"
            else:
                return False, "Circuit breaker open"
        
        elif circuit_state == CircuitState.HALF_OPEN:
            # Allow limited requests in half-open state
            recent_attempts = self._get_half_open_attempts(instance_domain)
            if recent_attempts < self.DEFAULT_HALF_OPEN_REQUESTS:
                self._increment_half_open_attempts(instance_domain)
                return True, None
            else:
                return False, "Circuit breaker testing, please wait"
        
        return True, None
    
    def get_instance_health(self, instance_domain: str) -> InstanceHealth:
        """Get overall health status of an instance"""
        metrics = self._get_metrics(instance_domain)
        
        # No data - assume healthy
        if metrics.success_count == 0 and metrics.failure_count == 0:
            return InstanceHealth.HEALTHY
        
        # Calculate health based on success rate and recent activity
        success_rate = metrics.success_rate
        
        # Check if instance is dead (no successful requests in a long time)
        if metrics.last_success:
            time_since_success = (datetime.now(timezone.utc) - metrics.last_success).total_seconds()
            if time_since_success > 86400:  # 24 hours
                return InstanceHealth.DEAD
        elif metrics.failure_count > 10:
            return InstanceHealth.DEAD
        
        # Determine health based on success rate
        if success_rate >= 0.95:
            return InstanceHealth.HEALTHY
        elif success_rate >= 0.80:
            return InstanceHealth.DEGRADED
        else:
            return InstanceHealth.UNHEALTHY
    
    def get_all_instance_health(self) -> Dict[str, Dict]:
        """Get health status for all monitored instances"""
        health_data = {}
        
        # Get all instances from database
        instances = Instance.query.filter(Instance.dormant == False).all()
        
        for instance in instances:
            metrics = self._get_metrics(instance.domain)
            circuit_state = self._get_circuit_state(instance.domain)
            health = self.get_instance_health(instance.domain)
            
            health_data[instance.domain] = {
                'health': health.value,
                'circuit_state': circuit_state.value,
                'success_rate': metrics.success_rate,
                'avg_response_time': metrics.avg_response_time,
                'consecutive_failures': metrics.consecutive_failures,
                'last_success': metrics.last_success.isoformat() if metrics.last_success else None,
                'last_failure': metrics.last_failure.isoformat() if metrics.last_failure else None
            }
        
        return health_data
    
    def reset_instance_health(self, instance_domain: str):
        """Reset health metrics for an instance"""
        keys = [
            f'instance_health:metrics:{instance_domain}',
            f'instance_health:circuit:{instance_domain}',
            f'instance_health:circuit_open_time:{instance_domain}',
            f'instance_health:half_open_attempts:{instance_domain}'
        ]
        
        for key in keys:
            self.redis_client.delete(key)
        
        logger.info(f"Reset health metrics for {instance_domain}")
    
    # Private methods
    
    def _get_metrics(self, instance_domain: str) -> HealthMetrics:
        """Get metrics for an instance"""
        key = f'instance_health:metrics:{instance_domain}'
        data = self.redis_client.get(key)
        
        if data:
            try:
                return HealthMetrics.from_dict(json.loads(data))
            except (json.JSONDecodeError, KeyError):
                pass
        
        return HealthMetrics()
    
    def _save_metrics(self, instance_domain: str, metrics: HealthMetrics):
        """Save metrics for an instance"""
        key = f'instance_health:metrics:{instance_domain}'
        data = json.dumps(metrics.to_dict())
        self.redis_client.setex(key, 86400 * 7, data)  # Keep for 7 days
    
    def _get_circuit_state(self, instance_domain: str) -> CircuitState:
        """Get circuit breaker state"""
        key = f'instance_health:circuit:{instance_domain}'
        state = self.redis_client.get(key)
        
        if state:
            try:
                return CircuitState(state.decode())
            except ValueError:
                pass
        
        return CircuitState.CLOSED
    
    def _set_circuit_state(self, instance_domain: str, state: CircuitState):
        """Set circuit breaker state"""
        key = f'instance_health:circuit:{instance_domain}'
        self.redis_client.setex(key, 86400, state.value)
    
    def _get_circuit_open_time(self, instance_domain: str) -> Optional[datetime]:
        """Get when circuit was opened"""
        key = f'instance_health:circuit_open_time:{instance_domain}'
        data = self.redis_client.get(key)
        
        if data:
            try:
                return datetime.fromisoformat(data.decode())
            except ValueError:
                pass
        
        return None
    
    def _set_circuit_open_time(self, instance_domain: str):
        """Set when circuit was opened"""
        key = f'instance_health:circuit_open_time:{instance_domain}'
        self.redis_client.setex(key, 86400, datetime., timezone().isoformat())
    
    def _get_recent_success_count(self, instance_domain: str) -> int:
        """Get count of recent successes (for half-open state)"""
        key = f'instance_health:recent_successes:{instance_domain}'
        count = self.redis_client.get(key)
        return int(count) if count else 0
    
    def _get_half_open_attempts(self, instance_domain: str) -> int:
        """Get number of attempts in half-open state"""
        key = f'instance_health:half_open_attempts:{instance_domain}'
        count = self.redis_client.get(key)
        return int(count) if count else 0
    
    def _increment_half_open_attempts(self, instance_domain: str):
        """Increment half-open attempts"""
        key = f'instance_health:half_open_attempts:{instance_domain}'
        self.redis_client.incr(key)
        self.redis_client.expire(key, 300)  # 5 minutes
    
    def _update_instance_health(self, instance_domain: str):
        """Update instance health in database"""
        try:
            instance = Instance.query.filter_by(domain=instance_domain).first()
            if instance:
                health = self.get_instance_health(instance_domain)
                
                # Update dormant status based on health
                if health == InstanceHealth.DEAD:
                    instance.dormant = True
                    instance.gone_forever = True
                elif health == InstanceHealth.HEALTHY:
                    instance.dormant = False
                    instance.failures = 0
                
                db.session.commit()
        except Exception as e:
            logger.error(f"Error updating instance health: {e}")
            db.session.rollback()


# Utility functions

def check_instance_health(instance_domain: str) -> Tuple[bool, Optional[str]]:
    """Check if we can send to an instance"""
    monitor = InstanceHealthMonitor()
    return monitor.can_send_to_instance(instance_domain)


def record_federation_success(instance_domain: str, response_time: float):
    """Record successful federation request"""
    monitor = InstanceHealthMonitor()
    monitor.record_success(instance_domain, response_time)


def record_federation_failure(instance_domain: str, error_type: str = 'generic'):
    """Record failed federation request"""
    monitor = InstanceHealthMonitor()
    monitor.record_failure(instance_domain, error_type)