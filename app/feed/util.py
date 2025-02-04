from typing import List, Tuple
from app.utils import feed_tree
from flask_babel import _




def feeds_for_form(current_feed: int) -> List[Tuple[int, str]]:
    result = [(0, _('None'))]
    feeds = feed_tree()
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