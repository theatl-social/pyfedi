from app import cache, db
from app.api.alpha.views import user_view, community_view, instance_view
from app.api.alpha.utils.validators import required, integer_expected, boolean_expected
from app.utils import authorise_api_user
from app.models import CommunityMember, InstanceBlock, Language
from app.shared.site import block_remote_instance, unblock_remote_instance

from flask import current_app, g

from sqlalchemy import text

@cache.memoize(timeout=86400)
def users_total():
    return db.session.execute(text(
        'SELECT COUNT(id) as c FROM "user" WHERE ap_id is null AND verified is true AND banned is false AND deleted is false')).scalar()


@cache.memoize(timeout=86400)
def moderating_communities(user):
    cms = CommunityMember.query.filter_by(user_id=user.id, is_moderator=True)
    moderates = []
    for cm in cms:
        moderates.append({'community': community_view(cm.community_id, variant=1, stub=True), 'moderator': user_view(user, variant=1, stub=True)})
    return moderates


@cache.memoize(timeout=86400)
def joined_communities(user):
    cms = CommunityMember.query.filter_by(user_id=user.id, is_banned=False)
    follows = []
    for cm in cms:
        follows.append({'community': community_view(cm.community_id, variant=1, stub=True), 'follower': user_view(user, variant=1, stub=True)})
    return follows


@cache.memoize(timeout=86400)
def blocked_people(user):
    blocked = []
    blocked_ids = db.session.execute(text('SELECT blocked_id FROM "user_block" WHERE blocker_id = :blocker_id'), {"blocker_id": user.id}).scalars()
    for blocked_id in blocked_ids:
        blocked.append({'person': user_view(user, variant=1, stub=True), 'target': user_view(blocked_id, variant=1, stub=True)})
    return blocked


@cache.memoize(timeout=86400)
def blocked_communities(user):
    blocked = []
    blocked_ids = db.session.execute(text('SELECT community_id FROM "community_block" WHERE user_id = :user_id'), {"user_id": user.id}).scalars()
    for blocked_id in blocked_ids:
        blocked.append({'person': user_view(user, variant=1, stub=True), 'community': community_view(blocked_id, variant=1, stub=True)})
    return blocked


@cache.memoize(timeout=86400)
def blocked_instances(user):
    blocked = []
    blocked_ids = db.session.execute(text('SELECT instance_id FROM "instance_block" WHERE user_id = :user_id'), {"user_id": user.id}).scalars()
    for blocked_id in blocked_ids:
        blocked.append({'person': user_view(user, variant=1, stub=True), 'instance': instance_view(blocked_id, variant=1)})
    return blocked


def get_site(auth):
    if auth:
        user = authorise_api_user(auth, return_type='model')
    else:
        user = None

    logo = g.site.logo if g.site.logo else '/static/images/logo2.png'
    logo_152 = g.site.logo_152 if g.site.logo_152 else '/static/images/apple-touch-icon.png'
    logo_32 = g.site.logo_32 if g.site.logo_32 else '/static/images/favicon-32x32.png'
    logo_16 = g.site.logo_16 if g.site.logo_16 else '/static/images/favicon-16x16.png'
    site = {
      "enable_downvotes": g.site.enable_downvotes,
      "icon": f"https://{current_app.config['SERVER_NAME']}{logo}",
      "icon_152": f"https://{current_app.config['SERVER_NAME']}{logo_152}",
      "icon_32": f"https://{current_app.config['SERVER_NAME']}{logo_32}",
      "icon_16": f"https://{current_app.config['SERVER_NAME']}{logo_16}",
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

    if user:
        my_user = {
          "local_user_view": {
            "local_user": {
            "show_nsfw": not user.hide_nsfw == 1,
            "default_sort_type": user.default_sort.capitalize(),
            "default_listing_type": user.default_filter.capitalize(),
            "show_scores": True,
            "show_bot_accounts": not user.ignore_bots == 1,
            "show_read_posts": True,
            },
            "person": {
              "id": user.id,
              "user_name": user.user_name,
              "banned": user.banned,
              "published": user.created.isoformat() + 'Z',
              "actor_id": user.public_url()[8:],
              "local": True,
              "deleted": user.deleted,
              "bot": user.bot,
              "instance_id": 1
            },
            "counts": {
              "person_id": user.id,
              "post_count": user.post_count,
             "comment_count": user.post_reply_count
            }
          },
          "moderates": moderating_communities(user),
          "follows": joined_communities(user),
          "community_blocks": blocked_communities(user),
          "instance_blocks": blocked_instances(user),
          "person_blocks": blocked_people(user),
          "discussion_languages": []        # TODO
        }
    data = {
      "version": "1.0.0",
      "site": site
    }
    if user:
        data['my_user'] = my_user

    return data


SRC_API = 3

def post_site_block(auth, data):
    required(['instance_id', 'block'], data)
    integer_expected(['instance_id'], data)
    boolean_expected(['block'], data)

    instance_id = data['instance_id']
    block = data['block']

    user_id = block_remote_instance(instance_id, SRC_API, auth) if block else unblock_remote_instance(instance_id, SRC_API, auth)
    blocked = InstanceBlock.query.filter_by(user_id=user_id, instance_id=instance_id).first()
    block = True if blocked else False
    data = {
      "blocked": block
    }
    return data
