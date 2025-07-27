"""
Actor creation limits and validation
Prevents DoS via unbounded actor creation
"""
from typing import Optional
from datetime import datetime, timedelta
from flask import current_app
import redis
from app.models import User, Instance
import logging

logger = logging.getLogger(__name__)


class ActorCreationLimiter:
    """Limit and validate actor creation to prevent DoS"""
    
    # Default limits
    DEFAULT_ACTORS_PER_INSTANCE_HOUR = 1000
    DEFAULT_ACTORS_PER_INSTANCE_DAY = 5000
    DEFAULT_TOTAL_ACTORS_PER_HOUR = 2500
    DEFAULT_SUSPICIOUS_INSTANCE_THRESHOLD = 1000
    
    def __init__(self):
        self.redis_client = redis.from_url(
            current_app.config.get('REDIS_URL', 'redis://redis:6379') # fix this at some point
        )
        self.actors_per_instance_hour = current_app.config.get(
            'ACTORS_PER_INSTANCE_HOUR',
            self.DEFAULT_ACTORS_PER_INSTANCE_HOUR
        )
        self.actors_per_instance_day = current_app.config.get(
            'ACTORS_PER_INSTANCE_DAY',
            self.DEFAULT_ACTORS_PER_INSTANCE_DAY
        )
        self.total_actors_per_hour = current_app.config.get(
            'TOTAL_ACTORS_PER_HOUR',
            self.DEFAULT_TOTAL_ACTORS_PER_HOUR
        )
    
    def can_create_actor(self, instance_domain: str, actor_uri: str) -> tuple[bool, Optional[str]]:
        """
        Check if actor creation is allowed
        
        Returns:
            (allowed, reason_if_denied)
        """
        # Check instance-level limits
        hourly_key = f"actor_create:instance:{instance_domain}:hour"
        daily_key = f"actor_create:instance:{instance_domain}:day"
        
        # Get current counts
        hourly_count = self.redis_client.get(hourly_key)
        daily_count = self.redis_client.get(daily_key)
        
        hourly_count = int(hourly_count) if hourly_count else 0
        daily_count = int(daily_count) if daily_count else 0
        
        # Check hourly limit
        if hourly_count >= self.actors_per_instance_hour:
            logger.warning(f"Instance {instance_domain} exceeded hourly actor creation limit")
            return False, f"Instance exceeded hourly limit ({self.actors_per_instance_hour} actors/hour)"
        
        # Check daily limit
        if daily_count >= self.actors_per_instance_day:
            logger.warning(f"Instance {instance_domain} exceeded daily actor creation limit")
            return False, f"Instance exceeded daily limit ({self.actors_per_instance_day} actors/day)"
        
        # Check global hourly limit
        global_key = "actor_create:global:hour"
        global_count = self.redis_client.get(global_key)
        global_count = int(global_count) if global_count else 0
        
        if global_count >= self.total_actors_per_hour:
            logger.warning("Global hourly actor creation limit exceeded")
            return False, "System temporarily unavailable for new actors"
        
        # Check if instance is suspicious
        if self._is_suspicious_instance(instance_domain):
            logger.warning(f"Suspicious instance {instance_domain} blocked from creating actors")
            return False, "Instance temporarily blocked"
        
        # Check for duplicate actor
        if self._actor_exists(actor_uri):
            return False, "Actor already exists"
        
        return True, None
    
    def record_actor_creation(self, instance_domain: str, actor_uri: str):
        """Record successful actor creation for rate limiting"""
        # Instance hourly
        hourly_key = f"actor_create:instance:{instance_domain}:hour"
        self.redis_client.incr(hourly_key)
        self.redis_client.expire(hourly_key, 3600)
        
        # Instance daily
        daily_key = f"actor_create:instance:{instance_domain}:day"
        self.redis_client.incr(daily_key)
        self.redis_client.expire(daily_key, 86400)
        
        # Global hourly
        global_key = "actor_create:global:hour"
        self.redis_client.incr(global_key)
        self.redis_client.expire(global_key, 3600)
        
        # Track for suspicious behavior
        self._track_instance_behavior(instance_domain)
    
    def _is_suspicious_instance(self, instance_domain: str) -> bool:
        """Check if instance shows suspicious behavior"""
        # Check if manually blocked
        if self.redis_client.exists(f"instance_blocked:{instance_domain}"):
            return True
        
        # Check actor count for instance
        instance = Instance.query.filter_by(domain=instance_domain).first()
        if instance:
            # High actor count relative to age
            actor_count = User.query.filter_by(instance_id=instance.id).count()
            instance_age_days = (datetime.utcnow() - instance.created_at).days
            
            if instance_age_days < 7 and actor_count > self.DEFAULT_SUSPICIOUS_INSTANCE_THRESHOLD:
                return True
            
            # Rapid growth pattern
            recent_actors = User.query.filter(
                User.instance_id == instance.id,
                User.created_at >= datetime.utcnow() - timedelta(hours=24)
            ).count()
            
            if recent_actors > self.actors_per_instance_day * 0.8:
                return True
        
        return False
    
    def _actor_exists(self, actor_uri: str) -> bool:
        """Check if actor already exists"""
        return User.query.filter_by(ap_profile_id=actor_uri).first() is not None
    
    def _track_instance_behavior(self, instance_domain: str):
        """Track instance behavior for anomaly detection"""
        behavior_key = f"instance_behavior:{instance_domain}"
        self.redis_client.lpush(behavior_key, datetime.utcnow().isoformat())
        self.redis_client.ltrim(behavior_key, 0, 999)  # Keep last 1000 events
        self.redis_client.expire(behavior_key, 604800)  # 7 days
    
    def block_instance(self, instance_domain: str, duration_hours: int = 24, reason: str = None):
        """Temporarily block an instance from creating actors"""
        block_key = f"instance_blocked:{instance_domain}"
        self.redis_client.setex(block_key, duration_hours * 3600, reason or "Manual block")
        logger.info(f"Blocked instance {instance_domain} for {duration_hours} hours: {reason}")
    
    def get_instance_stats(self, instance_domain: str) -> dict:
        """Get creation statistics for an instance"""
        hourly_key = f"actor_create:instance:{instance_domain}:hour"
        daily_key = f"actor_create:instance:{instance_domain}:day"
        
        hourly_count = self.redis_client.get(hourly_key)
        daily_count = self.redis_client.get(daily_key)
        
        return {
            'domain': instance_domain,
            'hourly_count': int(hourly_count) if hourly_count else 0,
            'daily_count': int(daily_count) if daily_count else 0,
            'hourly_limit': self.actors_per_instance_hour,
            'daily_limit': self.actors_per_instance_day,
            'is_blocked': self.redis_client.exists(f"instance_blocked:{instance_domain}")
        }


# Utility function
def check_actor_creation_allowed(instance_domain: str, actor_uri: str) -> tuple[bool, Optional[str]]:
    """Check if actor creation is allowed"""
    limiter = ActorCreationLimiter()
    return limiter.can_create_actor(instance_domain, actor_uri)
