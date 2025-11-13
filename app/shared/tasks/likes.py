from app import celery
from app.activitypub.signature import default_context, send_post_request, HttpSignature
from app.models import CommunityBan, Post, PostReply, User, ActivityBatch, Community
from app.utils import gibberish, instance_banned, get_task_session, patch_db_session

from flask import current_app, json

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
    with current_app.app_context():
        session = get_task_session()
        with patch_db_session(session):
            post = session.query(Post).filter_by(id=post_id).one()
            if federate:
                send_vote(user_id, post, vote_to_undo, vote_direction)


@celery.task
def vote_for_reply(send_async, user_id, reply_id, vote_to_undo, vote_direction, federate: bool=True):
    with current_app.app_context():
        session = get_task_session()
        with patch_db_session(session):
            reply = session.query(PostReply).filter_by(id=reply_id).one()
            if federate:
                send_vote(user_id, reply, vote_to_undo, vote_direction)


def send_vote(user_id, object, vote_to_undo, vote_direction):
    session = get_task_session()
    try:
        user = session.query(User).filter_by(id=user_id).one()
        community = object.community
        if community.local_only or not community.instance.online():
            return

        banned = session.query(CommunityBan).filter_by(user_id=user_id, community_id=community.id).first()
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
            # Select the appropriate payload
            if vote_to_undo:
                payload_copy = undo_public.copy()
            else:
                payload_copy = vote_public.copy()

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

            send_async = []

            # For local communities, we need to sends announcements to each instance
            for instance in community.following_instances():
                if not (instance.inbox and instance.online() and
                       not user.has_blocked_instance(instance.id) and
                       not instance_banned(instance.domain)):
                    continue

                if instance.software == 'piefed':  # Send in a batch later
                    session.add(ActivityBatch(instance_id=instance.id, community_id=community.id, payload=payload_copy))
                    session.commit()
                else:
                    if current_app.config['NOTIF_SERVER']:   # Votes make up a very high percentage of activities, so it is more efficient to send them via fastapi_server.py. However fastapi_server.py does not retry failed sends. For votes this is acceptable.
                        send_async.append(HttpSignature.signed_request(instance.inbox, announce,
                                                                       community.private_key,
                                                                       community.public_url() + '#main-key',
                                                                       send_via_async=True))
                    else:
                        # Send the announcement directly
                        send_post_request(instance.inbox, announce, community.private_key, community.public_url() + '#main-key')

            if len(send_async):
                from app import redis_client
                # send announce_activity via redis pub/sub to piefed_notifs service
                redis_client.publish("http_posts:activity", json.dumps({'urls': [url[0] for url in send_async],
                                                                        'headers': [url[1] for url in send_async],
                                                                        'data': send_async[0][2].decode('utf-8')}))
        else:
            # For remote communities, select appropriate payload
            if vote_to_undo:
                payload = undo_public
            else:
                payload = vote_public

            send_post_request(community.ap_inbox_url, payload, user.private_key, public_actor + '#main-key')
    except:
        session.rollback()
        raise
    finally:
        session.close()


@celery.task
def rate_community(user_id, community_id, rating):
    session = get_task_session()
    try:
        user = session.query(User).get(user_id)
        community = session.query(Community).get(community_id)
        if community.local_only or not community.instance.online():
            return

        banned = session.query(CommunityBan).filter_by(user_id=user_id, community_id=community.id).first()
        if banned:
            return
        if not community.is_local():
            if user.has_blocked_instance(community.instance.id) or instance_banned(community.instance.domain):
                return

        type = 'Rate'
        rate_id = f"https://{current_app.config['SERVER_NAME']}/activities/{type.lower()}/{gibberish(15)}"

        # public actor URL
        public_actor = user.public_url()

        # Vote payload
        payload = {
            'id': rate_id,
            'type': type,
            'actor': public_actor,
            'object': community.public_url(),
            'rating': rating,
            '@context': default_context(),
            'audience': community.public_url()
        }

        if community.is_local():
            # Select the appropriate payload

            # Remove context for inner object
            del payload['@context']

            # Create announcement with the selected payload
            announce_id = f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}"
            actor = community.public_url()
            to = ["https://www.w3.org/ns/activitystreams#Public"]
            cc = [community.ap_followers_url]
            announce = {
                'id': announce_id,
                'type': 'Announce',
                'actor': actor,
                'object': payload,
                '@context': default_context(),
                'to': to,
                'cc': cc
            }

            # For local communities, we need to sends announcements to each instance
            for instance in community.following_instances():
                if not (instance.inbox and instance.online() and
                        not user.has_blocked_instance(instance.id) and
                        not instance_banned(instance.domain)):
                    continue

                send_post_request(instance.inbox, announce, community.private_key, community.public_url() + '#main-key')
        else:
            send_post_request(community.ap_inbox_url, payload, user.private_key, public_actor + '#main-key')
    except:
        session.rollback()
        raise
    finally:
        session.close()
