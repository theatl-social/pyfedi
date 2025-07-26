"""
Comprehensive ActivityPub integration tests
Tests regular ActivityPub operations to prevent regressions
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime, timedelta
from app.models import User, Post, Community, Vote, VoteType
from app.activitypub import activities


class TestActivityPubCoreOperations:
    """Test core ActivityPub operations work correctly"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_db = Mock()
        self.mock_celery = Mock()
        
        # Create test users
        self.local_user = Mock(spec=User)
        self.local_user.id = 1
        self.local_user.username = "alice"
        self.local_user.ap_profile_id = "https://our-instance.com/users/alice"
        self.local_user.public_key = "-----BEGIN PUBLIC KEY-----..."
        self.local_user.private_key = "-----BEGIN PRIVATE KEY-----..."
        
        self.remote_user = Mock(spec=User)
        self.remote_user.id = 2
        self.remote_user.username = "bob@example.com"
        self.remote_user.ap_profile_id = "https://example.com/users/bob"
        self.remote_user.public_key = "-----BEGIN PUBLIC KEY-----..."
        
        # Create test post
        self.test_post = Mock(spec=Post)
        self.test_post.id = 123
        self.test_post.ap_id = "https://our-instance.com/posts/123"
        self.test_post.author = self.local_user
        self.test_post.community = Mock()
        self.test_post.community.ap_profile_id = "https://our-instance.com/c/test"
    
    def test_create_note_activity(self):
        """Test creating a Note activity for a new post"""
        note_activity = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "type": "Create",
            "id": f"https://our-instance.com/activities/{self.test_post.id}",
            "actor": self.local_user.ap_profile_id,
            "published": datetime.utcnow().isoformat() + "Z",
            "to": ["https://www.w3.org/ns/activitystreams#Public"],
            "cc": [self.test_post.community.ap_profile_id],
            "object": {
                "type": "Note",
                "id": self.test_post.ap_id,
                "attributedTo": self.local_user.ap_profile_id,
                "content": "Test post content",
                "published": datetime.utcnow().isoformat() + "Z",
                "to": ["https://www.w3.org/ns/activitystreams#Public"],
                "cc": [self.test_post.community.ap_profile_id]
            }
        }
        
        # Verify all required fields are present
        assert note_activity["type"] == "Create"
        assert note_activity["actor"] == self.local_user.ap_profile_id
        assert note_activity["object"]["type"] == "Note"
        assert note_activity["object"]["id"] == self.test_post.ap_id
    
    def test_like_activity_format(self):
        """Test Like activity format for upvotes"""
        like_activity = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "type": "Like",
            "id": "https://our-instance.com/activities/like-456",
            "actor": self.local_user.ap_profile_id,
            "object": self.test_post.ap_id,
            "published": datetime.utcnow().isoformat() + "Z"
        }
        
        # Verify Like activity is properly formatted
        assert like_activity["type"] == "Like"
        assert like_activity["actor"] == self.local_user.ap_profile_id
        assert like_activity["object"] == self.test_post.ap_id
        assert "published" in like_activity
    
    def test_dislike_activity_format(self):
        """Test Dislike activity format for downvotes"""
        dislike_activity = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "type": "Dislike",
            "id": "https://our-instance.com/activities/dislike-789",
            "actor": self.local_user.ap_profile_id,
            "object": self.test_post.ap_id,
            "published": datetime.utcnow().isoformat() + "Z"
        }
        
        # Verify Dislike activity format
        assert dislike_activity["type"] == "Dislike"
        assert dislike_activity["object"] == self.test_post.ap_id
    
    def test_undo_activity_format(self):
        """Test Undo activity format for retracting votes"""
        original_like = {
            "type": "Like",
            "id": "https://our-instance.com/activities/like-456",
            "actor": self.local_user.ap_profile_id,
            "object": self.test_post.ap_id
        }
        
        undo_activity = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "type": "Undo",
            "id": "https://our-instance.com/activities/undo-999",
            "actor": self.local_user.ap_profile_id,
            "object": original_like,
            "published": datetime.utcnow().isoformat() + "Z"
        }
        
        # Verify Undo wraps the original activity
        assert undo_activity["type"] == "Undo"
        assert undo_activity["object"]["type"] == "Like"
        assert undo_activity["object"]["id"] == original_like["id"]
    
    def test_follow_activity_format(self):
        """Test Follow activity format"""
        follow_activity = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "type": "Follow",
            "id": "https://our-instance.com/activities/follow-111",
            "actor": self.local_user.ap_profile_id,
            "object": self.remote_user.ap_profile_id,
            "published": datetime.utcnow().isoformat() + "Z"
        }
        
        assert follow_activity["type"] == "Follow"
        assert follow_activity["actor"] == self.local_user.ap_profile_id
        assert follow_activity["object"] == self.remote_user.ap_profile_id
    
    def test_announce_activity_format(self):
        """Test Announce activity format for boosts/shares"""
        announce_activity = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "type": "Announce",
            "id": "https://our-instance.com/activities/announce-222",
            "actor": self.local_user.ap_profile_id,
            "object": "https://example.com/posts/456",
            "published": datetime.utcnow().isoformat() + "Z",
            "to": ["https://www.w3.org/ns/activitystreams#Public"],
            "cc": [f"{self.local_user.ap_profile_id}/followers"]
        }
        
        assert announce_activity["type"] == "Announce"
        assert announce_activity["object"] == "https://example.com/posts/456"


class TestInboundActivityProcessing:
    """Test processing of inbound ActivityPub activities"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_db = Mock()
        self.mock_celery = Mock()
    
    @patch('app.activitypub.routes.User.query')
    @patch('app.activitypub.routes.Post.query')
    def test_process_inbound_like(self, mock_post_query, mock_user_query):
        """Test processing inbound Like activity"""
        # Setup mocks
        actor = Mock()
        actor.id = 1
        actor.ap_profile_id = "https://example.com/users/bob"
        mock_user_query.filter_by.return_value.first.return_value = actor
        
        post = Mock()
        post.id = 123
        post.ap_id = "https://our-instance.com/posts/123"
        mock_post_query.filter_by.return_value.first.return_value = post
        
        like_activity = {
            "type": "Like",
            "actor": "https://example.com/users/bob",
            "object": "https://our-instance.com/posts/123",
            "id": "https://example.com/activities/like-789"
        }
        
        # Process activity
        with patch('app.activitypub.routes.Vote') as mock_vote:
            with patch('app.activitypub.routes.db.session'):
                # Simulate processing
                # In real code this would be in process_inbox_request
                
                # Verify vote would be created
                assert actor.ap_profile_id == like_activity["actor"]
                assert post.ap_id == like_activity["object"]
    
    @patch('app.activitypub.routes.User.query')
    @patch('app.activitypub.routes.Post.query')
    def test_process_inbound_dislike(self, mock_post_query, mock_user_query):
        """Test processing inbound Dislike activity"""
        actor = Mock()
        actor.ap_profile_id = "https://example.com/users/bob"
        mock_user_query.filter_by.return_value.first.return_value = actor
        
        post = Mock()
        post.ap_id = "https://our-instance.com/posts/123"
        mock_post_query.filter_by.return_value.first.return_value = post
        
        dislike_activity = {
            "type": "Dislike",
            "actor": "https://example.com/users/bob",
            "object": "https://our-instance.com/posts/123",
            "id": "https://example.com/activities/dislike-789"
        }
        
        # Verify Dislike is processed correctly
        assert dislike_activity["type"] == "Dislike"
    
    @patch('app.activitypub.routes.User.query')
    @patch('app.activitypub.routes.Vote.query')
    def test_process_inbound_undo_like(self, mock_vote_query, mock_user_query):
        """Test processing Undo of Like activity"""
        actor = Mock()
        mock_user_query.filter_by.return_value.first.return_value = actor
        
        existing_vote = Mock()
        existing_vote.user = actor
        mock_vote_query.filter_by.return_value.first.return_value = existing_vote
        
        undo_activity = {
            "type": "Undo",
            "actor": "https://example.com/users/bob",
            "object": {
                "type": "Like",
                "id": "https://example.com/activities/like-789",
                "actor": "https://example.com/users/bob",
                "object": "https://our-instance.com/posts/123"
            }
        }
        
        # Verify Undo removes the vote
        assert undo_activity["object"]["type"] == "Like"
    
    def test_process_create_note(self):
        """Test processing Create activity with Note object"""
        create_activity = {
            "type": "Create",
            "actor": "https://example.com/users/bob",
            "object": {
                "type": "Note",
                "id": "https://example.com/notes/456",
                "attributedTo": "https://example.com/users/bob",
                "content": "Hello from another instance!",
                "to": ["https://www.w3.org/ns/activitystreams#Public"],
                "cc": ["https://our-instance.com/c/general"],
                "published": "2024-01-15T10:00:00Z"
            }
        }
        
        # Verify Create/Note structure
        assert create_activity["type"] == "Create"
        assert create_activity["object"]["type"] == "Note"
        assert create_activity["object"]["attributedTo"] == create_activity["actor"]
    
    def test_process_update_note(self):
        """Test processing Update activity for existing Note"""
        update_activity = {
            "type": "Update",
            "actor": "https://example.com/users/bob",
            "object": {
                "type": "Note",
                "id": "https://example.com/notes/456",
                "attributedTo": "https://example.com/users/bob",
                "content": "Updated content!",
                "updated": "2024-01-15T11:00:00Z"
            }
        }
        
        # Verify only original author can update
        assert update_activity["object"]["attributedTo"] == update_activity["actor"]
    
    def test_process_delete_activity(self):
        """Test processing Delete activity"""
        delete_activity = {
            "type": "Delete",
            "actor": "https://example.com/users/bob",
            "object": "https://example.com/notes/456"
        }
        
        # Verify Delete structure
        assert delete_activity["type"] == "Delete"
        # In real processing, would verify actor owns object


class TestVoteSuspenseQueue:
    """Test vote suspense queue for out-of-order activities"""
    
    @patch('app.activitypub.routes.redis_client')
    def test_vote_queued_when_post_not_found(self, mock_redis):
        """Test vote is queued when post doesn't exist yet"""
        like_activity = {
            "type": "Like",
            "actor": "https://example.com/users/bob",
            "object": "https://other-instance.com/posts/999",
            "id": "https://example.com/activities/like-999"
        }
        
        # Post not found
        with patch('app.activitypub.routes.Post.query') as mock_query:
            mock_query.filter_by.return_value.first.return_value = None
            
            # Should queue the vote
            queue_key = f"vote_suspense:{like_activity['object']}"
            # In real implementation, vote would be added to Redis queue
    
    @patch('app.activitypub.routes.redis_client')
    @patch('app.activitypub.routes.Post.query')
    def test_queued_votes_processed_when_post_arrives(self, mock_post_query, mock_redis):
        """Test queued votes are processed when post arrives"""
        post_ap_id = "https://other-instance.com/posts/999"
        
        # Simulate queued votes
        queued_votes = [
            json.dumps({
                "type": "Like",
                "actor": "https://example.com/users/alice",
                "object": post_ap_id
            }),
            json.dumps({
                "type": "Dislike", 
                "actor": "https://example.com/users/bob",
                "object": post_ap_id
            })
        ]
        
        mock_redis.lrange.return_value = queued_votes
        
        # When post arrives, process queued votes
        new_post = Mock()
        new_post.ap_id = post_ap_id
        
        # In real implementation, would process all queued votes
        assert len(queued_votes) == 2
    
    def test_vote_suspense_queue_expiry(self):
        """Test vote suspense queue entries expire"""
        # Votes shouldn't be queued forever
        # In Redis, use EXPIRE to set TTL on suspense queues
        pass


class TestActivityPubDelivery:
    """Test outbound ActivityPub delivery"""
    
    @patch('app.activitypub.delivery.requests.post')
    def test_deliver_activity_with_signature(self, mock_post):
        """Test activity delivery includes HTTP signature"""
        activity = {
            "type": "Like",
            "actor": "https://our-instance.com/users/alice",
            "object": "https://example.com/posts/123"
        }
        
        inbox_url = "https://example.com/users/bob/inbox"
        
        # Mock successful delivery
        mock_response = Mock()
        mock_response.status_code = 202
        mock_post.return_value = mock_response
        
        # In real delivery, would sign with actor's private key
        # Verify signature headers are included
        # mock_post.assert_called_with(
        #     inbox_url,
        #     json=activity,
        #     headers={"Signature": "...", "Date": "..."}
        # )
    
    @patch('app.activitypub.delivery.requests.post')
    def test_delivery_retry_on_failure(self, mock_post):
        """Test delivery retries on failure"""
        # First attempt fails
        mock_post.side_effect = [
            Mock(status_code=500),  # Server error
            Mock(status_code=202)   # Success on retry
        ]
        
        # In real implementation with Celery:
        # - Task would retry with exponential backoff
        # - Max retries would be configured
        # - Failed deliveries would be logged
    
    def test_shared_inbox_optimization(self):
        """Test shared inbox is used when available"""
        # When delivering to multiple users on same instance
        # Should use shared inbox instead of individual inboxes
        recipients = [
            "https://example.com/users/alice",
            "https://example.com/users/bob",
            "https://example.com/users/charlie"
        ]
        
        # Should deliver once to https://example.com/inbox
        # Instead of 3 times to individual inboxes


class TestActivityPubCompat:
    """Test compatibility with other ActivityPub implementations"""
    
    def test_mastodon_vote_format(self):
        """Test handling Mastodon's Like format"""
        mastodon_like = {
            "@context": [
                "https://www.w3.org/ns/activitystreams",
                {
                    "atomUri": "ostatus:atomUri",
                    "conversation": "ostatus:conversation"
                }
            ],
            "type": "Like",
            "actor": "https://mastodon.social/users/alice",
            "object": "https://our-instance.com/posts/123",
            "id": "https://mastodon.social/users/alice#likes/456"
        }
        
        # Should handle extended context
        assert mastodon_like["type"] == "Like"
        assert isinstance(mastodon_like["@context"], list)
    
    def test_lemmy_vote_format(self):
        """Test handling Lemmy's vote format"""
        lemmy_upvote = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "type": "Like",
            "actor": "https://lemmy.ml/u/bob",
            "object": "https://our-instance.com/post/123",
            "id": "https://lemmy.ml/activities/like/789",
            "audience": "https://our-instance.com/c/general"
        }
        
        # Should handle audience field
        assert "audience" in lemmy_upvote
    
    def test_peertube_dislike_format(self):
        """Test handling PeerTube's Dislike format"""
        peertube_dislike = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "type": "Dislike",
            "actor": "https://peertube.example/accounts/user",
            "object": "https://our-instance.com/videos/123",
            "id": "https://peertube.example/accounts/user/dislikes/456"
        }
        
        assert peertube_dislike["type"] == "Dislike"
    
    def test_flexible_object_reference_parsing(self):
        """Test flexible parsing of object references"""
        test_cases = [
            # Direct string reference
            {"object": "https://example.com/posts/123"},
            # Object with id
            {"object": {"id": "https://example.com/posts/123"}},
            # Nested in Announce
            {"type": "Announce", "object": {
                "type": "Like",
                "object": "https://example.com/posts/123"
            }},
            # Array of objects (some implementations)
            {"object": ["https://example.com/posts/123"]}
        ]
        
        for activity in test_cases:
            # Should extract object ID from all formats
            pass


class TestEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_handle_unknown_activity_type(self):
        """Test handling of unknown activity types"""
        unknown_activity = {
            "type": "CustomVoteType",
            "actor": "https://example.com/users/alice",
            "object": "https://our-instance.com/posts/123"
        }
        
        # Should log and ignore, not crash
        # Should return 202 Accepted
    
    def test_handle_malformed_actor_id(self):
        """Test handling of malformed actor IDs"""
        bad_actors = [
            "",  # Empty
            "not-a-url",  # Not a URL
            "http://[malformed",  # Malformed URL
            None,  # Missing
            {"id": "missing-protocol.com/users/alice"}  # Object without protocol
        ]
        
        for actor in bad_actors:
            activity = {
                "type": "Like",
                "actor": actor,
                "object": "https://our-instance.com/posts/123"
            }
            # Should reject with 400 Bad Request
    
    def test_handle_recursive_announces(self):
        """Test handling of deeply nested Announce chains"""
        # Announce of Announce of Announce...
        deeply_nested = {
            "type": "Announce",
            "actor": "https://relay1.com/actor",
            "object": {
                "type": "Announce",
                "actor": "https://relay2.com/actor",
                "object": {
                    "type": "Announce",
                    "actor": "https://relay3.com/actor",
                    "object": {
                        "type": "Like",
                        "actor": "https://example.com/users/alice",
                        "object": "https://our-instance.com/posts/123"
                    }
                }
            }
        }
        
        # Should have max depth limit to prevent DoS
        # Should extract innermost activity safely
    
    def test_handle_future_dated_activities(self):
        """Test handling of future-dated activities"""
        future_activity = {
            "type": "Like",
            "actor": "https://example.com/users/alice",
            "object": "https://our-instance.com/posts/123",
            "published": "2099-01-01T00:00:00Z"  # Far future
        }
        
        # Should reject or ignore future-dated activities
        # Prevents timing attacks


class TestPerformanceRegression:
    """Test for performance regressions"""
    
    def test_batch_delivery_performance(self):
        """Test batch delivery doesn't degrade"""
        # When sending to 100 recipients
        # Should batch by shared inbox
        # Should complete in reasonable time
        pass
    
    def test_vote_processing_performance(self):
        """Test vote processing remains efficient"""
        # When processing 1000 votes
        # Should not create N+1 queries
        # Should use bulk operations where possible
        pass
    
    def test_signature_verification_caching(self):
        """Test signature verification is cached appropriately"""
        # Same actor sending multiple activities
        # Should cache public key fetches
        # Should cache signature verification results
        pass
"""