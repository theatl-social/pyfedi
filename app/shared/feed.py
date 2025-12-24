from __future__ import annotations

from flask import flash
from flask_babel import _
from flask_login import current_user

from app import db
from app.constants import *
from app.models import User, Feed, FeedMember, FeedItem
from app.shared.tasks import task_selector
from app.shared.community import leave_community
from app.utils import authorise_api_user


# function can be shared between WEB and API (only WEB calls it for now)
def leave_feed(feed: int | Feed, src, auth=None, bulk_leave=False):
    if isinstance(feed, Feed):
        feed_id = feed.id
    elif isinstance(feed, int):
        feed_id = feed
        feed = db.session.query(Feed).get(feed_id)
    
    user_id = authorise_api_user(auth) if src == SRC_API else current_user.id

    fm = db.session.query(FeedMember).filter_by(user_id=user_id, feed_id=feed_id).one()

    if not fm.is_owner:
        task_selector('leave_feed', user_id=user_id, feed_id=feed_id)
        
        db.session.query(FeedMember).filter_by(user_id=user_id, feed_id=feed_id).delete()
        feed.subscriptions_count -= 1
        db.session.commit()

        if not bulk_leave:
            # Need to unsub from every community in the feed if the user has that option set
            # During bulk_leave, community memberships handled separately
            user = db.session.query(User).get(user_id)
            if user.feed_auto_leave:
                feed_items = db.session.query(FeedItem).filter_by(feed_id=feed_id).all()
                for feed_item in feed_items:
                    # Send the community unsub requests to celery - it will handle all the db commits and cache busting
                    leave_community(community_id=feed_item.community_id, src=src, auth=auth, bulk_leave=bulk_leave)

        if src == SRC_WEB and not bulk_leave:
            flash(_('You have unsubscribed from the %(feed_name)s feed, '
                    'please allow a couple minutes for it to fully process', feed_name = feed.title))
    else:
        if src == SRC_API:
            raise Exception("You cannot leave your own feed")
        else:
            flash(_('You cannot leave your own feed'), 'warning')
            return

    if src == SRC_API:
        # this is just modeled off leave_community...api is not tested
        return user_id
    else:
        # let calling function handle redirect
        return
