"""
Safe JSON parsing with protection against DoS attacks
"""
import json
from typing import Any, Dict, Optional
from flask import current_app


class SafeJSONParser:
    """
    JSON parser with built-in protection against:
    - Deeply nested objects (stack overflow)
    - Large payloads (memory exhaustion)
    - Key explosion attacks
    """
    
    DEFAULT_MAX_SIZE = 1_000_000  # 1MB
    DEFAULT_MAX_DEPTH = 50
    DEFAULT_MAX_KEYS = 1000
    DEFAULT_MAX_ARRAY_LENGTH = 10000
    
    def __init__(self):
        self.max_size = current_app.config.get('MAX_JSON_SIZE', self.DEFAULT_MAX_SIZE)
        self.max_depth = current_app.config.get('MAX_JSON_DEPTH', self.DEFAULT_MAX_DEPTH)
        self.max_keys = current_app.config.get('MAX_JSON_KEYS', self.DEFAULT_MAX_KEYS)
        self.max_array_length = current_app.config.get('MAX_JSON_ARRAY_LENGTH', self.DEFAULT_MAX_ARRAY_LENGTH)
        self._reset_counters()
    
    def _reset_counters(self):
        """Reset internal counters"""
        self.current_depth = 0
        self.total_keys = 0
        self.total_array_items = 0
        self._depth_stack = []
    
    def parse(self, data: bytes) -> Dict[str, Any]:
        """
        Safely parse JSON with enforced limits
        
        Args:
            data: Raw JSON bytes
            
        Returns:
            Parsed JSON object
            
        Raises:
            ValueError: If JSON exceeds safety limits or is malformed
        """
        # Size check
        if len(data) > self.max_size:
            raise ValueError(f"JSON too large: {len(data)} bytes exceeds maximum of {self.max_size}")
        
        # Empty data check
        if not data:
            raise ValueError("Empty JSON data")
        
        # Parse with safety checks
        self._reset_counters()
        try:
            # Use object_pairs_hook to check during parsing
            result = json.loads(
                data,
                object_pairs_hook=self._object_pairs_hook,
                parse_float=self._safe_float_parser
            )
            
            # Additional validation for root object
            if isinstance(result, dict):
                self._validate_object(result)
            elif isinstance(result, list):
                self._validate_array(result)
                
            return result
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
        except RecursionError:
            raise ValueError(f"JSON nested too deeply (max depth: {self.max_depth})")
        finally:
            self._reset_counters()
    
    def _object_pairs_hook(self, pairs):
        """Hook called for each JSON object during parsing"""
        # Depth check
        self.current_depth += 1
        if self.current_depth > self.max_depth:
            raise ValueError(f"JSON too deeply nested: depth {self.current_depth} exceeds maximum of {self.max_depth}")
        
        # Create object from pairs
        obj = dict(pairs)
        
        # Key count check
        self.total_keys += len(obj)
        if self.total_keys > self.max_keys:
            raise ValueError(f"Too many total keys: {self.total_keys} exceeds maximum of {self.max_keys}")
        
        # Track depth for proper cleanup
        self._depth_stack.append(self.current_depth)
        
        # Validate nested structures
        for value in obj.values():
            if isinstance(value, list):
                self._validate_array(value)
        
        # Clean up depth tracking
        if self._depth_stack:
            self._depth_stack.pop()
        self.current_depth -= 1
        
        return obj
    
    def _validate_array(self, arr: list):
        """Validate array constraints"""
        if len(arr) > self.max_array_length:
            raise ValueError(f"Array too large: {len(arr)} items exceeds maximum of {self.max_array_length}")
        
        self.total_array_items += len(arr)
        if self.total_array_items > self.max_array_length * 10:  # Total across all arrays
            raise ValueError(f"Too many total array items: {self.total_array_items}")
    
    def _validate_object(self, obj: dict):
        """Additional validation for objects"""
        # Check for suspicious patterns
        if self._has_suspicious_keys(obj):
            raise ValueError("JSON contains suspicious key patterns")
    
    def _has_suspicious_keys(self, obj: dict) -> bool:
        """Check for keys that might indicate an attack"""
        suspicious_patterns = [
            '__proto__',  # Prototype pollution
            'constructor',  # Constructor manipulation
            'prototype',  # Prototype manipulation
        ]
        
        for key in obj.keys():
            if key in suspicious_patterns:
                return True
            # Also check for very long keys
            if len(key) > 1000:
                return True
                
        return False
    
    def _safe_float_parser(self, value: str) -> float:
        """Safely parse float values"""
        try:
            f = float(value)
            # Prevent infinity and NaN
            if not (-1e308 < f < 1e308):
                raise ValueError(f"Float value out of range: {value}")
            return f
        except ValueError:
            raise ValueError(f"Invalid float value: {value}")


def validate_activitypub_object(obj: Dict[str, Any]) -> bool:
    """
    Validate that object conforms to basic ActivityPub requirements
    
    Args:
        obj: Parsed ActivityPub object
        
    Returns:
        True if valid
        
    Raises:
        ValueError: If object is invalid
    """
    # Must have a type
    if 'type' not in obj:
        raise ValueError("ActivityPub object missing required 'type' field")
    
    # Type must be a string
    if not isinstance(obj.get('type'), str):
        raise ValueError("ActivityPub 'type' field must be a string")
    
    # Type must not be excessively long
    if len(obj.get('type', '')) > 50:
        raise ValueError("ActivityPub 'type' field too long")
    
    # If it has an ID, validate it
    if 'id' in obj:
        if not isinstance(obj['id'], str):
            raise ValueError("ActivityPub 'id' field must be a string")
        if len(obj['id']) > 2048:
            raise ValueError("ActivityPub 'id' field too long")
    
    # If it has an actor, validate it
    if 'actor' in obj:
        actor = obj['actor']
        if isinstance(actor, str):
            if len(actor) > 2048:
                raise ValueError("ActivityPub 'actor' field too long")
        elif isinstance(actor, dict):
            if 'id' not in actor:
                raise ValueError("ActivityPub actor object must have 'id' field")
        else:
            raise ValueError("ActivityPub 'actor' field must be string or object")
    
    return True