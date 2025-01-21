from app import cache, db
from app.activitypub.signature import default_context, post_request_in_background, post_request
from app.community.util import send_to_remote_instance
from app.constants import *
from app.models import Instance, Notification, NotificationSubscription, Post, PostReply, PostReplyBookmark, Report, Site, User, utcnow
from app.shared.tasks import task_selector
from app.utils import gibberish, instance_banned, render_template, authorise_api_user, recently_upvoted_post_replies, recently_downvoted_post_replies, shorten_string, \
                      piefed_markdown_to_lemmy_markdown, markdown_to_html, ap_datetime, add_to_modlog_activitypub

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
    if src == SRC_API:
        reply = PostReply.query.filter_by(id=reply_id).one()
        user = authorise_api_user(auth, return_type='model')
    else:
        reply = PostReply.query.get_or_404(reply_id)
        user = current_user

    undo = reply.vote(user, vote_direction)

    task_selector('vote_for_reply', user_id=user.id, reply_id=reply_id, vote_to_undo=undo, vote_direction=vote_direction)

    if src == SRC_API:
        return user.id
    else:
        recently_upvoted = []
        recently_downvoted = []
        if vote_direction == 'upvote' and undo is None:
            recently_upvoted = [reply_id]
        elif vote_direction == 'downvote' and undo is None:
            recently_downvoted = [reply_id]

        return render_template('post/_reply_voting_buttons.html', comment=reply,
                               recently_upvoted_replies=recently_upvoted,
                               recently_downvoted_replies=recently_downvoted,
                               community=reply.community)


# function can be shared between WEB and API (only API calls it for now)
# post_reply_bookmark in app/post/routes would just need to do 'return bookmark_the_post_reply(comment_id, SRC_WEB)'
def bookmark_the_post_reply(comment_id: int, src, auth=None):
    if src == SRC_API:
        post_reply = PostReply.query.filter_by(id=comment_id, deleted=False).one()
        user_id = authorise_api_user(auth)
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
    if src == SRC_API:
        post_reply = PostReply.query.filter_by(id=comment_id, deleted=False).one()
        user_id = authorise_api_user(auth)
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


# function can be shared between WEB and API (only API calls it for now)
# post_reply_notification in app/post/routes would just need to do 'return toggle_post_reply_notification(post_reply_id, SRC_WEB)'
def toggle_post_reply_notification(post_reply_id: int, src, auth=None):
    # Toggle whether the current user is subscribed to notifications about replies to this reply or not
    if src == SRC_API:
        post_reply = PostReply.query.filter_by(id=post_reply_id, deleted=False).one()
        user_id = authorise_api_user(auth)
    else:
        post_reply = PostReply.query.get_or_404(post_reply_id)
        if post_reply.deleted:
            abort(404)
        user_id = current_user.id

    existing_notification = NotificationSubscription.query.filter(NotificationSubscription.entity_id == post_reply.id,
                                                                  NotificationSubscription.user_id == user_id,
                                                                  NotificationSubscription.type == NOTIF_REPLY).first()
    if existing_notification:
        db.session.delete(existing_notification)
        db.session.commit()
    else:  # no subscription yet, so make one
        new_notification = NotificationSubscription(name=shorten_string(_('Replies to my comment on %(post_title)s',
                                                    post_title=post_reply.post.title)), user_id=user_id, entity_id=post_reply.id,
                                                    type=NOTIF_REPLY)
        db.session.add(new_notification)
        db.session.commit()

    if src == SRC_API:
        return user_id
    else:
        return render_template('post/_reply_notification_toggle.html', comment={'comment': post_reply})


# there are undoubtedly better algos for this
def basic_rate_limit_check(user):
    weeks_active = int((utcnow() - user.created).days / 7)
    score = user.post_reply_count * weeks_active

    if score > 100:
        score = 10
    else:
        score = int(score/10)

    # a user with a 10-week old account, who has made 10 replies, will score 10, so their rate limit will be 0
    # a user with a new account, and/or has made zero replies, will score 0 (so will have to wait 10 minutes between each new comment)
    # other users will score from 1-9, so their rate limits will be between 9 and 1 minutes.

    rate_limit = (10-score)*60

    recent_reply = cache.get(f'{user.id} has recently replied')
    if not recent_reply:
        cache.set(f'{user.id} has recently replied', True, timeout=rate_limit)
        return True
    else:
        return False


def make_reply(input, post, parent_id, src, auth=None):
    if src == SRC_API:
        user = authorise_api_user(auth, return_type='model')
        #if not basic_rate_limit_check(user):
        #    raise Exception('rate_limited')
        content = input['body']
        notify_author = input['notify_author']
        language_id = input['language_id']
    else:
        user = current_user
        content = input.body.data
        notify_author = input.notify_author.data
        language_id = input.language_id.data

    if parent_id:
        parent_reply = PostReply.query.filter_by(id=parent_id).one()
    else:
        parent_reply = None


    # WEBFORM would call 'make_reply' in a try block, so any exception from 'new' would bubble-up for it to handle
    reply = PostReply.new(user, post, in_reply_to=parent_reply, body=piefed_markdown_to_lemmy_markdown(content),
                          body_html=markdown_to_html(content), notify_author=notify_author,
                          language_id=language_id)

    user.language_id = language_id
    reply.ap_id = reply.profile_id()
    db.session.commit()
    if src == SRC_WEB:
        input.body.data = ''
        flash('Your comment has been added.')

    task_selector('make_reply', user_id=user.id, reply_id=reply.id, parent_id=parent_id)

    if src == SRC_API:
        return user.id, reply
    else:
        return reply


def edit_reply(input, reply, post, src, auth=None):
    if src == SRC_API:
        user = authorise_api_user(auth, return_type='model', id_match=reply.user_id)
        content = input['body']
        notify_author = input['notify_author']
        language_id = input['language_id']
    else:
        user = current_user
        content = input.body.data
        notify_author = input.notify_author.data
        language_id = input.language_id.data

    reply.body = piefed_markdown_to_lemmy_markdown(content)
    reply.body_html = markdown_to_html(content)
    reply.notify_author = notify_author
    reply.community.last_active = utcnow()
    reply.edited_at = utcnow()
    reply.language_id = language_id
    db.session.commit()


    if src == SRC_WEB:
        flash(_('Your changes have been saved.'), 'success')

    task_selector('edit_reply', user_id=user.id, reply_id=reply.id, parent_id=reply.parent_id)

    if src == SRC_API:
        return user.id, reply
    else:
        return


# just for deletes by owner (mod deletes are classed as 'remove')
def delete_reply(reply_id, src, auth):
    if src == SRC_API:
        user_id = authorise_api_user(auth)
    else:
        user_id = current_user.id

    reply = PostReply.query.filter_by(id=reply_id, user_id=user_id, deleted=False).one()
    reply.deleted = True
    reply.deleted_by = user_id

    if not reply.author.bot:
        reply.post.reply_count -= 1
    reply.author.post_reply_count -= 1
    db.session.commit()
    if src == SRC_WEB:
        flash(_('Comment deleted.'))

    task_selector('delete_reply', user_id=user_id, reply_id=reply.id)

    if src == SRC_API:
        return user_id, reply
    else:
        return


def restore_reply(reply_id, src, auth):
    if src == SRC_API:
        user_id = authorise_api_user(auth)
    else:
        user_id = current_user.id

    reply = PostReply.query.filter_by(id=reply_id, user_id=user_id, deleted=True).one()
    reply.deleted = False
    reply.deleted_by = None

    if not reply.author.bot:
        reply.post.reply_count += 1
    reply.author.post_reply_count += 1
    db.session.commit()
    if src == SRC_WEB:
        flash(_('Comment restored.'))

    task_selector('restore_reply', user_id=user_id, reply_id=reply.id)

    if src == SRC_API:
        return user_id, reply
    else:
        return


def report_reply(reply_id, input, src, auth=None):
    if src == SRC_API:
        reply = PostReply.query.filter_by(id=reply_id).one()
        user_id = authorise_api_user(auth)
        reason = input['reason']
        description = input['description']
        report_remote = input['report_remote']
    else:
        reply = PostReply.query.get_or_404(reply_id)
        user_id = current_user.id
        reason = input.reasons_to_string(input.reasons.data)
        description = input.description.data
        report_remote = input.report_remote.data

    if reply.reports == -1:  # When a mod decides to ignore future reports, reply.reports is set to -1
        if src == SRC_API:
            raise Exception('already_reported')
        else:
            flash(_('Comment has already been reported, thank you!'))
            return

    report = Report(reasons=reason, description=description, type=2, reporter_id=user_id, suspect_post_id=reply.post.id, suspect_community_id=reply.community.id,
                    suspect_user_id=reply.author.id, suspect_post_reply_id=reply.id, in_community_id=reply.community.id, source_instance_id=1)
    db.session.add(report)

    # Notify moderators
    already_notified = set()
    for mod in reply.community.moderators():
        moderator = User.query.get(mod.user_id)
        if moderator and moderator.is_local():
            notification = Notification(user_id=mod.user_id, title=_('A comment has been reported'),
                                        url=f"https://{current_app.config['SERVER_NAME']}/comment/{reply.id}",
                                        author_id=user_id)
            db.session.add(notification)
            already_notified.add(mod.user_id)
    reply.reports += 1
    # todo: only notify admins for certain types of report
    for admin in Site.admins():
        if admin.id not in already_notified:
            notify = Notification(title='Suspicious content', url='/admin/reports', user_id=admin.id, author_id=user_id)
            db.session.add(notify)
            admin.unread_notifications += 1
    db.session.commit()

    # federate report to originating instance
    if not reply.community.is_local() and report_remote:
        summary = reason
        if description:
            summary += ' - ' + description

        task_selector('report_reply', user_id=user_id, reply_id=reply_id, summary=summary)

    if src == SRC_API:
        return user_id, report
    else:
        return


# mod deletes
def mod_remove_reply(reply_id, reason, src, auth):
    if src == SRC_API:
        user = authorise_api_user(auth, return_type='model')
    else:
        user = current_user

    reply = PostReply.query.filter_by(id=reply_id, deleted=False).one()
    if not reply.community.is_moderator(user) and not reply.community.is_instance_admin(user):
        raise Exception('Does not have permission')

    reply.deleted = True
    reply.deleted_by = user.id
    if not reply.author.bot:
        reply.post.reply_count -= 1
    reply.author.post_reply_count -= 1
    db.session.commit()
    if src == SRC_WEB:
        flash(_('Comment deleted.'))

    add_to_modlog_activitypub('delete_post_reply', user, community_id=reply.community_id,
                              link_text=shorten_string(f'comment on {shorten_string(reply.post.title)}'),
                              link=f'post/{reply.post_id}#comment_{reply.id}', reason=reason)

    task_selector('delete_reply', user_id=user.id, reply_id=reply.id, reason=reason)

    if src == SRC_API:
        return user.id, reply
    else:
        return


def mod_restore_reply(reply_id, reason, src, auth):
    if src == SRC_API:
        user = authorise_api_user(auth, return_type='model')
    else:
        user = current_user

    reply = PostReply.query.filter_by(id=reply_id, deleted=True).one()
    if not reply.community.is_moderator(user) and not reply.community.is_instance_admin(user):
        raise Exception('Does not have permission')

    reply.deleted = False
    reply.deleted_by = None
    if not reply.author.bot:
        reply.post.reply_count += 1
    reply.author.post_reply_count += 1
    db.session.commit()
    if src == SRC_WEB:
        flash(_('Comment restored.'))

    add_to_modlog_activitypub('restore_post_reply', user, community_id=reply.community_id,
                              link_text=shorten_string(f'comment on {shorten_string(reply.post.title)}'),
                              link=f'post/{reply.post_id}#comment_{reply.id}', reason=reason)

    task_selector('restore_reply', user_id=user.id, reply_id=reply.id, reason=reason)

    if src == SRC_API:
        return user.id, reply
    else:
        return
