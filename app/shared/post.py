from app import db, cache
from app.activitypub.util import make_image_sizes, notify_about_post
from app.constants import *
from app.community.util import tags_from_string_old, end_poll_date
from app.models import File, Notification, NotificationSubscription, Poll, PollChoice, Post, PostBookmark, PostVote, Report, Site, User, utcnow
from app.shared.tasks import task_selector
from app.utils import render_template, authorise_api_user, shorten_string, gibberish, ensure_directory_exists, \
                      piefed_markdown_to_lemmy_markdown, markdown_to_html, fixup_url, domain_from_url, \
                      opengraph_parse, url_to_thumbnail_file, can_create_post, is_video_hosting_site, recently_upvoted_posts, \
                      is_image_url, add_to_modlog_activitypub

from flask import abort, flash, redirect, request, url_for, current_app, g
from flask_babel import _
from flask_login import current_user

from pillow_heif import register_heif_opener
from PIL import Image, ImageOps

from sqlalchemy import text

import os


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


def extra_rate_limit_check(user):
    """
    The plan for this function is to do some extra limiting for an author who passes the rate limit for the route
    but who's posts are really unpopular and are probably spam
    """
    return False


def make_post(input, community, type, src, auth=None, uploaded_file=None):
    if src == SRC_API:
        user = authorise_api_user(auth, return_type='model')
        if extra_rate_limit_check(user):
            raise Exception('rate_limited')
        title = input['title']
        url = input['url']
        language_id = input['language_id']
    else:
        user = current_user
        title = input.title.data.strip()
        if type == POST_TYPE_LINK:
            url = input.link_url.data.strip()
        elif type == POST_TYPE_VIDEO:
            url = input.video_url.data.strip()
        else:
            url = None
        language_id = input.language_id.data

    # taking values from one JSON to put in another JSON to put in a DB to put in another JSON feels bad
    # instead, make_post shares code with edit_post
    # ideally, a similar change could be made for incoming activitypub (create_post() and update_post_from_activity() could share code)
    # once this happens, and post.new() just does the minimum before being passed off to an update function, post.new() can be used here again.

    if not can_create_post(user, community):
        raise Exception('You are not permitted to make posts in this community')

    if url:
        domain = domain_from_url(url)
        if domain:
            if domain.banned or domain.name.endswith('.pages.dev'):
                raise Exception(domain.name + ' is blocked by admin')

    if uploaded_file and uploaded_file.filename != '':
        # check if this is an allowed type of file
        allowed_extensions = ['.gif', '.jpg', '.jpeg', '.png', '.webp', '.heic', '.mpo', '.avif', '.svg']
        file_ext = os.path.splitext(uploaded_file.filename)[1]
        if file_ext.lower() not in allowed_extensions:
            raise Exception('filetype not allowed')

    post = Post(user_id=user.id, community_id=community.id, instance_id=user.instance_id, posted_at=utcnow(),
                ap_id=gibberish(), title=title, language_id=language_id)
    db.session.add(post)
    db.session.commit()

    post.up_votes = 1
    if user.reputation > 100:
        post.up_votes += 1
    effect = user.instance.vote_weight
    post.score = post.up_votes * effect
    post.ranking = post.post_ranking(post.score, post.posted_at)
    cache.delete_memoized(recently_upvoted_posts, user.id)

    community.post_count += 1
    community.last_active = g.site.last_active = utcnow()
    user.post_count += 1

    post.ap_id = f"https://{current_app.config['SERVER_NAME']}/post/{post.id}"
    vote = PostVote(user_id=user.id, post_id=post.id, author_id=user.id, effect=1)
    db.session.add(vote)
    db.session.commit()

    post = edit_post(input, post, type, src, user, auth, uploaded_file, from_scratch=True)

    notify_about_post(post)

    if src == SRC_API:
        return user.id, post
    else:
        return post


# 'from_scratch == True' means that it's not really a user edit, we're just re-using code for make_post()
def edit_post(input, post, type, src, user=None, auth=None, uploaded_file=None, from_scratch=False):
    if src == SRC_API:
        if not user:
             user = authorise_api_user(auth, return_type='model')
        title = input['title']
        body = input['body']
        url = input['url']
        nsfw = input['nsfw']
        notify_author = input['notify_author']
        language_id = input['language_id']
        tags = []
    else:
        if not user:
            user = current_user
        title = input.title.data.strip()
        body = input.body.data
        if type == POST_TYPE_LINK:
            url = input.link_url.data.strip()
        elif type == POST_TYPE_VIDEO:
            url = input.video_url.data.strip()
        elif type == POST_TYPE_IMAGE and not from_scratch:
            url = post.url
        else:
            url = None
        nsfw = input.nsfw.data
        notify_author = input.notify_author.data
        language_id = input.language_id.data
        tags = tags_from_string_old(input.tags.data)

    post.indexable = user.indexable
    post.sticky = False if src == SRC_API else input.sticky.data
    post.nsfw = nsfw
    post.nsfl = False if src == SRC_API else input.nsfl.data
    post.notify_author = notify_author
    post.language_id = language_id
    user.language_id = language_id
    post.title = title
    post.body = piefed_markdown_to_lemmy_markdown(body)
    post.body_html = markdown_to_html(post.body)
    post.type = type

    url_changed = False

    if not from_scratch:
        # Remove any subscription that currently exists
        existing_notification = NotificationSubscription.query.filter(NotificationSubscription.entity_id == post.id,
                                                                      NotificationSubscription.user_id == user.id,
                                                                      NotificationSubscription.type == NOTIF_POST).first()
        if existing_notification:
            db.session.delete(existing_notification)

        # Remove any poll votes that currently exists
        # Partially because it's easier to code but also to stop malicious alterations to polls after people have already voted
        db.session.execute(text('DELETE FROM "poll_choice_vote" WHERE post_id = :post_id'), {'post_id': post.id})
        db.session.execute(text('DELETE FROM "poll_choice" WHERE post_id = :post_id'), {'post_id': post.id})

        # Remove any old images, and set url_changed
        if url != post.url or uploaded_file:
            url_changed = True
            if post.image_id:
                remove_file = File.query.get(post.image_id)
                if remove_file:
                    remove_file.delete_from_disk()
                post.image_id = None
            if post.url:
                domain = domain_from_url(post.url)
                if domain:
                    domain.post_count -= 1

        # remove any old tags
        post.tags.clear()

        post.edited_at = utcnow()

        db.session.commit()

    if uploaded_file and uploaded_file.filename != '':
        # check if this is an allowed type of file
        allowed_extensions = ['.gif', '.jpg', '.jpeg', '.png', '.webp', '.heic', '.mpo', '.avif', '.svg']
        file_ext = os.path.splitext(uploaded_file.filename)[1]
        if file_ext.lower() not in allowed_extensions:
            raise Exception('filetype not allowed')

        new_filename = gibberish(15)
        # set up the storage directory
        directory = 'app/static/media/posts/' + new_filename[0:2] + '/' + new_filename[2:4]
        ensure_directory_exists(directory)

        # save the file
        final_place = os.path.join(directory, new_filename + file_ext)
        uploaded_file.seek(0)
        uploaded_file.save(final_place)

        if file_ext.lower() == '.heic':
            register_heif_opener()
        if file_ext.lower() == '.avif':
            import pillow_avif

        Image.MAX_IMAGE_PIXELS = 89478485

        # limit full sized version to 2000px
        if not final_place.endswith('.svg'):
            img = Image.open(final_place)
            if '.' + img.format.lower() in allowed_extensions:
                img = ImageOps.exif_transpose(img)

                img.thumbnail((2000, 2000))
                img.save(final_place)

                url = f"https://{current_app.config['SERVER_NAME']}/{final_place.replace('app/', '')}"
            else:
                raise Exception('filetype not allowed')
        else:
            url = f"https://{current_app.config['SERVER_NAME']}/{final_place.replace('app/', '')}"

    if url and (from_scratch or url_changed):
        domain = domain_from_url(url)
        if domain:
            if domain.banned or domain.name.endswith('.pages.dev'):
                raise Exception(domain.name + ' is blocked by admin')
            post.domain = domain
            domain.post_count += 1
            already_notified = set()  # often admins and mods are the same people - avoid notifying them twice
            if domain.notify_mods:
                for community_member in post.community.moderators():
                    if community_member.is_local():
                        notify = Notification(title='Suspicious content', url=post.ap_id, user_id=community_member.user_id, author_id=user.id)
                        db.session.add(notify)
                        already_notified.add(community_member.user_id)
            if domain.notify_admins:
                for admin in Site.admins():
                    if admin.id not in already_notified:
                        notify = Notification(title='Suspicious content', url=post.ap_id, user_id=admin.id, author_id=user.id)
                        db.session.add(notify)

        thumbnail_url, embed_url = fixup_url(url)
        if is_image_url(url):
            file = File(source_url=url)
            if uploaded_file and type == POST_TYPE_IMAGE:
                # change this line when uploaded_file is supported in API
                file.alt_text = input.image_alt_text.data if input.image_alt_text.data else title
            db.session.add(file)
            db.session.commit()
            post.image_id = file.id
            make_image_sizes(post.image_id, 170, 512, 'posts', post.community.low_quality)
            post.url = url
            post.type = POST_TYPE_IMAGE
        else:
            opengraph = opengraph_parse(thumbnail_url)
            if opengraph and (opengraph.get('og:image', '') != '' or opengraph.get('og:image:url', '') != ''):
                filename = opengraph.get('og:image') or opengraph.get('og:image:url')
                if not filename.startswith('/'):
                    file = url_to_thumbnail_file(filename)
                    if file:
                        file.alt_text = shorten_string(opengraph.get('og:title'), 295)
                        post.image = file
                        db.session.add(file)

            post.url = embed_url

            if url.endswith('.mp4') or url.endswith('.webm') or is_video_hosting_site(embed_url):
                post.type = POST_TYPE_VIDEO
            else:
                post.type = POST_TYPE_LINK

        post.calculate_cross_posts(url_changed=url_changed)

    federate = True
    if type == POST_TYPE_POLL:
        post.type = POST_TYPE_POLL
        for i in range(1, 10):
            # change this line when polls are supported in API
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

        if poll.local_only:
            federate = False

    # add tags
    post.tags = tags

    # Add subscription if necessary
    if notify_author:
        new_notification = NotificationSubscription(name=post.title, user_id=user.id, entity_id=post.id, type=NOTIF_POST)
        db.session.add(new_notification)

    db.session.commit()

    if from_scratch:
        if federate:
            task_selector('make_post', post_id=post.id)
    elif federate:
        task_selector('edit_post', post_id=post.id)

    if src == SRC_API:
        if from_scratch:
            return post
        else:
            return user.id, post
    elif from_scratch:
        return post


# just for deletes by owner (mod deletes are classed as 'remove')
def delete_post(post_id, src, auth):
    if src == SRC_API:
        user_id = authorise_api_user(auth)
    else:
        user_id = current_user.id

    post = Post.query.filter_by(id=post_id, user_id=user_id, deleted=False).one()
    if post.url:
        post.calculate_cross_posts(delete_only=True)

    post.deleted = True
    post.deleted_by = user_id
    post.author.post_count -= 1
    post.community.post_count -= 1
    db.session.commit()
    if src == SRC_WEB:
        flash(_('Post deleted.'))

    task_selector('delete_post', user_id=user_id, post_id=post.id)

    if src == SRC_API:
        return user_id, post
    else:
        return


def restore_post(post_id, src, auth):
    if src == SRC_API:
        user_id = authorise_api_user(auth)
    else:
        user_id = current_user.id

    post = Post.query.filter_by(id=post_id, user_id=user_id, deleted=True).one()
    if post.url:
        post.calculate_cross_posts()

    post.deleted = False
    post.deleted_by = None
    post.author.post_count -= 1
    post.community.post_count -= 1
    db.session.commit()
    if src == SRC_WEB:
        flash(_('Post restored.'))

    task_selector('restore_post', user_id=user_id, post_id=post.id)

    if src == SRC_API:
        return user_id, post
    else:
        return


def report_post(post_id, input, src, auth=None):
    if src == SRC_API:
        post = Post.query.filter_by(id=post_id).one()
        user_id = authorise_api_user(auth)
        reason = input['reason']
        description = input['description']
        report_remote = input['report_remote']
    else:
        post = Post.query.get_or_404(post_id)
        user_id = current_user.id
        reason = input.reasons_to_string(input.reasons.data)
        description = input.description.data
        report_remote = input.report_remote.data

    if post.reports == -1:  # When a mod decides to ignore future reports, post.reports is set to -1
        if src == SRC_API:
            raise Exception('already_reported')
        else:
            flash(_('Post has already been reported, thank you!'))
            return

    report = Report(reasons=reason, description=description, type=1, reporter_id=user_id, suspect_post_id=post.id, suspect_community_id=post.community_id,
                    suspect_user_id=post.user_id, in_community_id=post.community_id, source_instance_id=1)
    db.session.add(report)

    # Notify moderators
    already_notified = set()
    for mod in post.community.moderators():
        moderator = User.query.get(mod.user_id)
        if moderator and moderator.is_local():
            notification = Notification(user_id=mod.user_id, title=_('A comment has been reported'),
                                        url=f"https://{current_app.config['SERVER_NAME']}/comment/{post.id}",
                                        author_id=user_id)
            db.session.add(notification)
            already_notified.add(mod.user_id)
    post.reports += 1
    # todo: only notify admins for certain types of report
    for admin in Site.admins():
        if admin.id not in already_notified:
            notify = Notification(title='Suspicious content', url='/admin/reports', user_id=admin.id, author_id=user_id)
            db.session.add(notify)
            admin.unread_notifications += 1
    db.session.commit()

    # federate report to originating instance
    if not post.community.is_local() and report_remote:
        summary = reason
        if description:
            summary += ' - ' + description

        task_selector('report_post', user_id=user_id, post_id=post_id, summary=summary)

    if src == SRC_API:
        return user_id, report
    else:
        return


def lock_post(post_id, locked, src, auth=None):
    if src == SRC_API:
        user = authorise_api_user(auth, return_type='model')
    else:
        user = current_user

    post = Post.query.filter_by(id=post_id).one()
    if locked:
        comments_enabled = False
        modlog_type = 'lock_post'
    else:
        comments_enabled = True
        modlog_type = 'unlock_post'

    if post.community.is_moderator(user) or post.community.is_instance_admin(user):
        post.comments_enabled = comments_enabled
        db.session.commit()
        add_to_modlog_activitypub(modlog_type, user, community_id=post.community_id,
                                  link_text=shorten_string(post.title), link=f'post/{post.id}', reason='')

        if locked:
            if src == SRC_WEB:
                flash(_('%(name)s has been locked.', name=post.title))
            task_selector('lock_post', user_id=user.id, post_id=post_id)
        else:
            if src == SRC_WEB:
                flash(_('%(name)s has been unlocked.', name=post.title))
            task_selector('unlock_post', user_id=user.id, post_id=post_id)

    if src == SRC_API:
        return user.id, post


def sticky_post(post_id: int, featured: bool, src: int, auth=None):
    if src == SRC_API:
        user = authorise_api_user(auth, return_type='model')
    else:
        user = current_user

    post = Post.query.filter_by(id=post_id).one()
    community = post.community

    if post.community.is_moderator(user) or post.community.is_instance_admin(user) or user.is_admin():
        post.sticky = featured
        if featured:
            modlog_type = 'featured_post'
        else:
            modlog_type = 'unfeatured_post'
        if not community.ap_featured_url:
            community.ap_featured_url = community.ap_profile_id + '/featured'
        db.session.commit()
        add_to_modlog_activitypub(modlog_type, user, community_id=post.community_id,
                                  link_text=shorten_string(post.title), link=f'post/{post.id}', reason='')

    if featured:
        task_selector('sticky_post', user_id=user.id, post_id=post_id)
    else:
        task_selector('unsticky_post', user_id=user.id, post_id=post_id)

    return user.id, post


# mod deletes
def mod_remove_post(post_id, reason, src, auth):
    if src == SRC_API:
        user = authorise_api_user(auth, return_type='model')
    else:
        user = current_user

    post = Post.query.filter_by(id=post_id, user_id=user.id, deleted=False).one()
    if not post.community.is_moderator(user) and not post.community.is_instance_admin(user):
        raise Exception('Does not have permission')

    if post.url:
        post.calculate_cross_posts(delete_only=True)

    post.deleted = True
    post.deleted_by = user.id
    post.author.post_count -= 1
    post.community.post_count -= 1
    db.session.commit()
    if src == SRC_WEB:
        flash(_('Post deleted.'))

    add_to_modlog_activitypub('delete_post', user, community_id=post.community_id,
                              link_text=shorten_string(post.title), link=f'post/{post.id}', reason=reason)

    task_selector('delete_post', user_id=user.id, post_id=post.id, reason=reason)

    if src == SRC_API:
        return user.id, post
    else:
        return


def mod_restore_post(post_id, reason, src, auth):
    if src == SRC_API:
        user = authorise_api_user(auth, return_type='model')
    else:
        user = current_user

    post = Post.query.filter_by(id=post_id, user_id=user.id, deleted=True).one()
    if not post.community.is_moderator(user) and not post.community.is_instance_admin(user):
        raise Exception('Does not have permission')

    if post.url:
        post.calculate_cross_posts()

    post.deleted = False
    post.deleted_by = None
    post.author.post_count -= 1
    post.community.post_count -= 1
    db.session.commit()
    if src == SRC_WEB:
        flash(_('Post restored.'))

    add_to_modlog_activitypub('restore_post', user, community_id=post.community_id,
                              link_text=shorten_string(post.title), link=f'post/{post.id}', reason=reason)

    task_selector('restore_post', user_id=user.id, post_id=post.id, reason=reason)

    if src == SRC_API:
        return user.id, post
    else:
        return


