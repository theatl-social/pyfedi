"""
Test cases for JSON validator security module
Tests protection against JSON-based attacks
"""
import pytest
import json
from unittest.mock import Mock, patch
from app.security.json_validator import SafeJSONParser, validate_activitypub_object


class TestSafeJSONParser:
    """Test JSON parsing security"""
    
    def setup_method(self):
        """Set up test fixtures"""
        # Mock Flask app config
        self.mock_app = Mock()
        self.mock_app.config = {
            'MAX_JSON_SIZE': 1000000,
            'MAX_JSON_DEPTH': 50,
            'MAX_JSON_KEYS': 1000
        }
        
    def test_normal_json_parsing(self):
        """Test parsing valid JSON"""
        with patch('app.security.json_validator.current_app', self.mock_app):
            parser = SafeJSONParser()
            
            valid_json = {
                "type": "Like",
                "actor": "https://example.com/users/alice",
                "object": "https://example.com/posts/123"
            }
            
            result = parser.parse(json.dumps(valid_json).encode())
            assert result == valid_json
    
    def test_empty_json_rejected(self):
        """Test empty JSON is rejected"""
        with patch('app.security.json_validator.current_app', self.mock_app):
            parser = SafeJSONParser()
            
            with pytest.raises(ValueError, match="Empty JSON data"):
                parser.parse(b'')
    
    def test_oversized_json_rejected(self):
        """Test oversized JSON is rejected"""
        with patch('app.security.json_validator.current_app', self.mock_app):
            parser = SafeJSONParser()
            parser.max_size = 100  # Set small limit
            
            large_json = json.dumps({"data": "x" * 200})
            
            with pytest.raises(ValueError, match="JSON too large"):
                parser.parse(large_json.encode())
    
    def test_deeply_nested_json_rejected(self):
        """Test deeply nested JSON is rejected (prevents stack overflow)"""
        with patch('app.security.json_validator.current_app', self.mock_app):
            parser = SafeJSONParser()
            parser.max_depth = 5  # Set shallow limit
            
            # Create deeply nested structure
            nested = {"level": 1}
            current = nested
            for i in range(10):
                current["nested"] = {"level": i + 2}
                current = current["nested"]
            
            with pytest.raises(ValueError, match="JSON too deeply nested"):
                parser.parse(json.dumps(nested).encode())
    
    def test_json_bomb_key_explosion_rejected(self):
        """Test JSON with too many keys is rejected"""
        with patch('app.security.json_validator.current_app', self.mock_app):
            parser = SafeJSONParser()
            parser.max_keys = 10  # Set low limit
            
            # Create object with many keys
            bomb = {f"key{i}": i for i in range(20)}
            
            with pytest.raises(ValueError, match="Too many total keys"):
                parser.parse(json.dumps(bomb).encode())
    
    def test_array_bomb_rejected(self):
        """Test arrays with too many items are rejected"""
        with patch('app.security.json_validator.current_app', self.mock_app):
            parser = SafeJSONParser()
            parser.max_array_length = 10  # Set low limit
            
            # Create large array
            bomb = {"items": list(range(20))}
            
            with pytest.raises(ValueError, match="Array too large"):
                parser.parse(json.dumps(bomb).encode())
    
    def test_prototype_pollution_rejected(self):
        """Test prototype pollution attempts are rejected"""
        with patch('app.security.json_validator.current_app', self.mock_app):
            parser = SafeJSONParser()
            
            # Attempt prototype pollution
            malicious = {
                "__proto__": {"isAdmin": True},
                "user": "attacker"
            }
            
            with pytest.raises(ValueError, match="suspicious key patterns"):
                parser.parse(json.dumps(malicious).encode())
    
    def test_constructor_manipulation_rejected(self):
        """Test constructor manipulation attempts are rejected"""
        with patch('app.security.json_validator.current_app', self.mock_app):
            parser = SafeJSONParser()
            
            malicious = {
                "constructor": {"prototype": {"isAdmin": True}},
                "user": "attacker"
            }
            
            with pytest.raises(ValueError, match="suspicious key patterns"):
                parser.parse(json.dumps(malicious).encode())
    
    def test_invalid_float_values_rejected(self):
        """Test invalid float values are rejected"""
        with patch('app.security.json_validator.current_app', self.mock_app):
            parser = SafeJSONParser()
            
            # JSON with infinity (not valid in spec)
            with pytest.raises(ValueError):
                parser.parse(b'{"value": Infinity}')
            
            # JSON with NaN
            with pytest.raises(ValueError):
                parser.parse(b'{"value": NaN}')
    
    def test_malformed_json_rejected(self):
        """Test malformed JSON is rejected"""
        with patch('app.security.json_validator.current_app', self.mock_app):
            parser = SafeJSONParser()
            
            malformed = [
                b'{invalid json}',
                b'{"unclosed": "string',
                b'{"trailing": "comma",}',
                b'[1, 2, 3,]',
                b'{"duplicate": 1, "duplicate": 2}'  # Some parsers allow this
            ]
            
            for bad_json in malformed:
                with pytest.raises(ValueError, match="Invalid JSON"):
                    parser.parse(bad_json)
    
    def test_unicode_handling(self):
        """Test proper Unicode handling"""
        with patch('app.security.json_validator.current_app', self.mock_app):
            parser = SafeJSONParser()
            
            unicode_json = {
                "name": "Test 🦊",
                "text": "Hello 世界",
                "emoji": "🔐🛡️"
            }
            
            result = parser.parse(json.dumps(unicode_json).encode('utf-8'))
            assert result == unicode_json
    
    def test_complex_valid_activitypub_object(self):
        """Test parsing complex but valid ActivityPub object"""
        with patch('app.security.json_validator.current_app', self.mock_app):
            parser = SafeJSONParser()
            
            complex_ap = {
                "@context": [
                    "https://www.w3.org/ns/activitystreams",
                    {
                        "ostatus": "http://ostatus.org#",
                        "atomUri": "ostatus:atomUri"
                    }
                ],
                "type": "Create",
                "id": "https://example.com/activities/1",
                "actor": "https://example.com/users/alice",
                "object": {
                    "type": "Note",
                    "id": "https://example.com/notes/1",
                    "content": "Hello world!",
                    "to": ["https://www.w3.org/ns/activitystreams#Public"],
                    "cc": ["https://example.com/users/alice/followers"],
                    "attachment": [{
                        "type": "Image",
                        "url": "https://example.com/image.jpg"
                    }]
                }
            }
            
            result = parser.parse(json.dumps(complex_ap).encode())
            assert result == complex_ap


class TestActivityPubValidation:
    """Test ActivityPub object validation"""
    
    def test_valid_activitypub_object(self):
        """Test valid ActivityPub object passes validation"""
        valid_objects = [
            {"type": "Like"},
            {"type": "Create", "id": "https://example.com/1"},
            {"type": "Follow", "actor": "https://example.com/users/1"},
            {"type": "Announce", "actor": {"id": "https://example.com/users/1"}}
        ]
        
        for obj in valid_objects:
            assert validate_activitypub_object(obj) is True
    
    def test_missing_type_rejected(self):
        """Test object without type is rejected"""
        with pytest.raises(ValueError, match="missing required 'type' field"):
            validate_activitypub_object({})
    
    def test_invalid_type_field_rejected(self):
        """Test invalid type field formats are rejected"""
        # Type must be string
        with pytest.raises(ValueError, match="'type' field must be a string"):
            validate_activitypub_object({"type": 123})
        
        # Type must not be too long
        with pytest.raises(ValueError, match="'type' field too long"):
            validate_activitypub_object({"type": "x" * 100})
    
    def test_invalid_id_field_rejected(self):
        """Test invalid id field formats are rejected"""
        # ID must be string if present
        with pytest.raises(ValueError, match="'id' field must be a string"):
            validate_activitypub_object({"type": "Like", "id": 123})
        
        # ID must not be too long
        with pytest.raises(ValueError, match="'id' field too long"):
            validate_activitypub_object({"type": "Like", "id": "x" * 3000})
    
    def test_invalid_actor_field_rejected(self):
        """Test invalid actor field formats are rejected"""
        # Actor must be string or object
        with pytest.raises(ValueError, match="'actor' field must be string or object"):
            validate_activitypub_object({"type": "Like", "actor": 123})
        
        # Actor string must not be too long
        with pytest.raises(ValueError, match="'actor' field too long"):
            validate_activitypub_object({"type": "Like", "actor": "x" * 3000})
        
        # Actor object must have id
        with pytest.raises(ValueError, match="actor object must have 'id' field"):
            validate_activitypub_object({"type": "Like", "actor": {"name": "test"}})


class TestJSONAttackVectors:
    """Test specific JSON attack vectors"""
    
    def setup_method(self):
        self.mock_app = Mock()
        self.mock_app.config = {
            'MAX_JSON_SIZE': 1000000,
            'MAX_JSON_DEPTH': 50,
            'MAX_JSON_KEYS': 1000
        }
    
    def test_billion_laughs_attack(self):
        """Test protection against billion laughs / XML bomb style attack"""
        with patch('app.security.json_validator.current_app', self.mock_app):
            parser = SafeJSONParser()
            parser.max_keys = 100
            
            # Create expanding structure
            expanding = {
                "a": ["x"] * 10,
                "b": ["x"] * 10,
                "c": ["x"] * 10,
                "d": ["x"] * 10,
                "e": ["x"] * 10,
                "f": ["x"] * 10,
                "g": ["x"] * 10,
                "h": ["x"] * 10,
                "i": ["x"] * 10,
                "j": ["x"] * 10,
                "all": []  # Would reference all above
            }
            
            # This should be caught by array size limits
            parser.max_array_length = 50
            with pytest.raises(ValueError):
                parser.parse(json.dumps(expanding).encode())
    
    def test_hash_collision_attack(self):
        """Test protection against hash collision attacks"""
        with patch('app.security.json_validator.current_app', self.mock_app):
            parser = SafeJSONParser()
            parser.max_keys = 50
            
            # Many keys could cause hash collisions in poorly implemented parsers
            # But our parser limits total keys
            collision_attempt = {str(i): i for i in range(100)}
            
            with pytest.raises(ValueError, match="Too many total keys"):
                parser.parse(json.dumps(collision_attempt).encode())
    
    def test_recursive_reference_simulation(self):
        """Test handling of deeply recursive structures"""
        with patch('app.security.json_validator.current_app', self.mock_app):
            parser = SafeJSONParser()
            parser.max_depth = 3
            
            # Simulate recursive structure (can't have true circular refs in JSON)
            recursive = {
                "a": {
                    "b": {
                        "c": {
                            "d": "too deep"
                        }
                    }
                }
            }
            
            with pytest.raises(ValueError, match="JSON too deeply nested"):
                parser.parse(json.dumps(recursive).encode())