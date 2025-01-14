from app import db
from app.constants import *
from app.community.util import tags_from_string
from app.models import Language, NotificationSubscription, Post, PostBookmark
from app.shared.tasks import task_selector
from app.utils import render_template, authorise_api_user, shorten_string, gibberish, ensure_directory_exists

from flask import abort, flash, redirect, request, url_for, current_app
from flask_babel import _
from flask_login import current_user

from pillow_heif import register_heif_opener
from PIL import Image, ImageOps

import os

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


def make_post(input, community, type, src, auth=None, uploaded_file=None):
    if src == SRC_API:
        user = authorise_api_user(auth, return_type='model')
        #if not basic_rate_limit_check(user):
        #    raise Exception('rate_limited')
        title = input['title']
        body = input['body']
        url = input['url']
        nsfw = input['nsfw']
        notify_author = input['notify_author']
        language_id = input['language_id']
        tags = []
    else:
        user = current_user
        title = input.title.data
        body = input.body.data
        url = input.link_url.data
        nsfw = input.nsfw.data
        notify_author = input.notify_author.data
        language_id = input.language_id.data
        tags = tags_from_string(input.tags.data)

    language = Language.query.filter_by(id=language_id).one()

    request_json = {
      'id': None,
      'object': {
        'name': title,
        'type': 'Page',
        'stickied': False if src == SRC_API else input.sticky.data,
        'sensitive': nsfw,
        'nsfl': False if src == SRC_API else input.nsfl.data,
        'id': gibberish(),   # this will  be updated once we have the post.id
        'mediaType': 'text/markdown',
        'content': body,
        'tag': tags,
        'language': {'identifier': language.code, 'name': language.name}
      }
    }

    if type == 'link' or (type == 'image' and src == SRC_API):
        request_json['object']['attachment'] = [{'type': 'Link', 'href': url}]
    elif type == 'image' and src == SRC_WEB and uploaded_file and uploaded_file.filename != '':
        # check if this is an allowed type of file
        file_ext = os.path.splitext(uploaded_file.filename)[1]
        if file_ext.lower() not in allowed_extensions:
            abort(400, description="Invalid image type.")

        new_filename = gibberish(15)
        # set up the storage directory
        directory = 'app/static/media/posts/' + new_filename[0:2] + '/' + new_filename[2:4]
        ensure_directory_exists(directory)

        final_place = os.path.join(directory, new_filename + file_ext)
        uploaded_file.seek(0)
        uploaded_file.save(final_place)

        if file_ext.lower() == '.heic':
            register_heif_opener()
        if file_ext.lower() == '.avif':
            import pillow_avif

        Image.MAX_IMAGE_PIXELS = 89478485

        # resize if necessary
        if not final_place.endswith('.svg'):
            img = Image.open(final_place)
            if '.' + img.format.lower() in allowed_extensions:
                img = ImageOps.exif_transpose(img)

                # limit full sized version to 2000px
                img.thumbnail((2000, 2000))
                img.save(final_place)

        request_json['object']['attachment'] = [{
            'type': 'Image',
            'url': f'https://{current_app.config["SERVER_NAME"]}/{final_place.replace("app/", "")}',
            'name': input.image_alt_text.data,
            'file_path': final_place
        }]
    elif type == 'video':
        request_json['object']['attachment'] = [{'type': 'Document', 'url': url}]
    elif type == 'poll':
        request_json['object']['type'] = 'Question'
        choices = [input.choice_1, input.choice_2, input.choice_3, input.choice_4, input.choice_5,
                   input.choice_6, input.choice_7, input.choice_8, input.choice_9, input.choice_10]
        key = 'oneOf' if input.mode.data == 'single' else 'anyOf'
        request_json['object'][key] = []
        for choice in choices:
            choice_data = choice.data.strip()
            if choice_data:
                request_json['object'][key].append({'name': choice_data})
        request_json['object']['endTime'] = end_poll_date(input.finish_in.data)

    post = Post.new(user, community, request_json)
    post.ap_id = f"https://{current_app.config['SERVER_NAME']}/post/{post.id}"
    db.session.commit()

    task_selector('make_post', user_id=user.id, post_id=post.id)

    if src == SRC_API:
        return user.id, post
    else:
        return post


