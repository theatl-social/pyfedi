from app import cache, celery
from app.activitypub.signature import default_context, post_request, send_post_request
from app.models import CommunityBan, Post, PostReply, User
from app.utils import gibberish, instance_banned, recently_upvoted_posts, recently_downvoted_posts, recently_upvoted_post_replies, recently_downvoted_post_replies

from flask import current_app


""" JSON format
{
  'id':
  'type':
  'actor':
  'object':
  '@context':   (outer object only)
  'audience':   (inner object only)
  'to': []      (announce only)
  'cc': []      (announce only)
}
"""

@celery.task
def vote_for_post(send_async, user_id, post_id, vote_to_undo, vote_direction):
    post = Post.query.filter_by(id=post_id).one()
    cache.delete_memoized(recently_upvoted_posts, user_id)
    cache.delete_memoized(recently_downvoted_posts, user_id)
    send_vote(user_id, post, vote_to_undo, vote_direction)


@celery.task
def vote_for_reply(send_async, user_id, reply_id, vote_to_undo, vote_direction):
    reply = PostReply.query.filter_by(id=reply_id).one()
    cache.delete_memoized(recently_upvoted_post_replies, user_id)
    cache.delete_memoized(recently_downvoted_post_replies, user_id)
    send_vote(user_id, reply, vote_to_undo, vote_direction)


def send_vote(user_id, object, vote_to_undo, vote_direction):
    user = User.query.filter_by(id=user_id).one()
    community = object.community
    if community.local_only or not community.instance.online():
        return

    banned = CommunityBan.query.filter_by(user_id=user_id, community_id=community.id).first()
    if banned:
        return
    if not community.is_local():
        if user.has_blocked_instance(community.instance.id) or instance_banned(community.instance.domain):
            return

    if vote_to_undo:
        type = vote_to_undo
    else:
        type = 'Like' if vote_direction == 'upvote' else 'Dislike'
    vote_id = f"https://{current_app.config['SERVER_NAME']}/activities/{type.lower()}/{gibberish(15)}"
    
    # Create both public and private actor URLs
    public_actor = user.public_url(True)  # Public vote
    private_actor = user.public_url(False)  # Private vote
    
    # Create both public and private versions of votes
    vote_public = {
      'id': vote_id,
      'type': type,
      'actor': public_actor,
      'object': object.public_url(),
      '@context': default_context(),
      'audience': community.public_url()
    }
    
    vote_private = {
      'id': vote_id,
      'type': type,
      'actor': private_actor,
      'object': object.public_url(),
      '@context': default_context(),
      'audience': community.public_url()
    }

    # Create both public and private versions of undo
    if vote_to_undo:
        undo_id = f"https://{current_app.config['SERVER_NAME']}/activities/undo/{gibberish(15)}"
        
        # Public undo (with public vote)
        vote_public_copy = vote_public.copy()
        del vote_public_copy['@context']
        undo_public = {
          'id': undo_id,
          'type': 'Undo',
          'actor': public_actor,
          'object': vote_public_copy,
          '@context': default_context(),
          'audience': community.public_url()
        }
        
        # Private undo (with private vote)
        vote_private_copy = vote_private.copy()
        del vote_private_copy['@context']
        undo_private = {
          'id': undo_id,
          'type': 'Undo',
          'actor': private_actor,
          'object': vote_private_copy,
          '@context': default_context(),
          'audience': community.public_url()
        }

    if community.is_local():
        # For local communities, we need to create announcements for each instance
        # with the appropriate privacy level
        for instance in community.following_instances():
            if not (instance.inbox and instance.online() and 
                   not user.has_blocked_instance(instance.id) and 
                   not instance_banned(instance.domain)):
                continue
                
            # Determine if we need a private vote for this instance
            use_private = instance.votes_are_public() and user.vote_privately()
            
            # Select the appropriate payload based on privacy
            if vote_to_undo:
                payload_copy = undo_private.copy() if use_private else undo_public.copy()
            else:
                payload_copy = vote_private.copy() if use_private else vote_public.copy()
            
            # Remove context for inner object
            del payload_copy['@context']
            
            # Create announcement with the selected payload
            announce_id = f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}"
            actor = community.public_url()
            to = ["https://www.w3.org/ns/activitystreams#Public"]
            cc = [community.ap_followers_url]
            announce = {
              'id': announce_id,
              'type': 'Announce',
              'actor': actor,
              'object': payload_copy,
              '@context': default_context(),
              'to': to,
              'cc': cc
            }
            
            # Send the announcement
            send_post_request(instance.inbox, announce, community.private_key, community.public_url() + '#main-key')
    else:
        # For remote communities, select appropriate payload based on privacy
        use_private = community.instance.votes_are_public() and user.vote_privately()
        
        if vote_to_undo:
            payload = undo_private if use_private else undo_public
        else:
            payload = vote_private if use_private else vote_public
        
        # Send with appropriate key ID
        key_id = (private_actor if use_private else public_actor) + '#main-key'
        send_post_request(community.ap_inbox_url, payload, user.private_key, key_id)


