from app import celery
from app.activitypub.signature import default_context, post_request, send_post_request
from app.models import CommunityBan, Post, PostReply, User
from app.utils import gibberish, instance_banned

from flask import current_app


""" JSON format
Flag:
{
  'id':
  'type':
  'actor':
  'object':
  '@context':
  'audience':
  'to': []
  'summary':
}
"""


@celery.task
def report_reply(send_async, user_id, reply_id, summary):
    reply = PostReply.query.filter_by(id=reply_id).one()
    report_object(user_id, reply, summary)


@celery.task
def report_post(send_async, user_id, post_id, summary):
    post = Post.query.filter_by(id=post_id).one()
    report_object(user_id, post, summary)


def report_object(user_id, object, summary):
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

    flag_id = f"https://{current_app.config['SERVER_NAME']}/activities/flag/{gibberish(15)}"
    to = [community.public_url()]
    flag = {
      'id': flag_id,
      'type': 'Flag',
      'actor': user.public_url(),
      'object': object.public_url(),
      '@context': default_context(),
      'audience': community.public_url(),
      'to': to,
      'summary': summary
    }

    send_post_request(community.ap_inbox_url, flag, user.private_key, user.public_url() + '#main-key')


