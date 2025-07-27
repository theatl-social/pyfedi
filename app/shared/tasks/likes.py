from app import cache, celery
from app.activitypub.signature import default_context, post_request, send_post_request
from app.models import CommunityBan, Post, PostReply, User, ActivityBatch
from app.utils import gibberish, instance_banned, recently_upvoted_posts, recently_downvoted_posts, \
    recently_upvoted_post_replies, recently_downvoted_post_replies, get_task_session

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
def vote_for_post(send_async, user_id, post_id, vote_to_undo, vote_direction, federate: bool=True):
    print(f'CELERY: vote_for_post task STARTED in worker: user_id={user_id}, post_id={post_id}, federate={federate}')
    current_app.logger.info(f'vote_for_post task called: user_id={user_id}, post_id={post_id}, federate={federate}, send_async={send_async}')
    post = Post.query.filter_by(id=post_id).one()
    cache.delete_memoized(recently_upvoted_posts, user_id)
    cache.delete_memoized(recently_downvoted_posts, user_id)
    if federate:
        current_app.logger.info(f'vote_for_post: federate=True, calling send_vote')
        send_vote(user_id, post, vote_to_undo, vote_direction)
    else:
        current_app.logger.info(f'vote_for_post: federate=False, NOT calling send_vote')


@celery.task
def vote_for_reply(send_async, user_id, reply_id, vote_to_undo, vote_direction, federate: bool=True):
    reply = PostReply.query.filter_by(id=reply_id).one()
    cache.delete_memoized(recently_upvoted_post_replies, user_id)
    cache.delete_memoized(recently_downvoted_post_replies, user_id)
    if federate:
        send_vote(user_id, reply, vote_to_undo, vote_direction)


def send_vote(user_id, object, vote_to_undo, vote_direction):
    session = get_task_session()
    try:
        current_app.logger.info(f'send_vote called: user_id={user_id}, object_id={object.id}, vote_direction={vote_direction}, vote_to_undo={vote_to_undo}')
        user = session.query(User).filter_by(id=user_id).one()
        community = object.community
        current_app.logger.info(f'send_vote: community={community.name}, is_local={community.is_local()}, local_only={community.local_only}')
        if community.local_only or not community.instance.online():
            current_app.logger.info(f'send_vote: returning early - local_only={community.local_only}, instance.online={community.instance.online() if community.instance else "N/A"}')
            return

        banned = session.query(CommunityBan).filter_by(user_id=user_id, community_id=community.id).first()
        if banned:
            current_app.logger.info(f'send_vote: user {user_id} is banned from community {community.id}')
            return
        if not community.is_local():
            if user.has_blocked_instance(community.instance.id) or instance_banned(community.instance.domain):
                current_app.logger.info(f'send_vote: instance blocked or banned')
                return

        if vote_to_undo:
            type = vote_to_undo
        else:
            type = 'Like' if vote_direction == 'upvote' else 'Dislike'
        vote_id = f"https://{current_app.config['SERVER_NAME']}/activities/{type.lower()}/{gibberish(15)}"

        # public actor URL
        public_actor = user.public_url()

        # Vote payload
        vote_public = {
          'id': vote_id,
          'type': type,
          'actor': public_actor,
          'object': object.public_url(),
          '@context': default_context(),
          'audience': community.public_url()
        }

        # Create undo
        if vote_to_undo:
            undo_id = f"https://{current_app.config['SERVER_NAME']}/activities/undo/{gibberish(15)}"

            # Undo payload
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

        if community.is_local():
            # For local communities, we need to create announcements for each instance
            for instance in community.following_instances():
                if not (instance.inbox and instance.online() and
                       not user.has_blocked_instance(instance.id) and
                       not instance_banned(instance.domain)):
                    continue

                # Select the appropriate payload
                if vote_to_undo:
                    payload_copy = undo_public.copy()
                else:
                    payload_copy = vote_public.copy()

                # Remove context for inner object
                del payload_copy['@context']

                if current_app.config['FEP_AWESOME'] and instance.software == 'piefed':  # Send in a batch later
                    session.add(ActivityBatch(instance_id=instance.id, community_id=community.id, payload=payload_copy))
                    session.commit()
                else:
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
            # For remote communities, select appropriate payload
            current_app.logger.info(f'send_vote: sending to remote community {community.name} at {community.ap_inbox_url}')
            if vote_to_undo:
                payload = undo_public
            else:
                payload = vote_public

            current_app.logger.info(f'send_vote: calling send_post_request with payload type={payload.get("type")}')
            send_post_request(community.ap_inbox_url, payload, user.private_key, public_actor + '#main-key')
    except:
        session.rollback()
        raise
    finally:
        session.close()
