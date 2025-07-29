from datetime import timedelta

from flask import current_app, g
from sqlalchemy import desc, text

from app import db
from app.api.alpha.utils.validators import required, integer_expected, boolean_expected, string_expected, \
    array_of_integers_expected
from app.api.alpha.views import feed_view, topic_view
from app.constants import *
from app.models import User
from app.utils import authorise_api_user, blocked_communities, blocked_instances, filtered_out_communities, \
    communities_banned_from, moderating_communities_ids, joined_or_modding_communities, feed_tree_public, feed_tree, \
    subscribed_feeds, topic_tree


def get_topic_list(auth, data, user_id=None) -> dict:

    if auth:
        user_id = authorise_api_user(auth)

    # get the user to check if the user has hide_read posts set later down the function
    if user_id:
        user = User.query.get(user_id)
        g.user = user

        blocked_community_ids = blocked_communities(user_id)
        blocked_instance_ids = blocked_instances(user_id)
    else:
        blocked_community_ids = []
        blocked_instance_ids = []

    topics = topic_tree()

    if user_id:
        banned_from = communities_banned_from(user_id)
        communities_moderating = moderating_communities_ids(user_id)
        communities_joined = joined_or_modding_communities(user_id)
    else:
        banned_from = []
        communities_moderating = []
        communities_joined = []

    def process_nested_topics(feed_tree):
        """Process nested feed tree while preserving nested structure"""
        processed_feeds = []

        for item in feed_tree:
            view = topic_view(topic=item['topic'], variant=1,
                             communities_moderating=communities_moderating,
                             banned_from=banned_from, communities_joined=communities_joined,
                             blocked_community_ids=blocked_community_ids,
                             blocked_instance_ids=blocked_instance_ids)

            # Process nested children
            if item['children']:
                view['children'] = process_nested_topics(item['children'])
            else:
                view['children'] = []

            processed_feeds.append(view)

        return processed_feeds

    feedlist = process_nested_topics(topics)

    list_json = {
        "feeds": feedlist
    }

    return list_json