from app import celery
from app.activitypub.signature import default_context, send_post_request
from app.models import Post, PostReply, User, Instance
from app.utils import gibberish, get_task_session, patch_db_session

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
def report_reply(send_async, user_id, reply_id, summary, instance_ids):
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                reply = session.query(PostReply).filter_by(id=reply_id).one()
                report_object(session, user_id, reply, summary, instance_ids)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


@celery.task
def report_post(send_async, user_id, post_id, summary, instance_ids):
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                post = session.query(Post).filter_by(id=post_id).one()
                report_object(session, user_id, post, summary, instance_ids)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def report_object(session, user_id, object, summary, instance_ids):
    user = session.query(User).filter_by(id=user_id).one()
    community = object.community
    if community.local_only or not community.instance.online():
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

    instances = session.query(Instance).filter(Instance.id.in_(instance_ids))
    for instance in instances:
        if instance.inbox is not None:
            send_post_request(instance.inbox, flag, user.private_key, user.public_url() + '#main-key')


