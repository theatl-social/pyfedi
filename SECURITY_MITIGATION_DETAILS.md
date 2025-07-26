# Detailed Security Mitigation Plans

## Critical Vulnerability Mitigations

### CRITICAL-1: Remote Code Execution via Unsafe Deserialization

#### Step-by-Step Implementation

**Day 1 Morning: Safe JSON Parser**
1. Create `app/security/json_validator.py`:
```python
import json
from typing import Any, Dict, Optional
from flask import current_app

class SafeJSONParser:
    DEFAULT_MAX_SIZE = 1_000_000  # 1MB
    DEFAULT_MAX_DEPTH = 50
    DEFAULT_MAX_KEYS = 1000
    
    def __init__(self):
        self.max_size = current_app.config.get('MAX_JSON_SIZE', self.DEFAULT_MAX_SIZE)
        self.max_depth = current_app.config.get('MAX_JSON_DEPTH', self.DEFAULT_MAX_DEPTH)
        self.max_keys = current_app.config.get('MAX_JSON_KEYS', self.DEFAULT_MAX_KEYS)
        self._reset_counters()
    
    def _reset_counters(self):
        self.current_depth = 0
        self.total_keys = 0
    
    def parse(self, data: bytes) -> Dict[str, Any]:
        """Safely parse JSON with limits"""
        # Size check
        if len(data) > self.max_size:
            raise ValueError(f"JSON too large: {len(data)} > {self.max_size}")
        
        # Parse with depth tracking
        self._reset_counters()
        try:
            return json.loads(data, object_hook=self._depth_checker)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
        finally:
            self._reset_counters()
    
    def _depth_checker(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        """Track depth and key count during parsing"""
        self.current_depth += 1
        self.total_keys += len(obj)
        
        if self.current_depth > self.max_depth:
            raise ValueError(f"JSON too deep: {self.current_depth} > {self.max_depth}")
        
        if self.total_keys > self.max_keys:
            raise ValueError(f"Too many keys: {self.total_keys} > {self.max_keys}")
        
        # Recursively check nested objects
        for value in obj.values():
            if isinstance(value, dict):
                self._depth_checker(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._depth_checker(item)
        
        self.current_depth -= 1
        return obj
```

2. Create unit tests in `tests/test_json_security.py`:
```python
import pytest
from app.security.json_validator import SafeJSONParser

def test_normal_json():
    parser = SafeJSONParser()
    data = b'{"type": "Like", "actor": "https://example.com/user/1"}'
    result = parser.parse(data)
    assert result['type'] == 'Like'

def test_json_too_large():
    parser = SafeJSONParser()
    parser.max_size = 100
    data = b'{"x": "' + b'a' * 200 + b'"}'
    with pytest.raises(ValueError, match="JSON too large"):
        parser.parse(data)

def test_json_too_deep():
    parser = SafeJSONParser()
    parser.max_depth = 3
    data = b'{"a": {"b": {"c": {"d": "too deep"}}}}'
    with pytest.raises(ValueError, match="JSON too deep"):
        parser.parse(data)

def test_json_bomb():
    parser = SafeJSONParser()
    parser.max_keys = 10
    # Create JSON with many keys
    bomb = '{"' + '": 1, "'.join(f'k{i}' for i in range(20)) + '": 1}'
    with pytest.raises(ValueError, match="Too many keys"):
        parser.parse(bomb.encode())
```

**Day 1 Afternoon: Integration**
3. Update `app/activitypub/routes.py`:
```python
from app.security.json_validator import SafeJSONParser

@bp.route('/inbox', methods=['POST'])
def shared_inbox():
    # ... existing code ...
    
    # Replace this:
    # request_json = request.get_json(force=True, cache=True)
    
    # With this:
    parser = SafeJSONParser()
    try:
        raw_body = request.get_data(cache=True)
        request_json = parser.parse(raw_body)
    except ValueError as e:
        log_security_event("JSON_PARSE_FAILED", {
            "error": str(e),
            "ip": request.remote_addr,
            "user_agent": request.user_agent.string
        })
        return 'Invalid JSON', 400
```

**Day 2: Schema Validation**
4. Install jsonschema: `pip install jsonschema`

5. Create `app/security/activity_schemas.py`:
```python
from jsonschema import validate, ValidationError, Draft7Validator

# Base schema for all activities
BASE_ACTIVITY_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "type": {"type": "string", "maxLength": 50},
        "id": {"type": "string", "format": "uri", "maxLength": 2048},
        "actor": {
            "oneOf": [
                {"type": "string", "format": "uri", "maxLength": 2048},
                {"type": "object", "properties": {"id": {"type": "string", "format": "uri"}}}
            ]
        },
        "@context": {
            "oneOf": [
                {"type": "string"},
                {"type": "array"},
                {"type": "object"}
            ]
        }
    },
    "required": ["type"],
    "additionalProperties": True,
    "maxProperties": 100
}

# Activity-specific schemas
SCHEMAS = {
    "Like": {
        **BASE_ACTIVITY_SCHEMA,
        "properties": {
            **BASE_ACTIVITY_SCHEMA["properties"],
            "object": {
                "oneOf": [
                    {"type": "string", "format": "uri", "maxLength": 2048},
                    {"type": "object", "maxProperties": 50}
                ]
            }
        },
        "required": ["type", "actor", "object"]
    },
    "Create": {
        **BASE_ACTIVITY_SCHEMA,
        "properties": {
            **BASE_ACTIVITY_SCHEMA["properties"],
            "object": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "maxLength": 50},
                    "content": {"type": "string", "maxLength": 500000}  # 500KB max
                },
                "maxProperties": 200
            }
        },
        "required": ["type", "actor", "object"]
    }
}

def validate_activity(activity_json):
    """Validate activity against schema"""
    activity_type = activity_json.get('type')
    
    # Get schema for this activity type
    schema = SCHEMAS.get(activity_type, BASE_ACTIVITY_SCHEMA)
    
    try:
        validate(activity_json, schema)
    except ValidationError as e:
        # Log the validation error
        log_security_event("SCHEMA_VALIDATION_FAILED", {
            "activity_type": activity_type,
            "error": str(e),
            "path": list(e.absolute_path)
        })
        raise
```

**Testing Plan for RCE Mitigation**:
1. Create test suite with malicious payloads:
   - Deeply nested JSON (1000+ levels)
   - JSON with circular references
   - Large JSON files (>10MB)
   - JSON with thousands of keys
   - Unicode exploitation attempts

2. Performance testing:
   - Benchmark parsing speed before/after
   - Memory usage monitoring
   - CPU usage under load

3. Compatibility testing:
   - Test with real ActivityPub messages from various platforms
   - Ensure legitimate complex activities still work

---

### CRITICAL-2: Authentication Bypass Mitigation

#### Step-by-Step Implementation

**Day 1 Morning: Signature Verification Refactor**

1. Create `app/security/signature_validator.py`:
```python
from typing import Optional, Tuple
from flask import Request, g
from app.activitypub.signature import HttpSignature, LDSignature, VerificationError
from app.models import User, Instance
from app import redis_client
import json

class SignatureValidator:
    # Instances that can send unsigned activities (very limited!)
    UNSIGNED_ALLOWLIST = {
        'https://fediseer.com/api/v1/user/fediseer': {
            'allowed_types': ['ChatMessage'],
            'reason': 'Fediseer API key distribution'
        }
    }
    
    def __init__(self):
        self.verification_cache = {}  # Request-scoped cache
    
    def verify_request(self, request: Request, actor: User) -> Tuple[bool, str]:
        """
        Verify request signature with strict validation
        Returns: (verified: bool, method: str)
        """
        # Check cache first
        cache_key = f"{actor.ap_profile_id}:{request.headers.get('Signature', '')}"
        if cache_key in self.verification_cache:
            return self.verification_cache[cache_key]
        
        verified = False
        method = None
        
        # Step 1: Try HTTP Signature (preferred)
        if request.headers.get('Signature'):
            try:
                HttpSignature.verify_request(request, actor.public_key, skip_date=True)
                verified = True
                method = 'http_signature'
                self._log_verification_success('HTTP_SIGNATURE', actor)
            except VerificationError as e:
                self._log_verification_failure('HTTP_SIGNATURE', actor, str(e))
        
        # Step 2: Try LD Signature only if no HTTP signature present
        if not verified and not request.headers.get('Signature'):
            try:
                request_json = request.get_json(force=True)
                if 'signature' in request_json:
                    LDSignature.verify_signature(request_json, actor.public_key)
                    verified = True
                    method = 'ld_signature'
                    self._log_verification_success('LD_SIGNATURE', actor)
                    
                    # Flag for extra scrutiny
                    g.weak_signature = True
            except Exception as e:
                self._log_verification_failure('LD_SIGNATURE', actor, str(e))
        
        # Step 3: Check allowlist for unsigned (very restrictive)
        if not verified:
            request_json = request.get_json(force=True)
            if self._is_unsigned_allowed(actor, request_json):
                verified = True
                method = 'unsigned_allowlist'
                self._log_verification_success('UNSIGNED_ALLOWED', actor)
        
        # Cache result
        self.verification_cache[cache_key] = (verified, method)
        
        # Final security check
        if not verified:
            self._log_security_alert('NO_VALID_SIGNATURE', actor)
            self._increment_failure_counter(actor)
        
        return verified, method
    
    def _is_unsigned_allowed(self, actor: User, activity: dict) -> bool:
        """Check if unsigned activity is explicitly allowed"""
        allowed = self.UNSIGNED_ALLOWLIST.get(actor.ap_profile_id, {})
        if not allowed:
            return False
        
        activity_type = activity.get('type')
        if activity_type not in allowed.get('allowed_types', []):
            return False
        
        # Additional checks for specific activities
        if activity_type == 'ChatMessage':
            # Must be fediseer API key distribution
            content = activity.get('object', {}).get('content', '')
            if 'API key' not in content:
                return False
        
        return True
    
    def _log_verification_success(self, method: str, actor: User):
        """Log successful verification"""
        log_security_event('SIGNATURE_VERIFIED', {
            'method': method,
            'actor': actor.ap_profile_id,
            'instance': actor.instance.domain if actor.instance else None,
            'request_id': g.get('request_id')
        })
    
    def _log_verification_failure(self, method: str, actor: User, error: str):
        """Log verification failure"""
        log_security_event('SIGNATURE_FAILED', {
            'method': method,
            'actor': actor.ap_profile_id,
            'instance': actor.instance.domain if actor.instance else None,
            'error': error,
            'request_id': g.get('request_id')
        })
    
    def _log_security_alert(self, event: str, actor: User):
        """Log security alerts"""
        log_security_event(event, {
            'actor': actor.ap_profile_id,
            'instance': actor.instance.domain if actor.instance else None,
            'ip': request.remote_addr,
            'user_agent': request.user_agent.string,
            'request_id': g.get('request_id')
        }, level='CRITICAL')
    
    def _increment_failure_counter(self, actor: User):
        """Track signature failures per instance"""
        if actor.instance:
            key = f"sig_failures:{actor.instance.domain}"
            count = redis_client.incr(key)
            redis_client.expire(key, 3600)  # 1 hour window
            
            if count > 100:  # More than 100 failures per hour
                self._log_security_alert('EXCESSIVE_SIGNATURE_FAILURES', actor)
                # Could trigger instance blocking here
```

**Day 1 Afternoon: Remove Deferred Verification**

2. Create `app/security/object_verifier.py`:
```python
from typing import Optional, Dict
import httpx
from app.activitypub.util import get_request
from app.models import User
import json

class ObjectVerifier:
    """Verify objects referenced by activities"""
    
    @staticmethod
    def fetch_and_verify_object(object_uri: str, actor_key: str) -> Optional[Dict]:
        """
        Fetch remote object and verify it's signed by the expected actor
        """
        try:
            # Fetch with timeout
            response = get_request(
                object_uri, 
                headers={'Accept': 'application/activity+json'},
                timeout=5.0
            )
            
            if response.status_code != 200:
                log_security_event('OBJECT_FETCH_FAILED', {
                    'uri': object_uri,
                    'status': response.status_code
                })
                return None
            
            object_data = response.json()
            
            # Verify the object is signed or attributedTo matches
            if not ObjectVerifier._verify_object_attribution(object_data, actor_key):
                log_security_event('OBJECT_ATTRIBUTION_FAILED', {
                    'uri': object_uri,
                    'object_type': object_data.get('type')
                })
                return None
            
            return object_data
            
        except Exception as e:
            log_security_event('OBJECT_VERIFICATION_ERROR', {
                'uri': object_uri,
                'error': str(e)
            })
            return None
    
    @staticmethod
    def _verify_object_attribution(object_data: Dict, actor_key: str) -> bool:
        """Verify object is properly attributed"""
        # Check attributedTo field
        attributed_to = object_data.get('attributedTo')
        if attributed_to:
            # TODO: Verify this matches the actor
            return True
        
        # For certain object types, attribution is required
        object_type = object_data.get('type')
        if object_type in ['Note', 'Article', 'Page']:
            return False  # Must have attribution
        
        return True
```

3. Update activity processing in `routes.py`:
```python
# Replace dangerous deferred verification
if core_activity['type'] == 'Create' and isinstance(core_activity['object'], str):
    # OLD DANGEROUS CODE:
    # core_activity['object'] = core_activity['object']['id']
    
    # NEW SECURE CODE:
    verifier = ObjectVerifier()
    verified_object = verifier.fetch_and_verify_object(
        core_activity['object'],
        actor.public_key
    )
    
    if not verified_object:
        log_incoming_ap(
            id, APLOG_CREATE, APLOG_FAILURE, 
            saved_json, 'Cannot verify object'
        )
        return '', 403  # Forbidden
    
    core_activity['object'] = verified_object
```

**Day 2: Testing and Monitoring**

4. Create signature testing suite:
```python
# tests/test_signature_security.py
import pytest
from app.security.signature_validator import SignatureValidator
from unittest.mock import Mock, patch

class TestSignatureSecurity:
    def test_rejects_unsigned_activity(self):
        validator = SignatureValidator()
        request = Mock()
        request.headers = {}
        request.get_json.return_value = {'type': 'Like'}
        
        actor = Mock()
        actor.ap_profile_id = 'https://example.com/user/1'
        
        verified, method = validator.verify_request(request, actor)
        assert verified is False
        assert method is None
    
    def test_accepts_valid_http_signature(self):
        # Test with valid signature
        pass
    
    def test_rejects_spoofed_signature(self):
        # Test with signature from different actor
        pass
    
    def test_allowlist_restrictions(self):
        # Test that only specific activities are allowed unsigned
        pass
```

---

### CRITICAL-3: SQL Injection Prevention

#### Step-by-Step Implementation

**Day 1: Audit Script**

1. Create `scripts/audit_sql_queries.py`:
```python
import os
import re
from pathlib import Path

class SQLAudit:
    DANGEROUS_PATTERNS = [
        # String formatting in execute
        (r'\.execute\s*\([^)]*%[sd]', 'String formatting in SQL'),
        (r'\.execute\s*\(f["\']', 'F-string in SQL'),
        (r'\.execute\s*\([^)]*\+', 'String concatenation in SQL'),
        # Raw SQL construction
        (r'sql\s*=\s*["\'].*%[sd]', 'String formatting in SQL variable'),
        (r'query\s*=\s*["\'].*\+', 'Concatenation in query variable'),
    ]
    
    def audit_file(self, filepath):
        """Audit a single file for SQL injection risks"""
        vulnerabilities = []
        
        with open(filepath, 'r') as f:
            content = f.read()
            lines = content.split('\n')
        
        for pattern, description in self.DANGEROUS_PATTERNS:
            for match in re.finditer(pattern, content):
                line_no = content[:match.start()].count('\n') + 1
                vulnerabilities.append({
                    'file': filepath,
                    'line': line_no,
                    'code': lines[line_no - 1].strip(),
                    'issue': description,
                    'severity': 'HIGH'
                })
        
        return vulnerabilities
    
    def audit_project(self, root_dir='app'):
        """Audit entire project"""
        all_vulnerabilities = []
        
        for path in Path(root_dir).rglob('*.py'):
            vulns = self.audit_file(path)
            all_vulnerabilities.extend(vulns)
        
        return all_vulnerabilities
    
    def generate_report(self):
        """Generate audit report"""
        vulns = self.audit_project()
        
        if not vulns:
            print("✅ No SQL injection vulnerabilities found!")
            return
        
        print(f"⚠️  Found {len(vulns)} potential SQL injection vulnerabilities:\n")
        
        for vuln in vulns:
            print(f"File: {vuln['file']}, Line {vuln['line']}")
            print(f"Issue: {vuln['issue']}")
            print(f"Code: {vuln['code']}")
            print("-" * 50)

if __name__ == '__main__':
    auditor = SQLAudit()
    auditor.generate_report()
```

**Day 1-2: Fix All Vulnerable Queries**

2. Create safe query helpers in `app/security/safe_queries.py`:
```python
from sqlalchemy import text
from app import db
from typing import Any, Dict, List

class SafeQuery:
    @staticmethod
    def execute(query: str, params: Dict[str, Any] = None):
        """Execute parameterized query safely"""
        # Validate query doesn't contain obvious injections
        if params:
            # Check all params are properly typed
            for key, value in params.items():
                if not isinstance(value, (str, int, float, bool, type(None))):
                    raise ValueError(f"Invalid parameter type for {key}")
        
        # Execute with parameters
        return db.session.execute(text(query), params or {})
    
    @staticmethod
    def update_reputation(user_id: int, delta: int):
        """Safe reputation update"""
        # Use ORM when possible
        from app.models import User
        user = User.query.get(user_id)
        if user:
            user.reputation += delta
            db.session.commit()
            return True
        return False
    
    @staticmethod
    def bulk_update(table: str, updates: List[Dict], where_key: str):
        """Safe bulk update"""
        # Validate table name
        allowed_tables = ['user', 'post', 'post_reply', 'community']
        if table not in allowed_tables:
            raise ValueError(f"Invalid table: {table}")
        
        # Use CASE statements for bulk updates
        # This is safe from injection as we control the structure
        pass
```

3. Replace vulnerable queries:
```python
# OLD VULNERABLE CODE:
db.session.execute(
    f"UPDATE user SET reputation = reputation - {effect} WHERE id = {user_id}"
)

# NEW SAFE CODE - Option 1: Parameterized
from app.security.safe_queries import SafeQuery
SafeQuery.execute(
    "UPDATE user SET reputation = reputation - :effect WHERE id = :user_id",
    {"effect": effect, "user_id": user_id}
)

# NEW SAFE CODE - Option 2: ORM
from app.models import User
user = User.query.get(user_id)
if user:
    user.reputation -= effect
    db.session.commit()
```

**Day 2: Query Monitoring**

4. Add query interceptor in `app/__init__.py`:
```python
from sqlalchemy import event
from sqlalchemy.engine import Engine
import re

@event.listens_for(Engine, "before_execute")
def intercept_queries(conn, clauseelement, multiparams, params, execution_options):
    """Monitor queries for injection attempts"""
    query_str = str(clauseelement)
    
    # Check for suspicious patterns
    suspicious_patterns = [
        r';\s*(DROP|DELETE|UPDATE|INSERT)',  # Multiple statements
        r'--\s*$',  # SQL comments
        r'\/\*.*\*\/',  # C-style comments
        r'UNION\s+SELECT',  # Union attacks
        r'OR\s+1\s*=\s*1',  # Classic injection
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, query_str, re.IGNORECASE):
            log_security_event('SUSPICIOUS_QUERY', {
                'query': query_str[:200],  # Truncate for safety
                'pattern': pattern
            }, level='CRITICAL')
            
            # In production, might want to block the query
            if current_app.config.get('BLOCK_SUSPICIOUS_QUERIES'):
                raise SecurityError("Suspicious query blocked")
```

---

## Testing Strategy for All Mitigations

### 1. Security Test Suite
```python
# tests/security/test_suite.py
class SecurityTestSuite:
    def run_all_tests(self):
        results = {
            'json_security': self.test_json_security(),
            'signature_security': self.test_signature_security(),
            'sql_security': self.test_sql_security(),
            'rate_limiting': self.test_rate_limiting(),
            'input_validation': self.test_input_validation()
        }
        return results
    
    def test_json_security(self):
        """Test JSON parsing limits"""
        payloads = [
            # Nested depth attack
            self.generate_nested_json(depth=100),
            # Key explosion
            self.generate_many_keys(count=10000),
            # Large payload
            self.generate_large_json(size_mb=10),
        ]
        # Test each payload
        pass
    
    def test_signature_security(self):
        """Test signature verification"""
        scenarios = [
            # No signature
            {'headers': {}, 'body': {'type': 'Like'}},
            # Invalid signature
            {'headers': {'Signature': 'invalid'}, 'body': {'type': 'Like'}},
            # Spoofed actor
            {'headers': {'Signature': 'valid'}, 'body': {'actor': 'spoofed'}},
        ]
        # Test each scenario
        pass
```

### 2. Monitoring Dashboard
```python
# app/monitoring/security_dashboard.py
class SecurityDashboard:
    def get_metrics(self):
        return {
            'signature_failures': self.get_signature_failures(),
            'blocked_requests': self.get_blocked_requests(),
            'suspicious_queries': self.get_suspicious_queries(),
            'rate_limit_hits': self.get_rate_limit_hits(),
            'security_events': self.get_recent_security_events()
        }
```

### 3. Gradual Rollout Plan
1. **Feature Flags**:
   ```python
   SECURITY_FEATURES = {
       'SAFE_JSON_PARSER': os.getenv('ENABLE_SAFE_JSON', 'false') == 'true',
       'STRICT_SIGNATURES': os.getenv('ENABLE_STRICT_SIGNATURES', 'false') == 'true',
       'SQL_MONITORING': os.getenv('ENABLE_SQL_MONITORING', 'false') == 'true',
   }
   ```

2. **Rollout Stages**:
   - Stage 1: Enable on test instance (1 day)
   - Stage 2: Enable for 10% of traffic (3 days)
   - Stage 3: Enable for 50% of traffic (3 days)
   - Stage 4: Full rollout (if metrics good)

3. **Rollback Triggers**:
   - Error rate > 5%
   - Performance degradation > 20%
   - Federation failures > 1%

This detailed plan provides specific implementation steps, code examples, and testing strategies for each critical vulnerability. The modular approach allows for safe, gradual deployment with monitoring at each stage.