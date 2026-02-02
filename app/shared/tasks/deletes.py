from app import celery, db
from app.activitypub.signature import default_context, send_post_request
from app.constants import NOTIF_REPORT, NOTIF_REPORT_ESCALATION
from app.models import (
    Community,
    Instance,
    Post,
    PostReply,
    User,
    UserFollower,
    File,
    Notification,
    ChatMessage,
)
from app.utils import gibberish, instance_banned, get_task_session, patch_db_session

from flask import current_app
from sqlalchemy import Integer


""" JSON format
Delete:
{
  'id':
  'type':
  'actor':
  'object':
  'summary':    (if deleted by mod / admin)
  '@context':
  'audience':
  'to': []
  'cc': []
}
For Announce, remove @context from inner object, and use same fields except audience
"""


@celery.task
def delete_reply(send_async, user_id, reply_id, reason=None):
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                reply = session.query(PostReply).filter_by(id=reply_id).one()
                delete_object(user_id, reply, reason=reason, session=session)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


@celery.task
def restore_reply(send_async, user_id, reply_id, reason=None):
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                reply = session.query(PostReply).filter_by(id=reply_id).one()
                delete_object(
                    user_id, reply, is_restore=True, reason=reason, session=session
                )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


@celery.task
def delete_post(send_async, user_id, post_id, reason=None):
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                post = session.query(Post).get(post_id)
                delete_object(
                    user_id, post, is_post=True, reason=reason, session=session
                )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


@celery.task
def restore_post(send_async, user_id, post_id, reason=None):
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                post = session.query(Post).get(post_id)
                delete_object(
                    user_id,
                    post,
                    is_post=True,
                    is_restore=True,
                    reason=reason,
                    session=session,
                )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


@celery.task
def delete_community(send_async, user_id, community_id):
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                community = session.query(Community).filter_by(id=community_id).one()
                delete_object(user_id, community, session=session)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


@celery.task
def restore_community(send_async, user_id, community_id):
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                community = session.query(Community).filter_by(id=community_id).one()
                delete_object(user_id, community, is_restore=True, session=session)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def delete_object(
    user_id, object, is_post=False, is_restore=False, reason=None, session=None
):
    user = session.query(User).get(user_id)
    if isinstance(object, Community):
        community = object
    else:
        community = object.community

    # local_only communities can also be used to send activity to User Followers (only applies to posts, not comments)
    # return now though, if there aren't any
    if not is_post and community.local_only:
        return
    followers = session.query(UserFollower).filter_by(local_user_id=user.id).all()
    if not followers and community.local_only:
        return

    if not community.instance.online():
        return

    # commented out because surely we still want to be able to delete stuff in banned/blocked places?
    # banned = CommunityBan.query.filter_by(user_id=user_id, community_id=community.id).first()
    # if banned:
    #    return
    # if not community.is_local():
    #    if user.has_blocked_instance(community.instance.id) or instance_banned(community.instance.domain):
    #        return

    delete_id = f"{current_app.config['SERVER_URL']}/activities/delete/{gibberish(15)}"
    to = ["https://www.w3.org/ns/activitystreams#Public"]
    cc = [community.public_url()]
    delete = {
        "id": delete_id,
        "type": "Delete",
        "actor": user.public_url(),
        "object": object.public_url(),
        "@context": default_context(),
        "audience": community.public_url(),
        "to": to,
        "cc": cc,
    }
    if reason:
        delete["summary"] = reason

    if is_restore:
        del delete["@context"]
        undo_id = f"{current_app.config['SERVER_URL']}/activities/undo/{gibberish(15)}"
        undo = {
            "id": undo_id,
            "type": "Undo",
            "actor": user.public_url(),
            "object": delete,
            "@context": default_context(),
            "audience": community.public_url(),
            "to": to,
            "cc": cc,
        }

    domains_sent_to = []

    if community.is_local():
        if is_restore:
            del undo["@context"]
            object_json = undo
        else:
            del delete["@context"]
            object_json = delete

        announce_id = (
            f"{current_app.config['SERVER_URL']}/activities/announce/{gibberish(15)}"
        )
        actor = community.public_url()
        cc = [community.ap_followers_url]
        announce = {
            "id": announce_id,
            "type": "Announce",
            "actor": actor,
            "object": object_json,
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
                domains_sent_to.append(instance.domain)
    else:
        payload = undo if is_restore else delete
        send_post_request(
            community.ap_inbox_url,
            payload,
            user.private_key,
            user.public_url() + "#main-key",
        )
        domains_sent_to.append(community.instance.domain)

    if reason:
        return

    if is_post and followers:
        payload = undo if is_restore else delete
        for follower in followers:
            user_details = session.query(User).get(follower.remote_user_id)
            if user_details:
                payload["cc"].append(user_details.public_url())
        instances = (
            session.query(Instance)
            .join(User, User.instance_id == Instance.id)
            .join(UserFollower, UserFollower.remote_user_id == User.id)
        )
        instances = instances.filter(UserFollower.local_user_id == user.id).filter(
            Instance.gone_forever == False
        )
        for instance in instances:
            if instance.domain not in domains_sent_to:
                send_post_request(
                    instance.inbox,
                    payload,
                    user.private_key,
                    user.public_url() + "#main-key",
                )

    # remove any notifications about deleted posts
    if is_post:
        notifs = session.query(Notification).filter(
            Notification.targets.op("->>")("post_id").cast(Integer) == object.id
        )
        for notif in notifs:
            # dont delete report notifs
            if (
                notif.notif_type == NOTIF_REPORT
                or notif.notif_type == NOTIF_REPORT_ESCALATION
            ):
                continue
            session.delete(notif)
        session.commit()


@celery.task
def delete_posts_with_blocked_images(post_ids, user_id, send_async):
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                for post_id in post_ids:
                    post = session.query(Post).get(post_id)
                    if post:
                        if post.url:
                            post.calculate_cross_posts(delete_only=True)
                        post.deleted = True
                        post.deleted_by = user_id
                        post.author.post_count -= 1
                        post.community.post_count -= 1
                        if post.image_id:
                            file = session.query(File).get(post.image_id)
                            file.delete_from_disk()
                        session.commit()

                        delete_object(
                            user_id, post, is_post=True, reason="Contains blocked image"
                        )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


# deleting PMs will get a new function: I can't be bothered reworking delete_object to remove community logic for such an obscure activity
@celery.task
def delete_pm(send_async, message_id):
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                message = session.query(ChatMessage).filter_by(id=message_id).one()
                recipient = session.query(User).filter_by(id=message.recipient_id).one()
                delete_message(message, recipient)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


@celery.task
def restore_pm(send_async, message_id):
    with current_app.app_context():
        session = get_task_session()
        try:
            with patch_db_session(session):
                message = session.query(ChatMessage).filter_by(id=message_id).one()
                recipient = session.query(User).filter_by(id=message.recipient_id).one()
                delete_message(message, recipient, is_restore=True)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def delete_message(message, recipient, is_restore=False):
    if recipient.is_local():
        return

    delete_id = f"{current_app.config['SERVER_URL']}/activities/delete/{gibberish(15)}"
    delete = {
        "id": delete_id,
        "type": "Delete",
        "actor": message.sender.public_url(),
        "object": message.ap_id,
        "@context": default_context(),
        "to": recipient.public_url(),
    }

    if is_restore:
        del delete["@context"]
        undo_id = f"{current_app.config['SERVER_URL']}/activities/undo/{gibberish(15)}"
        undo = {
            "id": undo_id,
            "type": "Undo",
            "actor": message.sender.public_url(),
            "object": delete,
            "@context": default_context(),
            "to": recipient.public_url(),
        }

    payload = undo if is_restore else delete
    send_post_request(
        recipient.ap_inbox_url,
        payload,
        message.sender.private_key,
        message.sender.public_url() + "#main-key",
    )
