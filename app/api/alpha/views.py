from __future__ import annotations

from app import cache, db
from app.constants import *
from app.models import Community, CommunityMember, Post, PostReply, PostVote, User

from sqlalchemy import text

# 'stub' param: set to True to exclude optional fields


def post_view(post: Post | int, variant, stub=False, user_id=None, my_vote=0):
    if isinstance(post, int):
        post = Post.query.get(post)
    if not post or post.deleted:
        raise Exception('post_not_found')

    # Variant 1 - models/post/post.dart
    if variant == 1:
        include = ['id', 'title', 'user_id', 'community_id', 'deleted', 'nsfw', 'sticky']
        v1 = {column.name: getattr(post, column.name) for column in post.__table__.columns if column.name in include}
        v1.update({'published': post.posted_at.isoformat() + 'Z',
                        'ap_id': post.profile_id(),
                        'local': post.is_local(),
                        'language_id': post.language_id if post.language_id else 0,
                        'removed': post.deleted,
                        'locked': not post.comments_enabled})
        if post.body and not stub:
            v1['body'] = post.body
        if post.edited_at:
            v1['edited_at'] = post.edited_at.isoformat() + 'Z'
        if post.type == POST_TYPE_LINK or post.type == POST_TYPE_VIDEO:
            if post.url:
                v1['url'] = post.url
            if post.image_id:
                v1['thumbnail_url'] = post.image.thumbnail_url()
                if post.image.alt_text:
                    v1['alt_text'] = post.image.alt_text
        if post.type == POST_TYPE_IMAGE:
            if post.image_id:
                v1['url'] = post.image.view_url()
                v1['thumbnail_url'] = post.image.medium_url()
                if post.image.alt_text:
                    v1['alt_text'] = post.image.alt_text

        return v1

    # Variant 2 - views/post_view.dart - /post/list api endpoint
    if variant == 2:
        # counts - models/post/post_aggregates.dart
        counts = {'post_id': post.id, 'comments': post.reply_count, 'score': post.score, 'upvotes': post.up_votes, 'downvotes': post.down_votes,
                  'published': post.posted_at.isoformat() + 'Z', 'newest_comment_time': post.last_active.isoformat() + 'Z'}
        bookmarked = db.session.execute(text('SELECT user_id FROM "post_bookmark" WHERE post_id = :post_id and user_id = :user_id'), {'post_id': post.id, 'user_id': user_id}).scalar()
        post_sub = db.session.execute(text('SELECT user_id FROM "notification_subscription" WHERE type = :type and entity_id = :entity_id and user_id = :user_id'), {'type': NOTIF_POST, 'entity_id': post.id, 'user_id': user_id}).scalar()
        if not stub:
            banned =  db.session.execute(text('SELECT user_id FROM "community_ban" WHERE user_id = :user_id and community_id = :community_id'), {'user_id': post.user_id, 'community_id': post.community_id}).scalar()
            moderator = db.session.execute(text('SELECT is_moderator FROM "community_member" WHERE user_id = :user_id and community_id = :community_id'), {'user_id': post.user_id, 'community_id': post.community_id}).scalar()
            admin =  db.session.execute(text('SELECT user_id FROM "user_role" WHERE user_id = :user_id and role_id = 4'), {'user_id': post.user_id}).scalar()
        else:
            banned = False
            moderator = False
            admin = False
        if my_vote == 0 and user_id is not None:
            post_vote =  db.session.execute(text('SELECT effect FROM "post_vote" WHERE post_id = :post_id and user_id = :user_id'), {'post_id': post.id, 'user_id': user_id}).scalar()
            effect = post_vote if post_vote else 0
        else:
            effect = my_vote

        my_vote = int(effect)
        saved = True if bookmarked else False
        activity_alert = True if post_sub else False
        creator_banned_from_community = True if banned else False
        creator_is_moderator = True if moderator else False
        creator_is_admin = True if admin else False
        v2 = {'post': post_view(post=post, variant=1, stub=stub), 'counts': counts, 'banned_from_community': False, 'subscribed': 'NotSubscribed',
              'saved': saved, 'read': False, 'hidden': False, 'creator_blocked': False, 'unread_comments': post.reply_count, 'my_vote': my_vote, 'activity_alert': activity_alert,
              'creator_banned_from_community': creator_banned_from_community, 'creator_is_moderator': creator_is_moderator, 'creator_is_admin': creator_is_admin}

        try:
            creator = user_view(user=post.user_id, variant=1, stub=True)
            community = community_view(community=post.community_id, variant=1, stub=True)
            v2.update({'creator': creator, 'community': community})
        except:
            raise

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


@cache.memoize(timeout=600)
def cached_user_view_variant_1(user: User, stub=False):
    include = ['id', 'user_name', 'title', 'banned', 'deleted', 'bot']
    v1 = {column.name: getattr(user, column.name) for column in user.__table__.columns if column.name in include}
    v1.update({'published': user.created.isoformat() + 'Z',
                    'actor_id': user.public_url(),
                    'local': user.is_local(),
                    'instance_id': user.instance_id if user.instance_id else 1})
    if user.about and not stub:
        v1['about'] = user.about
    if user.avatar_id:
        v1['avatar'] = user.avatar.view_url()
    if user.cover_id and not stub:
        v1['banner'] = user.cover.view_url()

    return v1


def user_view(user: User | int, variant, stub=False):
    if isinstance(user, int):
        user = User.query.get(user)
    if not user:
        raise Exception('user_not_found')

    # Variant 1 - models/person/person.dart
    if variant == 1:
        return cached_user_view_variant_1(user=user, stub=stub)

    # Variant 2 - views/person_view.dart
    if variant == 2:
        counts = {'person_id': user.id, 'post_count': user.post_count, 'comment_count': user.post_reply_count}
        v2 = {'person': user_view(user=user, variant=1), 'counts': counts, 'is_admin': user.is_admin()}
        return v2

    # Variant 3 - models/user/get_person_details.dart - /user?person_id api endpoint
    modlist = cached_modlist_for_user(user)

    v3 = {'person_view': user_view(user=user, variant=2),
          'moderates': modlist,
          'posts': [],
          'comments': []}
    return v3


@cache.memoize(timeout=600)
def cached_community_view_variant_1(community: Community, stub=False):
    include = ['id', 'name', 'title', 'banned', 'nsfw', 'restricted_to_mods']
    v1 = {column.name: getattr(community, column.name) for column in community.__table__.columns if column.name in include}
    v1.update({'published': community.created_at.isoformat() + 'Z',
               'updated': community.created_at.isoformat() + 'Z',
               'deleted': False,
               'removed': False,
               'actor_id': community.public_url(),
               'local': community.is_local(),
               'hidden': not community.show_all,
               'instance_id': community.instance_id if community.instance_id else 1})
    if community.description and not stub:
        v1['description'] = community.description
    if community.icon_id:
        v1['icon'] = community.icon.view_url()
    if community.image_id and not stub:
        v1['banner'] = community.image.view_url()

    return v1


def community_view(community: Community | int | str, variant, stub=False, user_id=None):
    if isinstance(community, int):
        community = Community.query.get(community)
    elif isinstance(community, str):
        name, ap_domain = community.split('@')
        community = Community.query.filter_by(name=name, ap_domain=ap_domain).first()
    if not community:
        raise Exception('community_not_found')

    # Variant 1 - models/community/community.dart
    if variant == 1:
        return cached_community_view_variant_1(community=community, stub=stub)

    # Variant 2 - views/community_view.dart - /community/list api endpoint
    if variant == 2:
        # counts - models/community/community_aggregates
        include = ['id', 'subscriptions_count', 'post_count', 'post_reply_count']
        counts = {column.name: getattr(community, column.name) for column in community.__table__.columns if column.name in include}
        counts.update({'published': community.created_at.isoformat() + 'Z'})
        v2 = {'community': community_view(community=community, variant=1, stub=stub), 'subscribed': 'NotSubscribed', 'blocked': False, 'counts': counts}
        return v2

    # Variant 3 - models/community/get_community_response.dart - /community api endpoint
    if variant == 3:
        modlist = cached_modlist_for_community(community.id)

        v3  = {'community_view': community_view(community=community, variant=2),
               'moderators': modlist,
               'discussion_languages': []}
        return v3



# would be better to incrementally add to a post_reply.path field
@cache.memoize(timeout=86400)
def calculate_path(reply):
    path = "0." + str(reply.id)
    if reply.depth == 1:
        path = "0." + str(reply.parent_id) + "." + str(reply.id)
    elif reply.depth > 1:
        path = "0"
        parent_id = reply.parent_id
        depth = reply.depth - 1
        path_ids = [reply.id, reply.parent_id]
        while depth > 0:
            pid = db.session.execute(text('SELECT parent_id FROM "post_reply" WHERE id = :parent_id'), {'parent_id': parent_id}).scalar()
            path_ids.append(pid)
            parent_id = pid
            depth -= 1
        for pid in path_ids[::-1]:
            path += "." + str(pid)
    return path


# would be better to incrementally add to a post_reply.child_count field (walk along .path, and ++ each one)
@cache.memoize(timeout=86400)
def calculate_if_has_children(reply):    # result used as True / False
    return db.session.execute(text('SELECT COUNT(id) AS c FROM "post_reply" WHERE parent_id = :id'), {'id': reply.id}).scalar()


def reply_view(reply: PostReply | int, variant, user_id=None, my_vote=0):
    if isinstance(reply, int):
        reply = PostReply.query.get(reply)
    if not reply or reply.deleted:
        raise Exception('reply_not_found')


    # Variant 1 - models/comment/comment.dart
    if variant == 1:
        include = ['id', 'user_id', 'post_id', 'body', 'deleted']
        v1 = {column.name: getattr(reply, column.name) for column in reply.__table__.columns if column.name in include}

        v1['path'] = calculate_path(reply)

        v1.update({'published': reply.posted_at.isoformat() + 'Z',
                   'ap_id': reply.profile_id(),
                   'local': reply.is_local(),
                   'language_id': reply.language_id if reply.language_id else 0,
                   'removed': reply.deleted,
                   'distinguished': False})
        return v1

    # Variant 2 - views/comment_view.dart - /comment/list api endpoint
    if variant == 2:
        # counts - models/comment/comment_aggregates.dart
        counts = {'comment_id': reply.id, 'score': reply.score, 'upvotes': reply.up_votes, 'downvotes': reply.down_votes,
                  'published': reply.posted_at.isoformat() + 'Z', 'child_count': 1 if calculate_if_has_children(reply) else 0}

        bookmarked = db.session.execute(text('SELECT user_id FROM "post_reply_bookmark" WHERE post_reply_id = :post_reply_id and user_id = :user_id'), {'post_reply_id': reply.id, 'user_id': user_id}).scalar()
        reply_sub = db.session.execute(text('SELECT user_id FROM "notification_subscription" WHERE type = :type and entity_id = :entity_id and user_id = :user_id'), {'type': NOTIF_REPLY, 'entity_id': reply.id, 'user_id': user_id}).scalar()
        banned = db.session.execute(text('SELECT user_id FROM "community_ban" WHERE user_id = :user_id and community_id = :community_id'), {'user_id': reply.user_id, 'community_id': reply.community_id}).scalar()
        moderator = db.session.execute(text('SELECT is_moderator FROM "community_member" WHERE user_id = :user_id and community_id = :community_id'), {'user_id': reply.user_id, 'community_id': reply.community_id}).scalar()
        admin = db.session.execute(text('SELECT user_id FROM "user_role" WHERE user_id = :user_id and role_id = 4'), {'user_id': reply.user_id}).scalar()
        if my_vote == 0 and user_id is not None:
            reply_vote = db.session.execute(text('SELECT effect FROM "post_reply_vote" WHERE post_reply_id = :post_reply_id and user_id = :user_id'), {'post_reply_id': reply.id, 'user_id': user_id}).scalar()
            effect = reply_vote if reply_vote else 0
        else:
            effect = my_vote

        my_vote = int(effect)
        saved = True if bookmarked else False
        activity_alert = True if reply_sub else False
        creator_banned_from_community = True if banned else False
        creator_is_moderator = True if moderator else False
        creator_is_admin = True if admin else False

        v2 = {'comment': reply_view(reply=reply, variant=1), 'counts': counts, 'banned_from_community': False, 'subscribed': 'NotSubscribed',
              'saved': saved, 'creator_blocked': False, 'my_vote': my_vote, 'activity_alert': activity_alert,
              'creator_banned_from_community': creator_banned_from_community, 'creator_is_moderator': creator_is_moderator, 'creator_is_admin': creator_is_admin}
        try:
            creator = user_view(user=reply.user_id, variant=1, stub=True)
            community = community_view(community=reply.community_id, variant=1, stub=True)
            post = post_view(post=reply.post_id, variant=1)
            v2.update({'creator': creator, 'community': community, 'post': post})
        except:
            raise

        return v2

    # Variant 3 - would be for /comment api endpoint

    # Variant 4 - models/comment/comment_response.dart - /comment/like api endpoint
    if variant == 4:
        v4 = {'comment_view': reply_view(reply=reply, variant=2, user_id=user_id)}

        return v4


@cache.memoize(timeout=86400)
def cached_modlist_for_community(community_id):
    moderator_ids = db.session.execute(text('SELECT user_id FROM "community_member" WHERE community_id = :community_id and is_moderator = True'), {'community_id': community_id}).scalars()
    modlist = []
    for m_id in moderator_ids:
        entry = {
          'community': community_view(community=community_id, variant=1, stub=True),
          'moderator': user_view(user=m_id, variant=1, stub=True)
        }
        modlist.append(entry)
    return modlist


@cache.memoize(timeout=86400)
def cached_modlist_for_user(user):
    community_ids = db.session.execute(text('SELECT community_id FROM "community_member" WHERE user_id = :user_id and is_moderator = True'), {'user_id': user.id}).scalars()
    modlist = []
    for c_id in community_ids:
        entry = {
          'community': community_view(community=c_id, variant=1, stub=True),
          'moderator': user_view(user=user, variant=1, stub=True)
        }
        modlist.append(entry)
    return modlist
