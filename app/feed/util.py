from random import randint
from time import sleep
from typing import List, Tuple

import httpx
from flask import current_app
from flask_babel import _
from sqlalchemy import func, text

from app import db
from app.activitypub.util import actor_json_to_model
from app.community.util import search_for_community, retrieve_mods_and_backfill
from app.models import BannedInstances, Feed, FeedItem, Community
from app.utils import feed_tree, get_request


def feeds_for_form(current_feed: int, user_id: int) -> List[Tuple[int, str]]:
    result = [(0, _('None'))]
    feeds = feed_tree(user_id)
    for feed in feeds:
        if feed['feed'].id != current_feed:
            result.append((feed['feed'].id, feed['feed'].title))
        if feed['children']:
            result.extend(feeds_for_form_children(feed['children'], current_feed, 1))
    return result


def feeds_for_form_children(feeds, current_feed: int, depth: int) -> List[Tuple[int, str]]:
    result = []
    for feed in feeds:
        if feed['feed'].id != current_feed:
            result.append((feed['feed'].id, '--' * depth + ' ' + feed['feed'].title))
        if feed['children']:
            result.extend(feeds_for_form_children(feed['children'], current_feed, depth + 1))
    return result


def search_for_feed(address: str, allow_fetch: bool = True):
    if address.startswith('~'):
        name, server = address[1:].split('@')

        banned = BannedInstances.query.filter_by(domain=server).first()
        if banned:
            reason = f" Reason: {banned.reason}" if banned.reason is not None else ''
            raise Exception(f"{server} is blocked.{reason}")  # todo: create custom exception class hierarchy

        if current_app.config['SERVER_NAME'] == server:
            already_exists = Feed.query.filter_by(name=name, ap_id=None).first()
            return already_exists

        already_exists = Feed.query.filter_by(ap_id=address[1:]).first()
        if already_exists:
            return already_exists
        elif not allow_fetch:
            return None

        # Look up the profile address of the Feed using WebFinger
        try:
            webfinger_data = get_request(f"https://{server}/.well-known/webfinger",
                                         params={'resource': f"acct:{address}"})  # include the ~ on the start to indicate we're searching for a feed
        except httpx.HTTPError:
            sleep(randint(3, 10))
            try:
                webfinger_data = get_request(f"https://{server}/.well-known/webfinger",
                                             params={'resource': f"acct:{address}"})
            except httpx.HTTPError:
                return None

        if webfinger_data.status_code == 200:
            webfinger_json = webfinger_data.json()
            for links in webfinger_json['links']:
                if 'rel' in links and links['rel'] == 'self':  # this contains the URL of the activitypub profile
                    type = links['type'] if 'type' in links else 'application/activity+json'
                    # retrieve the activitypub profile
                    feed_data = get_request(links['href'], headers={'Accept': type})
                    if feed_data.status_code == 200:
                        feed_json = feed_data.json()
                        feed_data.close()
                        if feed_json['type'] == 'Feed':
                            feed = actor_json_to_model(feed_json, name, server)
                            if feed:
                                initialise_new_communities(feed)
                                return feed
        return None


def actor_to_feed(actor) -> Feed:
    actor = actor.strip()
    if '@' in actor:
        feed = Feed.query.filter_by(ap_id=actor).first()
    else:
        feed = Feed.query.filter(func.lower(Feed.name) == func.lower(actor)).filter_by(ap_id=None).first()
    return feed


def feed_communities_for_edit(feed_id: int) -> str:
    return_value = []
    for community in Community.query.filter(Community.banned == False).join(FeedItem, FeedItem.community_id == Community.id).\
            filter(FeedItem.feed_id == feed_id).all():
        ap_id = community.link()
        if '@' not in ap_id:
            ap_id = f'{ap_id}@{current_app.config["SERVER_NAME"]}'
        return_value.append(ap_id)
    return "\n".join(sorted(return_value))


def existing_communities(feed_id: int) -> List:
    return db.session.execute(text('SELECT community_id FROM feed_item WHERE feed_id = :feed_id'),
                              {'feed_id': feed_id}).scalars()


def form_communities_to_ids(form_communities: str) -> set:
    result = set()
    parts = form_communities.strip().split('\n')
    for community_ap_id in parts:
        if not community_ap_id.startswith('!'):
            community_ap_id = '!' + community_ap_id
        if not '@' in community_ap_id:
            community_ap_id = community_ap_id + '@' + current_app.config['SERVER_NAME']
        community = search_for_community(community_ap_id.strip())
        if community:
            result.add(community.id)
    return result


def initialise_new_communities(feed):
    if feed.num_communities == 0:
        return

    for feed_item in feed.member_communities:
        community = Community.query.get(feed_item.community_id)
        if community and community.post_count == 0:
            if current_app.debug:
                retrieve_mods_and_backfill(community.id, community.ap_domain, community.name)
                break  # just get 2 posts from 1 new community when in debug
            else:
                retrieve_mods_and_backfill.delay(community.id, community.ap_domain, community.name)
