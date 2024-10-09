from app.models import Community, Post, User, utcnow
from app.utils import authorise_api_user
from app.api.alpha.views import search_view, community_view, post_view, user_view

from datetime import timedelta
from sqlalchemy import desc


def get_communities_list(sort, page, limit, listing_type, user_id):
    # only support 'api/alpha/search?q&type_=Communities&sort=TopAll&listing_type=Local&page=1&limit=15' for now
    # (enough for instance view)
    communities = Community.query.filter_by(ap_id=None).order_by(desc(Community.subscriptions_count))
    communities = communities.paginate(page=page, per_page=limit, error_out=False)

    community_list = []
    for community in communities:
        community_list.append(community_view(community, variant=2, stub=True))
    return community_list


def get_posts_list(sort, page, limit, listing_type, user_id):
    # only support 'api/alpha/search?q&type_=Posts&sort=TopAll&listing_type=Local&page=1&limit=15' for now
    # (enough for instance view)
    posts = Post.query.filter_by(instance_id=1, deleted=False)

    if sort == "Hot":
        posts = posts.order_by(desc(Post.ranking)).order_by(desc(Post.posted_at))
    elif sort == "TopDay":
        posts = posts.filter(Post.posted_at > utcnow() - timedelta(days=1)).order_by(desc(Post.up_votes - Post.down_votes))
    elif sort == "New":
        posts = posts.order_by(desc(Post.posted_at))
    elif sort == "Active":
        posts = posts.order_by(desc(Post.last_active))

    posts = posts.paginate(page=page, per_page=limit, error_out=False)

    post_list = []
    for post in posts:
        post_list.append(post_view(post, variant=2, stub=True))
    return post_list


def get_users_list(sort, page, limit, listing_type, user_id):
    # only support 'api/alpha/search?q&type_=Users&sort=TopAll&listing_type=Local&page=1&limit=15' for now
    # (enough for instance view)
    users = User.query.filter_by(instance_id=1, deleted=False).order_by(User.id)
    users = users.paginate(page=page, per_page=limit, error_out=False)

    user_list = []
    for user in users:
        user_list.append(user_view(user, variant=2, stub=True))
    return user_list


def get_search(auth, data):
    if not data or ('q' not in data and 'type_' not in data):
        raise Exception('missing_parameters')

    type = data['type_']
    sort = data['sort'] if 'sort' in data else 'Top'
    page = int(data['page']) if 'page' in data else 1
    limit = int(data['limit']) if 'limit' in data else 15
    listing_type = data['listing_type'] if 'listing_type' in data else 'Local'

    user_id = authorise_api_user(auth) if auth else None

    search_json = search_view(type)
    if type == 'Communities':
        search_json['communities'] = get_communities_list(sort, page, limit, listing_type, user_id)
    elif type == 'Posts':
        search_json['posts'] = get_posts_list(sort, page, limit, listing_type, user_id)
    elif type == 'Users':
        search_json['users'] = get_users_list(sort, page, limit, listing_type, user_id)

    return search_json

