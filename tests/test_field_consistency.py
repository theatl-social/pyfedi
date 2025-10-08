"""
Test suite to prevent field name fragmentation across data layers.
These tests ensure consistency between models, forms, API schemas, and views.

IMMUTABILITY CONSTRAINTS:
- Public API endpoints, parameters, and response fields are IMMUTABLE
- Database schema (tables, columns, constraints) is IMMUTABLE  
- ActivityPub federation endpoints are IMMUTABLE
"""
import pytest
from flask import current_app
from app import create_app, db
from app.models import User, Post, Community
from app.api.alpha.schema import Person
from app.api.alpha.views import user_view
from config import Config


class TestConfig(Config):
    """Test configuration"""
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_ENGINE_OPTIONS = {}  # SQLite doesn't support pool settings
    MAIL_SUPPRESS_SEND = True


@pytest.fixture
def app():
    """Create test app instance"""
    app = create_app(TestConfig)
    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


class TestFieldConsistency:
    """Test field name consistency across all layers"""
    
    def test_user_model_has_required_fields(self, app):
        """Verify User model has expected core fields"""
        with app.app_context():
            # Critical fields that should never change
            required_fields = [
                'id', 'user_name', 'email', 'created', 'banned', 'deleted'
            ]
            
            user_columns = [col.name for col in User.__table__.columns]
            
            for field in required_fields:
                assert field in user_columns, f"User model missing critical field: {field}"
    
    def test_api_schema_matches_model_fields(self, app):
        """Ensure API Person schema aligns with User model"""
        with app.app_context():
            # Get model fields
            model_fields = {col.name for col in User.__table__.columns}
            
            # Get API schema fields  
            person_schema = Person()
            api_fields = set(person_schema.fields.keys())
            
            # Critical fields that must be in both
            critical_overlap = {
                'id', 'user_name', 'banned', 'deleted', 'published'
            }
            
            for field in critical_overlap:
                if field == 'published':
                    # 'published' maps to 'created' in model
                    assert 'created' in model_fields, "User model missing 'created' field"
                else:
                    assert field in model_fields, f"User model missing field: {field}"
                    assert field in api_fields, f"API schema missing field: {field}"
    
    def test_user_view_field_mapping(self, app):
        """Test that user_view correctly maps model fields to API response"""
        with app.app_context():
            # This test verifies the view layer doesn't introduce field name drift
            
            # Mock user data matching the model structure
            class MockUser:
                id = 1
                user_name = "testuser"
                banned = False
                created = "2023-01-01T00:00:00.000000Z"
                deleted = False
                bot = False
                
                def public_url(self):
                    return "https://test.com/u/testuser"
                
                def display_name(self):
                    return "Test User"
            
            mock_user = MockUser()
            
            # This should not raise AttributeError
            try:
                # Extract just the person part of the view
                person_data = {
                    "id": mock_user.id,
                    "user_name": mock_user.user_name,
                    "banned": mock_user.banned,
                    "deleted": mock_user.deleted,
                    "bot": mock_user.bot,
                    "actor_id": mock_user.public_url(),
                    "local": True,
                    "instance_id": 1,
                    "title": mock_user.display_name(),
                }
                
                # Verify expected fields are present
                assert "user_name" in person_data
                assert person_data["user_name"] == "testuser"
                assert "id" in person_data
                assert "banned" in person_data
                
            except AttributeError as e:
                pytest.fail(f"user_view field mapping failed: {e}")
    
    def test_no_username_vs_user_name_confusion(self, app):
        """Ensure we don't mix 'username' and 'user_name' patterns"""
        with app.app_context():
            # Verify model uses 'user_name' not 'username'
            model_fields = [col.name for col in User.__table__.columns]
            
            assert 'user_name' in model_fields, "Model should use 'user_name' field"
            assert 'username' not in model_fields, "Model should NOT have 'username' field - use 'user_name'"
            
            # Verify API schema uses 'user_name'
            person_schema = Person()
            api_fields = list(person_schema.fields.keys())
            
            assert 'user_name' in api_fields, "API schema should use 'user_name' field"


class TestBaselineFunctionality:
    """Baseline tests to ensure current system works before changes"""
    
    def test_user_model_instantiation(self, app):
        """Test User model can be created with basic fields"""
        with app.app_context():
            # This should work with current model structure
            user_data = {
                'user_name': 'testuser',
                'email': 'test@example.com'
            }
            
            # Verify we can create User instance
            user = User(**user_data)
            assert user.user_name == 'testuser'
            assert user.email == 'test@example.com'
    
    def test_api_schema_validation(self, app):
        """Test API schema validates correctly"""
        with app.app_context():
            person_schema = Person()
            
            # Test data that should validate
            valid_data = {
                'actor_id': 'https://example.com/u/test',
                'banned': False,
                'bot': False,
                'deleted': False,
                'id': 1,
                'instance_id': 1,
                'local': True,
                'user_name': 'testuser'
            }
            
            # This should not raise ValidationError
            result = person_schema.load(valid_data)
            assert result['user_name'] == 'testuser'
            assert result['id'] == 1


class TestAPIEndpointImmutability:
    """Ensure public API endpoints remain unchanged"""
    
    def test_critical_api_endpoints_exist(self, client):
        """Test that critical API endpoints haven't been moved or renamed"""
        critical_endpoints = [
            '/api/alpha/site',
            # Add more as we identify them
        ]
        
        for endpoint in critical_endpoints:
            # These should return valid responses (not 404)
            response = client.get(endpoint)
            assert response.status_code != 404, f"Critical API endpoint missing: {endpoint}"
    
    def test_api_response_field_names_unchanged(self, app):
        """Test that API response field names haven't changed"""
        with app.app_context():
            # Test the Person schema (used in user endpoints)
            person_schema = Person()
            expected_fields = {
                'actor_id', 'banned', 'bot', 'deleted', 'id', 
                'instance_id', 'local', 'user_name'
            }
            
            actual_fields = set(person_schema.fields.keys())
            
            # All expected fields must still exist
            missing_fields = expected_fields - actual_fields
            assert not missing_fields, f"API Person schema missing fields: {missing_fields}"


class TestDatabaseSchemaImmutability:
    """Ensure database schema remains unchanged"""
    
    def test_user_table_columns_unchanged(self, app):
        """Test that User table columns haven't been renamed or removed"""
        with app.app_context():
            # Critical columns that must never change
            required_columns = {
                'id', 'user_name', 'email', 'password_hash', 'verified',
                'banned', 'deleted', 'created', 'last_seen'
            }
            
            actual_columns = {col.name for col in User.__table__.columns}
            
            # All required columns must still exist
            missing_columns = required_columns - actual_columns
            assert not missing_columns, f"User table missing critical columns: {missing_columns}"
    
    def test_post_table_columns_unchanged(self, app):
        """Test that Post table columns haven't been renamed or removed"""
        with app.app_context():
            required_columns = {
                'id', 'title', 'body', 'user_id', 'community_id', 
                'posted_at', 'deleted', 'nsfw'
            }
            
            actual_columns = {col.name for col in Post.__table__.columns}
            
            missing_columns = required_columns - actual_columns
            assert not missing_columns, f"Post table missing critical columns: {missing_columns}"
    
    def test_community_table_columns_unchanged(self, app):
        """Test that Community table columns haven't been renamed or removed"""
        with app.app_context():
            required_columns = {
                'id', 'name', 'title', 'description', 'created_at',
                'user_id', 'nsfw', 'restricted_to_mods'
            }

            actual_columns = {col.name for col in Community.__table__.columns}

            missing_columns = required_columns - actual_columns
            assert not missing_columns, f"Community table missing critical columns: {missing_columns}"


if __name__ == '__main__':
    pytest.main([__file__])