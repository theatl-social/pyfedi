from app import db
from app.constants import *
from app.community.util import tags_from_string, tags_from_string_old, end_poll_date
from app.models import File, Language, NotificationSubscription, Poll, PollChoice, Post, PostBookmark, utcnow
from app.shared.tasks import task_selector
from app.utils import render_template, authorise_api_user, shorten_string, gibberish, ensure_directory_exists, \
                      piefed_markdown_to_lemmy_markdown, markdown_to_html, remove_tracking_from_link, domain_from_url, \
                      opengraph_parse, url_to_thumbnail_file, blocked_phrases

from flask import abort, flash, redirect, request, url_for, current_app, g
from flask_babel import _
from flask_login import current_user

from pillow_heif import register_heif_opener
from PIL import Image, ImageOps

from sqlalchemy import text

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


def edit_post(input, post, type, src, auth=None, uploaded_file=None):
    if src == SRC_API:
        user = authorise_api_user(auth, return_type='model')
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

    post.indexable = user.indexable
    post.sticky = False if src == SRC_API else input.sticky.data
    post.nsfw = nsfw
    post.nsfl = False if src == SRC_API else input.nsfl.data
    post.notify_author = notify_author
    post.language_id = language_id
    user.language_id = language_id
    post.title = title.strip()
    post.body = piefed_markdown_to_lemmy_markdown(body)
    post.body_html = markdown_to_html(post.body)

    allowed_extensions = ['.gif', '.jpg', '.jpeg', '.png', '.webp', '.heic', '.mpo', '.avif', '.svg']

    if not type or type == POST_TYPE_ARTICLE:
        post.type = POST_TYPE_ARTICLE
    elif type == POST_TYPE_LINK:
        url_changed = post.id is None or url != post.url      # post.id ?
        post.url = remove_tracking_from_link(url.strip())
        post.type = POST_TYPE_LINK
        domain = domain_from_url(url)
        domain.post_count += 1
        post.domain = domain

        if url_changed:
            if post.image_id:
                remove_file = File.query.get(post.image_id)
                remove_file.delete_from_disk()
                post.image_id = None

            if post.url.endswith('.mp4') or post.url.endswith('.webm'):
                post.type = POST_TYPE_VIDEO
                file = File(source_url=url)  # make_image_sizes() will take care of turning this into a still image
                post.image = file
                db.session.add(file)
            else:
                unused, file_extension = os.path.splitext(url)
                # this url is a link to an image - turn it into a image post
                if file_extension.lower() in allowed_extensions:
                    file = File(source_url=url)
                    post.image = file
                    db.session.add(file)
                    post.type = POST_TYPE_IMAGE
                else:
                    # check opengraph tags on the page and make a thumbnail if an image is available in the og:image meta tag
                    if not post.type == POST_TYPE_VIDEO:
                        tn_url = url
                        if tn_url[:32] == 'https://www.youtube.com/watch?v=':
                            tn_url = 'https://youtu.be/' + tn_url[32:43]            # better chance of thumbnail from youtu.be than youtube.com
                        opengraph = opengraph_parse(tn_url)
                        if opengraph and (opengraph.get('og:image', '') != '' or opengraph.get('og:image:url', '') != ''):
                            filename = opengraph.get('og:image') or opengraph.get('og:image:url')
                            if not filename.startswith('/'):
                                file = url_to_thumbnail_file(filename)
                                if file:
                                    file.alt_text = shorten_string(opengraph.get('og:title'), 295)
                                    post.image = file
                                    db.session.add(file)

    elif type == POST_TYPE_IMAGE:
        post.type = POST_TYPE_IMAGE
        # If we are uploading new file in the place of existing one just remove the old one
        if post.image_id is not None and src == SRC_WEB:
            post.image.delete_from_disk()
            image_id = post.image_id
            post.image_id = None
            db.session.add(post)
            db.session.commit()
            File.query.filter_by(id=image_id).delete()

        if uploaded_file and uploaded_file.filename != '' and src == SRC_WEB:
            if post.image_id:
                remove_file = File.query.get(post.image_id)
                remove_file.delete_from_disk()
                post.image_id = None

            # check if this is an allowed type of file
            file_ext = os.path.splitext(uploaded_file.filename)[1]
            if file_ext.lower() not in allowed_extensions:
                abort(400)
            new_filename = gibberish(15)

            # set up the storage directory
            directory = 'app/static/media/posts/' + new_filename[0:2] + '/' + new_filename[2:4]
            ensure_directory_exists(directory)

            # save the file
            final_place = os.path.join(directory, new_filename + file_ext)
            final_place_medium = os.path.join(directory, new_filename + '_medium.webp')
            final_place_thumbnail = os.path.join(directory, new_filename + '_thumbnail.webp')
            uploaded_file.seek(0)
            uploaded_file.save(final_place)

            if file_ext.lower() == '.heic':
                register_heif_opener()

            Image.MAX_IMAGE_PIXELS = 89478485

            # resize if necessary
            img = Image.open(final_place)
            if '.' + img.format.lower() in allowed_extensions:
                img = ImageOps.exif_transpose(img)

                # limit full sized version to 2000px
                img_width = img.width
                img_height = img.height
                img.thumbnail((2000, 2000))
                img.save(final_place)

                # medium sized version
                img.thumbnail((512, 512))
                img.save(final_place_medium, format="WebP", quality=93)

                # save a third, smaller, version as a thumbnail
                img.thumbnail((170, 170))
                img.save(final_place_thumbnail, format="WebP", quality=93)
                thumbnail_width = img.width
                thumbnail_height = img.height

                alt_text = input.image_alt_text.data if input.image_alt_text.data else title

                file = File(file_path=final_place_medium, file_name=new_filename + file_ext, alt_text=alt_text,
                            width=img_width, height=img_height, thumbnail_width=thumbnail_width,
                            thumbnail_height=thumbnail_height, thumbnail_path=final_place_thumbnail,
                            source_url=final_place.replace('app/static/', f"https://{current_app.config['SERVER_NAME']}/static/"))
                db.session.add(file)
                db.session.commit()
                post.image_id = file.id

    elif type == POST_TYPE_VIDEO:
        url = url.strip()
        url_changed = post.id is None or url != post.url
        post.url = remove_tracking_from_link(url)
        post.type = POST_TYPE_VIDEO
        domain = domain_from_url(url)
        domain.post_count += 1
        post.domain = domain

        if url_changed:
            if post.image_id:
                remove_file = File.query.get(post.image_id)
                remove_file.delete_from_disk()
                post.image_id = None
            if url.endswith('.mp4') or url('.webm'):
                file = File(source_url=url)  # make_image_sizes() will take care of turning this into a still image
                post.image = file
                db.session.add(file)
            else:
                # check opengraph tags on the page and make a thumbnail if an image is available in the og:image meta tag
                tn_url = url
                if tn_url[:32] == 'https://www.youtube.com/watch?v=':
                    tn_url = 'https://youtu.be/' + tn_url[32:43]  # better chance of thumbnail from youtu.be than youtube.com
                opengraph = opengraph_parse(tn_url)
                if opengraph and (opengraph.get('og:image', '') != '' or opengraph.get('og:image:url', '') != ''):
                    filename = opengraph.get('og:image') or opengraph.get('og:image:url')
                    if not filename.startswith('/'):
                        file = url_to_thumbnail_file(filename)
                        if file:
                            file.alt_text = shorten_string(opengraph.get('og:title'), 295)
                            post.image = file
                            db.session.add(file)

    elif type == POST_TYPE_POLL:
        post.body = title + '\n' + body if title not in body else body
        post.body_html = markdown_to_html(post.body)
        post.type = POST_TYPE_POLL
    else:
        raise Exception('invalid post type')

    if post.id is None:
        if user.reputation > 100:
            post.up_votes = 1
            post.score = 1
        if user.reputation < -100:
            post.score = -1
        post.ranking = post.post_ranking(post.score, utcnow())

        # Filter by phrase
        blocked_phrases_list = blocked_phrases()
        for blocked_phrase in blocked_phrases_list:
            if blocked_phrase in post.title:
                abort(401)
                return
        if post.body:
            for blocked_phrase in blocked_phrases_list:
                if blocked_phrase in post.body:
                    abort(401)
                    return

        db.session.add(post)
    else:
        db.session.execute(text('DELETE FROM "post_tag" WHERE post_id = :post_id'), {'post_id': post.id})
    post.tags = tags
    db.session.commit()

    # Save poll choices. NB this will delete all votes whenever a poll is edited. Partially because it's easier to code but also to stop malicious alterations to polls after people have already voted
    if type == POST_TYPE_POLL:
        db.session.execute(text('DELETE FROM "poll_choice_vote" WHERE post_id = :post_id'), {'post_id': post.id})
        db.session.execute(text('DELETE FROM "poll_choice" WHERE post_id = :post_id'), {'post_id': post.id})
        for i in range(1, 10):
            choice_data = getattr(input, f"choice_{i}").data.strip()
            if choice_data != '':
                db.session.add(PollChoice(post_id=post.id, choice_text=choice_data, sort_order=i))

        poll = Poll.query.filter_by(post_id=post.id).first()
        if poll is None:
            poll = Poll(post_id=post.id)
            db.session.add(poll)
        poll.mode = input.mode.data
        if input.finish_in:
            poll.end_poll = end_poll_date(input.finish_in.data)
        poll.local_only = input.local_only.data
        poll.latest_vote = None
        db.session.commit()

    # Notify author about replies
    # Remove any subscription that currently exists
    existing_notification = NotificationSubscription.query.filter(NotificationSubscription.entity_id == post.id,
                                                                  NotificationSubscription.user_id == user.id,
                                                                  NotificationSubscription.type == NOTIF_POST).first()
    if existing_notification:
        db.session.delete(existing_notification)

    # Add subscription if necessary
    if notify_author:
        new_notification = NotificationSubscription(name=post.title, user_id=user.id, entity_id=post.id,
                                                    type=NOTIF_POST)
        db.session.add(new_notification)

    g.site.last_active = utcnow()
    db.session.commit()

    task_selector('edit_post', user_id=user.id, post_id=post.id)

    if src == SRC_API:
        return user.id, post
