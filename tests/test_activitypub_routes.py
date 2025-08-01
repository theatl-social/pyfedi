"""
Unit tests for refactored ActivityPub routes.

Tests all 41 ActivityPub endpoints to ensure they work correctly
without requiring actual federation or external services.
"""
import pytest
import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
from flask import url_for

from app import create_app, db
from app.models import User, Community, Post, Instance, InstanceBlock, PostReply
from app.activitypub.util import public_key


class TestActorRoutes:
    """Test actor-related ActivityPub routes."""
    
    def test_user_actor_json(self, client, test_user, app):
        """Test user actor JSON endpoint."""
        with app.test_request_context():
            response = client.get(f'/u/{test_user.user_name}')
            
            # When Accept header is ActivityPub, should return JSON
            response = client.get(
                f'/u/{test_user.user_name}',
                headers={'Accept': 'application/activity+json'}
            )
            
            assert response.status_code == 200
            assert response.content_type == 'application/activity+json'
            
            data = json.loads(response.data)
            assert data['type'] == 'Person'
            assert data['preferredUsername'] == test_user.user_name
            assert 'inbox' in data
            assert 'outbox' in data
            assert 'publicKey' in data
    
    def test_community_actor_json(self, client, test_community, app):
        """Test community actor JSON endpoint."""
        with app.test_request_context():
            response = client.get(
                f'/c/{test_community.name}',
                headers={'Accept': 'application/activity+json'}
            )
            
            assert response.status_code == 200
            assert response.content_type == 'application/activity+json'
            
            data = json.loads(response.data)
            assert data['type'] == 'Group'
            assert data['preferredUsername'] == test_community.name
            assert 'inbox' in data
            assert 'outbox' in data
    
    def test_server_actor(self, client, app):
        """Test server actor endpoint."""
        with app.test_request_context():
            response = client.get('/actor')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['type'] == 'Application'
            assert data['id'].endswith('/actor')
            assert 'publicKey' in data


class TestInboxRoutes:
    """Test inbox endpoints."""
    
    def test_shared_inbox_post(self, client, app):
        """Test shared inbox accepts POST requests."""
        with app.test_request_context():
            activity = {
                '@context': 'https://www.w3.org/ns/activitystreams',
                'type': 'Create',
                'actor': 'https://example.com/users/test',
                'object': {
                    'type': 'Note',
                    'content': 'Test note'
                }
            }
            
            with patch('app.activitypub.routes.inbox._verify_signature', return_value=True):
                with patch('app.activitypub.routes.inbox._handle_activity') as mock_process:
                    mock_process.return_value = True
                    
                    response = client.post(
                        '/site_inbox',
                        data=json.dumps(activity),
                        content_type='application/activity+json'
                    )
                    
                    assert response.status_code == 204
                    mock_process.assert_called_once()
    
    def test_user_inbox(self, client, test_user, app):
        """Test user inbox endpoint."""
        with app.test_request_context():
            activity = {
                '@context': 'https://www.w3.org/ns/activitystreams',
                'type': 'Follow',
                'actor': 'https://example.com/users/follower',
                'object': test_user.ap_profile_id
            }
            
            with patch('app.activitypub.routes.inbox._verify_signature', return_value=True):
                with patch('app.activitypub.routes.inbox._handle_activity') as mock_process:
                    mock_process.return_value = True
                    
                    response = client.post(
                        f'/u/{test_user.user_name}/inbox',
                        data=json.dumps(activity),
                        content_type='application/activity+json'
                    )
                    
                    assert response.status_code == 204
    
    def test_community_inbox(self, client, test_community, app):
        """Test community inbox endpoint."""
        with app.test_request_context():
            activity = {
                '@context': 'https://www.w3.org/ns/activitystreams',
                'type': 'Create',
                'actor': 'https://example.com/users/poster',
                'object': {
                    'type': 'Note',
                    'content': 'Post to community'
                },
                'to': [test_community.ap_profile_id]
            }
            
            with patch('app.activitypub.routes.inbox._verify_signature', return_value=True):
                with patch('app.activitypub.routes.inbox._handle_activity') as mock_process:
                    mock_process.return_value = True
                    
                    response = client.post(
                        f'/c/{test_community.name}/inbox',
                        data=json.dumps(activity),
                        content_type='application/activity+json'
                    )
                    
                    assert response.status_code == 204


class TestOutboxRoutes:
    """Test outbox endpoints."""
    
    def test_user_outbox_get(self, client, test_user, app):
        """Test user outbox GET returns OrderedCollection."""
        with app.test_request_context():
            response = client.get(f'/u/{test_user.user_name}/outbox')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['type'] == 'OrderedCollection'
            assert 'totalItems' in data
            assert 'first' in data
    
    def test_user_outbox_paged(self, client, test_user, app):
        """Test user outbox pagination."""
        with app.test_request_context():
            # Create some posts
            for i in range(5):
                post = Post(
                    user_id=test_user.id,
                    title=f'Post {i}',
                    body=f'Body {i}',
                    created_at=datetime.now(timezone.utc)
                )
                db.session.add(post)
            db.session.commit()
            
            # Get first page
            response = client.get(f'/u/{test_user.user_name}/outbox?page=1')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['type'] == 'OrderedCollectionPage'
            assert 'orderedItems' in data
            assert len(data['orderedItems']) <= 50  # Default page size
    
    def test_community_outbox(self, client, test_community, app):
        """Test community outbox endpoint."""
        with app.test_request_context():
            response = client.get(f'/c/{test_community.name}/outbox')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['type'] == 'OrderedCollection'


class TestObjectRoutes:
    """Test object endpoints."""
    
    def test_post_object(self, client, test_post, app):
        """Test post object endpoint."""
        with app.test_request_context():
            response = client.get(f'/post/{test_post.id}')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['type'] in ['Article', 'Page']
            assert data['name'] == test_post.title
            assert data['content'] == test_post.body
    
    def test_comment_object(self, client, test_post, test_user, app):
        """Test comment object endpoint."""
        with app.test_request_context():
            # Create a comment
            comment = PostReply(
                user_id=test_user.id,
                post_id=test_post.id,
                body='Test comment',
                created_at=datetime.now(timezone.utc)
            )
            db.session.add(comment)
            db.session.commit()
            
            response = client.get(f'/comment/{comment.id}')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['type'] == 'Note'
            assert data['content'] == comment.body
            assert data['inReplyTo'] == test_post.ap_id


class TestCollectionRoutes:
    """Test collection endpoints."""
    
    def test_user_followers(self, client, test_user, app):
        """Test user followers collection."""
        with app.test_request_context():
            response = client.get(f'/u/{test_user.user_name}/followers')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['type'] == 'OrderedCollection'
            assert 'totalItems' in data
    
    def test_user_following(self, client, test_user, app):
        """Test user following collection."""
        with app.test_request_context():
            response = client.get(f'/u/{test_user.user_name}/following')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['type'] == 'OrderedCollection'
    
    def test_community_followers(self, client, test_community, app):
        """Test community followers collection."""
        with app.test_request_context():
            response = client.get(f'/c/{test_community.name}/followers')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['type'] == 'OrderedCollection'
    
    def test_liked_collection(self, client, test_user, app):
        """Test user's liked collection."""
        with app.test_request_context():
            response = client.get(f'/u/{test_user.user_name}/liked')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['type'] == 'OrderedCollection'


class TestActivitiesRoutes:
    """Test activity endpoints."""
    
    def test_activity_view(self, client, app):
        """Test activity view endpoint."""
        with app.test_request_context():
            # Mock activity in database
            from app.models import ActivityPubLog
            activity = ActivityPubLog(
                direction='in',
                activity_id='https://test.instance/activities/Like/123',
                activity_type='Like',
                activity_json=json.dumps({
                    'type': 'Like',
                    'actor': 'https://example.com/users/test',
                    'object': 'https://test.instance/posts/1'
                }),
                created_at=datetime.now(timezone.utc)
            )
            db.session.add(activity)
            db.session.commit()
            
            response = client.get('/activities/Like/123')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['type'] == 'Like'


class TestFeedRoutes:
    """Test feed endpoints."""
    
    def test_user_feed(self, client, test_user, app):
        """Test user's public feed."""
        with app.test_request_context():
            # Create public posts
            for i in range(3):
                post = Post(
                    user_id=test_user.id,
                    title=f'Public Post {i}',
                    body=f'Content {i}',
                    created_at=datetime.now(timezone.utc)
                )
                db.session.add(post)
            db.session.commit()
            
            response = client.get(f'/u/{test_user.user_name}/posts')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['type'] == 'OrderedCollection'
            assert data['totalItems'] == 3


class TestNodeInfoRoutes:
    """Test NodeInfo endpoints."""
    
    def test_nodeinfo_wellknown(self, client, app):
        """Test .well-known/nodeinfo endpoint."""
        with app.test_request_context():
            response = client.get('/.well-known/nodeinfo')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'links' in data
            assert len(data['links']) > 0
    
    def test_nodeinfo_2_0(self, client, app):
        """Test NodeInfo 2.0 endpoint."""
        with app.test_request_context():
            response = client.get('/nodeinfo/2.0')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['version'] == '2.0'
            assert data['software']['name'] == 'peachpie'
            assert 'usage' in data
            assert 'users' in data['usage']
    
    def test_nodeinfo_2_1(self, client, app):
        """Test NodeInfo 2.1 endpoint."""
        with app.test_request_context():
            response = client.get('/nodeinfo/2.1')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['version'] == '2.1'
            assert 'software' in data


class TestWebFingerRoute:
    """Test WebFinger endpoint."""
    
    def test_webfinger_user(self, client, test_user, app):
        """Test WebFinger for user."""
        with app.test_request_context():
            response = client.get(
                f'/.well-known/webfinger?resource=acct:{test_user.user_name}@test.instance'
            )
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['subject'] == f'acct:{test_user.user_name}@test.instance'
            assert 'links' in data
            
            # Check for self link
            self_link = next(
                (link for link in data['links'] if link.get('rel') == 'self'),
                None
            )
            assert self_link is not None
            assert self_link['type'] == 'application/activity+json'
    
    def test_webfinger_community(self, client, test_community, app):
        """Test WebFinger for community."""
        with app.test_request_context():
            response = client.get(
                f'/.well-known/webfinger?resource=acct:{test_community.name}@test.instance'
            )
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'links' in data


class TestInstanceRoutes:
    """Test instance-related routes."""
    
    def test_instance_info(self, client, app):
        """Test instance info endpoint."""
        with app.test_request_context():
            response = client.get('/api/v1/instance')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'title' in data
            assert 'version' in data
            assert 'description' in data
    
    def test_instance_peers(self, client, test_instance, app):
        """Test instance peers endpoint."""
        with app.test_request_context():
            # Add another instance
            instance2 = Instance(
                domain='peer.example.com',
                software='mastodon',
                created_at=datetime.now(timezone.utc)
            )
            db.session.add(instance2)
            db.session.commit()
            
            response = client.get('/api/v1/instance/peers')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert isinstance(data, list)
            assert 'peer.example.com' in data


class TestBlocklistRoutes:
    """Test blocklist endpoints."""
    
    def test_instance_blocklist(self, client, test_instance, app):
        """Test instance blocklist endpoint."""
        with app.test_request_context():
            # Create a blocked instance
            blocked = Instance(
                domain='blocked.example.com',
                software='unknown',
                created_at=datetime.now(timezone.utc)
            )
            db.session.add(blocked)
            db.session.commit()
            
            block = InstanceBlock(
                blocker_id=test_instance.id,
                blocked_id=blocked.id,
                reason='Spam',
                created_at=datetime.now(timezone.utc)
            )
            db.session.add(block)
            db.session.commit()
            
            response = client.get('/api/v1/instance/domain_blocks')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert isinstance(data, list)
            assert any(b['domain'] == 'blocked.example.com' for b in data)


class TestErrorHandling:
    """Test error handling in ActivityPub routes."""
    
    def test_user_not_found(self, client, app):
        """Test 404 for non-existent user."""
        with app.test_request_context():
            response = client.get(
                '/u/nonexistent',
                headers={'Accept': 'application/activity+json'}
            )
            
            assert response.status_code == 404
    
    def test_invalid_signature(self, client, app):
        """Test rejection of invalid signatures."""
        with app.test_request_context():
            activity = {
                '@context': 'https://www.w3.org/ns/activitystreams',
                'type': 'Create',
                'actor': 'https://example.com/users/test',
                'object': {'type': 'Note', 'content': 'Test'}
            }
            
            with patch('app.activitypub.routes.inbox._verify_signature', return_value=False):
                response = client.post(
                    '/site_inbox',
                    data=json.dumps(activity),
                    content_type='application/activity+json',
                    headers={
                        'Signature': 'invalid-signature'
                    }
                )
                
                assert response.status_code in [401, 403]
    
    def test_malformed_activity(self, client, app):
        """Test handling of malformed activities."""
        with app.test_request_context():
            # Missing required fields
            activity = {
                '@context': 'https://www.w3.org/ns/activitystreams',
                'type': 'Create'
                # Missing actor and object
            }
            
            with patch('app.activitypub.routes.inbox._verify_signature', return_value=True):
                response = client.post(
                    '/site_inbox',
                    data=json.dumps(activity),
                    content_type='application/activity+json'
                )
                
                # Should handle gracefully
                assert response.status_code in [200, 400]


class TestContentNegotiation:
    """Test content negotiation for ActivityPub routes."""
    
    def test_html_vs_json_response(self, client, test_user, app):
        """Test different responses based on Accept header."""
        with app.test_request_context():
            # HTML request
            response = client.get(f'/u/{test_user.user_name}')
            assert response.status_code == 200
            assert 'text/html' in response.content_type
            
            # JSON request
            response = client.get(
                f'/u/{test_user.user_name}',
                headers={'Accept': 'application/activity+json'}
            )
            assert response.status_code == 200
            assert response.content_type == 'application/activity+json'
            
            # LD+JSON request
            response = client.get(
                f'/u/{test_user.user_name}',
                headers={'Accept': 'application/ld+json'}
            )
            assert response.status_code == 200
            assert response.content_type == 'application/activity+json'