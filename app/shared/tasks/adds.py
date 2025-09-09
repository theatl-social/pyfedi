from flask import current_app

from app import celery
from app.activitypub.signature import default_context, post_request, send_post_request
from app.models import Community, Post, User
from app.utils import get_task_session, gibberish, instance_banned, patch_db_session

""" JSON format
Add:
{
  'id':
  'type':
  'actor':
  'object':
  'target':     (featured_url or moderators_url)
  '@context':
  'audience':
  'to': []
  'cc': []
}
For Announce, remove @context from inner object, and use same fields except audience
"""


@celery.task
def sticky_post(send_async, user_id, post_id):
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                post = session.query(Post).filter_by(id=post_id).one()
                add_object(session, user_id, post)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


@celery.task
def add_mod(send_async, user_id, mod_id, community_id):
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                mod = session.query(User).filter_by(id=mod_id).one()
                add_object(session, user_id, mod, community_id)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def add_object(session, user_id, object, community_id=None):
    user = session.query(User).filter_by(id=user_id).one()
    if not community_id:
        community = object.community
    else:
        community = session.query(Community).filter_by(id=community_id).one()

    if community.local_only or not community.instance.online():
        return

    add_id = (
        f"https://{current_app.config['SERVER_NAME']}/activities/add/{gibberish(15)}"
    )
    to = ["https://www.w3.org/ns/activitystreams#Public"]
    cc = [community.public_url()]
    add = {
        "id": add_id,
        "type": "Add",
        "actor": user.public_url(),
        "object": object.public_url(),
        "target": (
            community.ap_moderators_url if community_id else community.ap_featured_url
        ),
        "@context": default_context(),
        "audience": community.public_url(),
        "to": to,
        "cc": cc,
    }

    if community.is_local():
        del add["@context"]

        announce_id = f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}"
        actor = community.public_url()
        cc = [community.ap_followers_url]
        announce = {
            "id": announce_id,
            "type": "Announce",
            "actor": actor,
            "object": add,
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
        send_post_request(
            community.ap_inbox_url,
            add,
            user.private_key,
            user.public_url() + "#main-key",
        )
