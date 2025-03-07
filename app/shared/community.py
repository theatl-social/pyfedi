from app import db, cache
from app.constants import *
from app.models import CommunityBlock, CommunityMember
from app.shared.tasks import task_selector
from app.utils import authorise_api_user, blocked_communities
from app.constants import *

from flask import current_app, flash
from flask_babel import _
from flask_login import current_user


# function can be shared between WEB and API (only API calls it for now)
# call from admin.federation not tested
def join_community(community_id: int, src, auth=None, user_id=None):
    if src == SRC_API:
        user_id = authorise_api_user(auth)

    send_async = not (current_app.debug or src == SRC_WEB)     # False if using a browser

    sync_retval = task_selector('join_community', send_async, user_id=user_id, community_id=community_id, src=src)

    if send_async or sync_retval is True:
        existing_member = CommunityMember.query.filter_by(user_id=user_id,
                                                          community_id=community_id).first()
        if not existing_member:
            member = CommunityMember(user_id=user_id, community_id=community_id)
            db.session.add(member)
            db.session.commit()

    if src == SRC_API:
        return user_id
    elif src == SRC_PLD:
        return sync_retval
    else:
        return


# function can be shared between WEB and API (only API calls it for now)
def leave_community(community_id: int, src, auth=None):
    user_id = authorise_api_user(auth) if src == SRC_API else current_user.id
    cm = CommunityMember.query.filter_by(user_id=user_id, community_id=community_id).one()
    if not cm.is_owner:
        task_selector('leave_community', user_id=user_id, community_id=community_id)

        db.session.query(CommunityMember).filter_by(user_id=user_id, community_id=community_id).delete()
        db.session.commit()

        if src == SRC_WEB:
            flash('You have left the community')
    else:
        # todo: community deletion
        if src == SRC_API:
            raise Exception('need_to_make_someone_else_owner')
        else:
            flash('You need to make someone else the owner before unsubscribing.', 'warning')
            return

    if src == SRC_API:
        return user_id
    else:
        # let calling function handle redirect
        return


def block_community(community_id, src, auth=None):
    if src == SRC_API:
        user_id = authorise_api_user(auth)
    else:
        user_id = current_user.id

    existing = CommunityBlock.query.filter_by(user_id=user_id, community_id=community_id).first()
    if not existing:
        db.session.add(CommunityBlock(user_id=user_id, community_id=community_id))
        db.session.commit()
        cache.delete_memoized(blocked_communities, user_id)

    if src == SRC_API:
        return user_id
    else:
        return              # let calling function handle confirmation flash message and redirect


def unblock_community(community_id, src, auth=None):
    if src == SRC_API:
        user_id = authorise_api_user(auth)
    else:
        user_id = current_user.id

    existing_block = CommunityBlock.query.filter_by(user_id=user_id, community_id=community_id).first()
    if existing_block:
        db.session.delete(existing_block)
        db.session.commit()
        cache.delete_memoized(blocked_communities, user_id)

    if src == SRC_API:
        return user_id
    else:
        return              # let calling function handle confirmation flash message and redirect
