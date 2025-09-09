from flask import current_app
from sqlalchemy import desc, func, text
from sqlalchemy.orm.exc import NoResultFound

from app import cache, db
from app.activitypub.util import make_image_sizes
from app.api.alpha.utils.post import get_post_list
from app.api.alpha.utils.reply import get_reply_list
from app.api.alpha.utils.validators import (
    boolean_expected,
    integer_expected,
    required,
    string_expected,
)
from app.api.alpha.views import community_view, post_view, reply_view, user_view
from app.constants import *
from app.models import (
    ChatMessage,
    Community,
    Conversation,
    File,
    Notification,
    Post,
    PostReply,
    User,
    UserFlair,
)
from app.shared.user import block_another_user, subscribe_user, unblock_another_user
from app.utils import (
    authorise_api_user,
    blocked_users,
    communities_banned_from,
    in_sorted_list,
    user_in_restricted_country,
)


def get_user(auth, data):
    if not data or ("person_id" not in data and "username" not in data):
        raise Exception("missing_parameters")
    if "person_id" in data:
        person = int(data["person_id"])
    elif "username" in data:
        person = data["username"]
        if "@" not in person:
            name = person.lower()
            ap_domain = None
        else:
            name, ap_domain = person.strip().split("@")
            name = name.lower()
            if ap_domain == current_app.config["SERVER_NAME"]:
                ap_domain = None
            else:
                ap_domain = ap_domain.lower()
        person = User.query.filter(
            func.lower(User.user_name) == name,
            func.lower(User.ap_domain) == ap_domain,
            User.deleted == False,
        ).one()
        data["person_id"] = person.id
    include_content = data["include_content"] if "include_content" in data else False
    # include_content = True if include_content == 'true' else False
    saved_only = data["saved_only"] if "saved_only" in data else False
    # saved_only = True if saved_only == 'true' else False
    data["limit"] = data["limit"] if data and "limit" in data else 20

    user_details = None
    user_id = None
    if auth:
        user_details = authorise_api_user(auth, return_type="dict")
        if user_details:
            user_id = user_details["id"]
        auth = (
            None  # avoid authenticating user again in get_post_list and get_reply_list
        )

    # bit unusual. have to help construct the json here rather than in views, to avoid circular dependencies
    if include_content or saved_only:
        if saved_only:
            del data["person_id"]
        post_list = get_post_list(auth, data, user_id)
        reply_list = get_reply_list(auth, data, user_details)
    else:
        post_list = {"posts": []}
        reply_list = {"comments": []}

    user_json = user_view(user=person, variant=3, user_id=user_id)
    user_json["posts"] = post_list["posts"]
    user_json["comments"] = reply_list["comments"]
    return user_json


def get_user_list(auth, data):
    # only support 'api/alpha/search?q&type_=Users&sort=Top&listing_type=Local&page=1&limit=15' for now
    # (enough for instance view)

    type = data["type_"] if data and "type_" in data else "All"
    page = int(data["page"]) if data and "page" in data else 1
    sort = data["sort"] if data and "sort" in data else "Hot"
    limit = int(data["limit"]) if data and "limit" in data else 10

    query = data["q"] if data and "q" in data else ""

    user_id = authorise_api_user(auth) if auth else None

    if type == "Local":
        users = User.query.filter_by(instance_id=1, deleted=False, verified=True)
    else:
        users = User.query.filter(User.instance_id != 1, User.deleted == False)

    if query:
        if "@" in query:
            users = users.filter(User.ap_id.ilike(f"%{query}%"))
        else:
            users = users.filter(User.user_name.ilike(f"%{query}%"))

    if sort == "New":
        users = users.order_by(desc(User.created))
    elif sort.startswith("Top"):
        users = users.order_by(desc(User.post_count))
    else:
        users = users.order_by(User.id)

    users = users.paginate(page=page, per_page=limit, error_out=False)

    user_list = []
    for user in users:
        user_list.append(user_view(user, variant=2, stub=True, user_id=user_id))
    list_json = {
        "users": user_list,
        "next_page": str(users.next_num) if users.next_num else None,
    }

    return list_json


def post_user_block(auth, data):
    required(["person_id", "block"], data)
    integer_expected(["post_id"], data)
    boolean_expected(["block"], data)

    person_id = data["person_id"]
    block = data["block"]

    user_id = (
        block_another_user(person_id, SRC_API, auth)
        if block
        else unblock_another_user(person_id, SRC_API, auth)
    )
    user_json = user_view(user=person_id, variant=4, user_id=user_id)
    return user_json


def get_user_unread_count(auth):
    user = authorise_api_user(auth, return_type="model")
    unread_replies = unread_messages = unread_mentions = 0
    unread_notifications = user.unread_notifications
    if unread_notifications > 0:
        unread_comment_replies = db.session.execute(
            text(
                "SELECT COUNT(id) as c FROM notification WHERE user_id = :user_id AND read = false \
                AND notif_type = :notif_type AND subtype = 'new_reply_on_followed_comment'"
            ),
            {"user_id": user.id, "notif_type": NOTIF_REPLY},
        ).scalar()
        unread_post_replies = db.session.execute(
            text(
                "SELECT COUNT(id) as c FROM notification WHERE user_id = :user_id AND read = false \
                AND notif_type = :notif_type AND subtype = 'top_level_comment_on_followed_post'"
            ),
            {"user_id": user.id, "notif_type": NOTIF_POST},
        ).scalar()
        unread_replies = unread_comment_replies + unread_post_replies
        unread_comment_mentions = db.session.execute(
            text(
                "SELECT COUNT(id) as c FROM notification WHERE user_id = :user_id AND read = false \
                AND notif_type = :notif_type AND subtype = 'comment_mention'"
            ),
            {"user_id": user.id, "notif_type": NOTIF_MENTION},
        ).scalar()
        unread_post_mentions = db.session.execute(
            text(
                "SELECT COUNT(id) as c FROM notification WHERE user_id = :user_id AND read = false \
                AND notif_type = :notif_type AND subtype = 'post_mention'"
            ),
            {"user_id": user.id, "notif_type": NOTIF_MENTION},
        ).scalar()
        unread_mentions = unread_comment_mentions + unread_post_mentions
        unread_messages = db.session.execute(
            text(
                "SELECT COUNT(id) as c FROM chat_message WHERE recipient_id = :user_id AND read = false"
            ),
            {"user_id": user.id},
        ).scalar()

    # "other" is things like reports and activity alerts that this endpoint isn't really intended to support

    unread_count = {
        "replies": unread_replies,
        "mentions": unread_mentions,
        "private_messages": unread_messages,
        "other": unread_notifications
        - unread_replies
        - unread_messages
        - unread_mentions,
    }

    return unread_count


def get_user_replies(auth, data, mentions=False):
    page = int(data["page"]) if data and "page" in data else 1
    limit = int(data["limit"]) if data and "limit" in data else 10
    sort = data["sort"] if data and "sort" in data else "New"
    unread_only = data["unread_only"] if data and "unread_only" in data else True

    user_details = authorise_api_user(auth, return_type="dict")
    user_id = user_details["id"]

    all_comment_ids = []
    read_comment_ids = []
    if unread_only:
        if not mentions:
            query = "SELECT targets FROM notification WHERE user_id = :user_id and \
                    (subtype = 'new_reply_on_followed_comment' or subtype = 'top_level_comment_on_followed_post')"
        else:
            query = "SELECT targets FROM notification WHERE user_id = :user_id and subtype = 'comment_mention'"
        query += " AND read = false"
        targets = db.session.execute(text(query), {"user_id": user_id}).scalars()

        for target in targets:
            if "comment_id" in target:
                all_comment_ids.append(target["comment_id"])
    else:
        if not mentions:
            query = "SELECT targets, read FROM notification WHERE user_id = :user_id and \
                    (subtype = 'new_reply_on_followed_comment' or subtype = 'top_level_comment_on_followed_post')"
        else:
            query = "SELECT targets, read FROM notification WHERE user_id = :user_id and subtype = 'comment_mention'"
        results = db.session.execute(text(query), {"user_id": user_id}).all()

        for result in results:
            # result[0] = Notification.targets
            # result[1] = Notification.read
            if "comment_id" in result[0]:
                all_comment_ids.append(result[0]["comment_id"])
            if result[1] == True:
                read_comment_ids.append(result[0]["comment_id"])

    replies = PostReply.query.filter(PostReply.id.in_(all_comment_ids))
    if sort == "Hot":
        replies = replies.order_by(desc(PostReply.ranking)).order_by(
            desc(PostReply.posted_at)
        )
    elif sort == "Top":
        replies = replies.order_by(desc(PostReply.up_votes - PostReply.down_votes))
    elif sort == "Old":
        replies = replies.order_by(PostReply.posted_at)
    else:
        replies = replies.order_by(desc(PostReply.posted_at))
    replies = replies.paginate(page=page, per_page=limit, error_out=False)

    reply_list = []
    recipient = user_view(user=user_id, variant=1)
    for reply in replies:
        vote_effect = 0
        if in_sorted_list(user_details["upvoted_reply_ids"], reply.id):
            vote_effect = 1
        elif in_sorted_list(user_details["downvoted_reply_ids"], reply.id):
            vote_effect = -1
        reply_json = reply_view(
            reply=reply,
            variant=3,
            user_id=user_id,
            is_user_banned_from_community=reply.community_id
            in user_details["user_ban_community_ids"],
            is_user_following_community=reply.community_id
            in user_details["followed_community_ids"],
            is_reply_bookmarked=reply.id in user_details["bookmarked_reply_ids"],
            is_creator_blocked=reply.user_id in user_details["blocked_creator_ids"],
            vote_effect=vote_effect,
            is_reply_subscribed=reply.id in user_details["subscribed_reply_ids"],
            is_user_moderator=reply.community_id
            in user_details["moderated_community_ids"],
        )
        reply_json["comment_reply"] = reply_view(
            reply=reply, variant=6, user_id=user_id, read_comment_ids=read_comment_ids
        )
        reply_json["recipient"] = recipient
        reply_list.append(reply_json)
    list_json = {
        "replies": reply_list,
        "next_page": str(replies.next_num) if replies.next_num else None,
    }

    return list_json


def post_user_mark_all_as_read(auth):
    user = authorise_api_user(auth, return_type="model")

    notifications = Notification.query.filter_by(user_id=user.id, read=False)
    for notification in notifications:
        notification.read = True

    user.unread_notifications = 0

    conversations = (
        Conversation.query.filter_by(read=False)
        .join(ChatMessage, ChatMessage.conversation_id == Conversation.id)
        .filter_by(recipient_id=user.id)
    )
    for conversation in conversations:
        conversation.read = True

    chat_messages = ChatMessage.query.filter_by(recipient_id=user.id)
    for chat_message in chat_messages:
        chat_message.read = True

    db.session.commit()

    return {"replies": []}


def put_user_subscribe(auth, data):
    required(["person_id", "subscribe"], data)
    integer_expected(["person_id"], data)
    boolean_expected(["subscribe"], data)

    person_id = data["person_id"]
    subscribe = data["subscribe"]

    user_id = subscribe_user(person_id, subscribe, SRC_API, auth)
    user_json = user_view(user=person_id, variant=5, user_id=user_id)
    user_json["subscribed"] = subscribe
    return user_json


def put_user_save_user_settings(auth, data):
    user: User = authorise_api_user(auth, return_type="model")
    show_nsfw = data["show_nsfw"] if "show_nsfw" in data else None
    show_nsfl = data["show_nsfl"] if "show_nsfl" in data else None
    show_read_posts = data["show_read_posts"] if "show_read_posts" in data else None
    about = data["bio"] if "bio" in data else None
    # avatar = data['avatar'] if 'avatar' in data else None
    cover = data["cover"] if "cover" in data else None
    default_sort = data["default_sort_type"] if "default_sort" in data else None
    default_comment_sort = (
        data["default_comment_sort_type"] if "default_comment_sort" in data else None
    )

    if "avatar" in data:
        if not data["avatar"]:
            # null value passed, remove avatar image
            avatar = None
            remove_avatar = True
        else:
            # valid url passed, set avatar image
            avatar = data["avatar"]
            remove_avatar = False
    else:
        avatar = None
        remove_avatar = False

    if "cover" in data:
        if not data["cover"]:
            # null value passed, remove avatar image
            cover = None
            remove_cover = True
        else:
            # valid url passed, set avatar image
            cover = data["cover"]
            remove_cover = False
    else:
        cover = None
        remove_cover = False

    # english is fun, so lets do the reversing and update the user settings
    if show_nsfw == True:
        user.hide_nsfw = 0
    elif show_nsfw == False:
        user.hide_nsfw = 1
    if show_nsfl == True:
        user.hide_nsfl = 0
    elif show_nsfl == False:
        user.hide_nsfl = 1

    if user_in_restricted_country(user):
        user.hide_nsfw = 1  # Hide nsfw
        user.hide_nsfl = 1

    if show_read_posts == True:
        user.hide_read_posts = False
    elif show_read_posts == False:
        user.hide_read_posts = True

    if isinstance(about, str):
        from app.utils import markdown_to_html

        user.about = about
        user.about_html = markdown_to_html(about)

    if avatar:
        if user.avatar_id:
            remove_file = File.query.get(user.avatar_id)
            if remove_file:
                remove_file.delete_from_disk()
            user.avatar_id = None
        file = File(source_url=avatar)
        db.session.add(file)
        db.session.commit()
        user.avatar_id = file.id
        make_image_sizes(user.avatar_id, 40, 250, "users")
    elif remove_avatar:
        if user.avatar_id:
            remove_file = File.query.get(user.avatar_id)
            if remove_file:
                remove_file.delete_from_disk()
            user.avatar_id = None
        db.session.commit()

    if cover:
        if user.cover_id:
            remove_file = File.query.get(user.cover_id)
            if remove_file:
                remove_file.delete_from_disk()
            user.cover_id = None
        file = File(source_url=cover)
        db.session.add(file)
        db.session.commit()
        user.cover_id = file.id
        make_image_sizes(user.cover_id, 700, 1600, "users")
        cache.delete_memoized(User.cover_image, user)
    elif remove_cover:
        if user.cover_id:
            remove_file = File.query.get(user.cover_id)
            if remove_file:
                remove_file.delete_from_disk()
            user.cover_id = None
        db.session.commit()
        cache.delete_memoized(User.cover_image, user)

    if default_sort is not None:
        user.default_sort = default_sort.lower()
    if default_comment_sort is not None:
        user.default_comment_sort = default_comment_sort.lower()

    # save the change to the db
    db.session.commit()

    user_json = {"my_user": user_view(user=user, variant=6)}
    return user_json


def get_user_notifications(auth, data):
    # get the user from data.user_id
    user = authorise_api_user(auth, return_type="model")

    # get the status from data.status
    status = data["status"]

    # get the page for pagination from the data.page
    page = int(data["page"]) if data and "page" in data else 1
    limit = int(data["limit"]) if data and "limit" in data else 10

    # items dict
    items = []

    # setup the db query/generator all notifications for the user
    user_notifications = (
        Notification.query.filter_by(user_id=user.id)
        .order_by(desc(Notification.created_at))
        .paginate(page=page, per_page=limit, error_out=False)
    )

    # currently supported notif types
    supported_notif_types = [
        NOTIF_USER,
        NOTIF_COMMUNITY,
        NOTIF_TOPIC,
        NOTIF_POST,
        NOTIF_REPLY,
        NOTIF_FEED,
        NOTIF_MENTION,
    ]

    # new
    if status == "Unread":
        for item in user_notifications:
            if item.read == False and item.notif_type in supported_notif_types:
                if isinstance(item.subtype, str):
                    try:
                        notif = _process_notification_item(item)
                        items.append(notif)
                    except AttributeError:
                        # Something couldn't be fetched from the db, just skip
                        continue
    # all
    elif status == "All":
        for item in user_notifications:
            if (
                isinstance(item.subtype, str)
                and item.notif_type in supported_notif_types
            ):
                try:
                    notif = _process_notification_item(item)
                    items.append(notif)
                except AttributeError:
                    # Something couldn't be fetched from the db, just skip
                    continue
    # read
    elif status == "Read":
        for item in user_notifications:
            if item.read == True and item.notif_type in supported_notif_types:
                if isinstance(item.subtype, str):
                    try:
                        notif = _process_notification_item(item)
                        items.append(notif)
                    except AttributeError:
                        # Something couldn't be fetched from the db, just skip
                        continue

    # get counts for new/read/all
    counts = {}
    counts["total"] = (
        Notification.query.with_entities(func.count())
        .where(Notification.user_id == user.id)
        .scalar()
    )
    counts["unread"] = (
        Notification.query.with_entities(func.count())
        .where(Notification.user_id == user.id)
        .where(Notification.read == False)
        .scalar()
    )
    counts["read"] = counts["total"] - counts["unread"]

    # make dicts of that and pass back
    res = {}
    res["username"] = user.user_name
    res["status"] = status
    res["counts"] = counts
    res["items"] = items
    res["next_page"] = (
        str(user_notifications.next_num)
        if user_notifications.next_num is not None
        else None
    )
    return res


def _process_notification_item(item):
    # for the NOTIF_USER
    if item.notif_type == NOTIF_USER:
        author = User.query.get(item.author_id)
        post = Post.query.get(item.targets["post_id"])
        notification_json = {}
        notification_json["notif_id"] = item.id
        notification_json["notif_type"] = NOTIF_USER
        notification_json["notif_subtype"] = item.subtype
        notification_json["author"] = user_view(user=author.id, variant=1)
        notification_json["post"] = post_view(post, variant=2)
        notification_json["post_id"] = post.id
        notification_json["notif_body"] = post.body if post.body else ""
        notification_json["status"] = "Read" if item.read else "Unread"
        return notification_json
    # for the NOTIF_COMMUNITY
    elif item.notif_type == NOTIF_COMMUNITY:
        author = User.query.get(item.author_id)
        post = Post.query.get(item.targets["post_id"])
        community = Community.query.get(item.targets["community_id"])
        notification_json = {}
        notification_json["notif_id"] = item.id
        notification_json["notif_type"] = NOTIF_COMMUNITY
        notification_json["notif_subtype"] = item.subtype
        notification_json["author"] = user_view(user=author.id, variant=1)
        notification_json["post"] = post_view(post, variant=2)
        notification_json["post_id"] = post.id
        notification_json["community"] = community_view(community, variant=2)
        notification_json["notif_body"] = post.body if post.body else ""
        notification_json["status"] = "Read" if item.read else "Unread"
        return notification_json
    # for the NOTIF_TOPIC
    elif item.notif_type == NOTIF_TOPIC:
        author = User.query.get(item.author_id)
        post = Post.query.get(item.targets["post_id"])
        notification_json = {}
        notification_json["notif_id"] = item.id
        notification_json["notif_type"] = NOTIF_TOPIC
        notification_json["notif_subtype"] = item.subtype
        notification_json["author"] = user_view(user=author.id, variant=1)
        notification_json["post"] = post_view(post, variant=2)
        notification_json["post_id"] = post.id
        notification_json["notif_body"] = post.body if post.body else ""
        notification_json["status"] = "Read" if item.read else "Unread"
        return notification_json
    # for the NOTIF_POST
    elif item.notif_type == NOTIF_POST:
        author = User.query.get(item.author_id)
        post = Post.query.get(item.targets["post_id"])
        comment = PostReply.query.get(item.targets["comment_id"])
        notification_json = {}
        notification_json["notif_id"] = item.id
        notification_json["notif_type"] = NOTIF_POST
        notification_json["notif_subtype"] = item.subtype
        notification_json["author"] = user_view(user=author.id, variant=1)
        notification_json["post"] = post_view(post, variant=2)
        notification_json["post_id"] = post.id
        notification_json["comment"] = reply_view(comment, variant=1)
        notification_json["comment_id"] = comment.id
        notification_json["notif_body"] = comment.body if comment.body else ""
        notification_json["status"] = "Read" if item.read else "Unread"
        return notification_json
    # for the NOTIF_REPLY
    elif item.notif_type == NOTIF_REPLY:
        author = User.query.get(item.author_id)
        post = Post.query.get(item.targets["post_id"])
        comment = PostReply.query.get(item.targets["comment_id"])
        notification_json = {}
        notification_json["notif_id"] = item.id
        notification_json["notif_type"] = NOTIF_REPLY
        notification_json["notif_subtype"] = item.subtype
        notification_json["author"] = user_view(user=author.id, variant=1)
        notification_json["post"] = post_view(post, variant=2)
        notification_json["post_id"] = post.id
        notification_json["comment"] = reply_view(comment, variant=1)
        notification_json["comment_id"] = comment.id
        notification_json["notif_body"] = comment.body if comment.body else ""
        notification_json["status"] = "Read" if item.read else "Unread"
        return notification_json
    # for the NOTIF_FEED
    elif item.notif_type == NOTIF_FEED:
        author = User.query.get(item.author_id)
        post = Post.query.get(item.targets["post_id"])
        notification_json = {}
        notification_json["notif_id"] = item.id
        notification_json["notif_type"] = NOTIF_FEED
        notification_json["notif_subtype"] = item.subtype
        notification_json["author"] = user_view(user=author.id, variant=1)
        notification_json["post"] = post_view(post, variant=2)
        notification_json["post_id"] = post.id
        notification_json["notif_body"] = post.body if post.body else ""
        notification_json["status"] = "Read" if item.read else "Unread"
        return notification_json
    # for the NOTIF_MENTION
    elif item.notif_type == NOTIF_MENTION:
        notification_json = {}
        if item.subtype == "post_mention":
            author = User.query.get(item.author_id)
            post = Post.query.get(item.targets["post_id"])
            notification_json["author"] = user_view(user=author.id, variant=1)
            notification_json["post"] = post_view(post, variant=2)
            notification_json["post_id"] = post.id
            notification_json["notif_id"] = item.id
            notification_json["notif_type"] = NOTIF_MENTION
            notification_json["notif_subtype"] = item.subtype
            notification_json["notif_body"] = post.body if post.body else ""
            notification_json["status"] = "Read" if item.read else "Unread"
            return notification_json
        if item.subtype == "comment_mention":
            author = User.query.get(item.author_id)
            comment = PostReply.query.get(item.targets["comment_id"])
            notification_json["author"] = user_view(user=author.id, variant=1)
            notification_json["comment"] = reply_view(comment, variant=1)
            notification_json["comment_id"] = comment.id
            notification_json["notif_id"] = item.id
            notification_json["notif_type"] = NOTIF_MENTION
            notification_json["notif_subtype"] = item.subtype
            notification_json["notif_body"] = comment.body if comment.body else ""
            notification_json["status"] = "Read" if item.read else "Unread"
            return notification_json

    return False


def put_user_notification_state(auth, data):
    required(["notif_id", "read_state"], data)
    integer_expected(["notif_id"], data)
    boolean_expected(["read_state"], data)

    user_id = authorise_api_user(auth)
    notif_id = data["notif_id"]
    read_state = data["read_state"]

    # get the notification from the data.notif_id
    notif = Notification.query.filter_by(id=notif_id, user_id=user_id).one()

    try:
        # make a json for the specific notification and return that one item
        res = _process_notification_item(notif)
    except AttributeError:
        # Problems looking something up in the db
        raise Exception("There was a problem processing that notification")

    if not res:
        # Unsupported notification type
        raise Exception("This notification type is currently unsupported in the api")

    # set the read state for the notification
    notif.read = read_state

    # commit that change to the db
    db.session.commit()

    return res


def get_user_notifications_count(auth):
    # get the user
    user = authorise_api_user(auth, return_type="model")
    # get the user's unread notifications count
    unread_notifs_count = (
        Notification.query.with_entities(func.count())
        .where(Notification.user_id == user.id)
        .where(Notification.read == False)
        .scalar()
    )
    # make the dict and add that info, then return it
    res = {}
    res["count"] = unread_notifs_count
    return res


def put_user_mark_all_notifications_read(auth):
    # get the user
    user = authorise_api_user(auth, return_type="model")
    # set all the user's notifs as read
    db.session.execute(
        text("UPDATE notification SET read=true WHERE user_id = :user_id"),
        {"user_id": user.id},
    )
    # save the changes to the db
    db.session.commit()
    # return a message, though it may not be used by the client
    res = {"mark_all_notifications_as_read": "complete"}
    return res


def post_user_verify_credentials(data):
    required(["username", "password"], data)
    string_expected(["username", "password"], data)

    username = data["username"].lower()
    password = data["password"]

    if "@" in username:
        user = User.query.filter(
            func.lower(User.email) == username,
            User.ap_id == None,
            User.deleted == False,
        ).one()
    else:
        user = User.query.filter(
            func.lower(User.user_name) == username,
            User.ap_id == None,
            User.deleted == False,
        ).one()

    if user is None or not user.check_password(password):
        raise NoResultFound

    return {}


def post_user_set_flair(auth, data):
    required(["community_id"], data)
    integer_expected(["community_id"], data)

    flair_text = data["flair_text"] if data and "flair_text" in data else None

    if flair_text is not None and len(flair_text) > 50:
        raise Exception("Flair text is too long (50 chars max)")

    user = authorise_api_user(auth, return_type="model")
    community_id = data["community_id"]

    try:
        if flair_text is not None:
            user_flair = UserFlair.query.filter_by(
                user_id=user.id, community_id=community_id
            ).one()
            user_flair.flair = flair_text
            db.session.commit()
        else:
            user_flair = UserFlair.query.filter_by(
                user_id=user.id, community_id=community_id
            ).one()
            db.session.delete(user_flair)
            db.session.commit()
    except NoResultFound:
        if flair_text is not None:
            user_flair = UserFlair(
                user_id=user.id, community_id=community_id, flair=flair_text
            )
            db.session.add(user_flair)
            db.session.commit()

    return user_view(user=user, variant=5, flair_community_id=community_id)
