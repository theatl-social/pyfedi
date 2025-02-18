import httpx
from typing import List, Tuple
from app.activitypub.util import actor_json_to_model
from app.models import BannedInstances, Feed
from app.utils import feed_tree, get_request
from flask import current_app
from flask_babel import _
from time import sleep
from random import randint
from sqlalchemy import func


def feeds_for_form(current_feed: int, user_id: int) -> List[Tuple[int, str]]:
    result = [(0, _('None'))]
    feeds = feed_tree(user_id)
    for feed in feeds:
        if feed['feed'].id != current_feed:
            result.append((feed['feed'].id, feed['feed'].name))
        if feed['children']:
            result.extend(feeds_for_form_children(feed['children'], current_feed, 1))
    return result


def feeds_for_form_children(feeds, current_feed: int, depth: int) -> List[Tuple[int, str]]:
    result = []
    for feed in feeds:
        if feed['feed'].id != current_feed:
            result.append((feed['feed'].id, '--' * depth + ' ' + feed['feed'].name))
        if feed['children']:
            result.extend(feeds_for_form_children(feed['children'], current_feed, depth + 1))
    return result


def search_for_feed(address: str):
    print('in search_for_feed()')
    if address.startswith('~'):
        name, server = address[1:].split('@')

        print(f'address started with ~, name: {name}, server: {server}')

        banned = BannedInstances.query.filter_by(domain=server).first()
        if banned:
            reason = f" Reason: {banned.reason}" if banned.reason is not None else ''
            raise Exception(f"{server} is blocked.{reason}")  # todo: create custom exception class hierarchy

        if current_app.config['SERVER_NAME'] == server:
            already_exists = Feed.query.filter_by(name=name, ap_id=None).first()
            print(f'server == current_app.config SERVERNAME, already_exists: {already_exists}')
            return already_exists

        already_exists = Feed.query.filter_by(ap_id=address[1:]).first()
        if already_exists:
            print(f'server does not equal SERVER_NAME, already_exists: {already_exists}')
            return already_exists

        # Look up the profile address of the Feed using WebFinger
        try:
            webfinger_data = get_request(f"https://{server}/.well-known/webfinger",
                                         params={'resource': f"acct:{address[1:]}"})
            print(f'webfinger_data: {webfinger_data}')
        except httpx.HTTPError:
            sleep(randint(3, 10))
            try:
                webfinger_data = get_request(f"https://{server}/.well-known/webfinger",
                                            params={'resource': f"acct:{address[1:]}"})
            except httpx.HTTPError:
                return None

        if webfinger_data.status_code == 200:
            webfinger_json = webfinger_data.json()
            print(f'webfinger_data was 200, webfinger_json: {webfinger_json}')
            for links in webfinger_json['links']:
                if 'rel' in links and links['rel'] == 'self':  # this contains the URL of the activitypub profile
                    type = links['type'] if 'type' in links else 'application/activity+json'
                    # retrieve the activitypub profile
                    feed_data = get_request(links['href'], headers={'Accept': type})
                    if feed_data.status_code == 200:
                        print(f'feed_data: {feed_data}')
                        feed_json = feed_data.json()
                        print(f'feed_json: {feed_json}')
                        feed_data.close()
                        if feed_json['type'] == 'Feed':
                            feed = actor_json_to_model(feed_json, name, server)
                            print(f'feed after actor_json_to_model: {feed}')
                            if feed:
                                return feed
                            #     if current_app.debug:
                            #         retrieve_mods_and_backfill(community.id, server, name, community_json)
                            #     else:
                            #         retrieve_mods_and_backfill.delay(community.id, server, name, community_json)
                            # return community
        return None

def actor_to_feed(actor) -> Feed:
    actor = actor.strip()
    if '@' in actor:
        feed = Feed.query.filter_by(ap_id=actor).first()
    else:
        feed = Feed.query.filter(func.lower(Feed.name) == func.lower(actor)).filter_by(ap_id=None).first()
    return feed