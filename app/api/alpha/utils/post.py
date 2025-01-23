from app import cache
from app.api.alpha.views import post_view, post_report_view
from app.api.alpha.utils.validators import required, integer_expected, boolean_expected, string_expected
from app.constants import POST_TYPE_ARTICLE, POST_TYPE_LINK, POST_TYPE_IMAGE, POST_TYPE_VIDEO, POST_TYPE_POLL
from app.models import Post, Community, CommunityMember, utcnow
from app.shared.post import vote_for_post, bookmark_the_post, remove_the_bookmark_from_post, toggle_post_notification, make_post, edit_post, \
                            delete_post, restore_post, report_post, lock_post, sticky_post, mod_remove_post, mod_restore_post
from app.utils import authorise_api_user, blocked_users, blocked_communities, blocked_instances, community_ids_from_instances, is_image_url, is_video_url

from datetime import timedelta
from sqlalchemy import desc


@cache.memoize(timeout=3)
def cached_post_list(type, sort, user_id, community_id, community_name, person_id, query='', search_type='Posts'):
    if type == "All":
        if community_name:
            name, ap_domain = community_name.split('@')
            posts = Post.query.filter_by(deleted=False).join(Community, Community.id == Post.community_id).filter_by(show_all=True, name=name, ap_domain=ap_domain)
        elif community_id:
            posts = Post.query.filter_by(deleted=False).join(Community, Community.id == Post.community_id).filter_by(show_all=True, id=community_id)
        elif person_id:
            posts = Post.query.filter_by(deleted=False, user_id=person_id)
        else:
            posts = Post.query.filter_by(deleted=False).join(Community, Community.id == Post.community_id).filter_by(show_all=True)
    elif type == "Local":
        posts = Post.query.filter_by(deleted=False).join(Community, Community.id == Post.community_id).filter_by(ap_id=None)
    elif type == "Popular":
        posts = Post.query.filter_by(deleted=False).join(Community, Community.id == Post.community_id).filter(Community.show_popular == True, Post.score > 100)
    elif type == "Subscribed" and user_id is not None:
        posts = Post.query.filter_by(deleted=False).join(CommunityMember, Post.community_id == CommunityMember.community_id).filter_by(is_banned=False, user_id=user_id)
    else:
        posts = Post.query.filter_by(deleted=False)

    # change when polls are supported
    posts = posts.filter(Post.type != POST_TYPE_POLL)

    if user_id and user_id != person_id:
        blocked_person_ids = blocked_users(user_id)
        if blocked_person_ids:
            posts = posts.filter(Post.user_id.not_in(blocked_person_ids))
        blocked_community_ids = blocked_communities(user_id)
        if blocked_community_ids:
            posts = posts.filter(Post.community_id.not_in(blocked_community_ids))
        blocked_instance_ids = blocked_instances(user_id)
        if blocked_instance_ids:
            posts = posts.filter(Post.instance_id.not_in(blocked_instance_ids))                                         # users from blocked instance
            posts = posts.filter(Post.community_id.not_in(community_ids_from_instances(blocked_instance_ids)))          # communities from blocked instance

    if query:
        if search_type == 'Url':
            posts = posts.filter(Post.url.ilike(f"%{query}%"))
        else:
            posts = posts.filter(Post.title.ilike(f"%{query}%"))

    if sort == "Hot":
        posts = posts.order_by(desc(Post.ranking)).order_by(desc(Post.posted_at))
    elif sort == "TopDay":
        posts = posts.filter(Post.posted_at > utcnow() - timedelta(days=1)).order_by(desc(Post.up_votes - Post.down_votes))
    elif sort == "New":
        posts = posts.order_by(desc(Post.posted_at))
    elif sort == "Active":
        posts = posts.order_by(desc(Post.last_active))

    return posts.all()


def get_post_list(auth, data, user_id=None, search_type='Posts'):
    type = data['type_'] if data and 'type_' in data else "All"
    sort = data['sort'] if data and 'sort' in data else "Hot"
    page = int(data['page']) if data and 'page' in data else 1
    limit = int(data['limit']) if data and 'limit' in data else 10

    query = data['q'] if data and 'q' in data else ''

    if auth:
        user_id = authorise_api_user(auth)

    # user_id: the logged in user
    # person_id: the author of the posts being requested

    community_id = int(data['community_id']) if data and 'community_id' in data else None
    community_name = data['community_name'] if data and 'community_name' in data else None
    person_id = int(data['person_id']) if data and 'person_id' in data else None

    posts = cached_post_list(type, sort, user_id, community_id, community_name, person_id, query, search_type)

    start = (page - 1) * limit
    end = start + limit
    posts = posts[start:end]

    postlist = []
    for post in posts:
        try:
            postlist.append(post_view(post=post, variant=2, stub=True, user_id=user_id))
        except:
            continue
    list_json = {
        "posts": postlist
    }

    return list_json


def get_post(auth, data):
    if not data or 'id' not in data:
        raise Exception('missing parameters for post')

    id = int(data['id'])

    user_id = authorise_api_user(auth) if auth else None

    post_json = post_view(post=id, variant=3, user_id=user_id)
    return post_json


# would be in app/constants.py
SRC_API = 3

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
    cache.delete_memoized(cached_post_list)
    post_json = post_view(post=post_id, variant=4, user_id=user_id, my_vote=score)
    return post_json


def put_post_save(auth, data):
    required(['post_id', 'save'], data)
    integer_expected(['post_id'], data)
    boolean_expected(['save'], data)

    post_id = data['post_id']
    save = data['save']

    user_id = bookmark_the_post(post_id, SRC_API, auth) if save else remove_the_bookmark_from_post(post_id, SRC_API, auth)
    post_json = post_view(post=post_id, variant=4, user_id=user_id)
    return post_json


def put_post_subscribe(auth, data):
    required(['post_id', 'subscribe'], data)
    integer_expected(['post_id'], data)
    boolean_expected(['subscribe'], data)

    post_id = data['post_id']
    subscribe = data['subscribe']           # not actually processed - is just a toggle

    user_id = toggle_post_notification(post_id, SRC_API, auth)
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
    title = data['title']
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
    post = Post.query.filter_by(id=post_id).one()
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
