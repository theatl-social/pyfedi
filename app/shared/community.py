from app import db, cache
from app.activitypub.signature import post_request
from app.constants import *
from app.models import Community, CommunityBan, CommunityJoinRequest, CommunityMember
from app.utils import authorise_api_user, community_membership, joined_communities, gibberish

from flask import abort, current_app, flash
from flask_babel import _
from flask_login import current_user

# would be in app/constants.py
SRC_WEB = 1
SRC_PUB = 2
SRC_API = 3

# function can be shared between WEB and API (only API calls it for now)
# call from admin.federation not tested
def join_community(community_id: int, src, auth=None, user_id=None, main_user_name=True):
    if src == SRC_API:
        community = Community.query.get(community_id)
        if not community:
            raise Exception('community_not_found')
        try:
            user = authorise_api_user(auth, return_type='model')
        except:
            raise
    else:
        community = Community.query.get_or_404(community_id)
        if not user_id:
            user = current_user
        else:
            user = User.query.get(user_id)

    pre_load_message = {}
    if community_membership(user, community) != SUBSCRIPTION_MEMBER and community_membership(user, community) != SUBSCRIPTION_PENDING:
        banned = CommunityBan.query.filter_by(user_id=user.id, community_id=community.id).first()
        if banned:
            if src == SRC_API:
                raise Exception('banned_from_community')
            else:
                if main_user_name:
                    flash(_('You cannot join this community'))
                    return
                else:
                    pre_load_message['user_banned'] = True
                    return pre_load_message
    else:
        if src == SRC_API:
            return user.id
        else:
            if not main_user_name:
                pre_load_message['status'] = 'already subscribed, or subsciption pending'
                return pre_load_message

    success = True
    remote = not community.is_local()
    if remote:
        # send ActivityPub message to remote community, asking to follow. Accept message will be sent to our shared inbox
        join_request = CommunityJoinRequest(user_id=user.id, community_id=community.id)
        db.session.add(join_request)
        db.session.commit()
        if community.instance.online():
            follow = {
              "actor": user.public_url(main_user_name=main_user_name),
              "to": [community.public_url()],
              "object": community.public_url(),
              "type": "Follow",
              "id": f"https://{current_app.config['SERVER_NAME']}/activities/follow/{join_request.id}"
            }
            success = post_request(community.ap_inbox_url, follow, user.private_key,
                                    user.public_url(main_user_name=main_user_name) + '#main-key', timeout=10)
            if success is False or isinstance(success, str):
                if 'is not in allowlist' in success:
                    if src == SRC_API:
                        raise Exception('not_in_remote_instance_allowlist')
                    else:
                        msg_to_user = f'{community.instance.domain} does not allow us to join their communities.'
                        if main_user_name:
                            flash(_(msg_to_user), 'error')
                            return
                        else:
                            pre_load_message['status'] = msg_to_user
                            return pre_load_message
                else:
                    if src != SRC_API:
                        msg_to_user = "There was a problem while trying to communicate with remote server. If other people have already joined this community it won't matter."
                        if main_user_name:
                            flash(_(msg_to_user), 'error')
                            return
                        else:
                            pre_load_message['status'] = msg_to_user
                            return pre_load_message

    # for local communities, joining is instant
    member = CommunityMember(user_id=user.id, community_id=community.id)
    db.session.add(member)
    db.session.commit()
    if success is True:
        cache.delete_memoized(community_membership, user, community)
        cache.delete_memoized(joined_communities, user.id)
        if src == SRC_API:
            return user.id
        else:
            if main_user_name:
                flash('You joined ' + community.title)
            else:
                pre_load_message['status'] = 'joined'

            if not main_user_name:
                return pre_load_message

    # for SRC_WEB, calling function should handle if the community isn't found


# function can be shared between WEB and API (only API calls it for now)
def leave_community(community_id: int, src, auth=None):
    if src == SRC_API:
        community = Community.query.get(community_id)
        if not community:
            raise Exception('community_not_found')
        try:
            user = authorise_api_user(auth, return_type='model')
        except:
            raise
    else:
        community = Community.query.get_or_404(community_id)
        user = current_user

    subscription = community_membership(user, community)
    if subscription:
        if subscription != SUBSCRIPTION_OWNER:
            proceed = True
            # Undo the Follow
            if not community.is_local():
                success = True
                if not community.instance.gone_forever:
                    undo_id = f"https://{current_app.config['SERVER_NAME']}/activities/undo/" + gibberish(15)
                    follow = {
                      "actor": user.public_url(),
                      "to": [community.public_url()],
                      "object": community.public_url(),
                      "type": "Follow",
                      "id": f"https://{current_app.config['SERVER_NAME']}/activities/follow/{gibberish(15)}"
                    }
                    undo = {
                      'actor': user.public_url(),
                      'to': [community.public_url()],
                      'type': 'Undo',
                      'id': undo_id,
                      'object': follow
                    }
                    success = post_request(community.ap_inbox_url, undo, user.private_key,
                                              user.public_url() + '#main-key', timeout=10)
                    if success is False or isinstance(success, str):
                        if src != SRC_API:
                            flash('There was a problem while trying to unsubscribe', 'error')
                            return

            if proceed:
                db.session.query(CommunityMember).filter_by(user_id=user.id, community_id=community.id).delete()
                db.session.query(CommunityJoinRequest).filter_by(user_id=user.id, community_id=community.id).delete()
                db.session.commit()

                if src != SRC_API:
                    flash('You have left ' + community.title)

            cache.delete_memoized(community_membership, user, community)
            cache.delete_memoized(joined_communities, user.id)
        else:
            # todo: community deletion
            if src == SRC_API:
                raise Exception('need_to_make_someone_else_owner')
            else:
                flash('You need to make someone else the owner before unsubscribing.', 'warning')
                return

    if src == SRC_API:
        return user.id
    else:
        # let calling function handle redirect
        return












