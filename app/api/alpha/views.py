from __future__ import annotations

from flask import current_app, g
from sqlalchemy import text, func

from app import cache, db
from app.constants import *
from app.models import ChatMessage, Community, CommunityMember, Language, Instance, Post, PostReply, User, \
    AllowedInstances, BannedInstances, utcnow, Site
from app.utils import blocked_communities, blocked_instances, blocked_users, communities_banned_from


# 'stub' param: set to True to exclude optional fields


def post_view(post: Post | int, variant, stub=False, user_id=None, my_vote=0, communities_moderating=None, banned_from=None,
              bookmarked_posts=None, post_subscriptions=None, communities_joined=None, read_posts=None) -> dict:
    if isinstance(post, int):
        post = Post.query.filter_by(id=post, deleted=False).one()

    # Variant 1 - models/post/post.dart
    if variant == 1:
        include = ['id', 'title', 'user_id', 'community_id', 'deleted', 'nsfw', 'sticky']
        v1 = {column.name: getattr(post, column.name) for column in post.__table__.columns if column.name in include}
        v1.update({'published': post.posted_at.isoformat() + 'Z',
                   'ap_id': post.profile_id(),
                   'local': post.is_local(),
                   'language_id': post.language_id if post.language_id else 0,
                   'removed': False,
                   'locked': not post.comments_enabled})
        if post.body:
            v1['body'] = post.body
        if post.edited_at:
            v1['edited_at'] = post.edited_at.isoformat() + 'Z'
        if post.deleted == True:
            if post.deleted_by and post.user_id != post.deleted_by:
                v1['removed'] = True
                v1['deleted'] = False
        if post.type == POST_TYPE_LINK or post.type == POST_TYPE_VIDEO:
            if post.url:
                v1['url'] = post.url
            if post.image_id:
                v1['thumbnail_url'] = post.image.medium_url()
                v1['small_thumbnail_url'] = post.image.thumbnail_url()
                if post.image.alt_text:
                    v1['alt_text'] = post.image.alt_text
        if post.type == POST_TYPE_IMAGE:
            if post.image_id:
                v1['url'] = post.image.view_url()
                v1['thumbnail_url'] = post.image.medium_url()
                v1['small_thumbnail_url'] = post.image.thumbnail_url()
                if post.image.alt_text:
                    v1['alt_text'] = post.image.alt_text

        return v1

    # Variant 2 - views/post_view.dart - /post/list api endpoint
    if variant == 2:
        # counts - models/post/post_aggregates.dart
        counts = {'post_id': post.id, 'comments': post.reply_count, 'score': post.score, 'upvotes': post.up_votes,
                  'downvotes': post.down_votes,
                  'published': post.posted_at.isoformat() + 'Z',
                  'newest_comment_time': post.last_active.isoformat() + 'Z'}
        if user_id:
            if bookmarked_posts is None:
                bookmarked = db.session.execute(
                    text('SELECT user_id FROM "post_bookmark" WHERE post_id = :post_id and user_id = :user_id'),
                    {'post_id': post.id, 'user_id': user_id}).scalar()
            else:
                bookmarked = post.id in bookmarked_posts

            if post_subscriptions is None:
                post_sub = db.session.execute(text(
                    'SELECT user_id FROM "notification_subscription" WHERE type = :type and entity_id = :entity_id and user_id = :user_id'),
                                              {'type': NOTIF_POST, 'entity_id': post.id, 'user_id': user_id}).scalar()
            else:
                post_sub = post.id in post_subscriptions

            if communities_joined is None:
                followed = db.session.execute(text(
                    'SELECT user_id FROM "community_member" WHERE community_id = :community_id and user_id = :user_id'),
                                              {"community_id": post.community_id, "user_id": user_id}).scalar()
            else:
                followed = post.community_id in communities_joined

            if read_posts is None:
                read_post = db.session.execute(
                    text('SELECT user_id FROM "read_posts" WHERE read_post_id = :post_id and user_id = :user_id'),
                    {'post_id': post.id, 'user_id': user_id}).scalar()
            else:
                read_post = post.id in read_posts
        else:
            bookmarked = post_sub = followed = read_post = False
        if not stub:
            if banned_from is None:
                banned = post.community_id in communities_banned_from(post.user_id)
            else:
                banned = post.community_id in banned_from
            if communities_moderating is None:
                moderator = post.community.is_moderator(post.author) or post.community.is_owner(post.author)
            else:
                moderator = post.community_id in communities_moderating
            admin = post.user_id in g.admin_ids
        else:
            banned = False
            moderator = False
            admin = False
        if my_vote == 0 and user_id is not None:
            post_vote = db.session.execute(
                text('SELECT effect FROM "post_vote" WHERE post_id = :post_id and user_id = :user_id'),
                {'post_id': post.id, 'user_id': user_id}).scalar()
            effect = post_vote if post_vote else 0
        else:
            effect = my_vote

        my_vote = int(effect)
        saved = True if bookmarked else False
        read = True if read_post else False
        activity_alert = True if post_sub else False
        creator_banned_from_community = True if banned else False
        creator_is_moderator = True if moderator else False
        creator_is_admin = True if admin else False
        subscribe_type = 'Subscribed' if followed else 'NotSubscribed'
        v2 = {'post': post_view(post=post, variant=1, stub=stub), 'counts': counts, 'banned_from_community': False,
              'subscribed': subscribe_type,
              'saved': saved, 'read': read, 'hidden': False, 'unread_comments': post.reply_count, 'my_vote': my_vote,
              'activity_alert': activity_alert,
              'creator_banned_from_community': creator_banned_from_community,
              'creator_is_moderator': creator_is_moderator, 'creator_is_admin': creator_is_admin}

        creator = user_view(user=post.user_id, variant=1, stub=True, flair_community_id=post.community_id)
        community = community_view(community=post.community_id, variant=1, stub=True)
        if user_id:
            user = User.query.get(user_id)
            post_community = Community.query.get(post.community_id)
            can_auth_user_moderate = post_community.is_moderator(user) or post_community.is_owner(user)
            v2.update({'canAuthUserModerate': can_auth_user_moderate})

        v2.update({'creator': creator, 'community': community})

        return v2

    # Variant 3 - models/post/get_post_response.dart - /post api endpoint
    if variant == 3:
        modlist = cached_modlist_for_community(post.community_id)

        xplist = []
        if post.cross_posts:
            for xp_id in post.cross_posts:
                entry = post_view(post=xp_id, variant=2, stub=True)
                xplist.append(entry)

        v3 = {'post_view': post_view(post=post, variant=2, user_id=user_id),
              'community_view': community_view(community=post.community_id, variant=2),
              'moderators': modlist,
              'cross_posts': xplist}

        return v3

    # Variant 4 - models/post/post_response.dart - api endpoint for /post/like and post/save
    if variant == 4:
        v4 = {'post_view': post_view(post=post, variant=2, user_id=user_id)}

        return v4

    # Variant 5 - from resolve_object
    if variant == 5:
        v5 = {'post': post_view(post=post, variant=2, user_id=user_id)}

        return v5


# 'user' param can be anyone (including the logged in user), 'user_id' param belongs to the user making the request
def user_view(user: User | int, variant, stub=False, user_id=None, flair_community_id=None) -> dict:
    if isinstance(user, int):
        user = User.query.filter_by(id=user).one()

    # Variant 1 - models/person/person.dart
    if variant == 1:
        include = ['id', 'user_name', 'title', 'banned', 'deleted', 'bot']
        v1 = {column.name: getattr(user, column.name) for column in user.__table__.columns if column.name in include}
        v1.update({'published': user.created.isoformat() + 'Z',
                   'actor_id': user.public_url(),
                   'local': user.is_local(),
                   'instance_id': user.instance_id if user.instance_id else 1})
        if user.about and not stub:
            v1['about'] = user.about
        if user.avatar_id:
            v1['avatar'] = user.avatar.medium_url()
        if user.cover_id and not stub:
            v1['banner'] = user.cover.medium_url()
        if flair_community_id:
            flair = user.community_flair(flair_community_id)
            if flair:
                v1['flair'] = flair

        return v1

    # Variant 2 - views/person_view.dart
    if variant == 2:
        counts = {'person_id': user.id, 'post_count': user.post_count, 'comment_count': user.post_reply_count}
        v2 = {'person': user_view(user=user, variant=1), 'counts': counts, 'is_admin': user.is_admin()}
        user_sub = False
        if user_id and user_id != user.id:
            user_sub = db.session.execute(text(
                'SELECT user_id FROM "notification_subscription" WHERE type = :type and entity_id = :entity_id and user_id = :user_id'),
                                          {'type': NOTIF_USER, 'entity_id': user.id, 'user_id': user_id}).scalar()
        activity_alert = True if user_sub else False
        v2 = {'person': user_view(user=user, variant=1, flair_community_id=flair_community_id), 'activity_alert': activity_alert, 'counts': counts,
              'is_admin': user.is_admin()}
        return v2

    # Variant 3 - models/user/get_person_details.dart - /user?person_id api endpoint
    if variant == 3:
        modlist = cached_modlist_for_user(user)

        v3 = {'person_view': user_view(user=user, variant=2, user_id=user_id),
              'moderates': modlist,
              'posts': [],
              'comments': []}
        return v3

    # Variant 4 - models/user/block_person_response.dart - /user/block api endpoint
    if variant == 4:
        block = db.session.execute(
            text('SELECT blocker_id FROM "user_block" WHERE blocker_id = :blocker_id and blocked_id = :blocked_id'),
            {'blocker_id': user_id, 'blocked_id': user.id}).scalar()
        blocked = True if block else False
        v4 = {'person_view': user_view(user=user, variant=2, user_id=user_id),
              'blocked': blocked}
        return v4

    # Variant 5 - PersonResponse (for user activity_alert subscriptions, to be consistent with the response to community activity_alert subscriptions)
    if variant == 5:
        v5 = {'person_view': user_view(user=user, variant=2, user_id=user_id, flair_community_id=flair_community_id)}
        return v5

    # Variant 6 - User Settings - api/user.dart saveUserSettings
    if variant == 6:
        v6 = {
            "local_user_view": {
                "local_user": {
                    "show_nsfw": not user.hide_nsfw == 1,
                    "default_sort_type": user.default_sort.capitalize(),
                    "default_listing_type": user.default_filter.capitalize(),
                    "show_scores": True,
                    "show_bot_accounts": not user.ignore_bots == 1,
                    "show_read_posts": not user.hide_read_posts == True
                },
                "person": {
                    "id": user.id,
                    "user_name": user.user_name,
                    "banned": user.banned,
                    "published": user.created.isoformat() + 'Z',
                    "actor_id": user.public_url(),
                    "local": True,
                    "deleted": user.deleted,
                    "bot": user.bot,
                    "instance_id": 1,
                    "title": user.display_name(),
                    "avatar": user.avatar.medium_url() if user.avatar_id else None,
                    "banner": user.cover.medium_url() if user.cover_id else None,
                },
                "counts": {
                    "person_id": user.id,
                    "post_count": user.post_count,
                    "comment_count": user.post_reply_count
                }
            },
            "moderates": moderating_communities_view(user),
            "follows": joined_communities_view(user),
            "community_blocks": blocked_communities_view(user),
            "instance_blocks": blocked_instances_view(user),
            "person_blocks": blocked_people_view(user),
            "discussion_languages": []  # TODO
        }
        return v6

    # Variant 7 - from resolve_object
    if variant == 7:
        v7 = {'person': user_view(user=user, variant=2, user_id=user_id)}
        return v7


def community_view(community: Community | int | str, variant, stub=False, user_id=None) -> dict:
    if isinstance(community, int):
        community = Community.query.filter_by(id=community).one()
    elif isinstance(community, str):
        name, ap_domain = community.strip().split('@')
        community = Community.query.filter_by(name=name, ap_domain=ap_domain).first()
        if community is None:
            community = Community.query.filter(func.lower(Community.name) == name.lower(),
                                               func.lower(Community.ap_domain) == ap_domain.lower()).one()

    # Variant 1 - models/community/community.dart
    if variant == 1:
        include = ['id', 'name', 'title', 'banned', 'nsfw', 'restricted_to_mods']
        v1 = {column.name: getattr(community, column.name) for column in community.__table__.columns if
              column.name in include}
        v1.update({'published': community.created_at.isoformat() + 'Z',
                   'updated': community.created_at.isoformat() + 'Z',
                   'deleted': community.banned,
                   'removed': False,
                   'actor_id': community.public_url(),
                   'local': community.is_local(),
                   'hidden': not community.show_all,
                   'instance_id': community.instance_id if community.instance_id else 1,
                   'ap_domain': community.ap_domain})
        if community.description and not stub:
            v1['description'] = community.description
        if not stub:
            v1['posting_warning'] = community.posting_warning
        if community.icon_id:
            v1['icon'] = community.icon.medium_url()
        if community.image_id and not stub:
            v1['banner'] = community.image.medium_url()

        return v1

    # Variant 2 - views/community_view.dart - /community/list api endpoint
    if variant == 2:
        # counts - models/community/community_aggregates
        include = ['id', 'subscriptions_count', 'total_subscriptions_count', 'post_count', 'post_reply_count',
                   'active_daily', 'active_weekly', 'active_monthly', 'active_6monthly']
        counts = {column.name: getattr(community, column.name) for column in community.__table__.columns if
                  column.name in include}
        if counts['total_subscriptions_count'] == None or counts['total_subscriptions_count'] == 0:
            counts['total_subscriptions_count'] = counts['subscriptions_count']
        counts.update({'published': community.created_at.isoformat() + 'Z'})
        if user_id:
            followed = db.session.execute(text(
                'SELECT user_id FROM "community_member" WHERE community_id = :community_id and user_id = :user_id'),
                                          {"community_id": community.id, "user_id": user_id}).scalar()
            blocked = True if community.id in blocked_communities(user_id) else False
            community_sub = db.session.execute(text(
                'SELECT user_id FROM "notification_subscription" WHERE type = :type and entity_id = :entity_id and user_id = :user_id'),
                                               {'type': NOTIF_COMMUNITY, 'entity_id': community.id,
                                                'user_id': user_id}).scalar()
        else:
            followed = blocked = community_sub = False
        subscribe_type = 'Subscribed' if followed else 'NotSubscribed'
        activity_alert = True if community_sub else False
        v2 = {'community': community_view(community=community, variant=1, stub=stub), 'subscribed': subscribe_type,
              'blocked': blocked, 'activity_alert': activity_alert, 'counts': counts}
        return v2

    # Variant 3 - models/community/get_community_response.dart - /community api endpoint
    if variant == 3:
        modlist = cached_modlist_for_community(community.id)

        v3 = {'community_view': community_view(community=community, variant=2, stub=False, user_id=user_id),
              'moderators': modlist,
              'discussion_languages': []}
        return v3

    # Variant 4 - models/community/community_response.dart - /community/follow api endpoint
    if variant == 4:
        v4 = {'community_view': community_view(community=community, variant=2, stub=False, user_id=user_id),
              'discussion_languages': []}
        return v4

    # Variant 5 - models/community/block_community_response.dart - /community/block api endpoint
    if variant == 5:
        block = db.session.execute(
            text('SELECT user_id FROM "community_block" WHERE user_id = :user_id and community_id = :community_id'),
            {'user_id': user_id, 'community_id': community.id}).scalar()
        blocked = True if block else False
        v5 = {'community_view': community_view(community=community, variant=2, stub=False, user_id=user_id),
              'blocked': blocked}
        return v5

    # Variant 6 - from resolve_object
    if variant == 6:
        v6 = {'community': community_view(community=community, variant=2, stub=False, user_id=user_id)}
        return v6


# emergency function - shouldn't be called in normal circumstances
@cache.memoize(timeout=86400)
def calculate_path(reply):
    path = [0, reply.id]
    if reply.depth == 1:
        path = [0, reply.parent_id, reply.id]
    elif reply.depth > 1:
        path = [0]
        parent_id = reply.parent_id
        depth = reply.depth - 1
        path_ids = [reply.id, reply.parent_id]
        while depth > 0:
            pid = db.session.execute(text('SELECT parent_id FROM "post_reply" WHERE id = :parent_id'),
                                     {'parent_id': parent_id}).scalar()
            path_ids.append(pid)
            parent_id = pid
            depth -= 1
        for pid in path_ids[::-1]:
            path.append(pid)
    reply.path = path
    db.session.commit()


# emergency function - shouldn't be called in normal circumstances
def calculate_child_count(reply):
    child_count = db.session.execute(
        text('select count(id) as c from post_reply where :id = ANY(path) and id != :id and deleted = false'),
        {"id": reply.id}).scalar()
    reply.child_count = child_count
    db.session.commit()


def reply_view(reply: PostReply | int, variant: int, user_id=None, my_vote=0, read=False, mods=None, banned_from=None,
               bookmarked_replies=None, reply_subscriptions=None) -> dict:
    if isinstance(reply, int):
        reply = PostReply.query.filter_by(id=reply).one()

    # Variant 1 - models/comment/comment.dart
    if variant == 1:
        include = ['id', 'user_id', 'post_id', 'body', 'deleted']
        v1 = {column.name: getattr(reply, column.name) for column in reply.__table__.columns if column.name in include}

        v1.update({'published': reply.posted_at.isoformat() + 'Z',
                   'ap_id': reply.profile_id(),
                   'local': reply.is_local(),
                   'language_id': reply.language_id if reply.language_id else 0,
                   'distinguished': reply.distinguished,
                   'repliesEnabled': reply.replies_enabled,
                   'removed': False})

        if not reply.path:
            calculate_path(reply)
        v1['path'] = '.'.join(str(id) for id in reply.path)
        if reply.edited_at:
            v1['edited_at'] = reply.edited_at.isoformat() + 'Z'
        if reply.deleted == True:
            v1['body'] = ''
            if reply.deleted_by and reply.user_id != reply.deleted_by:
                v1['removed'] = True
                v1['deleted'] = False

        return v1

    # Variant 2 - currently unused
    # Variant 3 - currently unused

    # Variant 4 - models/comment/comment_response.dart - /comment/like api endpoint
    if variant == 4:
        v4 = {'comment_view': reply_view(reply=reply, variant=9, user_id=user_id)}

        return v4

    # Variant 5 - views/comment_reply_view.dart - /user/replies api endpoint
    if variant == 5:
        if bookmarked_replies is None:
            bookmarked = db.session.execute(text(
                'SELECT user_id FROM "post_reply_bookmark" WHERE post_reply_id = :post_reply_id and user_id = :user_id'),
                {'post_reply_id': reply.id, 'user_id': user_id}).scalar()
        else:
            bookmarked = reply.id in bookmarked_replies

        if reply_subscriptions is None:
            reply_sub = db.session.execute(text(
                'SELECT user_id FROM "notification_subscription" WHERE type = :type and entity_id = :entity_id and user_id = :user_id'),
                {'type': NOTIF_REPLY, 'entity_id': reply.id, 'user_id': user_id}).scalar()
        else:
            reply_sub = reply.id in reply_subscriptions

        if banned_from is None:
            banned = reply.community_id in communities_banned_from(user_id)
        else:
            banned = reply.community_id in banned_from

        moderator = db.session.execute(text(
            'SELECT is_moderator FROM "community_member" WHERE user_id = :user_id and community_id = :community_id'),
                                       {'user_id': reply.user_id, 'community_id': reply.community_id}).scalar()
        admin = reply.user_id in g.admin_ids
        if my_vote == 0 and user_id is not None:
            reply_vote = db.session.execute(text(
                'SELECT effect FROM "post_reply_vote" WHERE post_reply_id = :post_reply_id and user_id = :user_id'),
                                            {'post_reply_id': reply.id, 'user_id': user_id}).scalar()
            effect = reply_vote if reply_vote else 0
        else:
            effect = my_vote

        my_vote = int(effect)
        saved = True if bookmarked else False
        activity_alert = True if reply_sub else False
        creator_banned_from_community = True if banned else False
        creator_is_moderator = True if moderator else False
        creator_is_admin = True if admin else False

        v5 = {'comment_reply': {'id': reply.id, 'recipient_id': user_id, 'comment_id': reply.id, 'read': read,
                                'published': reply.posted_at.isoformat() + 'Z'},
              'comment': reply_view(reply=reply, variant=1),
              'creator': user_view(user=reply.author, variant=1, flair_community_id=reply.community_id),
              'post': post_view(post=reply.post, variant=1),
              'community': community_view(community=reply.community, variant=1),
              'recipient': user_view(user=user_id, variant=1),
              'counts': {'comment_id': reply.id, 'score': reply.score, 'upvotes': reply.up_votes,
                         'downvotes': reply.down_votes, 'published': reply.posted_at.isoformat() + 'Z',
                         'child_count': 0},
              'activity_alert': activity_alert,
              'creator_banned_from_community': creator_banned_from_community,
              'creator_is_moderator': creator_is_moderator,
              'creator_is_admin': creator_is_admin,
              'subscribed': 'NotSubscribed',
              'saved': saved,
              'creator_blocked': False,
              'my_vote': my_vote
              }

        return v5

    # Variant 6 - from resolve_object
    if variant == 6:
        v6 = {'comment': reply_view(reply=reply, variant=9, user_id=user_id)}

        return v6

    # Variant 7 - comments/list endpoint. post_view, community_view and canAuthModerateUser are the same for all, so get once in calling function
    # Variant 8 - comments/list endpoint. community_view and canAuthModerateUser are the same for all, so get once in calling function
    # Variant 9 - comments/list endpoint. post_view, community_view, and canAuthModerateUser can be different for each reply, so fetch each time
    #           - also used for individual reply responses
    # when they're the same for all replies
    if variant == 7 or variant == 8 or variant == 9:
        # counts - models/comment/comment_aggregates.dart
        counts = {'comment_id': reply.id, 'score': reply.score, 'upvotes': reply.up_votes,
                  'downvotes': reply.down_votes,
                  'published': reply.posted_at.isoformat() + 'Z',
                  'child_count': reply.child_count if reply.child_count is not None else 0}

        if bookmarked_replies is None:
            bookmarked = list(db.session.execute(text(
                'SELECT post_reply_id FROM "post_reply_bookmark" WHERE post_reply_id = :post_reply_id and user_id = :user_id'),
                                            {'post_reply_id': reply.id, 'user_id': user_id}).scalars())
        else:
            bookmarked = reply.id in bookmarked_replies

        if reply_subscriptions is None:
            reply_sub = list(db.session.execute(text(
                'SELECT entity_id FROM "notification_subscription" WHERE type = :type and entity_id = :entity_id and user_id = :user_id'),
                                           {'type': NOTIF_REPLY, 'entity_id': reply.id, 'user_id': user_id}).scalars())
        else:
            reply_sub = reply.id in reply_subscriptions

        if banned_from is None:
            banned = reply.community_id in communities_banned_from(user_id)
        else:
            banned = reply.community_id in banned_from

        if mods is None:
            moderator = reply.community.is_moderator(reply.author) or reply.community.is_owner(reply.author)
        else:
            moderator = reply.user_id in mods

        admin = reply.user_id in g.admin_ids

        if my_vote == 0 and user_id is not None:
            reply_vote = db.session.execute(text(
                'SELECT effect FROM "post_reply_vote" WHERE post_reply_id = :post_reply_id and user_id = :user_id'),
                                            {'post_reply_id': reply.id, 'user_id': user_id}).scalar()
            effect = reply_vote if reply_vote else 0
        else:
            effect = my_vote

        my_vote = int(effect)
        saved = True if bookmarked else False
        activity_alert = True if reply_sub else False
        creator_banned_from_community = True if banned else False
        creator_is_moderator = True if moderator else False
        creator_is_admin = True if admin else False

        v7 = {'comment': reply_view(reply=reply, variant=1), 'counts': counts, 'banned_from_community': False,
              'subscribed': 'NotSubscribed',
              'saved': saved, 'creator_blocked': False, 'my_vote': my_vote, 'activity_alert': activity_alert,
              'creator_banned_from_community': creator_banned_from_community,
              'creator_is_moderator': creator_is_moderator,
              'creator_is_admin': creator_is_admin,
              'creator': user_view(user=reply.author, variant=1, stub=True, flair_community_id=reply.community_id)}
        if variant == 7:
            return v7
        if variant == 8:
            v8 = v7
            v8['post'] = post_view(post=reply.post, variant=1)
            return v8
        if variant == 9:
            v9 = v7
            v9['post'] = post_view(post=reply.post, variant=1)
            v9['community'] = community_view(community=reply.community, variant=1, stub=True)
            v9['canAuthUserModerate'] = False
            if user_id:
                v9['canAuthUserModerate'] = any(
                    moderator.user_id == user_id for moderator in reply.community.moderators())
            return v9


def reply_report_view(report, reply_id, user_id) -> dict:
    # views/comment_report_view.dart - /comment/report api endpoint
    reply_json = reply_view(reply=reply_id, variant=9, user_id=user_id)
    post_json = post_view(post=reply_json['comment']['post_id'], variant=1, stub=True)
    community_json = community_view(community=post_json['community_id'], variant=1, stub=True)

    banned = db.session.execute(
        text('SELECT user_id FROM "community_ban" WHERE user_id = :user_id and community_id = :community_id'),
        {'user_id': report.reporter_id, 'community_id': community_json['id']}).scalar()
    moderator = db.session.execute(
        text('SELECT is_moderator FROM "community_member" WHERE user_id = :user_id and community_id = :community_id'),
        {'user_id': report.reporter_id, 'community_id': community_json['id']}).scalar()
    admin = db.session.execute(text('SELECT user_id FROM "user_role" WHERE user_id = :user_id and role_id = 4'),
                               {'user_id': report.reporter_id}).scalar()

    creator_banned_from_community = True if banned else False
    creator_is_moderator = True if moderator else False
    creator_is_admin = True if admin else False

    v1 = {
        'comment_report_view': {
            'comment_report': {
                'id': report.id,
                'creator_id': report.reporter_id,
                'comment_id': report.suspect_post_reply_id,
                'original_comment_text': reply_json['comment']['body'],
                'reason': report.reasons,
                'resolved': report.status == 3,
                'published': report.created_at.isoformat() + 'Z'
            },
            'comment': reply_json['comment'],
            'post': post_json,
            'community': community_json,
            'creator': user_view(user=user_id, variant=1, stub=True),
            'comment_creator': user_view(user=report.suspect_user_id, variant=1, stub=True),
            'counts': reply_json['counts'],
            'creator_banned_from_community': creator_banned_from_community,
            'creator_is_moderator': creator_is_moderator,
            'creator_is_admin': creator_is_admin,
            'creator_blocked': False,
            'subscribed': reply_json['subscribed'],
            'saved': reply_json['saved']
        }
    }
    return v1


def post_report_view(report, post_id, user_id) -> dict:
    # views/post_report_view.dart - /post/report api endpoint
    post_json = post_view(post=post_id, variant=2, user_id=user_id)
    community_json = community_view(community=post_json['post']['community_id'], variant=1, stub=True)

    banned = db.session.execute(
        text('SELECT user_id FROM "community_ban" WHERE user_id = :user_id and community_id = :community_id'),
        {'user_id': report.reporter_id, 'community_id': community_json['id']}).scalar()
    moderator = db.session.execute(
        text('SELECT is_moderator FROM "community_member" WHERE user_id = :user_id and community_id = :community_id'),
        {'user_id': report.reporter_id, 'community_id': community_json['id']}).scalar()
    admin = db.session.execute(text('SELECT user_id FROM "user_role" WHERE user_id = :user_id and role_id = 4'),
                               {'user_id': report.reporter_id}).scalar()

    creator_banned_from_community = True if banned else False
    creator_is_moderator = True if moderator else False
    creator_is_admin = True if admin else False

    v1 = {
        'post_report_view': {
            'post_report': {
                'id': report.id,
                'creator_id': report.reporter_id,
                'post_id': report.suspect_post_id,
                'original_post_name': post_json['post']['title'],
                'original_post_body': '',
                'reason': report.reasons,
                'resolved': report.status == 3,
                'published': report.created_at.isoformat() + 'Z'
            },
            'post': post_json['post'],
            'community': community_json,
            'creator': user_view(user=user_id, variant=1, stub=True),
            'post_creator': user_view(user=report.suspect_user_id, variant=1, stub=True),
            'counts': post_json['counts'],
            'creator_banned_from_community': creator_banned_from_community,
            'creator_is_moderator': creator_is_moderator,
            'creator_is_admin': creator_is_admin,
            'creator_blocked': False,
            'subscribed': post_json['subscribed'],
            'saved': post_json['saved']
        }
    }
    return v1


def search_view(type) -> dict:
    v1 = {
        'type_': type,
        'comments': [],
        'posts': [],
        'communities': [],
        'users': []
    }
    return v1


def instance_view(instance: Instance | int, variant) -> dict:
    if isinstance(instance, int):
        instance = Instance.query.filter_by(id=instance).one()

    if variant == 1:
        include = ['id', 'domain', 'software', 'version']
        v1 = {column.name: getattr(instance, column.name) for column in instance.__table__.columns if
              column.name in include}
        if not v1['version']:
            v1.update({'version': '0.0.1'})
        v1.update(
            {'published': instance.created_at.isoformat() + 'Z', 'updated': instance.updated_at.isoformat() + 'Z'})

        return v1


def private_message_view(cm: ChatMessage, variant) -> dict:
    creator = user_view(cm.sender_id, variant=1)
    recipient = user_view(cm.recipient_id, variant=1)
    is_local = (creator['instance_id'] == 1 and recipient['instance_id'] == 1)

    v1 = {
        'private_message': {
            'id': cm.id,
            'creator_id': cm.sender_id,
            'recipient_id': cm.recipient_id,
            'content': cm.body,
            'deleted': False,
            'read': cm.read,
            'published': cm.created_at.isoformat() + 'Z',
            'ap_id': cm.ap_id,
            'local': is_local
        },
        'creator': creator,
        'recipient': recipient
    }

    if variant == 1:
        return v1

    v2 = {
        'private_message_view': v1
    }

    if variant == 2:
        return v2


def site_view(user) -> dict:
    logo = g.site.logo if g.site.logo else '/static/images/piefed_logo_icon_t_75.png'
    site = {
        "enable_downvotes": g.site.enable_downvotes,
        "icon": f"https://{current_app.config['SERVER_NAME']}{logo}",
        "registration_mode": g.site.registration_mode,
        "name": g.site.name,
        "actor_id": f"https://{current_app.config['SERVER_NAME']}/",
        "user_count": users_total(),
        "all_languages": []
    }
    if g.site.sidebar:
        site['sidebar'] = g.site.sidebar
    if g.site.description:
        site['description'] = g.site.description
    for language in Language.query.all():
        site["all_languages"].append({
            "id": language.id,
            "code": language.code,
            "name": language.name
        })

    v1 = {
        "version": current_app.config['VERSION'],
        "admins": [],
        "site": site
    }
    for admin in Site.admins():
        v1['admins'].append(user_view(user=admin, variant=2))
    if user:
        v1['my_user'] = user_view(user=user, variant=6)

    return v1


@cache.memoize(timeout=600)
def federated_instances_view():
    instances = Instance.query.filter(Instance.id != 1, Instance.gone_forever == False).all()
    linked = []
    allowed = []
    blocked = []
    for instance in AllowedInstances.query.all():
        allowed.append({"id": instance.id, "domain": instance.domain, "published": utcnow(), "updated": utcnow()})
    for instance in BannedInstances.query.all():
        blocked.append({"id": instance.id, "domain": instance.domain, "published": utcnow(), "updated": utcnow()})
    for instance in instances:
        instance_data = {"id": instance.id, "domain": instance.domain, "published": instance.created_at.isoformat(),
                         "updated": instance.updated_at.isoformat()}
        if instance.software:
            instance_data['software'] = instance.software
        if instance.version:
            instance_data['version'] = instance.version
        if not any(blocked_instance.get('domain') == instance.domain for blocked_instance in blocked):
            linked.append(instance_data)
    v1 = {
        "federated_instances": {
            "linked": linked,
            "allowed": allowed,
            "blocked": blocked
        }
    }
    return v1


@cache.memoize(timeout=60)
def cached_modlist_for_community(community_id):
    moderator_ids = db.session.execute(
        text('SELECT user_id FROM "community_member" WHERE community_id = :community_id and (is_moderator = True or is_owner = True)'),
        {'community_id': community_id}).scalars()
    modlist = []
    for m_id in moderator_ids:
        entry = {
            'community': community_view(community=community_id, variant=1, stub=True),
            'moderator': user_view(user=m_id, variant=1, stub=True)
        }
        modlist.append(entry)
    return modlist


@cache.memoize(timeout=60)
def cached_modlist_for_user(user):
    community_ids = db.session.execute(
        text('SELECT community_id FROM "community_member" WHERE user_id = :user_id and (is_moderator = True or is_owner = True)'),
        {'user_id': user.id}).scalars()
    modlist = []
    for c_id in community_ids:
        entry = {
            'community': community_view(community=c_id, variant=1, stub=True),
            'moderator': user_view(user=user, variant=1, stub=True)
        }
        modlist.append(entry)
    return modlist


@cache.memoize(timeout=3000)
def users_total():
    return db.session.execute(text(
        'SELECT COUNT(id) as c FROM "user" WHERE ap_id is null AND verified is true AND banned is false AND deleted is false')).scalar()


# @cache.memoize(timeout=60)
def moderating_communities_view(user):
    cms = CommunityMember.query.filter_by(user_id=user.id, is_moderator=True)
    moderates = []
    inner_user_view = user_view(user, variant=1, stub=True)
    for cm in cms:
        moderates.append({'community': community_view(cm.community_id, variant=1, stub=True), 'moderator': inner_user_view})
    return moderates


# @cache.memoize(timeout=60)
def joined_communities_view(user):
    cms = CommunityMember.query.filter_by(user_id=user.id, is_banned=False)
    follows = []
    inner_user_view = user_view(user, variant=1, stub=True)
    for cm in cms:
        follows.append({'community': community_view(cm.community_id, variant=1, stub=True), 'follower': inner_user_view})
    return follows


# @cache.memoize(timeout=86400)
def blocked_people_view(user) -> list[dict]:
    blocked_ids = blocked_users(user.id)
    blocked = []
    for blocked_id in blocked_ids:
        blocked.append({'person': user_view(user, variant=1, stub=True), 'target': user_view(blocked_id, variant=1, stub=True)})
    return blocked


# @cache.memoize(timeout=86400)
def blocked_communities_view(user) -> list[dict]:
    blocked_ids = blocked_communities(user.id)
    blocked = []
    for blocked_id in blocked_ids:
        blocked.append({'person': user_view(user, variant=1, stub=True),
                        'community': community_view(blocked_id, variant=1, stub=True)})
    return blocked


# @cache.memoize(timeout=86400)
def blocked_instances_view(user) -> list[dict]:
    blocked_ids = blocked_instances(user.id)
    blocked = []
    for blocked_id in blocked_ids:
        blocked.append({'person': user_view(user, variant=1, stub=True), 'instance': instance_view(blocked_id, variant=1)})
    return blocked
