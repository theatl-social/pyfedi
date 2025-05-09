from app import db
from app.api.alpha.views import post_view, post_report_view
from app.api.alpha.utils.validators import required, integer_expected, boolean_expected, string_expected
from app.constants import *
from app.models import Post, PostVote, Community, CommunityMember, utcnow, User
from app.shared.post import vote_for_post, bookmark_post, remove_bookmark_post, subscribe_post, make_post, edit_post, \
                            delete_post, restore_post, report_post, lock_post, sticky_post, mod_remove_post, mod_restore_post
from app.utils import authorise_api_user, blocked_users, blocked_communities, blocked_instances, recently_upvoted_posts

from datetime import timedelta
from sqlalchemy import desc, text


def get_post_list(auth, data, user_id=None, search_type='Posts'):
    type = data['type_'] if data and 'type_' in data else "All"
    sort = data['sort'].lower() if data and 'sort' in data else "hot"
    page = int(data['page_cursor']) if data and 'page_cursor' in data else 1
    limit = int(data['limit']) if data and 'limit' in data else 50
    liked_only = data['liked_only'] if data and 'liked_only' in data else 'false'
    liked_only = True if liked_only == 'true' else False

    query = data['q'] if data and 'q' in data else ''

    if auth:
        user_id = authorise_api_user(auth)

    # get the user to check if the user has hide_read posts set later down the function
    if user_id:
        user = User.query.get(user_id)

    # user_id: the logged in user
    # person_id: the author of the posts being requested

    community_id = int(data['community_id']) if data and 'community_id' in data else None
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

    # Post.user_id.not_in(blocked_person_ids)               # exclude posts by blocked users
    # Post.community_id.not_in(blocked_community_ids)       # exclude posts in blocked communities
    # Post.instance_id.not_in(blocked_instance_ids)         # exclude posts by users on blocked instances
    # Community.instance_id.not_in(blocked_instance_ids)    # exclude posts in communities on blocked instances

    if type == "Local":
        posts = Post.query.filter(Post.deleted == False, Post.status > POST_STATUS_REVIEWING, Post.user_id.not_in(blocked_person_ids), Post.community_id.not_in(blocked_community_ids)).\
            join(Community, Community.id == Post.community_id).filter_by(ap_id=None)
    elif type == "Popular":
        posts = Post.query.filter(Post.deleted == False, Post.status > POST_STATUS_REVIEWING, Post.user_id.not_in(blocked_person_ids), Post.community_id.not_in(blocked_community_ids), Post.instance_id.not_in(blocked_instance_ids)).\
            join(Community, Community.id == Post.community_id).filter(Community.show_popular == True, Post.score > 100, Community.instance_id.not_in(blocked_instance_ids))
    elif type == "Subscribed" and user_id is not None:
        posts = Post.query.filter(Post.deleted == False, Post.status > POST_STATUS_REVIEWING, Post.user_id.not_in(blocked_person_ids), Post.community_id.not_in(blocked_community_ids), Post.instance_id.not_in(blocked_instance_ids)).\
            join(CommunityMember, Post.community_id == CommunityMember.community_id).filter_by(is_banned=False, user_id=user_id).\
            join(Community, Community.id == CommunityMember.community_id).filter(Community.instance_id.not_in(blocked_instance_ids))
    elif type == "ModeratorView" and user_id is not None:
         posts = Post.query.filter(Post.deleted == False, Post.status > POST_STATUS_REVIEWING, Post.user_id.not_in(blocked_person_ids), Post.community_id.not_in(blocked_community_ids), Post.instance_id.not_in(blocked_instance_ids)).\
            join(CommunityMember, Post.community_id == CommunityMember.community_id).filter_by(user_id=user_id, is_moderator=True).\
            join(Community, Community.id == CommunityMember.community_id).filter(Community.instance_id.not_in(blocked_instance_ids))
    else: # type == "All"
        if community_name:
            name, ap_domain = community_name.split('@')
            posts = Post.query.filter(Post.deleted == False, Post.status > POST_STATUS_REVIEWING, Post.user_id.not_in(blocked_person_ids), Post.community_id.not_in(blocked_community_ids), Post.instance_id.not_in(blocked_instance_ids)).\
                join(Community, Community.id == Post.community_id).filter(Community.show_all == True, Community.name == name, Community.ap_domain == ap_domain, Community.instance_id.not_in(blocked_instance_ids))
        elif community_id:
            posts = Post.query.filter(Post.deleted == False, Post.status > POST_STATUS_REVIEWING, Post.user_id.not_in(blocked_person_ids), Post.community_id.not_in(blocked_community_ids), Post.instance_id.not_in(blocked_instance_ids)).\
                join(Community, Community.id == Post.community_id).filter(Community.show_all == True, Community.id == community_id, Community.instance_id.not_in(blocked_instance_ids))
        elif person_id:
            posts = Post.query.filter(Post.deleted == False, Post.status > POST_STATUS_REVIEWING, Post.community_id.not_in(blocked_community_ids), Post.instance_id.not_in(blocked_instance_ids), Post.user_id == person_id).\
                join(Community, Community.id == Post.community_id).filter(Community.instance_id.not_in(blocked_instance_ids))
        else:
            posts = Post.query.filter(Post.deleted == False, Post.status > POST_STATUS_REVIEWING, Post.user_id.not_in(blocked_person_ids), Post.community_id.not_in(blocked_community_ids), Post.instance_id.not_in(blocked_instance_ids)).\
                join(Community, Community.id == Post.community_id).filter(Community.show_all == True, Community.instance_id.not_in(blocked_instance_ids))

    # change when polls are supported
    posts = posts.filter(Post.type != POST_TYPE_POLL)

    if query:
        if search_type == 'Url':
            posts = posts.filter(Post.url.ilike(f"%{query}%"))
        else:
            posts = posts.filter(Post.title.ilike(f"%{query}%"))

    if user_id and liked_only:
        upvoted_post_ids = recently_upvoted_posts(user_id)
        posts = posts.filter(Post.id.in_(upvoted_post_ids), Post.user_id != user_id)
    elif user_id and user.hide_read_posts:
        u_rp_ids = db.session.execute(text('SELECT read_post_id FROM "read_posts" WHERE user_id = :user_id'), {"user_id": user_id}).scalars()
        posts = posts.filter(Post.id.not_in(u_rp_ids))

    if sort == "hot":
        posts = posts.order_by(desc(Post.ranking)).order_by(desc(Post.posted_at))
    elif sort == "top":
        posts = posts.filter(Post.posted_at > utcnow() - timedelta(days=1)).order_by(desc(Post.up_votes - Post.down_votes))
    elif sort == "new":
        posts = posts.order_by(desc(Post.posted_at))
    elif sort == "scaled":
        posts = posts.order_by(desc(Post.ranking_scaled)).order_by(desc(Post.ranking)).order_by(desc(Post.posted_at))
    elif sort == "active":
        posts = posts.order_by(desc(Post.last_active))

    posts = posts.paginate(page=page, per_page=limit, error_out=False)

    postlist = []
    for post in posts:
        try:
            postlist.append(post_view(post=post, variant=2, stub=True, user_id=user_id))
        except:
            continue
    list_json = {
        "posts": postlist,
        "next_page": str(posts.next_num)
    }

    return list_json


def get_post(auth, data):
    if not data or 'id' not in data:
        raise Exception('missing parameters for post')

    id = int(data['id'])

    user_id = authorise_api_user(auth) if auth else None

    post_json = post_view(post=id, variant=3, user_id=user_id)
    return post_json


def post_post_like(auth, data):
    required(['post_id', 'score'], data)
    integer_expected(['post_id', 'score'], data)

    post_id = data['post_id']
    score = data['score']
    if score == 1:
        direction = 'upvote'
    elif score == -1:
        direction = 'downvote'
    else:
        score = 0
        direction = 'reversal'

    user_id = vote_for_post(post_id, direction, SRC_API, auth)
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
    language_id = data['language_id'] if 'language_id' in data else 2       # FIXME: use site language
    if language_id < 2:
        language_id = 2

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
        language_id = 2   # FIXME: use site language

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
