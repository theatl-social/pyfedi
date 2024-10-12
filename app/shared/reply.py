from app import cache, db
from app.activitypub.signature import default_context, post_request_in_background, post_request
from app.community.util import send_to_remote_instance
from app.constants import *
from app.models import NotificationSubscription, PostReply, PostReplyBookmark, User, utcnow
from app.utils import gibberish, instance_banned, render_template, authorise_api_user, recently_upvoted_post_replies, recently_downvoted_post_replies, shorten_string, \
                      piefed_markdown_to_lemmy_markdown, markdown_to_html, ap_datetime

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
        reply = PostReply.query.get(reply_id)
        if not reply:
            raise Exception('reply_not_found')
        user = authorise_api_user(auth, return_type='model')
    else:
        reply = PostReply.query.get_or_404(reply_id)
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
    if src == SRC_API:
        post_reply = PostReply.query.get(comment_id)
        if not post_reply or post_reply.deleted:
            raise Exception('comment_not_found')
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
        post_reply = PostReply.query.get(comment_id)
        if not post_reply or post_reply.deleted:
            raise Exception('comment_not_found')
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
        post_reply = PostReply.query.get(post_reply_id)
        if not post_reply or post_reply.deleted:
            raise Exception('comment_not_found')
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
        if not basic_rate_limit_check(user):
            raise Exception('rate_limited')
        content = input['body']
        notify_author = input['notify_author']
        language_id = input['language_id']
    else:
        user = current_user
        content = input.body.data
        notify_author = input.notify_author.data
        language_id = input.language_id.data

    if parent_id:
        parent_reply = PostReply.query.get(parent_id)
        if not parent_reply:
            raise Exception('parent_reply_not_found')
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

    # federation
    if parent_id:
        in_reply_to = parent_reply
    else:
        in_reply_to = post

    if not post.community.local_only:
        reply_json = {
          'type': 'Note',
          'id': reply.public_url(),
          'attributedTo': user.public_url(),
          'to': [
            'https://www.w3.org/ns/activitystreams#Public'
          ],
          'cc': [
            post.community.public_url(),
            in_reply_to.author.public_url()
          ],
          'content': reply.body_html,
          'inReplyTo': in_reply_to.profile_id(),
          'url': reply.profile_id(),
          'mediaType': 'text/html',
          'source': {'content': reply.body, 'mediaType': 'text/markdown'},
          'published': ap_datetime(utcnow()),
          'distinguished': False,
          'audience': post.community.public_url(),
          'contentMap': {
            'en': reply.body_html
          },
          'language': {
            'identifier': reply.language_code(),
            'name': reply.language_name()
          }
        }
        create_json = {
          '@context': default_context(),
          'type': 'Create',
          'actor': user.public_url(),
          'audience': post.community.public_url(),
          'to': [
            'https://www.w3.org/ns/activitystreams#Public'
          ],
          'cc': [
            post.community.public_url(),
            in_reply_to.author.public_url()
          ],
          'object': reply_json,
          'id': f"https://{current_app.config['SERVER_NAME']}/activities/create/{gibberish(15)}"
        }
        if in_reply_to.notify_author and in_reply_to.author.ap_id is not None:
            reply_json['tag'] = [
              {
                'href': in_reply_to.author.public_url(),
                'name': in_reply_to.author.mention_tag(),
                'type': 'Mention'
              }
            ]
            create_json['tag'] = [
              {
                'href': in_reply_to.author.public_url(),
                'name': in_reply_to.author.mention_tag(),
                'type': 'Mention'
              }
            ]
        if not post.community.is_local():    # this is a remote community, send it to the instance that hosts it
            success = post_request(post.community.ap_inbox_url, create_json, user.private_key,
                                    user.public_url() + '#main-key')
            if src == SRC_WEB:
                if success is False or isinstance(success, str):
                    flash('Failed to send reply', 'error')
        else:                                # local community - send it to followers on remote instances
            del create_json['@context']
            announce = {
              'id': f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}",
              'type': 'Announce',
              'to': [
                'https://www.w3.org/ns/activitystreams#Public'
              ],
              'actor': post.community.public_url(),
              'cc': [
                post.community.ap_followers_url
              ],
              '@context': default_context(),
              'object': create_json
            }
            for instance in post.community.following_instances():
                if instance.inbox and not user.has_blocked_instance(instance.id) and not instance_banned(instance.domain):
                    send_to_remote_instance(instance.id, post.community.id, announce)

        # send copy of Note to comment author (who won't otherwise get it if no-one else on their instance is subscribed to the community)
        if not in_reply_to.author.is_local() and in_reply_to.author.ap_domain != reply.community.ap_domain:
            if not post.community.is_local() or (post.community.is_local and not post.community.has_followers_from_domain(in_reply_to.author.ap_domain)):
                success = post_request(in_reply_to.author.ap_inbox_url, create_json, user.private_key, user.public_url() + '#main-key')
                if success is False or isinstance(success, str):
                    # sending to shared inbox is good enough for Mastodon, but Lemmy will reject it the local community has no followers
                    personal_inbox = in_reply_to.author.public_url() + '/inbox'
                    post_request(personal_inbox, create_json, user.private_key, user.public_url() + '#main-key')


    if src == SRC_API:
        return user.id, reply
    else:
        return reply


def edit_reply(input, reply, post, src, auth=None):
    if src == SRC_API:
        user = authorise_api_user(auth, return_type='model')
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

    if reply.parent_id:
        in_reply_to = PostReply.query.get(reply.parent_id)
    else:
        in_reply_to = post

    # federate edit
    if not post.community.local_only:
        reply_json = {
          'type': 'Note',
          'id': reply.public_url(),
          'attributedTo': user.public_url(),
          'to': [
            'https://www.w3.org/ns/activitystreams#Public'
          ],
          'cc': [
            post.community.public_url(),
            in_reply_to.author.public_url()
          ],
          'content': reply.body_html,
          'inReplyTo': in_reply_to.profile_id(),
          'url': reply.public_url(),
          'mediaType': 'text/html',
          'source': {'content': reply.body, 'mediaType': 'text/markdown'},
          'published': ap_datetime(reply.posted_at),
          'updated': ap_datetime(reply.edited_at),
          'distinguished': False,
          'audience': post.community.public_url(),
          'contentMap': {
            'en': reply.body_html
          },
          'language': {
            'identifier': reply.language_code(),
            'name': reply.language_name()
          }
        }
        update_json = {
          '@context': default_context(),
          'type': 'Update',
          'actor': user.public_url(),
          'audience': post.community.public_url(),
          'to': [
            'https://www.w3.org/ns/activitystreams#Public'
          ],
          'cc': [
            post.community.public_url(),
            in_reply_to.author.public_url()
          ],
          'object': reply_json,
          'id': f"https://{current_app.config['SERVER_NAME']}/activities/update/{gibberish(15)}"
        }
        if in_reply_to.notify_author and in_reply_to.author.ap_id is not None:
            reply_json['tag'] = [
              {
                'href': in_reply_to.author.public_url(),
                'name': in_reply_to.author.mention_tag(),
                'type': 'Mention'
              }
            ]
            update_json['tag'] = [
              {
                'href': in_reply_to.author.public_url(),
                'name': in_reply_to.author.mention_tag(),
                'type': 'Mention'
              }
            ]
        if not post.community.is_local():    # this is a remote community, send it to the instance that hosts it
            success = post_request(post.community.ap_inbox_url, update_json, user.private_key,
                                                               user.public_url() + '#main-key')
            if src == SRC_WEB:
                if success is False or isinstance(success, str):
                    flash('Failed to send send edit to remote server', 'error')
        else:                                # local community - send it to followers on remote instances
            del update_json['@context']
            announce = {
              'id': f"https://{current_app.config['SERVER_NAME']}/activities/announce/{gibberish(15)}",
              'type': 'Announce',
              'to': [
                'https://www.w3.org/ns/activitystreams#Public'
              ],
              'actor': post.community.public_url(),
              'cc': [
                post.community.ap_followers_url
              ],
              '@context': default_context(),
              'object': update_json
            }

            for instance in post.community.following_instances():
                if instance.inbox and not user.has_blocked_instance(instance.id) and not instance_banned(instance.domain):
                    send_to_remote_instance(instance.id, post.community.id, announce)

        # send copy of Note to post author (who won't otherwise get it if no-one else on their instance is subscribed to the community)
        if not in_reply_to.author.is_local() and in_reply_to.author.ap_domain != reply.community.ap_domain:
            if not post.community.is_local() or (post.community.is_local and not post.community.has_followers_from_domain(in_reply_to.author.ap_domain)):
                success = post_request(in_reply_to.author.ap_inbox_url, update_json, user.private_key, user.public_url() + '#main-key')
                if success is False or isinstance(success, str):
                    # sending to shared inbox is good enough for Mastodon, but Lemmy will reject it the local community has no followers
                    personal_inbox = in_reply_to.author.public_url() + '/inbox'
                    post_request(personal_inbox, update_json, user.private_key, user.public_url() + '#main-key')

    if src == SRC_API:
        return user.id, reply
    else:
        return
