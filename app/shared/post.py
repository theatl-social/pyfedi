from app import cache, db
from app.activitypub.signature import default_context, post_request_in_background
from app.community.util import send_to_remote_instance
from app.constants import *
from app.models import NotificationSubscription, Post, PostBookmark, User
from app.utils import gibberish, instance_banned, render_template, authorise_api_user, recently_upvoted_posts, recently_downvoted_posts, shorten_string

from flask import abort, current_app, flash, redirect, request, url_for
from flask_babel import _
from flask_login import current_user


# would be in app/constants.py
SRC_WEB = 1
SRC_PUB = 2
SRC_API = 3

# function can be shared between WEB and API (only API calls it for now)
# post_vote in app/post/routes would just need to do 'return vote_for_post(post_id, vote_direction, SRC_WEB)'

def vote_for_post(post_id: int, vote_direction, src, auth=None):
    if src == SRC_API:
        post = Post.query.get(post_id)
        if not post:
            raise Exception('post_not_found')
        try:
            user = authorise_api_user(auth, return_type='model')
        except:
            raise
    else:
        post = Post.query.get_or_404(post_id)
        user = current_user

    undo = post.vote(user, vote_direction)

    if not post.community.local_only:
        if undo:
            action_json = {
                'actor': user.public_url(not(post.community.instance.votes_are_public() and user.vote_privately())),
                'type': 'Undo',
                'id': f"https://{current_app.config['SERVER_NAME']}/activities/undo/{gibberish(15)}",
                'audience': post.community.public_url(),
                'object': {
                    'actor': user.public_url(not(post.community.instance.votes_are_public() and user.vote_privately())),
                    'object': post.public_url(),
                    'type': undo,
                    'id': f"https://{current_app.config['SERVER_NAME']}/activities/{undo.lower()}/{gibberish(15)}",
                    'audience': post.community.public_url()
                }
            }
        else:
            action_type = 'Like' if vote_direction == 'upvote' else 'Dislike'
            action_json = {
                'actor': user.public_url(not(post.community.instance.votes_are_public() and user.vote_privately())),
                'object': post.profile_id(),
                'type': action_type,
                'id': f"https://{current_app.config['SERVER_NAME']}/activities/{action_type.lower()}/{gibberish(15)}",
                'audience': post.community.public_url()
            }
        if post.community.is_local():
            announce = {
                    "id": f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}",
                    "type": 'Announce',
                    "to": [
                        "https://www.w3.org/ns/activitystreams#Public"
                    ],
                    "actor": post.community.public_url(),
                    "cc": [
                        post.community.ap_followers_url
                    ],
                    '@context': default_context(),
                    'object': action_json
            }
            for instance in post.community.following_instances():
                if instance.inbox and not user.has_blocked_instance(instance.id) and not instance_banned(instance.domain):
                    send_to_remote_instance(instance.id, post.community.id, announce)
        else:
            post_request_in_background(post.community.ap_inbox_url, action_json, user.private_key,
                                       user.public_url(not(post.community.instance.votes_are_public() and user.vote_privately())) + '#main-key')


    if src == SRC_API:
        return user.id
    else:
        recently_upvoted = []
        recently_downvoted = []
        if vote_direction == 'upvote' and undo is None:
            recently_upvoted = [post_id]
        elif vote_direction == 'downvote' and undo is None:
            recently_downvoted = [post_id]
        cache.delete_memoized(recently_upvoted_posts, user.id)
        cache.delete_memoized(recently_downvoted_posts, user.id)

        template = 'post/_post_voting_buttons.html' if request.args.get('style', '') == '' else 'post/_post_voting_buttons_masonry.html'
        return render_template(template, post=post, community=post.community, recently_upvoted=recently_upvoted,
                               recently_downvoted=recently_downvoted)


# function can be shared between WEB and API (only API calls it for now)
# post_bookmark in app/post/routes would just need to do 'return bookmark_the_post(post_id, SRC_WEB)'
def bookmark_the_post(post_id: int, src, auth=None):
    if src == SRC_API:
        post = Post.query.get(post_id)
        if not post or post.deleted:
            raise Exception('post_not_found')
        try:
            user_id = authorise_api_user(auth)
        except:
            raise
    else:
        post = Post.query.get_or_404(post_id)
        if post.deleted:
            abort(404)
        user_id = current_user.id

    existing_bookmark = PostBookmark.query.filter(PostBookmark.post_id == post_id, PostBookmark.user_id == user_id).first()
    if not existing_bookmark:
        db.session.add(PostBookmark(post_id=post_id, user_id=user_id))
        db.session.commit()
        if src == SRC_WEB:
            flash(_('Bookmark added.'))
    else:
        if src == SRC_WEB:
            flash(_('This post has already been bookmarked.'))

    if src == SRC_API:
        return user_id
    else:
        return redirect(url_for('activitypub.post_ap', post_id=post.id))


# function can be shared between WEB and API (only API calls it for now)
# post_remove_bookmark in app/post/routes would just need to do 'return remove_the_bookmark_from_post(post_id, SRC_WEB)'
def remove_the_bookmark_from_post(post_id: int, src, auth=None):
    if src == SRC_API:
        post = Post.query.get(post_id)
        if not post or post.deleted:
            raise Exception('post_not_found')
        try:
            user_id = authorise_api_user(auth)
        except:
            raise
    else:
        post = Post.query.get_or_404(post_id)
        if post.deleted:
            abort(404)
        user_id = current_user.id

    existing_bookmark = PostBookmark.query.filter(PostBookmark.post_id == post_id, PostBookmark.user_id == user_id).first()
    if existing_bookmark:
        db.session.delete(existing_bookmark)
        db.session.commit()
        if src == SRC_WEB:
            flash(_('Bookmark has been removed.'))

    if src == SRC_API:
        return user_id
    else:
        return redirect(url_for('activitypub.post_ap', post_id=post.id))



# function can be shared between WEB and API (only API calls it for now)
# post_notification in app/post/routes would just need to do 'return toggle_post_notification(post_id, SRC_WEB)'
def toggle_post_notification(post_id: int, src, auth=None):
    # Toggle whether the current user is subscribed to notifications about top-level replies to this post or not
    if src == SRC_API:
        post = Post.query.get(post_id)
        if not post or post.deleted:
            raise Exception('post_not_found')
        try:
            user_id = authorise_api_user(auth)
        except:
            raise
    else:
        post = Post.query.get_or_404(post_id)
        if post.deleted:
            abort(404)
        user_id = current_user.id

    existing_notification = NotificationSubscription.query.filter(NotificationSubscription.entity_id == post.id,
                                                                  NotificationSubscription.user_id == user_id,
                                                                  NotificationSubscription.type == NOTIF_POST).first()
    if existing_notification:
        db.session.delete(existing_notification)
        db.session.commit()
    else:  # no subscription yet, so make one
        new_notification = NotificationSubscription(name=shorten_string(_('Replies to my post %(post_title)s',
                                                                              post_title=post.title)),
                                                    user_id=user_id, entity_id=post.id,
                                                    type=NOTIF_POST)
        db.session.add(new_notification)
        db.session.commit()

    if src == SRC_API:
        return user_id
    else:
        return render_template('post/_post_notification_toggle.html', post=post)
