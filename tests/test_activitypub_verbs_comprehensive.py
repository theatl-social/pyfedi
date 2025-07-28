"""
Comprehensive test suite for all ActivityPub verbs

This test suite ensures that every ActivityPub verb/activity type
is properly tested with various edge cases and scenarios.
"""
import pytest
import json
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from app import create_app, db
from app.models import User, Community, Post, PostReply, Instance
from app.activitypub.signature import generate_rsa_keypair
from app.federation.types import ActivityType, Priority
from app.federation.producer import FederationProducer


class TestActivityPubVerbs:
    """Test all ActivityPub verb implementations"""
    
    @pytest.fixture(autouse=True)
    def setup(self, app, client):
        """Set up test data"""
        self.app = app
        self.client = client
        
        with app.app_context():
            # Create test instance
            self.instance = Instance(
                domain='remote.example',
                software='mastodon',
                version='4.0.0',
                online=True
            )
            db.session.add(self.instance)
            
            # Create test community
            self.community = Community(
                name='testcommunity',
                title='Test Community',
                description='A test community',
                nsfw=False,
                private_key, public_key = generate_rsa_keypair()
            )
            self.community.private_key = private_key
            self.community.public_key = public_key
            self.community.ap_profile_id = f'https://{app.config["SERVER_NAME"]}/c/testcommunity'
            self.community.ap_inbox_url = f'https://{app.config["SERVER_NAME"]}/c/testcommunity/inbox'
            db.session.add(self.community)
            
            # Create test user
            self.user = User(
                user_name='testuser',
                email='test@example.com',
                private_key, public_key = generate_rsa_keypair()
            )
            self.user.private_key = private_key
            self.user.public_key = public_key
            self.user.ap_profile_id = f'https://{app.config["SERVER_NAME"]}/u/testuser'
            self.user.ap_inbox_url = f'https://{app.config["SERVER_NAME"]}/u/testuser/inbox'
            db.session.add(self.user)
            
            # Create test post
            self.post = Post(
                community=self.community,
                user=self.user,
                title='Test Post',
                body='Test post body',
                comments_enabled=True,
                nsfw=False
            )
            self.post.ap_id = f'https://{app.config["SERVER_NAME"]}/post/{self.post.id}'
            db.session.add(self.post)
            
            db.session.commit()
    
    def create_activity(self, activity_type: str, actor: str, obj: dict = None, **kwargs):
        """Helper to create test activities"""
        activity = {
            '@context': 'https://www.w3.org/ns/activitystreams',
            'id': f'https://remote.example/activities/{activity_type.lower()}/{datetime.utcnow().timestamp()}',
            'type': activity_type,
            'actor': actor,
            'published': datetime.utcnow().isoformat() + 'Z'
        }
        
        if obj:
            activity['object'] = obj
        
        activity.update(kwargs)
        return activity
    
    @patch('app.federation.producer.FederationProducer.queue_activity')
    def test_like_activity(self, mock_queue):
        """Test Like activity processing"""
        # Create Like activity
        like = self.create_activity(
            ActivityType.LIKE.value,
            'https://remote.example/users/alice',
            obj=self.post.ap_id
        )
        
        # Post to community inbox
        response = self.client.post(
            f'/c/testcommunity/inbox',
            data=json.dumps(like),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code in [200, 202]
        mock_queue.assert_called_once()
        
        # Verify the activity was queued correctly
        call_args = mock_queue.call_args[1]
        assert call_args['activity']['type'] == ActivityType.LIKE.value
        assert call_args['activity']['object'] == self.post.ap_id
    
    @patch('app.federation.producer.FederationProducer.queue_activity')
    def test_dislike_activity(self, mock_queue):
        """Test Dislike activity (downvote)"""
        dislike = self.create_activity(
            ActivityType.DISLIKE.value,
            'https://remote.example/users/bob',
            obj=self.post.ap_id
        )
        
        response = self.client.post(
            f'/c/testcommunity/inbox',
            data=json.dumps(dislike),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code in [200, 202]
        mock_queue.assert_called_once()
    
    @patch('app.federation.producer.FederationProducer.queue_activity')
    def test_create_note_activity(self, mock_queue):
        """Test Create activity with Note object (comment)"""
        note = {
            'type': 'Note',
            'id': 'https://remote.example/notes/123',
            'attributedTo': 'https://remote.example/users/alice',
            'content': '<p>This is a comment</p>',
            'inReplyTo': self.post.ap_id,
            'published': datetime.utcnow().isoformat() + 'Z'
        }
        
        create = self.create_activity(
            ActivityType.CREATE.value,
            'https://remote.example/users/alice',
            obj=note,
            to=['https://www.w3.org/ns/activitystreams#Public'],
            cc=[self.community.ap_profile_id]
        )
        
        response = self.client.post(
            f'/c/testcommunity/inbox',
            data=json.dumps(create),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code in [200, 202]
        mock_queue.assert_called_once()
    
    @patch('app.federation.producer.FederationProducer.queue_activity')
    def test_create_article_activity(self, mock_queue):
        """Test Create activity with Article object (post)"""
        article = {
            'type': 'Article',
            'id': 'https://remote.example/articles/456',
            'attributedTo': 'https://remote.example/users/bob',
            'name': 'New Article',
            'content': '<p>Article content</p>',
            'published': datetime.utcnow().isoformat() + 'Z'
        }
        
        create = self.create_activity(
            ActivityType.CREATE.value,
            'https://remote.example/users/bob',
            obj=article,
            to=[self.community.ap_profile_id],
            cc=['https://www.w3.org/ns/activitystreams#Public']
        )
        
        response = self.client.post(
            f'/c/testcommunity/inbox',
            data=json.dumps(create),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code in [200, 202]
        mock_queue.assert_called_once()
    
    @patch('app.federation.producer.FederationProducer.queue_activity')
    def test_update_activity(self, mock_queue):
        """Test Update activity"""
        updated_note = {
            'type': 'Note',
            'id': 'https://remote.example/notes/123',
            'attributedTo': 'https://remote.example/users/alice',
            'content': '<p>Updated comment</p>',
            'updated': datetime.utcnow().isoformat() + 'Z'
        }
        
        update = self.create_activity(
            ActivityType.UPDATE.value,
            'https://remote.example/users/alice',
            obj=updated_note
        )
        
        response = self.client.post(
            f'/c/testcommunity/inbox',
            data=json.dumps(update),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code in [200, 202]
        mock_queue.assert_called_once()
    
    @patch('app.federation.producer.FederationProducer.queue_activity')
    def test_delete_activity(self, mock_queue):
        """Test Delete activity"""
        delete = self.create_activity(
            ActivityType.DELETE.value,
            'https://remote.example/users/alice',
            obj={'id': 'https://remote.example/notes/123', 'type': 'Tombstone'}
        )
        
        response = self.client.post(
            f'/c/testcommunity/inbox',
            data=json.dumps(delete),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code in [200, 202]
        mock_queue.assert_called_once()
    
    @patch('app.federation.producer.FederationProducer.queue_activity')
    def test_follow_activity(self, mock_queue):
        """Test Follow activity"""
        follow = self.create_activity(
            ActivityType.FOLLOW.value,
            'https://remote.example/users/alice',
            obj=self.community.ap_profile_id
        )
        
        response = self.client.post(
            f'/c/testcommunity/inbox',
            data=json.dumps(follow),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code in [200, 202]
        mock_queue.assert_called_once()
    
    @patch('app.federation.producer.FederationProducer.queue_activity')
    def test_accept_activity(self, mock_queue):
        """Test Accept activity (accepting follow)"""
        original_follow = {
            'id': 'https://example.com/follows/123',
            'type': 'Follow',
            'actor': self.user.ap_profile_id,
            'object': 'https://remote.example/users/alice'
        }
        
        accept = self.create_activity(
            ActivityType.ACCEPT.value,
            'https://remote.example/users/alice',
            obj=original_follow
        )
        
        response = self.client.post(
            f'/u/testuser/inbox',
            data=json.dumps(accept),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code in [200, 202]
        mock_queue.assert_called_once()
    
    @patch('app.federation.producer.FederationProducer.queue_activity')
    def test_reject_activity(self, mock_queue):
        """Test Reject activity (rejecting follow)"""
        original_follow = {
            'id': 'https://example.com/follows/456',
            'type': 'Follow',
            'actor': self.user.ap_profile_id,
            'object': 'https://remote.example/users/bob'
        }
        
        reject = self.create_activity(
            ActivityType.REJECT.value,
            'https://remote.example/users/bob',
            obj=original_follow
        )
        
        response = self.client.post(
            f'/u/testuser/inbox',
            data=json.dumps(reject),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code in [200, 202]
        mock_queue.assert_called_once()
    
    @patch('app.federation.producer.FederationProducer.queue_activity')
    def test_announce_activity(self, mock_queue):
        """Test Announce activity (boost/share)"""
        announce = self.create_activity(
            ActivityType.ANNOUNCE.value,
            'https://remote.example/users/alice',
            obj=self.post.ap_id,
            to=['https://www.w3.org/ns/activitystreams#Public'],
            cc=['https://remote.example/users/alice/followers']
        )
        
        response = self.client.post(
            f'/c/testcommunity/inbox',
            data=json.dumps(announce),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code in [200, 202]
        mock_queue.assert_called_once()
    
    @patch('app.federation.producer.FederationProducer.queue_activity')
    def test_undo_like_activity(self, mock_queue):
        """Test Undo Like activity"""
        original_like = {
            'id': 'https://remote.example/likes/789',
            'type': 'Like',
            'actor': 'https://remote.example/users/alice',
            'object': self.post.ap_id
        }
        
        undo = self.create_activity(
            ActivityType.UNDO.value,
            'https://remote.example/users/alice',
            obj=original_like
        )
        
        response = self.client.post(
            f'/c/testcommunity/inbox',
            data=json.dumps(undo),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code in [200, 202]
        mock_queue.assert_called_once()
    
    @patch('app.federation.producer.FederationProducer.queue_activity')
    def test_undo_follow_activity(self, mock_queue):
        """Test Undo Follow activity"""
        original_follow = {
            'id': 'https://remote.example/follows/321',
            'type': 'Follow',
            'actor': 'https://remote.example/users/bob',
            'object': self.community.ap_profile_id
        }
        
        undo = self.create_activity(
            ActivityType.UNDO.value,
            'https://remote.example/users/bob',
            obj=original_follow
        )
        
        response = self.client.post(
            f'/c/testcommunity/inbox',
            data=json.dumps(undo),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code in [200, 202]
        mock_queue.assert_called_once()
    
    @patch('app.federation.producer.FederationProducer.queue_activity')
    def test_flag_activity(self, mock_queue):
        """Test Flag activity (report)"""
        flag = self.create_activity(
            ActivityType.FLAG.value,
            'https://remote.example/users/alice',
            obj=[self.post.ap_id, 'https://remote.example/users/spammer'],
            content='This post contains spam'
        )
        
        response = self.client.post(
            f'/c/testcommunity/inbox',
            data=json.dumps(flag),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code in [200, 202]
        mock_queue.assert_called_once()
    
    @patch('app.federation.producer.FederationProducer.queue_activity')
    def test_add_activity(self, mock_queue):
        """Test Add activity (add moderator, pin post)"""
        # Add moderator
        add_mod = self.create_activity(
            ActivityType.ADD.value,
            self.community.ap_profile_id,
            obj='https://remote.example/users/alice',
            target=f'{self.community.ap_profile_id}/moderators'
        )
        
        response = self.client.post(
            f'/c/testcommunity/inbox',
            data=json.dumps(add_mod),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code in [200, 202]
        mock_queue.assert_called_once()
        
        # Add pinned post
        mock_queue.reset_mock()
        add_pin = self.create_activity(
            ActivityType.ADD.value,
            self.community.ap_profile_id,
            obj=self.post.ap_id,
            target=f'{self.community.ap_profile_id}/featured'
        )
        
        response = self.client.post(
            f'/c/testcommunity/inbox',
            data=json.dumps(add_pin),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code in [200, 202]
        mock_queue.assert_called_once()
    
    @patch('app.federation.producer.FederationProducer.queue_activity')
    def test_remove_activity(self, mock_queue):
        """Test Remove activity (remove moderator, unpin post)"""
        # Remove moderator
        remove_mod = self.create_activity(
            ActivityType.REMOVE.value,
            self.community.ap_profile_id,
            obj='https://remote.example/users/alice',
            target=f'{self.community.ap_profile_id}/moderators'
        )
        
        response = self.client.post(
            f'/c/testcommunity/inbox',
            data=json.dumps(remove_mod),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code in [200, 202]
        mock_queue.assert_called_once()
    
    @patch('app.federation.producer.FederationProducer.queue_activity')
    def test_block_activity(self, mock_queue):
        """Test Block activity"""
        block = self.create_activity(
            ActivityType.BLOCK.value,
            self.community.ap_profile_id,
            obj='https://remote.example/users/troll'
        )
        
        response = self.client.post(
            f'/c/testcommunity/inbox',
            data=json.dumps(block),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code in [200, 202]
        mock_queue.assert_called_once()
    
    def test_activity_with_invalid_type(self):
        """Test handling of unknown activity type"""
        invalid = self.create_activity(
            'InvalidType',
            'https://remote.example/users/alice',
            obj={'id': 'https://example.com/objects/1'}
        )
        
        response = self.client.post(
            f'/c/testcommunity/inbox',
            data=json.dumps(invalid),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        # Should accept but not process unknown types
        assert response.status_code in [200, 202]
    
    def test_activity_missing_required_fields(self):
        """Test handling of activities missing required fields"""
        # Missing actor
        incomplete = {
            '@context': 'https://www.w3.org/ns/activitystreams',
            'id': 'https://remote.example/activities/incomplete',
            'type': 'Like',
            'object': self.post.ap_id
        }
        
        response = self.client.post(
            f'/c/testcommunity/inbox',
            data=json.dumps(incomplete),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code == 400
    
    @patch('app.federation.producer.FederationProducer.queue_activity')
    def test_collection_activities(self, mock_queue):
        """Test activities with collection objects"""
        # OrderedCollection in Create
        collection = {
            'type': 'OrderedCollection',
            'totalItems': 2,
            'orderedItems': [
                {
                    'type': 'Note',
                    'id': 'https://remote.example/notes/1',
                    'content': 'First note'
                },
                {
                    'type': 'Note', 
                    'id': 'https://remote.example/notes/2',
                    'content': 'Second note'
                }
            ]
        }
        
        create = self.create_activity(
            ActivityType.CREATE.value,
            'https://remote.example/users/alice',
            obj=collection
        )
        
        response = self.client.post(
            f'/c/testcommunity/inbox',
            data=json.dumps(create),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code in [200, 202]
        mock_queue.assert_called_once()
    
    @patch('app.federation.producer.FederationProducer.queue_activity')
    def test_nested_activities(self, mock_queue):
        """Test nested activity structures"""
        # Announce of Create
        create = {
            'type': 'Create',
            'id': 'https://remote.example/creates/123',
            'actor': 'https://remote.example/users/alice',
            'object': {
                'type': 'Note',
                'id': 'https://remote.example/notes/nested',
                'content': 'Nested note'
            }
        }
        
        announce = self.create_activity(
            ActivityType.ANNOUNCE.value,
            'https://remote.example/users/bob',
            obj=create
        )
        
        response = self.client.post(
            f'/c/testcommunity/inbox',
            data=json.dumps(announce),
            content_type='application/activity+json',
            headers={'Host': self.app.config['SERVER_NAME']}
        )
        
        assert response.status_code in [200, 202]
        mock_queue.assert_called_once()


class TestActivityPubVerbPriorities:
    """Test priority assignment for different activity types"""
    
    def test_activity_priorities(self):
        """Verify each activity type gets appropriate priority"""
        from app.federation.types import get_activity_priority, Priority
        
        # High priority activities
        assert get_activity_priority(ActivityType.DELETE.value) == Priority.URGENT
        assert get_activity_priority(ActivityType.BLOCK.value) == Priority.URGENT
        
        # Normal priority activities
        assert get_activity_priority(ActivityType.CREATE.value) == Priority.NORMAL
        assert get_activity_priority(ActivityType.UPDATE.value) == Priority.NORMAL
        assert get_activity_priority(ActivityType.FOLLOW.value) == Priority.NORMAL
        assert get_activity_priority(ActivityType.ACCEPT.value) == Priority.NORMAL
        assert get_activity_priority(ActivityType.REJECT.value) == Priority.NORMAL
        
        # Low priority activities
        assert get_activity_priority(ActivityType.LIKE.value) == Priority.BULK
        assert get_activity_priority(ActivityType.DISLIKE.value) == Priority.BULK
        assert get_activity_priority(ActivityType.ANNOUNCE.value) == Priority.BULK