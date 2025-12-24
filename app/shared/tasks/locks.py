from app import celery
from app.activitypub.signature import default_context, send_post_request
from app.models import Post, User, PostReply
from app.utils import gibberish, instance_banned, get_task_session, patch_db_session

from flask import current_app


""" JSON format
Lock:
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
def lock_post(send_async, user_id, post_id):
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                post = session.query(Post).filter_by(id=post_id).one()
                lock_object(session, user_id, post)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


@celery.task
def unlock_post(send_async, user_id, post_id):
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                post = session.query(Post).filter_by(id=post_id).one()
                lock_object(session, user_id, post, is_undo=True)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


@celery.task
def lock_post_reply(send_async, user_id, post_reply_id):
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                post = session.query(PostReply).filter_by(id=post_reply_id).one()
                lock_object(session, user_id, post)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


@celery.task
def unlock_post_reply(send_async, user_id, post_reply_id):
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                post = session.query(PostReply).filter_by(id=post_reply_id).one()
                lock_object(session, user_id, post, is_undo=True)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def lock_object(session, user_id, object, is_undo=False):
    user = session.query(User).get(user_id)
    community = object.community

    if community.local_only or not community.instance.online():
        return

    lock_id = (
        f"https://{current_app.config['SERVER_NAME']}/activities/lock/{gibberish(15)}"
    )
    to = ["https://www.w3.org/ns/activitystreams#Public"]
    cc = [community.public_url()]
    lock = {
        "id": lock_id,
        "type": "Lock",
        "actor": user.public_url(),
        "object": object.public_url(),
        "@context": default_context(),
        "audience": community.public_url(),
        "to": to,
        "cc": cc,
    }

    if is_undo:
        del lock["@context"]
        undo_id = f"https://{current_app.config['SERVER_NAME']}/activities/undo/{gibberish(15)}"
        undo = {
            "id": undo_id,
            "type": "Undo",
            "actor": user.public_url(),
            "object": lock,
            "@context": default_context(),
            "audience": community.public_url(),
            "to": to,
            "cc": cc,
        }

    if community.is_local():
        if is_undo:
            del undo["@context"]
            object = undo
        else:
            del lock["@context"]
            object = lock

        announce_id = f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}"
        actor = community.public_url()
        cc = [community.ap_followers_url]
        announce = {
            "id": announce_id,
            "type": "Announce",
            "actor": actor,
            "object": object,
            "@context": default_context(),
            "to": to,
            "cc": cc,
        }
        for instance in community.following_instances():
            if (
                instance.inbox
                and instance.online()
                and not user.has_blocked_instance(instance.id)
                and not instance_banned(instance.domain)
            ):
                send_post_request(
                    instance.inbox,
                    announce,
                    community.private_key,
                    community.public_url() + "#main-key",
                )
    else:
        payload = undo if is_undo else lock
        send_post_request(
            community.ap_inbox_url,
            payload,
            user.private_key,
            user.public_url() + "#main-key",
        )
