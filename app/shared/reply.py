from app import cache, db
from app.activitypub.signature import default_context, post_request_in_background
from app.community.util import send_to_remote_instance
from app.models import PostReply, PostReplyBookmark, User
from app.utils import gibberish, instance_banned, render_template, authorise_api_user, recently_upvoted_post_replies, recently_downvoted_post_replies

from flask import abort, current_app, flash, redirect, request, url_for
from flask_babel import _
from flask_login import current_user


# would be in app/constants.py
SRC_WEB = 1
SRC_PUB = 2
SRC_API = 3

# function can be shared between WEB and API (only API calls it for now)
# comment_vote in app/post/routes would just need to do 'return vote_for_reply(reply_id, vote_direction, SRC_WEB)'

def vote_for_reply(reply_id: int, vote_direction, src, auth=None):
    if src == SRC_API and auth is not None:
        reply = PostReply.query.get(reply_id)
        if not reply:
            raise Exception('reply_not_found')
        try:
            user = authorise_api_user(auth, return_type='model')
        except:
            raise
    else:
        reply = PostReply.query.get_or_404(post_id)
        user = current_user

    undo = reply.vote(user, vote_direction)

    if not reply.community.local_only:
        if undo:
            action_json = {
                'actor': user.public_url(not(reply.community.instance.votes_are_public() and user.vote_privately())),
                'type': 'Undo',
                'id': f"https://{current_app.config['SERVER_NAME']}/activities/undo/{gibberish(15)}",
                'audience': reply.community.public_url(),
                'object': {
                    'actor': user.public_url(not(reply.community.instance.votes_are_public() and user.vote_privately())),
                    'object': reply.public_url(),
                    'type': undo,
                    'id': f"https://{current_app.config['SERVER_NAME']}/activities/{undo.lower()}/{gibberish(15)}",
                    'audience': reply.community.public_url()
                }
            }
        else:
            action_type = 'Like' if vote_direction == 'upvote' else 'Dislike'
            action_json = {
                'actor': user.public_url(not(reply.community.instance.votes_are_public() and user.vote_privately())),
                'object': reply.public_url(),
                'type': action_type,
                'id': f"https://{current_app.config['SERVER_NAME']}/activities/{action_type.lower()}/{gibberish(15)}",
                'audience': reply.community.public_url()
            }
        if reply.community.is_local():
            announce = {
                    "id": f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}",
                    "type": 'Announce',
                    "to": [
                        "https://www.w3.org/ns/activitystreams#Public"
                    ],
                    "actor": reply.community.ap_profile_id,
                    "cc": [
                        reply.community.ap_followers_url
                    ],
                    '@context': default_context(),
                    'object': action_json
            }
            for instance in reply.community.following_instances():
                if instance.inbox and not user.has_blocked_instance(instance.id) and not instance_banned(instance.domain):
                    send_to_remote_instance(instance.id, reply.community.id, announce)
        else:
            post_request_in_background(reply.community.ap_inbox_url, action_json, user.private_key,
                                       user.public_url(not(reply.community.instance.votes_are_public() and user.vote_privately())) + '#main-key')

    if src == SRC_API:
        return user.id
    else:
        recently_upvoted = []
        recently_downvoted = []
        if vote_direction == 'upvote' and undo is None:
            recently_upvoted = [reply_id]
        elif vote_direction == 'downvote' and undo is None:
            recently_downvoted = [reply_id]
        cache.delete_memoized(recently_upvoted_post_replies, user.id)
        cache.delete_memoized(recently_downvoted_post_replies, user.id)

        return render_template('post/_reply_voting_buttons.html', comment=reply,
                               recently_upvoted_replies=recently_upvoted,
                               recently_downvoted_replies=recently_downvoted,
                               community=reply.community)


# function can be shared between WEB and API (only API calls it for now)
# post_reply_bookmark in app/post/routes would just need to do 'return bookmark_the_post_reply(comment_id, SRC_WEB)'
def bookmark_the_post_reply(comment_id: int, src, auth=None):
    if src == SRC_API and auth is not None:
        post_reply = PostReply.query.get(comment_id)
        if not post_reply or post_reply.deleted:
            raise Exception('comment_not_found')
        try:
            user_id = authorise_api_user(auth)
        except:
            raise
    else:
        post_reply = PostReply.query.get_or_404(comment_id)
        if post_reply.deleted:
            abort(404)
        user_id = current_user.id

    existing_bookmark = PostReplyBookmark.query.filter(PostReplyBookmark.post_reply_id == comment_id,
                                                       PostReplyBookmark.user_id == user_id).first()
    if not existing_bookmark:
        db.session.add(PostReplyBookmark(post_reply_id=comment_id, user_id=user_id))
        db.session.commit()
        if src == SRC_WEB:
            flash(_('Bookmark added.'))
    else:
        if src == SRC_WEB:
            flash(_('This comment has already been bookmarked'))

    if src == SRC_API:
        return user_id
    else:
        return redirect(url_for('activitypub.post_ap', post_id=post_reply.post_id, _anchor=f'comment_{comment_id}'))


# function can be shared between WEB and API (only API calls it for now)
# post_reply_remove_bookmark in app/post/routes would just need to do 'return remove_the_bookmark_from_post_reply(comment_id, SRC_WEB)'
def remove_the_bookmark_from_post_reply(comment_id: int, src, auth=None):
    if src == SRC_API and auth is not None:
        post_reply = PostReply.query.get(comment_id)
        if not post_reply or post_reply.deleted:
            raise Exception('comment_not_found')
        try:
            user_id = authorise_api_user(auth)
        except:
            raise
    else:
        post_reply = PostReply.query.get_or_404(comment_id)
        if post_reply.deleted:
            abort(404)
        user_id = current_user.id

    existing_bookmark = PostReplyBookmark.query.filter(PostReplyBookmark.post_reply_id == comment_id,
                                                       PostReplyBookmark.user_id == user_id).first()
    if existing_bookmark:
        db.session.delete(existing_bookmark)
        db.session.commit()
        if src == SRC_WEB:
            flash(_('Bookmark has been removed.'))

    if src == SRC_API:
        return user_id
    else:
        return redirect(url_for('activitypub.post_ap', post_id=post_reply.post_id))
