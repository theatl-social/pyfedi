from app import db
from app.utils import authorise_api_user
from app.models import Language

from flask import current_app, g

from sqlalchemy import text

def users_total():
    return db.session.execute(text(
        'SELECT COUNT(id) as c FROM "user" WHERE ap_id is null AND verified is true AND banned is false AND deleted is false')).scalar()

def get_site(auth):
    if auth:
        try:
            user = authorise_api_user(auth, return_type='model')
        except Exception as e:
            raise e
    else:
        user = None

    logo = g.site.logo if g.site.logo else '/static/images/logo2.png'
    site = {
      "enable_downvotes": g.site.enable_downvotes,
      "icon": f"https://{current_app.config['SERVER_NAME']}{logo}",
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
          #"moderates": [],
          #"follows": [],
          "community_blocks": [],           # TODO
          "instance_blocks": [],            # TODO
          "person_blocks": [],              # TODO
          "discussion_languages": []        # TODO
        }
        """
        Note: Thunder doesn't use moderates[] and follows[] from here, but it would be more efficient if it did (rather than getting them from /user and /community)
        cms = CommunityMember.query.filter_by(user_id=user_id, is_moderator=True)
        for cm in cms:
            my_user['moderates'].append({'community': Community.api_json(variant=1, id=cm.community_id, stub=True), 'moderator': User.api_json(variant=1, id=user_id, stub=True)})
        cms = CommunityMember.query.filter_by(user_id=user_id, is_banned=False)
        for cm in cms:
            my_user['follows'].append({'community': Community.api_json(variant=1, id=cm.community_id, stub=True), 'follower': User.api_json(variant=1, id=user_id, stub=True)})
        """

    data = {
      "version": "1.0.0",
      "site": site
    }
    if user:
        data['my_user'] = my_user

    return data

