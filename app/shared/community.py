from app import db, cache
from app.activitypub.signature import post_request_in_background
from app.chat.util import send_message
from app.constants import *
from app.email import send_email
from app.models import CommunityBlock, CommunityMember, Notification, User, utcnow, Conversation, Community
from app.shared.tasks import task_selector
from app.user.utils import search_for_user
from app.utils import authorise_api_user, blocked_communities, shorten_string, gibberish, markdown_to_html, \
    instance_banned
from app.constants import *

from flask import current_app, flash, render_template
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


def block_community(community_id: int, src, auth=None):
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


def unblock_community(community_id: int, src, auth=None):
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


def invite_with_chat(community_id: int, handle: str, src, auth=None):
    if src == SRC_API:
        user_id = authorise_api_user(auth)
        user = User.query.get(user_id)
    else:
        user = current_user

    recipient = search_for_user(handle)
    if recipient and not recipient.banned and not instance_banned(recipient.instance.domain):
        community = Community.query.get(community_id)
        if community.banned:
            return 0

        conversation = Conversation(user_id=user.id)
        conversation.members.append(recipient)
        conversation.members.append(user)
        db.session.add(conversation)
        db.session.commit()

        message = f"Hi there,\n\nI think you might appreciate this community, check it out: https://{current_app.config['SERVER_NAME']}/c/{community.link()}.\n\n"
        if recipient.is_local():
            message += f"If you'd like to join it use this link: https://{current_app.config['SERVER_NAME']}/c/{community.link()}/subscribe."
        else:
            if recipient.instance.software.lower() == 'piefed':
                message += f"Join the community by going to https://{recipient.instance.domain}/c/{community.link()}/subscribe or if that doesn't work try pasting {community.lemmy_link()} into this form: https://{recipient.instance.domain}/community/add_remote."
            elif recipient.instance.software.lower() == 'lemmy' or recipient.instance.software.lower() == 'mbin':
                message += f"Join the community by clicking 'Join' at https://{recipient.instance.domain}/c/{community.link()} or if that doesn't work try pasting {community.lemmy_link()} into your search function."
            else:
                message = render_template('email/invite_to_community.txt', user=user, community=community, host=current_app.config['SERVER_NAME'])

        if current_app.debug:
            reply = send_message(message, conversation.id)
        else:
            send_message.delay(message, conversation.id)
            reply = 'ok'

        return 1 if reply else 0
    return 0


def invite_with_email(community_id: int, to: str, src, auth=None):
    if src == SRC_API:
        user_id = authorise_api_user(auth)
        user = User.query.get(user_id)
    else:
        user = current_user

    community = Community.query.get(community_id)
    if community.banned:
        return 0

    message = render_template('email/invite_to_community.txt', user=user, community=community, host=current_app.config['SERVER_NAME'])

    send_email(f"{community.display_name()} on {current_app.config['SERVER_NAME']}",
               f"{user.display_name()} <noreply@{current_app.config['SERVER_NAME']}>",
               [to], message, markdown_to_html(message))
    return 1
