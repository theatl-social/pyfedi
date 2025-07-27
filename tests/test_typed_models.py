"""Test typed models match database schema and Python specifications"""
import pytest
from typing import get_type_hints, get_origin, get_args
from sqlalchemy import inspect
from sqlalchemy.orm import Mapped

from app import create_app, db
from app.models import User, Community, Post, PostReply, Instance
from app.models_typed import TypedUser, TypedCommunity, TypedPost, TypedPostReply, TypedInstance


class TestTypedModels:
    """Test that typed models match original models"""
    
    @pytest.fixture
    def app(self):
        """Create application context"""
        app = create_app()
        app.config['TESTING'] = True
        with app.app_context():
            yield app
    
    def test_user_model_fields(self, app):
        """Test TypedUser has all fields from User model"""
        # Get columns from original User model
        user_columns = {col.name: col for col in inspect(User).columns}
        
        # Get columns from TypedUser model
        typed_user_columns = {col.name: col for col in inspect(TypedUser).columns}
        
        # Check all columns exist
        missing_columns = set(user_columns.keys()) - set(typed_user_columns.keys())
        assert not missing_columns, f"TypedUser missing columns: {missing_columns}"
        
        # Check column types match
        for col_name, col in user_columns.items():
            typed_col = typed_user_columns[col_name]
            assert str(col.type) == str(typed_col.type), \
                f"Column {col_name} type mismatch: {col.type} vs {typed_col.type}"
    
    def test_user_type_annotations(self, app):
        """Test TypedUser has proper type annotations"""
        type_hints = get_type_hints(TypedUser)
        
        # Check some key fields have Mapped annotations
        assert 'id' in type_hints
        assert get_origin(type_hints['id']) is Mapped
        
        assert 'user_name' in type_hints
        assert get_origin(type_hints['user_name']) is Mapped
        
        # Check optional fields
        assert 'email' in type_hints
        email_type = get_args(type_hints['email'])[0]
        assert get_origin(email_type) is type(None) or type(None) in get_args(email_type)
    
    def test_community_model_fields(self, app):
        """Test TypedCommunity has all fields from Community model"""
        community_columns = {col.name: col for col in inspect(Community).columns}
        typed_community_columns = {col.name: col for col in inspect(TypedCommunity).columns}
        
        missing_columns = set(community_columns.keys()) - set(typed_community_columns.keys())
        assert not missing_columns, f"TypedCommunity missing columns: {missing_columns}"
    
    def test_post_model_fields(self, app):
        """Test TypedPost has all fields from Post model"""
        post_columns = {col.name: col for col in inspect(Post).columns}
        typed_post_columns = {col.name: col for col in inspect(TypedPost).columns}
        
        missing_columns = set(post_columns.keys()) - set(typed_post_columns.keys())
        assert not missing_columns, f"TypedPost missing columns: {missing_columns}"
    
    def test_instance_model_fields(self, app):
        """Test TypedInstance has all fields from Instance model"""
        instance_columns = {col.name: col for col in inspect(Instance).columns}
        typed_instance_columns = {col.name: col for col in inspect(TypedInstance).columns}
        
        missing_columns = set(instance_columns.keys()) - set(typed_instance_columns.keys())
        assert not missing_columns, f"TypedInstance missing columns: {missing_columns}"
    
    def test_relationships_typed(self, app):
        """Test relationships are properly typed"""
        # Check User relationships
        user_hints = get_type_hints(TypedUser)
        assert 'posts' in user_hints
        assert 'communities' in user_hints
        
        # Check Community relationships  
        comm_hints = get_type_hints(TypedCommunity)
        assert 'members' in user_hints
        assert 'posts' in comm_hints
    
    def test_methods_exist(self, app):
        """Test all methods from original models exist in typed versions"""
        # User methods
        assert hasattr(TypedUser, 'is_local')
        assert hasattr(TypedUser, 'is_remote')
        assert hasattr(TypedUser, 'public_url')
        assert hasattr(TypedUser, 'is_banned')
        assert hasattr(TypedUser, 'display_name')
        
        # Community methods
        assert hasattr(TypedCommunity, 'is_local')
        assert hasattr(TypedCommunity, 'public_url')
        
        # Instance methods
        assert hasattr(TypedInstance, 'online')
        assert hasattr(TypedInstance, 'votes_are_public')
        assert hasattr(TypedInstance, 'weight')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])