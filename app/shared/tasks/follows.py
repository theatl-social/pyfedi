from app import cache, celery, db
from app.activitypub.signature import default_context, post_request
from app.models import Community, CommunityBan, CommunityJoinRequest, User
from app.utils import community_membership, gibberish, joined_communities, instance_banned

from flask import current_app, flash
from flask_babel import _


# would be in app/constants.py
SRC_WEB = 1
SRC_PUB = 2
SRC_API = 3
SRC_PLD = 4


""" JSON format
{
  'id':
  'type':
  'actor':
  'object':
  '@context':   (outer object only)
  'to': []
}
"""

"""
async:
    delete memoized
    add or delete community_join_request
    used for admin preload in production (return values are ignored)
    used for API
sync:
    add or delete community_member
    used for debug mode
    used for web users to provide feedback
"""


@celery.task
def join_community(send_async, user_id, community_id, src):
    user = User.query.filter_by(id=user_id).one()
    community = Community.query.filter_by(id=community_id).one()

    pre_load_message = {}
    banned = CommunityBan.query.filter_by(user_id=user_id, community_id=community_id).first()
    if banned:
        if not send_async:
            if src == SRC_WEB:
                flash(_('You cannot join this community'))
                return
            elif src == SRC_PLD:
                pre_load_message['user_banned'] = True
                return pre_load_message
            elif src == SRC_API:
                raise Exception('banned_from_community')
        return

    if (not community.is_local() and
        (user.has_blocked_instance(community.instance.id) or
         instance_banned(community.instance.domain))):
        if not send_async:
            if src == SRC_WEB:
                flash(_('Community is on banned or blocked instance'))
                return
            elif src == SRC_PLD:
                pre_load_message['community_on_banned_or_blocked_instance'] = True
                return pre_load_message
            elif src == SRC_API:
                raise Exception('community_on_banned_or_blocked_instance')
        return

    success = True
    if not community.is_local() and community.instance.online():
        join_request = CommunityJoinRequest(user_id=user_id, community_id=community_id)
        db.session.add(join_request)
        db.session.commit()

        follow_id = f"https://{current_app.config['SERVER_NAME']}/activities/follow/{join_request.id}"
        follow = {
          'id': follow_id,
          'type': 'Follow',
          'actor': user.public_url(),
          'object': community.public_url(),
          '@context': default_context(),
          'to': [community.public_url()],
        }
        success = post_request(community.ap_inbox_url, follow, user.private_key,
                               user.public_url() + '#main-key', timeout=10)
        if success is False or isinstance(success, str):
            if not send_async:
                db.session.query(CommunityJoinRequest).filter_by(user_id=user_id, community_id=community_id).delete()
                db.session.commit()

                if 'is not in allowlist' in success:
                    msg_to_user = f'{community.instance.domain} does not allow us to join their communities.'
                else:
                    msg_to_user = "There was a problem while trying to communicate with remote server. Please try again later."

                if src == SRC_WEB:
                    flash(_(msg_to_user), 'error')
                    return
                elif src == SRC_PLD:
                    pre_load_message['status'] = msg_to_user
                    return pre_load_message
                elif src == SRC_API:
                    raise Exception(msg_to_user)

    # for communities on local or offline instances, joining is instant
    if success is True:
        cache.delete_memoized(community_membership, user, community)
        cache.delete_memoized(joined_communities, user.id)

        if src == SRC_WEB:
            flash('You joined ' + community.title)
            return
        elif src == SRC_PLD:
            pre_load_message['status'] = 'joined'
            return pre_load_message

    return success


@celery.task
def leave_community(send_async, user_id, community_id):
    user = User.query.filter_by(id=user_id).one()
    community = Community.query.filter_by(id=community_id).one()

    cache.delete_memoized(community_membership, user, community)
    cache.delete_memoized(joined_communities, user.id)

    if community.is_local():
        return

    join_request = CommunityJoinRequest.query.filter_by(user_id=user_id, community_id=community_id).one()
    db.session.delete(join_request)
    db.session.commit()

    if (not community.instance.online() or
       user.has_blocked_instance(community.instance.id) or
       instance_banned(community.instance.domain)):
        return

    follow_id = f"https://{current_app.config['SERVER_NAME']}/activities/follow/{join_request.id}"
    follow = {
      'id': follow_id,
      'type': 'Follow',
      'actor': user.public_url(),
      'object': community.public_url(),
      'to': [community.public_url()]
    }
    undo_id = f"https://{current_app.config['SERVER_NAME']}/activities/undo/{gibberish(15)}"
    undo = {
      'id': undo_id,
      'type': 'Undo',
      'actor': user.public_url(),
      'object': follow,
      '@context': default_context(),
      'to': [community.public_url()]
    }

    post_request(community.ap_inbox_url, undo, user.private_key, user.public_url() + '#main-key', timeout=10)


