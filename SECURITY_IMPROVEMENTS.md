# PyFedi/PeachPie Security Improvements Plan

## Overview

This document outlines critical and high-priority security vulnerabilities identified in the PyFedi/PeachPie codebase and provides detailed mitigation plans. Security fixes should be implemented before platform improvements to ensure a secure foundation.

## Critical Vulnerabilities (Fix Within 48 Hours)

### CRITICAL-1: Remote Code Execution via Unsafe Deserialization

**Severity**: CRITICAL  
**CVSS Score**: 9.8 (Critical)  
**Location**: `app/activitypub/routes.py:805-831`

**Vulnerability Details**:
- Unbounded JSON parsing allows deeply nested objects
- No validation on object size or complexity
- Recursive processing without stack depth limits
- Could lead to stack overflow or memory exhaustion

**Attack Vector**:
```json
{
  "type": "Create",
  "object": {
    "type": "Note",
    "content": {
      "nested": {
        "deeply": {
          // ... 1000+ levels deep
        }
      }
    }
  }
}
```

**Detailed Mitigation Plan**:

1. **Implement Safe JSON Parser** (Day 1)
   ```python
   import json
   from functools import wraps
   
   MAX_JSON_SIZE = 1_000_000  # 1MB
   MAX_NESTING_DEPTH = 50
   
   def safe_json_parse(data, max_size=MAX_JSON_SIZE):
       if len(data) > max_size:
           raise ValueError(f"JSON too large: {len(data)} > {max_size}")
       
       # Use object_hook to track depth
       depth = 0
       def depth_checker(obj):
           nonlocal depth
           depth += 1
           if depth > MAX_NESTING_DEPTH:
               raise ValueError(f"JSON too deep: {depth} > {MAX_NESTING_DEPTH}")
           return obj
       
       try:
           return json.loads(data, object_hook=depth_checker)
       finally:
           depth = 0
   ```

2. **Add Request Size Validation** (Day 1)
   ```python
   @bp.before_request
   def validate_request_size():
       if request.content_length and request.content_length > MAX_CONTENT_LENGTH:
           abort(413, "Request entity too large")
   ```

3. **Implement Schema Validation** (Day 2)
   ```python
   from jsonschema import validate, ValidationError
   
   ACTIVITY_SCHEMA = {
       "type": "object",
       "properties": {
           "type": {"type": "string", "maxLength": 50},
           "actor": {"type": "string", "maxLength": 2048},
           "object": {
               "oneOf": [
                   {"type": "string", "maxLength": 2048},
                   {"type": "object", "maxProperties": 100}
               ]
           }
       },
       "required": ["type", "actor", "object"],
       "additionalProperties": True,
       "maxProperties": 100
   }
   
   def validate_activity(activity_json):
       try:
           validate(activity_json, ACTIVITY_SCHEMA)
       except ValidationError as e:
           log_security_event("SCHEMA_VALIDATION_FAILED", str(e))
           raise
   ```

**Testing Requirements**:
- Test with nested JSON bombs
- Verify memory usage stays bounded
- Test legitimate complex activities still work
- Benchmark performance impact

**Rollback Plan**:
- Feature flag: `ENABLE_SAFE_JSON_PARSER`
- Gradual rollout by instance
- Monitor for false positives

---

### CRITICAL-2: Authentication Bypass via Signature Verification Fallback

**Severity**: CRITICAL  
**CVSS Score**: 9.1 (Critical)  
**Location**: `app/activitypub/routes.py:991-1026`

**Vulnerability Details**:
- Falls back to weaker verification methods
- Accepts unsigned activities in some cases
- Defers verification for certain activity types
- No logging of verification failures

**Attack Scenario**:
1. Send activity with invalid HTTP signature
2. Include weak LD signature or trigger fallback
3. Bypass authentication checks

**Detailed Mitigation Plan**:

1. **Strict Signature Verification** (Day 1)
   ```python
   def verify_request_signature(request, actor):
       verified = False
       verification_method = None
       
       # Try HTTP signature first
       try:
           HttpSignature.verify_request(request, actor.public_key)
           verified = True
           verification_method = "http_signature"
       except VerificationError as e:
           log_security_event("HTTP_SIGNATURE_FAILED", {
               "actor": actor.ap_profile_id,
               "error": str(e),
               "request_id": g.request_id
           })
       
       # Only try LD signature if HTTP signature explicitly not present
       if not verified and request.headers.get('Signature') is None:
           if 'signature' in request.json:
               try:
                   LDSignature.verify_signature(request.json, actor.public_key)
                   verified = True
                   verification_method = "ld_signature"
               except VerificationError as e:
                   log_security_event("LD_SIGNATURE_FAILED", {
                       "actor": actor.ap_profile_id,
                       "error": str(e)
                   })
       
       if not verified:
           # Check explicit allowlist for unsigned activities
           if is_explicitly_allowed_unsigned(actor, request.json):
               verified = True
               verification_method = "allowlist"
               log_security_event("UNSIGNED_ALLOWED", {
                   "actor": actor.ap_profile_id,
                   "reason": "explicit_allowlist"
               })
       
       if not verified:
           raise SecurityError("No valid signature found")
       
       log_security_event("SIGNATURE_VERIFIED", {
           "method": verification_method,
           "actor": actor.ap_profile_id
       })
       
       return verified
   ```

2. **Remove Deferred Verification** (Day 1)
   ```python
   # DELETE this dangerous pattern:
   elif request_json['type'] == 'Create' and isinstance(request_json['object'], str):
       request_json['object'] = request_json['object']['id']  # NO!
   
   # REPLACE with:
   elif request_json['type'] == 'Create' and isinstance(request_json['object'], str):
       # Must fetch and verify object before processing
       verified_object = fetch_and_verify_object(
           request_json['object'], 
           actor.public_key
       )
       if not verified_object:
           raise SecurityError("Cannot verify object signature")
       request_json['object'] = verified_object
   ```

3. **Implement Allowlist for Unsigned Activities** (Day 2)
   ```python
   ALLOWED_UNSIGNED = {
       # Only for specific trusted services
       'https://fediseer.com/api/v1/user/fediseer': ['ChatMessage'],
   }
   
   def is_explicitly_allowed_unsigned(actor, activity):
       allowed_types = ALLOWED_UNSIGNED.get(actor.ap_profile_id, [])
       return activity.get('type') in allowed_types
   ```

**Testing Requirements**:
- Test with various invalid signatures
- Verify all legitimate activities still work
- Test with spoofed activities
- Monitor for increased rejection rate

**Rollback Plan**:
- Feature flag: `STRICT_SIGNATURE_VERIFICATION`
- Temporary compatibility mode for known issues
- Gradual rollout with monitoring

---

### CRITICAL-3: SQL Injection Risk in Dynamic Queries

**Severity**: CRITICAL  
**CVSS Score**: 8.6 (High)  
**Location**: Multiple locations using `db.session.execute()`

**Vulnerability Details**:
- Raw SQL with string formatting
- Not all parameters properly bound
- Risk of SQL injection if user input reaches queries

**Detailed Mitigation Plan**:

1. **Audit All Raw SQL** (Day 1)
   ```python
   # Create security audit script
   def audit_sql_queries():
       dangerous_patterns = [
           r'\.execute\s*\(\s*["\'].*%[sd]',  # String formatting
           r'\.execute\s*\(\s*f["\']',         # F-strings
           r'\.execute\s*\([^,]+\+',           # String concatenation
       ]
       
       for pattern in dangerous_patterns:
           # Scan codebase and report
           pass
   ```

2. **Replace with Parameterized Queries** (Day 1-2)
   ```python
   # UNSAFE - current code
   db.session.execute(
       f"UPDATE user SET reputation = reputation - {effect} WHERE id = {user_id}"
   )
   
   # SAFE - parameterized
   db.session.execute(
       text("UPDATE user SET reputation = reputation - :effect WHERE id = :user_id"),
       {"effect": effect, "user_id": user_id}
   )
   
   # SAFER - use ORM
   user = User.query.get(user_id)
   if user:
       user.reputation -= effect
       db.session.commit()
   ```

3. **Add Query Interceptor** (Day 2)
   ```python
   from sqlalchemy import event
   
   @event.listens_for(Engine, "before_execute")
   def log_queries(conn, clauseelement, multiparams, params, execution_options):
       # Log and analyze queries for injection patterns
       query_str = str(clauseelement)
       if looks_suspicious(query_str):
           log_security_event("SUSPICIOUS_QUERY", {
               "query": query_str,
               "params": params
           })
   ```

**Testing Requirements**:
- SQL injection test suite
- Performance comparison ORM vs raw SQL
- Verify all queries still function correctly

---

## High Priority Vulnerabilities (Fix Within 2 Weeks)

### HIGH-1: Denial of Service via Unlimited Actor Creation

**Severity**: HIGH  
**CVSS Score**: 7.5 (High)  
**Location**: `app/activitypub/util.py:251`

**Detailed Mitigation Plan**:

1. **Implement Rate Limiting** (Week 1)
   ```python
   from app import redis_client
   
   def rate_limit_actor_creation(instance_domain):
       key = f"actor_creation:{instance_domain}"
       
       # Allow 100 new actors per hour per instance
       current = redis_client.incr(key)
       if current == 1:
           redis_client.expire(key, 3600)
       
       if current > 100:
           raise RateLimitError(f"Too many actors from {instance_domain}")
   ```

2. **Add Instance Reputation** (Week 1)
   ```python
   class InstanceReputation:
       def get_limits(self, instance):
           if instance.trusted:
               return {"actors_per_hour": 1000}
           elif instance.established:  # > 30 days old
               return {"actors_per_hour": 100}
           else:
               return {"actors_per_hour": 10}
   ```

3. **Queue Suspicious Actors** (Week 2)
   ```python
   def find_actor_or_create(actor_url):
       # Check if we should queue instead
       if should_queue_actor(actor_url):
           queue_actor_for_review.delay(actor_url)
           return None
       
       # Normal creation with rate limiting
       rate_limit_actor_creation(get_domain(actor_url))
       return create_actor(actor_url)
   ```

---

### HIGH-2: Vote Amplification Attack

**Severity**: HIGH  
**CVSS Score**: 7.1 (High)  
**Location**: `app/activitypub/routes.py:2467-2505`

**Detailed Mitigation Plan**:

1. **Vote Deduplication** (Week 1)
   ```python
   def process_vote_with_dedup(activity_json, user, vote_type):
       activity_id = activity_json['id']
       
       # Check if we've seen this activity
       if redis_client.exists(f"vote_seen:{activity_id}"):
           log_security_event("DUPLICATE_VOTE", {
               "activity_id": activity_id,
               "actor": user.ap_profile_id
           })
           return
       
       # Mark as seen (24 hour TTL)
       redis_client.setex(f"vote_seen:{activity_id}", 86400, 1)
       
       # Process vote
       process_vote(user, activity_json, vote_type)
   ```

2. **Rate Limiting Per Actor/Object** (Week 1)
   ```python
   def check_vote_rate_limit(user, object):
       key = f"vote_rate:{user.id}:{object.id}"
       
       # Allow 1 vote per minute per object
       if redis_client.exists(key):
           raise RateLimitError("Vote rate limit exceeded")
       
       redis_client.setex(key, 60, 1)
   ```

3. **Anomaly Detection** (Week 2)
   ```python
   def detect_vote_anomalies(user, community):
       # Track voting patterns
       key = f"vote_pattern:{user.id}:{community.id}"
       
       # Increment vote count
       count = redis_client.hincrby(key, "count", 1)
       
       # Check for anomalies
       if count > 100:  # More than 100 votes in window
           log_security_event("VOTE_ANOMALY", {
               "user": user.ap_profile_id,
               "community": community.name,
               "count": count
           })
           
           # Take action
           if count > 1000:
               block_user_voting(user, community)
   ```

---

### HIGH-3: Insufficient Input Validation on Object URIs

**Severity**: HIGH  
**CVSS Score**: 7.3 (High)  
**Location**: Throughout codebase

**Detailed Mitigation Plan**:

1. **URI Validation Library** (Week 1)
   ```python
   import ipaddress
   from urllib.parse import urlparse
   
   class URIValidator:
       BLOCKED_SCHEMES = ['file', 'ftp', 'gopher', 'javascript', 'data']
       BLOCKED_PORTS = [22, 23, 25, 445, 3389]
       
       @classmethod
       def validate(cls, uri):
           try:
               parsed = urlparse(uri)
               
               # Check scheme
               if parsed.scheme not in ['http', 'https']:
                   raise ValueError(f"Invalid scheme: {parsed.scheme}")
               
               # Check for local/private IPs
               if cls.is_private_ip(parsed.hostname):
                   raise ValueError(f"Private IP not allowed: {parsed.hostname}")
               
               # Check port
               port = parsed.port or (443 if parsed.scheme == 'https' else 80)
               if port in cls.BLOCKED_PORTS:
                   raise ValueError(f"Blocked port: {port}")
               
               # Check length
               if len(uri) > 2048:
                   raise ValueError("URI too long")
               
               return True
               
           except Exception as e:
               log_security_event("URI_VALIDATION_FAILED", {
                   "uri": uri[:100],  # Truncate for safety
                   "error": str(e)
               })
               raise
       
       @staticmethod
       def is_private_ip(hostname):
           try:
               ip = ipaddress.ip_address(hostname)
               return ip.is_private or ip.is_loopback or ip.is_link_local
           except:
               # Not an IP, do DNS check
               return False
   ```

2. **Apply Validation Everywhere** (Week 1-2)
   ```python
   def find_liked_object(ap_id):
       # Validate before using
       URIValidator.validate(ap_id)
       
       post = Post.get_by_ap_id(ap_id)
       # ... rest of function
   ```

---

### HIGH-4: Missing Access Control on Announce Activities

**Severity**: HIGH  
**CVSS Score**: 6.8 (Medium-High)  
**Location**: `app/activitypub/routes.py:1241-1284`

**Detailed Mitigation Plan**:

1. **Verify Announce Authority** (Week 1)
   ```python
   def verify_announce_authority(announcer, announced_object, community):
       # Only community actors can announce
       if announcer.ap_profile_id != community.ap_profile_id:
           # Check if announcer is a moderator
           if not community.is_moderator(announcer):
               raise SecurityError(
                   f"Unauthorized announce from {announcer.ap_profile_id}"
               )
       
       # Verify object is appropriate for community
       if not is_appropriate_for_community(announced_object, community):
           raise SecurityError("Inappropriate content for community")
   ```

2. **Add Announce Filtering** (Week 2)
   ```python
   def filter_announced_content(activity, community):
       # Check against community rules
       if community.nsfw and not activity.get('sensitive'):
           activity['sensitive'] = True
       
       # Apply content filters
       if community.blocked_words:
           check_blocked_content(activity, community.blocked_words)
       
       return activity
   ```

---

### HIGH-5: Insecure Direct Object References in Vote Processing

**Severity**: HIGH  
**CVSS Score**: 6.5 (Medium-High)  
**Location**: `app/activitypub/routes.py:2470-2472`

**Detailed Mitigation Plan**:

1. **Standardize Object Reference Parsing** (Week 1)
   ```python
   def parse_object_reference(activity_json, announced=False):
       """Safely parse object references from activities"""
       
       if announced:
           # For announced activities, the object is nested
           container = activity_json.get('object', {})
           if not isinstance(container, dict):
               raise ValueError("Invalid announced activity structure")
           obj = container.get('object')
       else:
           obj = activity_json.get('object')
       
       # Normalize to URI string
       if isinstance(obj, str):
           uri = obj
       elif isinstance(obj, dict) and 'id' in obj:
           uri = obj['id']
       else:
           raise ValueError("Invalid object reference format")
       
       # Validate URI
       URIValidator.validate(uri)
       
       return uri
   ```

2. **Verify Object Ownership** (Week 1)
   ```python
   def verify_vote_target(object_uri, community):
       """Verify the vote target belongs to the expected community"""
       
       obj = find_liked_object(object_uri)
       if not obj:
           return False
       
       if hasattr(obj, 'community_id'):
           return obj.community_id == community.id
       
       return False
   ```

## Implementation Schedule

### Week 1: Critical Fixes
- Days 1-2: Authentication bypass fix
- Days 3-4: RCE prevention
- Days 5-6: SQL injection audit and fixes
- Day 7: Testing and validation

### Week 2: High Priority Fixes
- Days 1-3: Rate limiting implementation
- Days 4-5: URI validation
- Days 6-7: Vote deduplication

### Week 3: Remaining High Priority
- Days 1-3: Announce access control
- Days 4-5: Object reference security
- Days 6-7: Integration testing

### Week 4: Deployment and Monitoring
- Gradual rollout
- Security monitoring
- Performance validation
- Documentation updates

## Testing Strategy

1. **Security Test Suite**
   - Penetration testing for each fix
   - Fuzzing for input validation
   - Load testing for DoS prevention

2. **Regression Testing**
   - Full federation test suite
   - Compatibility testing with major platforms
   - Performance benchmarking

3. **Monitoring and Alerting**
   - Security event dashboard
   - Anomaly detection alerts
   - Rate limit monitoring
   - Failed signature tracking

## Success Criteria

- Zero critical vulnerabilities in production
- 99% reduction in security events
- No degradation in federation compatibility
- < 5% performance impact from security measures
- 100% of security events logged and monitored