from datetime import timedelta

from flask import current_app, g
from sqlalchemy import desc, text

from app import db
from app.api.alpha.views import feed_view
from app.constants import *
from app.models import User, Feed
from app.utils import authorise_api_user, blocked_communities, blocked_or_banned_instances, filtered_out_communities, \
    communities_banned_from, moderating_communities_ids, joined_or_modding_communities, feed_tree_public, feed_tree, \
    subscribed_feeds


def get_feed_list(auth, data, user_id=None) -> dict:

    mine_only = data['mine_only'] if 'mine_only' in data else False
    include_communities = data['include_communities'] if 'include_communities' in data else True

    if auth:
        user_id = authorise_api_user(auth)

    # get the user to check if the user has hide_read posts set later down the function
    if user_id:
        user = User.query.get(user_id)
        g.user = user

        blocked_community_ids = blocked_communities(user_id)
        blocked_instance_ids = blocked_or_banned_instances(user_id)
    else:
        blocked_community_ids = []
        blocked_instance_ids = []

    if user_id and mine_only:
        feeds = feed_tree(user_id)
    else:
        feeds = feed_tree_public()

    if user_id:
        subscribed = subscribed_feeds(user_id)
        banned_from = communities_banned_from(user_id)
        communities_moderating = moderating_communities_ids(user_id)
        communities_joined = joined_or_modding_communities(user_id)
    else:
        subscribed = []
        banned_from = []
        communities_moderating = []
        communities_joined = []

    def process_nested_feeds(feed_tree):
        """Process nested feed tree while preserving nested structure"""
        processed_feeds = []
        
        for item in feed_tree:
            view = feed_view(feed=item['feed'], variant=1, user_id=user_id, subscribed=subscribed,
                             include_communities=include_communities, communities_moderating=communities_moderating,
                             banned_from=banned_from, communities_joined=communities_joined,
                             blocked_community_ids=blocked_community_ids,
                             blocked_instance_ids=blocked_instance_ids)
            
            # Process nested children
            if item['children']:
                view['children'] = process_nested_feeds(item['children'])
            else:
                view['children'] = []
            
            processed_feeds.append(view)
        
        return processed_feeds
    
    feedlist = process_nested_feeds(feeds)

    list_json = {
        "feeds": feedlist
    }

    return list_json


def get_feed(auth, data, user_id=None):
    id = data['id'] if 'id' in data else False
    name = data['name'] if 'name' in data else ''

    if auth:
        user_id = authorise_api_user(auth)

    if user_id:
        user = User.query.get(user_id)
        g.user = user

        blocked_community_ids = blocked_communities(user_id)
        blocked_instance_ids = blocked_or_banned_instances(user_id)

        subscribed = subscribed_feeds(user_id)
        banned_from = communities_banned_from(user_id)
        communities_moderating = moderating_communities_ids(user_id)
        communities_joined = joined_or_modding_communities(user_id)
    else:
        subscribed = []
        banned_from = []
        communities_moderating = []
        communities_joined = []
        blocked_community_ids = []
        blocked_instance_ids = []

    if id:
        feed = Feed.query.get(id)
    elif name:
        parts = name.split('@')
        feed = Feed.query.filter(Feed.name == parts[0], Feed.ap_domain == parts[1]).first()
    else:
        raise Exception('invalid_request')
    if feed:
        if feed.public or feed.user_id == user_id:
            return feed_view(feed, variant=2, user_id=user_id, subscribed=subscribed,
                                     include_communities=True, communities_moderating=communities_moderating,
                                     banned_from=banned_from, communities_joined=communities_joined,
                                     blocked_community_ids=blocked_community_ids,
                                     blocked_instance_ids=blocked_instance_ids)['feed']
        else:
            raise Exception('access_denied')
    else:
        raise Exception('feed_not_found')