from app import celery
from app.activitypub.signature import default_context, send_post_request
from app.models import Post, User, Community
from app.utils import gibberish, instance_banned, get_task_session, patch_db_session

from flask import current_app


""" JSON format
Move:
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
def move_post(send_async, user_id, old_community_id, new_community_id, post_id):
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                post = session.query(Post).get(post_id)
                if post and not post.deleted:
                    new_community = session.query(Community).get(new_community_id)
                    old_community = session.query(Community).get(old_community_id)
                    move_object(session, user_id, post, origin=old_community, target=new_community)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def move_object(session, user_id, object, origin, target):
    user = session.query(User).get(user_id)

    if isinstance(origin, Community) and isinstance(target, Community):
        community = origin
    else:
        raise Exception('Unsupported origin or target')

    if community.local_only or not community.instance.online():
        return

    move_id = f"https://{current_app.config['SERVER_NAME']}/activities/move/{gibberish(15)}"
    to = ["https://www.w3.org/ns/activitystreams#Public"]
    cc = [community.public_url()]
    move = {
      'id': move_id,
      'type': 'Move',
      'actor': user.public_url(),
      'object': object.public_url(),
      '@context': default_context(),
      'origin': origin.public_url(),
      'target': target.public_url(),
      'to': to,
      'cc': cc
    }

    if community.is_local():
        del move['@context']

        announce_id = f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}"
        actor = community.public_url()
        cc = [community.ap_followers_url]
        announce = {
          'id': announce_id,
          'type': 'Announce',
          'actor': actor,
          'object': move,
          '@context': default_context(),
          'to': to,
          'cc': cc
        }
        for instance in community.following_instances():
            if instance.inbox and instance.online() and not user.has_blocked_instance(instance.id) and not instance_banned(instance.domain):
                send_post_request(instance.inbox, announce, community.private_key, community.public_url() + '#main-key')
    else:
        send_post_request(community.ap_inbox_url, move, user.private_key, user.public_url() + '#main-key')
