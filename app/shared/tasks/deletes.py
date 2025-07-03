from app import celery, db
from app.activitypub.signature import default_context, send_post_request
from app.models import Community, Instance, Post, PostReply, User, UserFollower, File
from app.utils import gibberish, instance_banned

from flask import current_app


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
    reply = PostReply.query.filter_by(id=reply_id).one()
    delete_object(user_id, reply, reason=reason)


@celery.task
def restore_reply(send_async, user_id, reply_id, reason=None):
    reply = PostReply.query.filter_by(id=reply_id).one()
    delete_object(user_id, reply, is_restore=True, reason=reason)


@celery.task
def delete_post(send_async, user_id, post_id, reason=None):
    post = Post.query.filter_by(id=post_id).one()
    delete_object(user_id, post, is_post=True, reason=reason)


@celery.task
def restore_post(send_async, user_id, post_id, reason=None):
    post = Post.query.filter_by(id=post_id).one()
    delete_object(user_id, post, is_post=True, is_restore=True, reason=reason)


@celery.task
def delete_community(send_async, user_id, community_id):
    community = Community.query.filter_by(id=community_id).one()
    delete_object(user_id, community)


@celery.task
def restore_community(send_async, user_id, community_id):
    community = Community.query.filter_by(id=community_id).one()
    delete_object(user_id, community, is_restore=True)


def delete_object(user_id, object, is_post=False, is_restore=False, reason=None):
    user = User.query.filter_by(id=user_id).one()
    if isinstance(object, Community):
        community = object
    else:
        community = object.community

    # local_only communities can also be used to send activity to User Followers (only applies to posts, not comments)
    # return now though, if there aren't any
    if not is_post and community.local_only:
        return
    followers = UserFollower.query.filter_by(local_user_id=user.id).all()
    if not followers and community.local_only:
        return

    if not community.instance.online():
        return

    # commented out because surely we still want to be able to delete stuff in banned/blocked places?
    #banned = CommunityBan.query.filter_by(user_id=user_id, community_id=community.id).first()
    #if banned:
    #    return
    #if not community.is_local():
    #    if user.has_blocked_instance(community.instance.id) or instance_banned(community.instance.domain):
    #        return

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
    if reason:
        delete['summary'] = reason

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

    domains_sent_to = []

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
                send_post_request(instance.inbox, announce, community.private_key, community.public_url() + '#main-key')
                domains_sent_to.append(instance.domain)
    else:
        payload = undo if is_restore else delete
        send_post_request(community.ap_inbox_url, payload, user.private_key, user.public_url() + '#main-key')
        domains_sent_to.append(community.instance.domain)

    if reason:
        return

    if is_post and followers:
        payload = undo if is_restore else delete
        for follower in followers:
            user_details = User.query.get(follower.remote_user_id)
            if user_details:
                payload['cc'].append(user_details.public_url())
        instances = Instance.query.join(User, User.instance_id == Instance.id).join(UserFollower, UserFollower.remote_user_id == User.id)
        instances = instances.filter(UserFollower.local_user_id == user.id).filter(Instance.gone_forever == False)
        for instance in instances:
            if instance.domain not in domains_sent_to:
                send_post_request(instance.inbox, payload, user.private_key, user.public_url() + '#main-key')


@celery.task
def delete_posts_with_blocked_images(post_ids, user_id, send_async):
    try:
        for post_id in post_ids:
            post = Post.query.get(post_id)
            if post:
                if post.url:
                    post.calculate_cross_posts(delete_only=True)
                post.deleted = True
                post.deleted_by = user_id
                post.author.post_count -= 1
                post.community.post_count -= 1
                if post.image_id:
                    file = File.query.get(post.image_id)
                    file.delete_from_disk()
                db.session.commit()

            delete_object(user_id, post, is_post=True, reason='Contains blocked image')
    except Exception:
        db.session.rollback()
        raise
    finally:
        db.session.remove()
