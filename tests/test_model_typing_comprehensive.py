"""Comprehensive tests to verify typed models match database schema exactly"""
import pytest
from typing import get_type_hints, get_origin, get_args, Union
from sqlalchemy import inspect
from sqlalchemy.orm import Mapped
from sqlalchemy.sql.sqltypes import String, Integer, Boolean, Float, Text, DateTime, JSON

from app import create_app, db
from app.models import (
    User, Community, Post, PostReply, Instance,
    CommunityMember, PostVote, PostReplyVote, Notification,
    ActivityPubLog, CommunityJoinRequest, InstanceRole,
    BannedInstances, AllowedInstances, ActivityBatch, SendQueue
)
from app.models_typed import (
    TypedUser, TypedCommunity, TypedPost, TypedPostReply, TypedInstance
)
from app.models_typed_relations import (
    TypedCommunityMember, TypedPostVote, TypedPostReplyVote,
    TypedNotification, TypedUserBlock, TypedInstanceBlock, TypedCommunityBan
)
from app.models_typed_activitypub import (
    TypedActivityPubLog, TypedCommunityJoinRequest, TypedInstanceRole,
    TypedBannedInstances, TypedAllowedInstances, TypedActivityBatch, TypedSendQueue
)


class TestModelTypingComprehensive:
    """Comprehensive tests for all typed models"""
    
    @pytest.fixture
    def app(self):
        """Create application context"""
        app = create_app()
        app.config['TESTING'] = True
        with app.app_context():
            yield app
    
    def compare_model_columns(self, original_model, typed_model, model_name):
        """Compare columns between original and typed models"""
        # Get columns from both models
        orig_columns = {col.name: col for col in inspect(original_model).columns}
        typed_columns = {col.name: col for col in inspect(typed_model).columns}
        
        # Check for missing columns
        missing = set(orig_columns.keys()) - set(typed_columns.keys())
        extra = set(typed_columns.keys()) - set(orig_columns.keys())
        
        assert not missing, f"{model_name}: Missing columns in typed model: {missing}"
        assert not extra, f"{model_name}: Extra columns in typed model: {extra}"
        
        # Compare column types
        for col_name, orig_col in orig_columns.items():
            typed_col = typed_columns[col_name]
            
            # Compare SQLAlchemy types
            orig_type = str(orig_col.type)
            typed_type = str(typed_col.type)
            
            # Allow some flexibility for equivalent types
            if orig_type != typed_type:
                # Check for equivalent types
                equivalents = [
                    ('VARCHAR(', 'STRING('),  # VARCHAR and STRING are equivalent
                    ('INTEGER', 'INTEGER'),
                    ('BOOLEAN', 'BOOLEAN'),
                    ('TEXT', 'TEXT'),
                    ('FLOAT', 'FLOAT'),
                    ('DATETIME', 'DATETIME'),
                ]
                
                type_match = False
                for equiv_pair in equivalents:
                    if any(t in orig_type.upper() for t in equiv_pair) and \
                       any(t in typed_type.upper() for t in equiv_pair):
                        type_match = True
                        break
                
                assert type_match, \
                    f"{model_name}.{col_name}: Type mismatch - original: {orig_type}, typed: {typed_type}"
            
            # Compare nullable
            assert orig_col.nullable == typed_col.nullable, \
                f"{model_name}.{col_name}: Nullable mismatch - original: {orig_col.nullable}, typed: {typed_col.nullable}"
            
            # Compare default values (if set)
            if hasattr(orig_col, 'default') and orig_col.default is not None:
                if hasattr(typed_col, 'default') and typed_col.default is not None:
                    # Compare default values (accounting for callables)
                    orig_default = orig_col.default.arg if hasattr(orig_col.default, 'arg') else orig_col.default
                    typed_default = typed_col.default.arg if hasattr(typed_col.default, 'arg') else typed_col.default
                    
                    # Skip comparison for callable defaults (like datetime.utcnow)
                    if not callable(orig_default) and not callable(typed_default):
                        assert orig_default == typed_default, \
                            f"{model_name}.{col_name}: Default value mismatch"
    
    def check_type_annotations(self, typed_model, model_name):
        """Check that all fields have proper Mapped[] annotations"""
        type_hints = get_type_hints(typed_model)
        
        # Get all column names
        columns = {col.name for col in inspect(typed_model).columns}
        
        # Check each column has a type annotation
        for col_name in columns:
            assert col_name in type_hints, \
                f"{model_name}.{col_name}: Missing type annotation"
            
            # Check it's wrapped in Mapped[]
            hint = type_hints[col_name]
            assert get_origin(hint) is Mapped, \
                f"{model_name}.{col_name}: Not wrapped in Mapped[], got {hint}"
    
    def test_user_model(self, app):
        """Test TypedUser matches User model exactly"""
        self.compare_model_columns(User, TypedUser, "User")
        self.check_type_annotations(TypedUser, "TypedUser")
    
    def test_community_model(self, app):
        """Test TypedCommunity matches Community model"""
        self.compare_model_columns(Community, TypedCommunity, "Community")
        self.check_type_annotations(TypedCommunity, "TypedCommunity")
    
    def test_post_model(self, app):
        """Test TypedPost matches Post model"""
        self.compare_model_columns(Post, TypedPost, "Post")
        self.check_type_annotations(TypedPost, "TypedPost")
    
    def test_post_reply_model(self, app):
        """Test TypedPostReply matches PostReply model"""
        self.compare_model_columns(PostReply, TypedPostReply, "PostReply")
        self.check_type_annotations(TypedPostReply, "TypedPostReply")
    
    def test_instance_model(self, app):
        """Test TypedInstance matches Instance model"""
        self.compare_model_columns(Instance, TypedInstance, "Instance")
        self.check_type_annotations(TypedInstance, "TypedInstance")
    
    def test_community_member_model(self, app):
        """Test TypedCommunityMember matches CommunityMember model"""
        self.compare_model_columns(CommunityMember, TypedCommunityMember, "CommunityMember")
        self.check_type_annotations(TypedCommunityMember, "TypedCommunityMember")
    
    def test_post_vote_model(self, app):
        """Test TypedPostVote matches PostVote model"""
        self.compare_model_columns(PostVote, TypedPostVote, "PostVote")
        self.check_type_annotations(TypedPostVote, "TypedPostVote")
    
    def test_notification_model(self, app):
        """Test TypedNotification matches Notification model"""
        self.compare_model_columns(Notification, TypedNotification, "Notification")
        self.check_type_annotations(TypedNotification, "TypedNotification")
    
    def test_activitypub_log_model(self, app):
        """Test TypedActivityPubLog matches ActivityPubLog model"""
        self.compare_model_columns(ActivityPubLog, TypedActivityPubLog, "ActivityPubLog")
        self.check_type_annotations(TypedActivityPubLog, "TypedActivityPubLog")
    
    def test_methods_preserved(self, app):
        """Test that all methods from original models exist in typed versions"""
        # User methods
        user_methods = ['is_local', 'is_remote', 'is_banned', 'display_name', 
                       'public_url', 'get_inbox_url', 'has_blocked_user', 
                       'has_blocked_instance', 'is_subscribed_to']
        for method in user_methods:
            assert hasattr(TypedUser, method), f"TypedUser missing method: {method}"
        
        # Instance methods
        instance_methods = ['online', 'user_is_admin', 'votes_are_public', 
                           'update_dormant_gone', 'weight']
        for method in instance_methods:
            assert hasattr(TypedInstance, method), f"TypedInstance missing method: {method}"
        
        # Vote methods
        vote_methods = ['is_upvote', 'is_downvote']
        for method in vote_methods:
            assert hasattr(TypedPostVote, method), f"TypedPostVote missing method: {method}"
            assert hasattr(TypedPostReplyVote, method), f"TypedPostReplyVote missing method: {method}"
    
    def test_optional_fields_typed_correctly(self, app):
        """Test that nullable fields are typed as Optional[]"""
        type_hints = get_type_hints(TypedUser)
        
        # Check some known optional fields
        optional_fields = ['email', 'title', 'about', 'banned_until', 'timezone']
        for field in optional_fields:
            hint = type_hints[field]
            # Get the inner type from Mapped[]
            inner_type = get_args(hint)[0]
            # Check if it's Optional (Union with None)
            assert type(None) in get_args(inner_type) or get_origin(inner_type) is type(None), \
                f"TypedUser.{field} should be Optional but got {inner_type}"
    
    def test_relationships_exist(self, app):
        """Test that relationships are defined"""
        # User relationships
        user_rels = inspect(TypedUser).relationships
        assert 'posts' in {r.key for r in user_rels}
        assert 'communities' in {r.key for r in user_rels}
        
        # Community relationships
        comm_rels = inspect(TypedCommunity).relationships
        assert 'posts' in {r.key for r in comm_rels}
        assert 'members' in {r.key for r in comm_rels}
    
    def test_indexes_preserved(self, app):
        """Test that indexes are preserved in typed models"""
        # Check User indexes
        user_indexes = {idx.name for idx in inspect(TypedUser).indexes if idx.name}
        assert 'idx_user_instance_ap' in user_indexes
        assert 'idx_user_reputation' in user_indexes
        
        # Check Post indexes  
        post_indexes = {idx.name for idx in inspect(TypedPost).indexes if idx.name}
        assert 'idx_post_community_sticky_score' in post_indexes
        assert 'idx_post_hot_rank' in post_indexes


if __name__ == '__main__':
    pytest.main([__file__, '-v'])