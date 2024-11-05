from app import celery
from app.activitypub.signature import default_context, post_request
from app.models import CommunityBan, PostReply, User
from app.utils import gibberish, instance_banned

from flask import current_app


""" JSON format
Delete:
{
  'id':
  'type':
  'actor':
  'object':
  '@context':
  'audience':
  'to': []
  'cc': []
}
For Announce, remove @context from inner object, and use same fields except audience
"""


@celery.task
def delete_reply(send_async, user_id, reply_id):
    reply = PostReply.query.filter_by(id=reply_id).one()
    delete_object(user_id, reply)


@celery.task
def restore_reply(send_async, user_id, reply_id):
    reply = PostReply.query.filter_by(id=reply_id).one()
    delete_object(user_id, reply, is_restore=True)


def delete_object(user_id, object, is_restore=False):
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

    delete_id = f"https://{current_app.config['SERVER_NAME']}/activities/delete/{gibberish(15)}"
    to = ["https://www.w3.org/ns/activitystreams#Public"]
    cc = [community.public_url()]
    delete = {
      'id': delete_id,
      'type': 'Delete',
      'actor': user.public_url(),
      'object': object.public_url(),
      '@context': default_context(),
      'audience': community.public_url(),
      'to': to,
      'cc': cc
    }

    if is_restore:
        del delete['@context']
        undo_id = f"https://{current_app.config['SERVER_NAME']}/activities/undo/{gibberish(15)}"
        undo = {
          'id': undo_id,
          'type': 'Undo',
          'actor': user.public_url(),
          'object': delete,
          '@context': default_context(),
          'audience': community.public_url(),
          'to': to,
          'cc': cc
        }

    if community.is_local():
        if is_restore:
            del undo['@context']
            object=undo
        else:
            del delete['@context']
            object=delete

        announce_id = f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}"
        actor = community.public_url()
        cc = [community.ap_followers_url]
        announce = {
          'id': announce_id,
          'type': 'Announce',
          'actor': actor,
          'object': object,
          '@context': default_context(),
          'to': to,
          'cc': cc
        }
        for instance in community.following_instances():
            if instance.inbox and instance.online() and not user.has_blocked_instance(instance.id) and not instance_banned(instance.domain):
               post_request(instance.inbox, announce, community.private_key, community.public_url() + '#main-key')
    else:
        payload = undo if is_restore else delete
        post_request(community.ap_inbox_url, payload, user.private_key, user.public_url() + '#main-key')


