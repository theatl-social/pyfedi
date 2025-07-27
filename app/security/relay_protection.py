"""
Protection against vote amplification via relays
"""
from typing import Dict, Any, Optional
from flask import current_app
import redis
from app.models import User
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class RelayProtection:
    """Prevent vote amplification and relay abuse"""
    
    # Known relay software patterns
    KNOWN_RELAY_SOFTWARE = [
        'activityrelay',
        'federelay',
        'aoderelay',
        'yukimochi',
        'pub-relay'
    ]
    
    # Suspicious patterns in actor URLs
    RELAY_ACTOR_PATTERNS = [
        '/relay',
        '/actor',
        '/inbox',
        '/service',
        '/system'
    ]
    
    def __init__(self):
        self.redis_client = redis.from_url(
            current_app.config.get('REDIS_URL', 'redis://localhost:6379/0')
        )
        self.max_announces_per_object = current_app.config.get('MAX_ANNOUNCES_PER_OBJECT', 5)
        self.vote_rate_limit = current_app.config.get('VOTE_RATE_LIMIT_PER_ACTOR', 100)
    
    def is_relay_actor(self, actor: User) -> bool:
        """Detect if an actor is likely a relay"""
        # Check software type
        if actor.instance and actor.instance.software:
            software_lower = actor.instance.software.lower()
            if any(relay in software_lower for relay in self.KNOWN_RELAY_SOFTWARE):
                return True
        
        # Check actor URL patterns
        if actor.ap_profile_id:
            parsed = urlparse(actor.ap_profile_id)
            path_lower = parsed.path.lower()
            if any(pattern in path_lower for pattern in self.RELAY_ACTOR_PATTERNS):
                # Additional check - real users rarely have these exact paths
                if path_lower in ['/relay', '/actor', '/inbox']:
                    return True
        
        # Check actor properties
        if hasattr(actor, 'type') and actor.type in ['Service', 'Application']:
            return True
        
        # Check for relay-like behavior
        if self._shows_relay_behavior(actor):
            return True
        
        return False
    
    def validate_announced_activity(self, announce: Dict[str, Any], announcing_actor: User) -> tuple[bool, Optional[str]]:
        """
        Validate an announced (boosted) activity
        
        Returns:
            (is_valid, error_reason)
        """
        # Check if announcer is a relay
        if self.is_relay_actor(announcing_actor):
            # Apply stricter validation for relays
            return self._validate_relay_announce(announce, announcing_actor)
        
        # Check announce depth (prevent deeply nested announces)
        if self._get_announce_depth(announce) > 2:
            return False, "Announce depth exceeds limit"
        
        # Check if object has been over-announced
        object_id = self._extract_object_id(announce)
        if object_id and self._is_over_announced(object_id):
            return False, "Object has been announced too many times"
        
        # Validate the inner activity
        inner_activity = announce.get('object')
        if isinstance(inner_activity, dict):
            # Check for vote activities from relays
            if inner_activity.get('type') in ['Like', 'Dislike']:
                return self._validate_relayed_vote(inner_activity, announcing_actor)
        
        return True, None
    
    def _validate_relay_announce(self, announce: Dict[str, Any], relay_actor: User) -> tuple[bool, Optional[str]]:
        """Special validation for relay announces"""
        inner_activity = announce.get('object')
        
        if not isinstance(inner_activity, dict):
            return True, None  # String references are ok
        
        activity_type = inner_activity.get('type')
        
        # Relays should not amplify votes
        if activity_type in ['Like', 'Dislike', 'EmojiReact']:
            logger.warning(f"Relay {relay_actor.ap_profile_id} attempted to amplify vote")
            return False, "Relays cannot amplify votes"
        
        # Relays should not amplify sensitive activities
        if activity_type in ['Flag', 'Block', 'Report']:
            return False, "Relays cannot amplify moderation activities"
        
        # Check relay announce rate
        if not self._check_relay_rate_limit(relay_actor):
            return False, "Relay rate limit exceeded"
        
        return True, None
    
    def _validate_relayed_vote(self, vote_activity: Dict[str, Any], relay_actor: User) -> tuple[bool, Optional[str]]:
        """Validate a vote that came through a relay"""
        # Get the original actor
        original_actor_id = vote_activity.get('actor')
        if not original_actor_id:
            return False, "Vote missing actor"
        
        # Don't accept votes where relay modified the actor
        if relay_actor.ap_profile_id == original_actor_id:
            return False, "Relay cannot vote on behalf of itself"
        
        # Check vote rate for original actor
        if not self._check_vote_rate(original_actor_id):
            return False, "Original actor vote rate exceeded"
        
        # Verify the vote target exists and is local
        target = vote_activity.get('object')
        if not self._is_valid_vote_target(target):
            return False, "Invalid vote target"
        
        return True, None
    
    def _shows_relay_behavior(self, actor: User) -> bool:
        """Detect relay-like behavior patterns"""
        # Check if actor only announces, never creates original content
        if hasattr(actor, 'posts') and hasattr(actor, 'announces'):
            if actor.posts.count() == 0 and actor.announces.count() > 100:
                return True
        
        # Check follower/following ratio
        if hasattr(actor, 'followers') and hasattr(actor, 'following'):
            # Relays typically have many followers but follow few/none
            if actor.followers.count() > 1000 and actor.following.count() < 10:
                return True
        
        return False
    
    def _get_announce_depth(self, activity: Dict[str, Any], depth: int = 0) -> int:
        """Calculate announce nesting depth"""
        if depth > 10:  # Prevent infinite recursion
            return depth
        
        if activity.get('type') != 'Announce':
            return depth
        
        inner = activity.get('object')
        if isinstance(inner, dict) and inner.get('type') == 'Announce':
            return self._get_announce_depth(inner, depth + 1)
        
        return depth
    
    def _extract_object_id(self, activity: Dict[str, Any]) -> Optional[str]:
        """Extract the ultimate object ID from an activity"""
        obj = activity.get('object')
        
        # Handle nested announces
        while isinstance(obj, dict) and obj.get('type') == 'Announce':
            obj = obj.get('object')
        
        if isinstance(obj, str):
            return obj
        elif isinstance(obj, dict):
            return obj.get('id')
        
        return None
    
    def _is_over_announced(self, object_id: str) -> bool:
        """Check if an object has been announced too many times"""
        announce_key = f"announce_count:{object_id}"
        count = self.redis_client.get(announce_key)
        return int(count) > self.max_announces_per_object if count else False
    
    def record_announce(self, object_id: str):
        """Record an announce for rate limiting"""
        announce_key = f"announce_count:{object_id}"
        self.redis_client.incr(announce_key)
        self.redis_client.expire(announce_key, 3600)  # 1 hour window
    
    def _check_relay_rate_limit(self, relay_actor: User) -> bool:
        """Check if relay is within rate limits"""
        rate_key = f"relay_rate:{relay_actor.ap_profile_id}"
        current = self.redis_client.incr(rate_key)
        self.redis_client.expire(rate_key, 300)  # 5 minute window
        return current <= 100  # Max 100 announces per 5 minutes
    
    def _check_vote_rate(self, actor_id: str) -> bool:
        """Check vote rate for an actor"""
        rate_key = f"vote_rate:{actor_id}"
        current = self.redis_client.incr(rate_key)
        self.redis_client.expire(rate_key, 3600)  # 1 hour window
        return current <= self.vote_rate_limit
    
    def _is_valid_vote_target(self, target: str) -> bool:
        """Check if vote target is valid and local"""
        if not target or not isinstance(target, str):
            return False
        
        # Check if target is local (simplified check)
        local_domain = current_app.config.get('SERVER_NAME', '')
        return local_domain in target
    
    def get_relay_stats(self) -> Dict[str, Any]:
        """Get statistics about relay activity"""
        # This would query the database for relay statistics
        return {
            'known_relays': len(self.KNOWN_RELAY_SOFTWARE),
            'blocked_amplifications': 0,  # Would track in Redis
            'active_relays': 0  # Would query database
        }


# Utility function
def validate_relay_activity(activity: Dict[str, Any], actor: User) -> tuple[bool, Optional[str]]:
    """Validate an activity that may involve relays"""
    protector = RelayProtection()
    
    if activity.get('type') == 'Announce':
        return protector.validate_announced_activity(activity, actor)
    
    return True, None
