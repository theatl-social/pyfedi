from flask import current_app

from app import celery
from app.activitypub.signature import default_context, post_request, send_post_request
from app.models import CommunityBan, Post, PostReply, User
from app.utils import get_task_session, gibberish, instance_banned, patch_db_session

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
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                reply = session.query(PostReply).filter_by(id=reply_id).one()
                report_object(session, user_id, reply, summary)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


@celery.task
def report_post(send_async, user_id, post_id, summary):
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                post = session.query(Post).filter_by(id=post_id).one()
                report_object(session, user_id, post, summary)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def report_object(session, user_id, object, summary):
    user = session.query(User).filter_by(id=user_id).one()
    community = object.community
    if community.local_only or not community.instance.online():
        return

    banned = (
        session.query(CommunityBan)
        .filter_by(user_id=user_id, community_id=community.id)
        .first()
    )
    if banned:
        return
    if not community.is_local():
        if user.has_blocked_instance(community.instance.id) or instance_banned(
            community.instance.domain
        ):
            return

    flag_id = (
        f"https://{current_app.config['SERVER_NAME']}/activities/flag/{gibberish(15)}"
    )
    to = [community.public_url()]
    flag = {
        "id": flag_id,
        "type": "Flag",
        "actor": user.public_url(),
        "object": object.public_url(),
        "@context": default_context(),
        "audience": community.public_url(),
        "to": to,
        "summary": summary,
    }

    send_post_request(
        community.ap_inbox_url, flag, user.private_key, user.public_url() + "#main-key"
    )
