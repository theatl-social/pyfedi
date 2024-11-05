from app import db
from app.constants import *
from app.models import NotificationSubscription, Post, PostBookmark
from app.shared.tasks import task_selector
from app.utils import render_template, authorise_api_user, shorten_string

from flask import abort, flash, redirect, request, url_for
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
        post = Post.query.filter_by(id=post_id).one()
        user = authorise_api_user(auth, return_type='model')
    else:
        post = Post.query.get_or_404(post_id)
        user = current_user

    undo = post.vote(user, vote_direction)

    task_selector('vote_for_post', user_id=user.id, post_id=post_id, vote_to_undo=undo, vote_direction=vote_direction)

    if src == SRC_API:
        return user.id
    else:
        recently_upvoted = []
        recently_downvoted = []
        if vote_direction == 'upvote' and undo is None:
            recently_upvoted = [post_id]
        elif vote_direction == 'downvote' and undo is None:
            recently_downvoted = [post_id]

        template = 'post/_post_voting_buttons.html' if request.args.get('style', '') == '' else 'post/_post_voting_buttons_masonry.html'
        return render_template(template, post=post, community=post.community, recently_upvoted=recently_upvoted,
                               recently_downvoted=recently_downvoted)


# function can be shared between WEB and API (only API calls it for now)
# post_bookmark in app/post/routes would just need to do 'return bookmark_the_post(post_id, SRC_WEB)'
def bookmark_the_post(post_id: int, src, auth=None):
    if src == SRC_API:
        post = Post.query.filter_by(id=post_id, deleted=False).one()
        user_id = authorise_api_user(auth)
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
        post = Post.query.filter_by(id=post_id, deleted=False).one()
        user_id = authorise_api_user(auth)
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
        post = Post.query.filter_by(id=post_id, deleted=False).one()
        user_id = authorise_api_user(auth)
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
        new_notification = NotificationSubscription(name=shorten_string(_('Replies to my post %(post_title)s', post_title=post.title)),
                                                    user_id=user_id, entity_id=post.id, type=NOTIF_POST)
        db.session.add(new_notification)
        db.session.commit()

    if src == SRC_API:
        return user_id
    else:
        return render_template('post/_post_notification_toggle.html', post=post)
