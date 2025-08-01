from flask import g
from sqlalchemy import desc, or_, text

from app import db
from app.api.alpha.utils.validators import required, integer_expected, boolean_expected, string_expected
from app.api.alpha.views import reply_view, reply_report_view, post_view, community_view
from app.constants import *
from app.models import Notification, PostReply, Post, User
from app.post.util import post_replies, get_comment_branch
from app.shared.reply import vote_for_reply, bookmark_reply, remove_bookmark_reply, subscribe_reply, make_reply, \
    edit_reply, \
    delete_reply, restore_reply, report_reply, mod_remove_reply, mod_restore_reply
from app.utils import authorise_api_user, blocked_users, blocked_instances, site_language_id, \
    recently_upvoted_post_replies, communities_banned_from


def get_reply_list(auth, data, user_id=None):
    sort = data['sort'] if data and 'sort' in data else "New"
    depth_first = data['depth_first'] if data and 'depth_first' in data else ""  # sort by depth before sorting by anything else
    max_depth = data['max_depth'] if data and 'max_depth' in data else None
    page = int(data['page']) if data and 'page' in data else 1
    limit = int(data['limit']) if data and 'limit' in data else 10
    post_id = data['post_id'] if data and 'post_id' in data else None
    parent_id = data['parent_id'] if data and 'parent_id' in data else None
    person_id = data['person_id'] if data and 'person_id' in data else None
    community_id = data['community_id'] if data and 'community_id' in data else None
    liked_only = data['liked_only'] if data and 'liked_only' in data else 'false'
    liked_only = True if liked_only == 'true' else False
    saved_only = data['saved_only'] if data and 'saved_only' in data else 'false'
    saved_only = True if saved_only == 'true' else False

    # user_id: the logged in user
    # person_id: the author of the posts being requested

    if auth:
        user_id = authorise_api_user(auth)

    if user_id:
        g.user = User.query.get(user_id)    # save the currently logged in user into g, to save loading it up again and again in reply_view.

    post_is_same = False
    community_is_same = False
    if parent_id and post_id:
        replies = PostReply.query.filter(PostReply.root_id == parent_id, PostReply.post_id == post_id)
        if replies.count() == 0:
            reply_ids = db.session.execute(text('select id from "post_reply" where path @> ARRAY[:id]'),
                                           {"id": int(parent_id)}).scalars()
            replies = PostReply.query.filter(PostReply.id.in_(reply_ids), PostReply.post_id == post_id)
        post_is_same = community_is_same = True
    elif post_id:
        replies = PostReply.query.filter(PostReply.post_id == post_id)
        post_is_same = community_is_same = True
    elif parent_id:
        replies = PostReply.query.filter(PostReply.root_id == parent_id)
        if replies.count() == 0:
            reply_ids = db.session.execute(text('SELECT id FROM "post_reply" WHERE path @> ARRAY[:id]'),
                                           {"id": int(parent_id)}).scalars()
            replies = PostReply.query.filter(PostReply.id.in_(reply_ids))
        post_is_same = community_is_same = True
    elif person_id:
        replies = PostReply.query.filter_by(user_id=person_id)
    elif community_id:
        replies = PostReply.query.filter_by(community_id=community_id)
        community_is_same = True
    else:
        replies = PostReply.query

    if max_depth:
        replies = replies.filter(PostReply.depth <= max_depth)

    if user_id and user_id != person_id:
        blocked_person_ids = blocked_users(user_id)
        if blocked_person_ids:
            replies = replies.filter(PostReply.user_id.not_in(blocked_person_ids))
        blocked_instance_ids = blocked_instances(user_id)
        if blocked_instance_ids:
            replies = replies.filter(PostReply.instance_id.not_in(blocked_instance_ids))

    if user_id and liked_only:
        upvoted_reply_ids = recently_upvoted_post_replies(user_id)
        replies = replies.filter(PostReply.id.in_(upvoted_reply_ids), PostReply.user_id != user_id)
    elif user_id and saved_only:
        bookmarked_reply_ids = db.session.execute(
            text('SELECT post_reply_id FROM "post_reply_bookmark" WHERE user_id = :user_id'),
            {"user_id": user_id}).scalars()
        replies = replies.filter(PostReply.id.in_(bookmarked_reply_ids))

    if depth_first:
        replies = replies.order_by(PostReply.depth)
    if sort == "Hot":
        replies = replies.order_by(desc(PostReply.ranking)).order_by(desc(PostReply.posted_at))
    elif sort == "Top":
        replies = replies.order_by(desc(PostReply.up_votes - PostReply.down_votes))
    elif sort == "New":
        replies = replies.order_by(desc(PostReply.posted_at))

    if page is not None:
        replies = replies.paginate(page=page, per_page=limit, error_out=False)
    else:
        replies = replies.all()

    replylist = []
    inner_post_view = None
    inner_community_view = None
    can_auth_user_moderate = False
    mods = None
    banned_from = communities_banned_from(user_id)
    bookmarked_replies = list(db.session.execute(text(
        'SELECT post_reply_id FROM "post_reply_bookmark" WHERE user_id = :user_id'),
        {'user_id': user_id}).scalars())
    if bookmarked_replies is None:
        bookmarked_replies = []
    reply_subscriptions = list(db.session.execute(text(
        'SELECT entity_id FROM "notification_subscription" WHERE type = :type and user_id = :user_id'),
        {'type': NOTIF_REPLY, 'user_id': user_id}).scalars())
    if reply_subscriptions is None:
        reply_subscriptions = []

    for reply in replies:
        if post_is_same and community_is_same:
            if mods is None:
                mods = [moderator.user_id for moderator in reply.community.moderators()]
            view = reply_view(reply=reply, variant=7, user_id=user_id, mods=mods, banned_from=banned_from,
                              bookmarked_replies=bookmarked_replies, reply_subscriptions=reply_subscriptions)
            if not inner_post_view:
                inner_post_view = post_view(reply.post, variant=1)
            view['post'] = inner_post_view
            if not inner_community_view:
                inner_community_view = community_view(reply.community, variant=1, stub=True)
                if user_id:
                    can_auth_user_moderate = user_id in mods
            view['community'] = inner_community_view
            view['can_auth_user_moderate'] = can_auth_user_moderate
            replylist.append(view)
        elif community_is_same:
            if mods is None:
                mods = [moderator.user_id for moderator in reply.community.moderators()]
            view = reply_view(reply=reply, variant=8, user_id=user_id, mods=mods, banned_from=banned_from)
            if not inner_community_view:
                inner_community_view = community_view(reply.community, variant=1, stub=True)
                if user_id:
                    can_auth_user_moderate = user_id in mods
            view['community'] = inner_community_view
            view['can_auth_user_moderate'] = can_auth_user_moderate
            replylist.append(view)
        else:
            replylist.append(reply_view(reply=reply, variant=9, user_id=user_id))

    list_json = {
        "comments": replylist,
        "next_page": str(replies.next_num) if replies.next_num is not None else None
    }

    return list_json


def get_post_reply_list(auth, data, user_id=None):
    sort = data['sort'] if data and 'sort' in data else "New"
    max_depth = int(data['max_depth']) if data and 'max_depth' in data else None
    page_cursor = data['page'] if data and 'page' in data else None  # Now expects reply ID or None for first page
    limit = int(data['limit']) if data and 'limit' in data else 20
    post_id = data['post_id'] if data and 'post_id' in data else None
    parent_id = data['parent_id'] if data and 'parent_id' in data else None

    if auth:
        user_id = authorise_api_user(auth)

    if user_id:
        g.user = User.query.get(user_id)    # save the currently logged in user into g, to save loading it up again and again in reply_view.

    if parent_id:
        parent = PostReply.query.get_or_404(parent_id)
        if post_id is None:
            post_id = parent.post_id
        post = Post.query.get(post_id)
        replies = get_comment_branch(post, parent.id, sort.lower(), g.user if hasattr(g, 'user') else None)
    else:
        post = Post.query.get(post_id)
        replies = post_replies(post, sort.lower(), g.user if hasattr(g, 'user') else None)

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
    can_auth_user_moderate = False
    mods = None
    banned_from = communities_banned_from(user_id)
    bookmarked_replies = list(db.session.execute(text(
        'SELECT post_reply_id FROM "post_reply_bookmark" WHERE user_id = :user_id'),
        {'user_id': user_id}).scalars())
    if bookmarked_replies is None:
        bookmarked_replies = []
    reply_subscriptions = list(db.session.execute(text(
        'SELECT entity_id FROM "notification_subscription" WHERE type = :type and user_id = :user_id'),
        {'type': NOTIF_REPLY, 'user_id': user_id}).scalars())
    if reply_subscriptions is None:
        reply_subscriptions = []

    # Process nested reply tree while preserving structure
    def process_nested_replies(reply_tree, is_top_level=True):
        """Process nested reply tree while preserving nested structure"""
        nonlocal mods, inner_post_view, inner_community_view, can_auth_user_moderate
        processed_replies = []
        
        for item in reply_tree:
            reply = item['comment']
            if mods is None:
                mods = [moderator.user_id for moderator in post.community.moderators()]
            
            view = reply_view(reply=reply, variant=7, user_id=user_id, mods=mods, banned_from=banned_from,
                              bookmarked_replies=bookmarked_replies, reply_subscriptions=reply_subscriptions)
            
            # Only include post and community info on top-level replies
            if is_top_level:
                if not inner_post_view:
                    inner_post_view = post_view(post, variant=1)
                view['post'] = inner_post_view
                if not inner_community_view:
                    inner_community_view = community_view(post.community, variant=1, stub=True)
                    if user_id:
                        can_auth_user_moderate = user_id in mods
                view['community'] = inner_community_view
                view['can_auth_user_moderate'] = can_auth_user_moderate
            
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


def get_reply(auth, data):
    if not data or 'id' not in data:
        raise Exception('missing parameters for comment')

    id = int(data['id'])

    user_id = authorise_api_user(auth) if auth else None

    reply_json = reply_view(reply=id, variant=4, user_id=user_id)
    return reply_json


def post_reply_like(auth, data):
    required(['comment_id', 'score'], data)
    integer_expected(['comment_id', 'score'], data)
    boolean_expected(['private'], data)

    score = data['score']
    reply_id = data['comment_id']
    if score == 1:
        direction = 'upvote'
    elif score == -1:
        direction = 'downvote'
    else:
        score = 0
        direction = 'reversal'
    private = data['private'] if 'private' in data else False

    user_id = vote_for_reply(reply_id, direction, not private, SRC_API, auth)
    reply_json = reply_view(reply=reply_id, variant=4, user_id=user_id, my_vote=score)
    return reply_json


def put_reply_save(auth, data):
    required(['comment_id', 'save'], data)
    integer_expected(['comment_id'], data)
    boolean_expected(['save'], data)

    reply_id = data['comment_id']
    save = data['save']

    user_id = bookmark_reply(reply_id, SRC_API, auth) if save else remove_bookmark_reply(reply_id, SRC_API, auth)
    reply_json = reply_view(reply=reply_id, variant=4, user_id=user_id)
    return reply_json


def put_reply_subscribe(auth, data):
    required(['comment_id', 'subscribe'], data)
    integer_expected(['comment_id'], data)
    boolean_expected(['subscribe'], data)

    reply_id = data['comment_id']
    subscribe = data['subscribe']

    user_id = subscribe_reply(reply_id, subscribe, SRC_API, auth)
    reply_json = reply_view(reply=reply_id, variant=4, user_id=user_id)
    return reply_json


def post_reply(auth, data):
    required(['body', 'post_id'], data)
    string_expected(['body', ], data)
    integer_expected(['post_id', 'parent_id', 'language_id'], data)

    body = data['body']
    post_id = data['post_id']
    parent_id = data['parent_id'] if 'parent_id' in data else None
    language_id = data['language_id'] if 'language_id' in data else site_language_id()
    if language_id < 2:
        language_id = site_language_id()

    input = {'body': body, 'notify_author': True, 'language_id': language_id}
    post = Post.query.filter_by(id=post_id).one()

    user_id, reply = make_reply(input, post, parent_id, SRC_API, auth)

    reply_json = reply_view(reply=reply, variant=4, user_id=user_id)
    return reply_json


def put_reply(auth, data):
    required(['comment_id'], data)
    string_expected(['body', ], data)
    integer_expected(['comment_id', 'language_id'], data)
    boolean_expected(['distinguished'], data)

    reply_id = data['comment_id']
    reply = PostReply.query.filter_by(id=reply_id).one()

    body = data['body'] if 'body' in data else reply.body
    language_id = data['language_id'] if 'language_id' in data else reply.language_id
    distinguished = data['distinguished'] if 'distinguished' in data else False
    if language_id < 2:
        language_id = site_language_id()

    input = {'body': body, 'notify_author': True, 'language_id': language_id, 'distinguished': distinguished}
    post = Post.query.filter_by(id=reply.post_id).one()

    user_id, reply = edit_reply(input, reply, post, SRC_API, auth)

    reply_json = reply_view(reply=reply, variant=4, user_id=user_id)
    return reply_json


def post_reply_delete(auth, data):
    required(['comment_id', 'deleted'], data)
    integer_expected(['comment_id'], data)
    boolean_expected(['deleted'], data)

    reply_id = data['comment_id']
    deleted = data['deleted']

    if deleted == True:
        user_id, reply = delete_reply(reply_id, SRC_API, auth)
    else:
        user_id, reply = restore_reply(reply_id, SRC_API, auth)

    reply_json = reply_view(reply=reply, variant=4, user_id=user_id)
    return reply_json


def post_reply_report(auth, data):
    required(['comment_id', 'reason'], data)
    integer_expected(['comment_id'], data)
    string_expected(['reason'], data)

    reply_id = data['comment_id']
    reason = data['reason']
    input = {'reason': reason, 'description': '', 'report_remote': True}

    user_id, report = report_reply(reply_id, input, SRC_API, auth)

    reply_json = reply_report_view(report=report, reply_id=reply_id, user_id=user_id)
    return reply_json


def post_reply_remove(auth, data):
    required(['comment_id', 'removed'], data)
    integer_expected(['comment_id'], data)
    boolean_expected(['removed'], data)
    string_expected(['reason'], data)

    reply_id = data['comment_id']
    removed = data['removed']

    if removed == True:
        reason = data['reason'] if 'reason' in data else 'Removed by mod'
        user_id, reply = mod_remove_reply(reply_id, reason, SRC_API, auth)
    else:
        reason = data['reason'] if 'reason' in data else 'Restored by mod'
        user_id, reply = mod_restore_reply(reply_id, reason, SRC_API, auth)

    reply_json = reply_view(reply=reply, variant=4, user_id=user_id)
    return reply_json


def post_reply_mark_as_read(auth, data):
    required(['comment_reply_id', 'read'], data)
    integer_expected(['comment_reply_id'], data)
    boolean_expected(['read'], data)

    reply_id = data['comment_reply_id']
    read = data['read']

    user = authorise_api_user(auth, return_type='model')

    # no real support for this. Just marking the Notification for the reply really
    # notification has its own id, which would be handy, but reply_view is currently just returning the reply.id for that
    reply = PostReply.query.filter_by(id=reply_id).one()

    reply_url = '#comment_' + str(reply.id)
    mention_url = '/comment/' + str(reply.id)
    notification = Notification.query.filter(Notification.user_id == user.id,
                                             or_(Notification.url.ilike(f"%{reply_url}%"),
                                                 Notification.url.ilike(f"%{mention_url}%"))).first()
    if notification:
        notification.read = read
        if read == True and user.unread_notifications > 0:
            user.unread_notifications -= 1
        elif read == False:
            user.unread_notifications += 1
        db.session.commit()

    reply_json = {'comment_reply_view': reply_view(reply=reply, variant=5, user_id=user.id, read=True)}
    return reply_json
