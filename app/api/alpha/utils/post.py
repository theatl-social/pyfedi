from datetime import timedelta

from flask import current_app, g
from sqlalchemy import desc, text

from app import db
from app.api.alpha.utils.validators import required, integer_expected, boolean_expected, string_expected, \
    array_of_integers_expected
from app.api.alpha.views import post_view, post_report_view, reply_view, community_view, user_view, flair_view
from app.constants import *
from app.feed.routes import get_all_child_feed_ids
from app.models import Post, Community, CommunityMember, utcnow, User, Feed, FeedItem, Topic, PostReply, PostVote, \
    CommunityFlair
from app.shared.post import vote_for_post, bookmark_post, remove_bookmark_post, subscribe_post, make_post, edit_post, \
    delete_post, restore_post, report_post, lock_post, sticky_post, mod_remove_post, mod_restore_post, mark_post_read
from app.post.util import post_replies, get_comment_branch
from app.topic.routes import get_all_child_topic_ids
from app.utils import authorise_api_user, blocked_users, blocked_communities, blocked_instances, recently_upvoted_posts, \
    site_language_id, filtered_out_communities, communities_banned_from, joined_or_modding_communities, \
    moderating_communities_ids, user_filters_home, user_filters_posts, in_sorted_list
from app.shared.tasks import task_selector


def get_post_list(auth, data, user_id=None, search_type='Posts') -> dict:
    type = data['type_'] if data and 'type_' in data else "All"
    sort = data['sort'] if data and 'sort' in data else "Hot"
    if data and 'page_cursor' in data:
        page = int(data['page_cursor'])
    elif data and 'page' in data:
        page = int(data['page'])
    else:
        page = 1
    limit = int(data['limit']) if data and 'limit' in data else 50
    liked_only = data['liked_only'] if data and 'liked_only' in data else False
    saved_only = data['saved_only'] if data and 'saved_only' in data else False

    query = data['q'] if data and 'q' in data else ''

    if auth:
        user_id = authorise_api_user(auth)

    # get the user to check if the user has hide_read posts set later down the function
    if user_id:
        user = User.query.get(user_id)
        g.user = user   # save the currently logged in user into g, to save loading it up again and again in post_view.

    # user_id: the logged in user
    # person_id: the author of the posts being requested

    community_id = int(data['community_id']) if data and 'community_id' in data else None
    feed_id = int(data['feed_id']) if data and 'feed_id' in data else None
    topic_id = int(data['topic_id']) if data and 'topic_id' in data else None
    community_name = data['community_name'] if data and 'community_name' in data else None
    person_id = int(data['person_id']) if data and 'person_id' in data else None

    if user_id and user_id != person_id:
        blocked_person_ids = blocked_users(user_id)
        blocked_community_ids = blocked_communities(user_id)
        blocked_instance_ids = blocked_instances(user_id)
    else:
        blocked_person_ids = []
        blocked_community_ids = []
        blocked_instance_ids = []

    content_filters = {}
    u_rp_ids = []

    # Post.user_id.not_in(blocked_person_ids)               # exclude posts by blocked users
    # Post.community_id.not_in(blocked_community_ids)       # exclude posts in blocked communities
    # Post.instance_id.not_in(blocked_instance_ids)         # exclude posts by users on blocked instances
    # Community.instance_id.not_in(blocked_instance_ids)    # exclude posts in communities on blocked instances

    if type == "Local":
        posts = Post.query.filter(Post.deleted == False, Post.status > POST_STATUS_REVIEWING,
                                  Post.user_id.not_in(blocked_person_ids),
                                  Post.community_id.not_in(blocked_community_ids)). \
            join(Community, Community.id == Post.community_id).filter_by(ap_id=None)
    elif type == "Popular":
        posts = Post.query.filter(Post.deleted == False, Post.status > POST_STATUS_REVIEWING,
                                  Post.user_id.not_in(blocked_person_ids),
                                  Post.community_id.not_in(blocked_community_ids),
                                  Post.instance_id.not_in(blocked_instance_ids)). \
            join(Community, Community.id == Post.community_id).filter(Community.show_popular == True, Post.score > 100,
                                                                      Community.instance_id.not_in(
                                                                          blocked_instance_ids))
    elif type == "Subscribed" and user_id is not None:
        posts = Post.query.filter(Post.deleted == False, Post.status > POST_STATUS_REVIEWING,
                                  Post.user_id.not_in(blocked_person_ids),
                                  Post.community_id.not_in(blocked_community_ids),
                                  Post.instance_id.not_in(blocked_instance_ids)). \
            join(CommunityMember, Post.community_id == CommunityMember.community_id).filter_by(is_banned=False,
                                                                                               user_id=user_id). \
            join(Community, Community.id == CommunityMember.community_id).filter(
            Community.instance_id.not_in(blocked_instance_ids))
    elif (type == "ModeratorView" or type == "Moderating") and user_id is not None:
        posts = Post.query.filter(Post.deleted == False, Post.status > POST_STATUS_REVIEWING,
                                  Post.user_id.not_in(blocked_person_ids),
                                  Post.community_id.not_in(blocked_community_ids),
                                  Post.instance_id.not_in(blocked_instance_ids)). \
            join(CommunityMember, Post.community_id == CommunityMember.community_id).filter_by(user_id=user_id,
                                                                                               is_moderator=True). \
            join(Community, Community.id == CommunityMember.community_id).filter(
            Community.instance_id.not_in(blocked_instance_ids))
    else:  # type == "All"
        if community_name:
            if not '@' in community_name:
                community_name = f"{community_name}@{current_app.config['SERVER_NAME']}"
            name, ap_domain = community_name.split('@')
            posts = Post.query.filter(Post.deleted == False, Post.status > POST_STATUS_REVIEWING,
                                      Post.user_id.not_in(blocked_person_ids),
                                      Post.community_id.not_in(blocked_community_ids),
                                      Post.instance_id.not_in(blocked_instance_ids)). \
                join(Community, Community.id == Post.community_id).filter(Community.show_all == True,
                                                                          Community.name == name,
                                                                          Community.ap_domain == ap_domain,
                                                                          Community.instance_id.not_in(
                                                                              blocked_instance_ids))
            content_filters = user_filters_posts(user_id) if user_id else {}
        elif community_id:
            posts = Post.query.filter(Post.deleted == False, Post.status > POST_STATUS_REVIEWING,
                                      Post.user_id.not_in(blocked_person_ids),
                                      Post.community_id.not_in(blocked_community_ids),
                                      Post.instance_id.not_in(blocked_instance_ids)). \
                join(Community, Community.id == Post.community_id).filter(Community.id == community_id,
                                                                          Community.instance_id.not_in(
                                                                              blocked_instance_ids))
            content_filters = user_filters_posts(user_id) if user_id else {}
        elif feed_id:
            feed = Feed.query.get(feed_id)
            if feed.show_posts_in_children:  # include posts from child feeds
                feed_ids = get_all_child_feed_ids(feed)
            else:
                feed_ids = [feed.id]

            # for each feed get the community ids (FeedItem) in the feed
            # used for the posts searching
            feed_community_ids = []
            for fid in feed_ids:
                feed_items = FeedItem.query.join(Feed, FeedItem.feed_id == fid).all()
                for item in feed_items:
                    feed_community_ids.append(item.community_id)

            posts = Post.query.filter(Post.deleted == False, Post.status > POST_STATUS_REVIEWING,
                                      Post.user_id.not_in(blocked_person_ids),
                                      Post.community_id.not_in(blocked_community_ids),
                                      Post.instance_id.not_in(blocked_instance_ids)). \
                join(Community, Community.id == Post.community_id).filter(Community.id.in_(feed_community_ids),
                                                                          Community.instance_id.not_in(
                                                                              blocked_instance_ids))
            content_filters = user_filters_posts(user_id) if user_id else {}
        elif topic_id:
            topic = Topic.query.get(topic_id)
            if topic.show_posts_in_children:  # include posts from child feeds
                topic_ids = get_all_child_topic_ids(topic)
            else:
                topic_ids = [topic.id]

            # for each feed get the community ids (FeedItem) in the feed
            # used for the posts searching
            topic_community_ids = []
            for tid in topic_ids:
                communities = Community.query.filter(Community.topic_id == tid).all()
                for item in communities:
                    topic_community_ids.append(item.id)

            posts = Post.query.filter(Post.deleted == False, Post.status > POST_STATUS_REVIEWING,
                                      Post.user_id.not_in(blocked_person_ids),
                                      Post.community_id.not_in(blocked_community_ids),
                                      Post.instance_id.not_in(blocked_instance_ids)). \
                join(Community, Community.id == Post.community_id).filter(Community.id.in_(topic_community_ids),
                                                                          Community.instance_id.not_in(
                                                                              blocked_instance_ids))
            content_filters = user_filters_posts(user_id) if user_id else {}
        elif person_id:
            posts = Post.query.filter(Post.deleted == False, Post.status > POST_STATUS_REVIEWING,
                                      Post.community_id.not_in(blocked_community_ids),
                                      Post.instance_id.not_in(blocked_instance_ids), Post.user_id == person_id). \
                join(Community, Community.id == Post.community_id).filter(
                Community.instance_id.not_in(blocked_instance_ids))
        else:
            posts = Post.query.filter(Post.deleted == False, Post.status > POST_STATUS_REVIEWING,
                                      Post.user_id.not_in(blocked_person_ids),
                                      Post.community_id.not_in(blocked_community_ids),
                                      Post.instance_id.not_in(blocked_instance_ids)). \
                join(Community, Community.id == Post.community_id).filter(Community.show_all == True,
                                                                          Community.instance_id.not_in(
                                                                              blocked_instance_ids))
            content_filters = user_filters_home(user_id) if user_id else {}

    # change when polls and events are supported
    posts = posts.filter(Post.type != POST_TYPE_POLL).filter(Post.type != POST_TYPE_EVENT)

    if query:
        if search_type == 'Url':
            posts = posts.filter(Post.url.ilike(f"%{query}%"))
        else:
            posts = posts.filter(Post.title.ilike(f"%{query}%"))

    if user_id:
        if liked_only:
            upvoted_post_ids = recently_upvoted_posts(user_id)
            posts = posts.filter(Post.id.in_(upvoted_post_ids), Post.user_id != user_id)
        elif saved_only:
            bookmarked_post_ids = tuple(db.session.execute(text('SELECT post_id FROM "post_bookmark" WHERE user_id = :user_id'),
                                                     {"user_id": user_id}).scalars())
            posts = posts.filter(Post.id.in_(bookmarked_post_ids))
        else:
            u_rp_ids = tuple(db.session.execute(text('SELECT read_post_id FROM "read_posts" WHERE user_id = :user_id'),
                                          {"user_id": user_id}).scalars())
            if user.hide_read_posts:
                posts = posts.filter(Post.id.not_in(u_rp_ids))              # do not pass set() into not_in(), only tuples or lists

        filtered_out_community_ids = filtered_out_communities(user)
        if len(filtered_out_community_ids):
            posts = posts.filter(Post.community_id.not_in(filtered_out_community_ids))

    if sort == "Hot":
        posts = posts.order_by(desc(Post.ranking)).order_by(desc(Post.posted_at))
    elif sort == "Top" or sort == "TopDay":
        posts = posts.filter(Post.posted_at > utcnow() - timedelta(days=1)).order_by(
            desc(Post.up_votes - Post.down_votes))
    elif sort == "TopHour":
        posts = posts.filter(Post.posted_at > utcnow() - timedelta(hours=1)).order_by(
            desc(Post.up_votes - Post.down_votes))
    elif sort == "TopSixHour":
        posts = posts.filter(Post.posted_at > utcnow() - timedelta(hours=6)).order_by(
            desc(Post.up_votes - Post.down_votes))
    elif sort == "TopTwelveHour":
        posts = posts.filter(Post.posted_at > utcnow() - timedelta(hours=12)).order_by(
            desc(Post.up_votes - Post.down_votes))
    elif sort == "TopWeek":
        posts = posts.filter(Post.posted_at > utcnow() - timedelta(days=7)).order_by(
            desc(Post.up_votes - Post.down_votes))
    elif sort == "TopMonth":
        posts = posts.filter(Post.posted_at > utcnow() - timedelta(days=28)).order_by(
            desc(Post.up_votes - Post.down_votes))
    elif sort == "TopThreeMonths":
        posts = posts.filter(Post.posted_at > utcnow() - timedelta(days=90)).order_by(
            desc(Post.up_votes - Post.down_votes))
    elif sort == "TopSixMonths":
        posts = posts.filter(Post.posted_at > utcnow() - timedelta(days=180)).order_by(
            desc(Post.up_votes - Post.down_votes))
    elif sort == "TopNineMonths":
        posts = posts.filter(Post.posted_at > utcnow() - timedelta(days=270)).order_by(
            desc(Post.up_votes - Post.down_votes))
    elif sort == "TopYear":
        posts = posts.filter(Post.posted_at > utcnow() - timedelta(days=365)).order_by(
            desc(Post.up_votes - Post.down_votes))
    elif sort == "TopAll":
        posts = posts.order_by(desc(Post.up_votes - Post.down_votes))
    elif sort == "New":
        posts = posts.order_by(desc(Post.posted_at))
    elif sort == "Scaled":
        posts = posts.filter(Post.ranking_scaled != None).order_by(desc(Post.ranking_scaled)).order_by(
            desc(Post.ranking)).order_by(desc(Post.posted_at))
    elif sort == "Active":
        posts = posts.order_by(desc(Post.last_active))

    posts = posts.paginate(page=page, per_page=limit, error_out=False)

    if user_id:

        banned_from = communities_banned_from(user_id)

        bookmarked_posts = list(db.session.execute(text(
            'SELECT post_id FROM "post_bookmark" WHERE user_id = :user_id'),
            {'user_id': user_id}).scalars())
        if bookmarked_posts is None:
            bookmarked_posts = []

        post_subscriptions = list(db.session.execute(text(
            'SELECT entity_id FROM "notification_subscription" WHERE type = :type and user_id = :user_id'),
            {'type': NOTIF_POST, 'user_id': user_id}).scalars())
        if post_subscriptions is None:
            post_subscriptions = []

        read_posts = set(u_rp_ids)  # lookups ("in") on a set is O(1), tuples/lists are O(n). read_posts can be very large so this makes a difference.

        communities_moderating = moderating_communities_ids(user.id)
        communities_joined = joined_or_modding_communities(user.id)
    else:
        bookmarked_posts = []
        banned_from = []
        post_subscriptions = []
        read_posts = set()
        communities_moderating = []
        communities_joined = []

    postlist = []
    for post in posts:
        postlist.append(post_view(post=post, variant=2, stub=True, user_id=user_id,
                                  communities_moderating=communities_moderating,
                                  banned_from=banned_from, bookmarked_posts=bookmarked_posts,
                                  post_subscriptions=post_subscriptions, read_posts=read_posts,
                                  communities_joined=communities_joined, content_filters=content_filters))

    list_json = {
        "posts": postlist,
        "next_page": str(posts.next_num) if posts.next_num is not None else None
    }

    return list_json


def get_post(auth, data):
    if not data or 'id' not in data:
        raise Exception('missing parameters for post')

    id = int(data['id'])

    user_id = authorise_api_user(auth) if auth else None

    post_json = post_view(post=id, variant=3, user_id=user_id)
    return post_json


def get_post_replies(auth, data):
    sort = data['sort'] if data and 'sort' in data else 'New'
    max_depth = int(data['max_depth']) if data and 'max_depth' in data else None
    page_cursor = data['page'] if data and 'page' in data else None  # Expects reply ID or None for first page
    limit = int(data['limit']) if data and 'limit' in data else 20
    post_id = data['post_id'] if data and 'post_id' in data else None
    parent_id = data['parent_id'] if data and 'parent_id' in data else None

    if auth:
        user_details = authorise_api_user(auth, return_type='dict')
        user_id = user_details['id']
        # get_comment_branch() is borrowed from the web-ui so needs the full User
        user = User.query.filter_by(id=user_id).one()
    else:
        user_details = {}
        user_id = None
        user = None

    if parent_id:
        parent = PostReply.query.filter_by(id=parent_id).one()
        if post_id is None:
            post_id = parent.post_id
        post = Post.query.filter_by(id=post_id).one()
        replies = get_comment_branch(post, parent.id, sort.lower(), user)
    else:
        post = Post.query.filter_by(id=post_id).one()
        replies = post_replies(post, sort.lower(), user)

    is_user_banned_from_community = post.community_id in user_details['user_ban_community_ids'] if user_details else False
    is_user_following_community = post.community_id in user_details['followed_community_ids'] if user_details else False
    is_user_moderator = post.community_id in user_details['moderated_community_ids'] if user_details else False

    # Apply max_depth filter to the nested reply tree
    def filter_max_depth(reply_tree, current_depth=0, parent_depth=0):
        """Filter nested reply tree by max_depth"""
        if max_depth is None:
            return reply_tree

        filtered_tree = []
        for item in reply_tree:
            comment = item['comment']
            # Calculate depth relative to parent_id if specified, otherwise use absolute depth
            effective_depth = current_depth if parent_id else comment.depth

            if effective_depth <= max_depth:
                filtered_item = {
                    'comment': comment,
                    'replies': filter_max_depth(item['replies'], current_depth + 1, parent_depth)
                }
                filtered_tree.append(filtered_item)

        return filtered_tree

    # Apply max_depth filter
    if max_depth:
        replies = filter_max_depth(replies)

    # Apply cursor-based pagination
    def paginate_with_cursor(reply_tree, cursor_id, limit):
        """Paginate using reply ID cursor while keeping complete branches together"""
        if not reply_tree:
            return [], None

        # Find starting position based on cursor
        start_index = 0
        if cursor_id:
            try:
                cursor_id = int(cursor_id)
                # Find the top-level branch that matches this cursor
                for i, branch in enumerate(reply_tree):
                    if branch['comment'].id == cursor_id:
                        start_index = i  # Start from the cursor branch itself
                        break
                else:
                    # Cursor not found, return empty (past end)
                    return [], None
            except (ValueError, TypeError):
                # Invalid cursor, start from beginning
                start_index = 0

        # Count flattened items in branches to respect limit
        def get_branch_size(branch):
            """Count total items in a branch (including all descendants)"""
            count = 1  # The branch itself
            for child in branch['replies']:
                count += get_branch_size(child)
            return count

        # Collect branches starting from cursor position
        included_branches = []
        total_items = 0

        for i in range(start_index, len(reply_tree)):
            branch = reply_tree[i]
            branch_size = get_branch_size(branch)

            # Always include at least one branch, even if it exceeds limit
            if not included_branches:
                included_branches.append(branch)
                total_items += branch_size
            elif total_items + branch_size <= limit or total_items == 0:
                # Include this branch if it fits within limit
                included_branches.append(branch)
                total_items += branch_size
            else:
                # Would exceed limit, stop here
                break

        # Determine next cursor (ID of next top-level branch after those included)
        next_cursor = None
        if included_branches:
            last_included_index = start_index + len(included_branches) - 1
            if last_included_index + 1 < len(reply_tree):
                next_cursor = reply_tree[last_included_index + 1]['comment'].id

        return included_branches, next_cursor

    # Apply pagination
    replies, next_cursor = paginate_with_cursor(replies, page_cursor, limit)

    inner_post_view = None
    inner_community_view = None

    # Process nested reply tree while preserving structure
    def process_nested_replies(reply_tree, is_top_level=True):
        """Process nested reply tree while preserving nested structure"""
        nonlocal inner_post_view, inner_community_view
        nonlocal is_user_banned_from_community, is_user_following_community, is_user_moderator
        processed_replies = []

        for item in reply_tree:
            reply = item['comment']
            is_reply_bookmarked = reply.id in user_details['bookmarked_reply_ids'] if user_details else None
            is_creator_blocked = reply.user_id in user_details['blocked_creator_ids'] if user_details else False
            vote_effect = 0
            if user_details and in_sorted_list(user_details['upvoted_reply_ids'], reply.id):
                vote_effect = 1
            elif user_details and in_sorted_list(user_details['downvoted_reply_ids'], reply.id):
                vote_effect = -1
            is_reply_subscribed = reply.id in user_details['subscribed_reply_ids'] if user_details else None

            view = reply_view(reply=reply, variant=3, user_id=user_id,
                              is_user_banned_from_community=is_user_banned_from_community,
                              is_user_following_community=is_user_following_community,
                              is_reply_bookmarked=is_reply_bookmarked,
                              is_creator_blocked=is_creator_blocked,
                              vote_effect=vote_effect,
                              is_reply_subscribed=is_reply_subscribed,
                              is_user_moderator=is_user_moderator,
                              add_post_in_view=False,
                              add_community_in_view=False)

            # Only include post and community info on top-level replies
            if is_top_level:
                if not inner_post_view:
                    inner_post_view = post_view(post, variant=1)
                view['post'] = inner_post_view
                if not inner_community_view:
                    inner_community_view = community_view(post.community, variant=1, stub=True)
                view['community'] = inner_community_view

            # Process nested replies
            if item['replies']:
                view['replies'] = process_nested_replies(item['replies'], is_top_level=False)
            else:
                view['replies'] = []

            processed_replies.append(view)

        return processed_replies

    replylist = process_nested_replies(replies)

    list_json = {
        "comments": replylist,
        "next_page": str(next_cursor) if next_cursor is not None else None
    }

    return list_json


def post_post_like(auth, data):
    required(['post_id', 'score'], data)
    integer_expected(['post_id', 'score'], data)
    boolean_expected(['private'], data)

    post_id = data['post_id']
    score = data['score']
    private = data['private'] if 'private' in data else False
    if score == 1:
        direction = 'upvote'
    elif score == -1:
        direction = 'downvote'
    else:
        score = 0
        direction = 'reversal'

    user_id = vote_for_post(post_id, direction, not private, SRC_API, auth)
    post_json = post_view(post=post_id, variant=4, user_id=user_id, my_vote=score)
    return post_json


def put_post_save(auth, data):
    required(['post_id', 'save'], data)
    integer_expected(['post_id'], data)
    boolean_expected(['save'], data)

    post_id = data['post_id']
    save = data['save']

    user_id = bookmark_post(post_id, SRC_API, auth) if save else remove_bookmark_post(post_id, SRC_API, auth)
    post_json = post_view(post=post_id, variant=4, user_id=user_id)
    return post_json


def put_post_subscribe(auth, data):
    required(['post_id', 'subscribe'], data)
    integer_expected(['post_id'], data)
    boolean_expected(['subscribe'], data)

    post_id = data['post_id']
    subscribe = data['subscribe']

    user_id = subscribe_post(post_id, subscribe, SRC_API, auth)
    post_json = post_view(post=post_id, variant=4, user_id=user_id)
    return post_json


def post_post(auth, data):
    required(['title', 'community_id'], data)
    integer_expected(['language_id'], data)
    boolean_expected(['nsfw'], data)
    string_expected(['title', 'body', 'url'], data)

    title = data['title']
    community_id = data['community_id']
    body = data['body'] if 'body' in data else ''
    url = data['url'] if 'url' in data else None
    nsfw = data['nsfw'] if 'nsfw' in data else False
    language_id = data['language_id'] if 'language_id' in data else site_language_id()
    if language_id < 2:
        language_id = site_language_id()

    # change when Polls are supported
    type = POST_TYPE_ARTICLE
    if url:
        type = POST_TYPE_LINK

    input = {'title': title, 'body': body, 'url': url, 'nsfw': nsfw, 'language_id': language_id, 'notify_author': True}
    community = Community.query.filter_by(id=community_id).one()
    user_id, post = make_post(input, community, type, SRC_API, auth)

    post_json = post_view(post=post, variant=4, user_id=user_id)
    return post_json


def put_post(auth, data):
    required(['post_id'], data)
    integer_expected(['language_id'], data)
    boolean_expected(['nsfw'], data)
    string_expected(['title', 'body', 'url'], data)

    post_id = data['post_id']
    post = Post.query.filter_by(id=post_id).one()

    title = data['title'] if 'title' in data else post.title
    body = data['body'] if 'body' in data else post.body
    url = data['url'] if 'url' in data else post.url
    nsfw = data['nsfw'] if 'nsfw' in data else post.nsfw
    language_id = data['language_id'] if 'language_id' in data else post.language_id
    if language_id < 2:
        language_id = site_language_id()

    # change when Polls are supported
    type = POST_TYPE_ARTICLE
    if url:
        type = POST_TYPE_LINK

    input = {'title': title, 'body': body, 'url': url, 'nsfw': nsfw, 'language_id': language_id, 'notify_author': True}
    user_id, post = edit_post(input, post, type, SRC_API, auth=auth)

    post_json = post_view(post=post, variant=4, user_id=user_id)
    return post_json


def post_post_delete(auth, data):
    required(['post_id', 'deleted'], data)
    integer_expected(['post_id'], data)
    boolean_expected(['deleted'], data)

    post_id = data['post_id']
    deleted = data['deleted']

    if deleted == True:
        user_id, post = delete_post(post_id, SRC_API, auth)
    else:
        user_id, post = restore_post(post_id, SRC_API, auth)

    post_json = post_view(post=post, variant=4, user_id=user_id)
    return post_json


def post_post_report(auth, data):
    required(['post_id', 'reason'], data)
    integer_expected(['post_id'], data)
    string_expected(['reason'], data)

    post_id = data['post_id']
    reason = data['reason']
    input = {'reason': reason, 'description': '', 'report_remote': True}

    user_id, report = report_post(post_id, input, SRC_API, auth)

    post_json = post_report_view(report=report, post_id=post_id, user_id=user_id)
    return post_json


def post_post_lock(auth, data):
    required(['post_id', 'locked'], data)
    integer_expected(['post_id'], data)
    boolean_expected(['locked'], data)

    post_id = data['post_id']
    locked = data['locked']

    user_id, post = lock_post(post_id, locked, SRC_API, auth)

    post_json = post_view(post=post, variant=4, user_id=user_id)
    return post_json


def post_post_feature(auth, data):
    required(['post_id', 'featured', 'feature_type'], data)
    integer_expected(['post_id'], data)
    boolean_expected(['featured'], data)
    string_expected(['feature_type'], data)

    post_id = data['post_id']
    featured = data['featured']

    user_id, post = sticky_post(post_id, featured, SRC_API, auth)

    post_json = post_view(post=post, variant=4, user_id=user_id)
    return post_json


def post_post_remove(auth, data):
    required(['post_id', 'removed'], data)
    integer_expected(['post_id'], data)
    boolean_expected(['removed'], data)
    string_expected(['reason'], data)

    post_id = data['post_id']
    removed = data['removed']

    if removed == True:
        reason = data['reason'] if 'reason' in data else 'Removed by mod'
        user_id, post = mod_remove_post(post_id, reason, SRC_API, auth)
    else:
        reason = data['reason'] if 'reason' in data else 'Restored by mod'
        user_id, post = mod_restore_post(post_id, reason, SRC_API, auth)

    post_json = post_view(post=post, variant=4, user_id=user_id)
    return post_json


def post_post_mark_as_read(auth, data):
    required(['read'], data)
    integer_expected(['post_id'], data)
    array_of_integers_expected(['post_ids'], data)
    boolean_expected(['read'], data)

    if not 'post_id' in data and not 'post_ids' in data:
        raise Exception('post_id or post_ids required')

    user_id = authorise_api_user(auth)

    if 'post_id' in data:
        mark_post_read([data['post_id']], data['read'], user_id)
    elif 'post_ids' in data:
        mark_post_read(data['post_ids'], data['read'], user_id)

    return {"success": True}


def get_post_like_list(auth, data):
    post_id = data['post_id']
    page = data['page'] if 'page' in data else 1
    limit = data['limit'] if 'limit' in data else 50

    user = authorise_api_user(auth, return_type='model')
    post = Post.query.filter_by(id=post_id).one()

    if post.community.is_moderator(user) or user.is_admin() or user.is_staff():
        banned_from_site_user_ids = list(db.session.execute(text('SELECT id FROM "user" WHERE banned = true')).scalars())
        banned_from_community_user_ids = list(db.session.execute(text
            ('SELECT user_id from "community_ban" WHERE community_id = :community_id'), {"community_id": post.community_id}).scalars())
        likes = PostVote.query.filter(PostVote.post_id == post_id, PostVote.effect != 0).order_by(PostVote.effect).order_by(
                  PostVote.created_at).paginate(page=page, per_page=limit, error_out=False)
        post_likes = []
        for like in likes:
            post_likes.append({
                'score': like.effect,
                'creator_banned_from_community': like.user_id in banned_from_community_user_ids,
                'creator_banned': like.user_id in banned_from_site_user_ids,
                'creator': user_view(user=like.user_id, variant=1, stub=True)
            })
        response_json = {
            'next_page': str(likes.next_num) if likes.next_num is not None else None,
            'post_likes': post_likes
        }
        return response_json
    else:
        raise Exception('Not a moderator')


def put_post_set_flair(auth, data):
    post_id = data['post_id']
    flair_list = data['flair_id_list'] if 'flair_id_list' in data else []

    post = Post.query.filter_by(id=post_id).one()
    user = authorise_api_user(auth, return_type='model')
    
    if post.community.is_moderator(user) or user.is_admin_or_staff() or post.user_id == user.id:
        # Start by clearing the existing flair
        post.flair = []

        if flair_list:
            comm_flair = CommunityFlair.query.filter_by(community_id=post.community_id).all()
            flair_objs = [CommunityFlair.query.get(flair_id) for flair_id in flair_list]

            for flair in flair_objs:
                if flair in comm_flair:
                    # Flair from correct community, add it
                    post.flair.append(flair)

        db.session.commit()

        if post.status == POST_STATUS_PUBLISHED:
            task_selector('edit_post', post_id=post.id)
        
        return post_view(post=post, variant=2, stub=False)
    else:
        raise Exception("Insufficient permissions")
