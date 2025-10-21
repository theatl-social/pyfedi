import re

from urllib.parse import urlparse

from flask import current_app
from sqlalchemy import desc

from app.activitypub.util import find_actor_or_create, remote_object_to_json, actor_json_to_model, \
    find_community, create_resolved_object
from app.api.alpha.utils.community import get_community_list
from app.api.alpha.utils.post import get_post_list
from app.api.alpha.utils.user import get_user_list
from app.api.alpha.views import search_view, post_view, reply_view, user_view, community_view
from app.community.util import search_for_community
from app.models import Post, PostReply, User, Community, BannedInstances
from app.user.utils import search_for_user
from app.utils import authorise_api_user, gibberish
from app import db


def get_search(auth, data):
    if not data or ('q' not in data and 'type_' not in data):
        raise Exception('missing parameters for search')

    type = data['type_']
    listing_type = data['listing_type'] if 'listing_type' in data else 'All'

    data['type_'] = listing_type

    search_type = 'Posts' if type == 'Url' else type
    search_json = search_view(search_type)
    if type == 'Communities':
        search_json['communities'] = get_community_list(auth, data)['communities']
    elif type == 'Posts' or type == 'Url':
        search_json['posts'] = get_post_list(auth, data, search_type=type)['posts']
    elif type == 'Users':
        search_json['users'] = get_user_list(auth, data)['users']

    return search_json


def get_resolve_object(auth, data, user_id=None, recursive=False):
    if not data or 'q' not in data:
        raise Exception('missing q parameter for resolve_object')
    if auth:
        user_id = authorise_api_user(auth)

    query = data['q']

    # Check to see if the query parameter is already federated and is the canonical ap url
    object = db.session.query(PostReply).filter_by(ap_id=query).first()
    if object:
        if object.deleted:
            raise Exception('No object found.')
        return reply_view(reply=object, variant=5, user_id=user_id) if not recursive else object
    object = db.session.query(Post).filter_by(ap_id=query).first()
    if object:
        if object.deleted:
            raise Exception('No object found.')
        return post_view(post=object, variant=5, user_id=user_id) if not recursive else object
    object = db.session.query(Community).filter_by(ap_profile_id=query.lower()).first()
    if object:
        if object.banned:
            raise Exception('No object found.')
        return community_view(community=object, variant=6, user_id=user_id) if not recursive else object
    object = db.session.query(User).filter_by(ap_profile_id=query.lower()).first()
    if object:
        if object.deleted or object.banned:
            raise Exception('No object found.')
        return user_view(user=object, variant=7, user_id=user_id) if not recursive else object

    # if not found and user is logged in, fetch the object if it's not hosted on a banned instance
    # note: accommodating ! and @ queries for communities and people is different from lemmy's v3 api

    server = None
    if query.startswith('https://'):
        parsed_url = urlparse(query)
        server = parsed_url.netloc.lower()
    elif query.startswith('!') or query.startswith('@'):
        address = query[1:]
        if '@' in address:
            name, server = address.lower().split('@')

    if not server:  # can't find server
        raise Exception('No object found.')
    
    if server == current_app.config['SERVER_NAME']:
        local_request = True
    else:
        if query.startswith('!'):
            # Check if this community is already federated
            local_request = bool(search_for_community(query.lower(), allow_fetch=False))
        elif query.startswith('@'):
            # Check if this user is already federated
            if query.endswith(current_app.config['SERVER_NAME']):
                user_name = query[1:]
                user_name = user_name.split('@')[0]
            local_request = bool(search_for_user(user_name.lower(), allow_fetch=False))
        else:
            local_request = False
    
    if not user_id and not local_request:  # not logged in
        raise Exception('No object found.')

    banned = db.session.query(BannedInstances).filter_by(domain=server).first()
    if banned:
        raise Exception('No object found.')
    
    # Request for something on the local instance already, check local db instead of fetching remote info
    if local_request:

        # Communities
        if (
            (query.startswith('!')) or 
            (('/c/' in query) and ('/p/' not in query)) or 
            (('/m/' in query) and ('/t/' not in query)) and 
            ('/comment/' not in query)):
            # This is a community specified using !communtiy@instance.tld notation
            if query.startswith('!'):
                object = search_for_community(query.lower(), allow_fetch=bool(user_id))
                if object:
                    return community_view(community=object, variant=6, user_id=user_id)
                else:
                    raise Exception('No object found.')
            
            # This is a community specified by url
            comm_pattern = re.compile(r"/[cm]/(.*?)(/|$)")
            matches = re.search(comm_pattern, query)
            
            try:
                comm_name = "!" + matches.group(1)
            except:
                comm_name = None
            
            if not comm_name:
                raise Exception('No object found.')
            
            if "@" not in comm_name:
                comm_name = comm_name + "@" + current_app.config['SERVER_NAME']

            object = search_for_community(comm_name.lower(), allow_fetch=bool(user_id))

            if object:
                return community_view(community=object, variant=6, user_id=user_id)
            else:
                raise Exception('No object found.')

        # Users
        if query.startswith("@") or "/u/" in query:

            # This is a user specified using the @user@instance.tld notation
            if query.startswith("@"):
                if query.endswith(current_app.config['SERVER_NAME']):
                    user_name = query[1:]
                    user_name = user_name.split('@')[0]
                object = search_for_user(user_name.lower(), allow_fetch=bool(user_id))
                if object:
                    return user_view(user=object, variant=7, user_id=user_id)
                else:
                    raise Exception('No object found.')
            
            # This is a user specified by url
            user_pattern = re.compile(r"/u/(.*?)(/|$)")
            matches = re.search(user_pattern, query)

            try:
                user_name = matches.group(1)
            except:
                user_name = None
            
            if not user_name:
                raise Exception('No object found.')
            
            if user_name.endswith(current_app.config['SERVER_NAME']) and '@' in user_name:
                user_name = user_name.split('@')[0]

            object = search_for_user(user_name.lower(), allow_fetch=bool(user_id))
            if object:
                return user_view(user=object, variant=7, user_id=user_id)
            else:
                raise Exception('No object found.')
        
        # Posts
        post_patterns = ["/post/", "/p/", "/t/"]
        if any(pattern in query for pattern in post_patterns) and "/comment/" not in query:

            if "/post/" in query:
                # Post url from lemmy or older piefed url format
                post_pattern = re.compile(r"/post/(\d*)(/|$)")
            elif "/p/" in query:
                # Post url from more recent piefed versions
                post_pattern = re.compile(r"/p/(\d*)(/|$)")
            elif "/t/" in query:
                # Post url from mbin
                post_pattern = re.compile(r"/t/(\d*)(/|$)")
            else:
                post_pattern = None

            if not post_pattern:
                raise Exception('No object found.')
            
            # Do the regex
            matches = re.search(post_pattern, query)
            try:
                post_id = matches.group(1)
            except:
                post_id = None
                
            if not post_id:
                raise Exception('No object found.')
            
            # Since this is a local request, just search for the post by id
            object = Post.query.get(post_id)

            if not object:
                raise Exception('No object found.')
            else:
                return post_view(post=object, variant=5, user_id=user_id)
        
        # Comments
        if "/comment/" in query:
            # Do the regex
            comment_pattern = re.compile(r"/comment/(\d*)(/|$)")
            matches = re.search(comment_pattern, query)
            try:
                comment_id = matches.group(1)
            except:
                comment_id = None
            
            if not comment_id:
                raise Exception('No object found.')
            
            # Since this is a local request, just search for the comment by id
            object = PostReply.query.get(comment_id)

            if not object:
                raise Exception('No object found.')
            else:
                return reply_view(reply=object, variant=5, user_id=user_id)

    # use hints first in query first
    # assume that queries starting with ! are for a community
    if not recursive and query.startswith('!'):
        object = search_for_community(query.lower())
        if object:
            return community_view(community=object, variant=6, user_id=user_id)
    # assume that queries starting with @ are for a user
    if not recursive and query.startswith('@'):
        object = search_for_user(query.lower())
        if object:
            return user_view(user=object, variant=7, user_id=user_id)
    # if the instance is following the lemmy convention, a '/u/' means user and '/c/' means community
    if '/u/' in query or '/c/' in query:
        object = find_actor_or_create(query.lower())
        if object:
            if isinstance(object, User):
                return user_view(user=object, variant=7, user_id=user_id) if not recursive else object
            elif isinstance(object, Community):
                return community_view(community=object, variant=6, user_id=user_id) if not recursive else object

    # no more hints from query
    ap_json = remote_object_to_json(query)
    if not ap_json:
        raise Exception('No object found.')
    if not 'id' in ap_json:
        raise Exception('No object found.')
    if query != ap_json['id']:
        # query URL doesn't match original author's URL, so call this function with that URL instead
        # 'recursive' is (incorrectly) set to False to get the view, not the object
        return get_resolve_object(None, {"q": ap_json['id']}, user_id, False)

    # a user or a community
    if not 'type' in ap_json:
        raise Exception('No object found.')

    if (ap_json['type'] == 'Person' or ap_json['type'] == 'Service' or ap_json['type'] == 'Group' and
            'preferredUsername' in ap_json):
        name = ap_json['preferredUsername'].lower()
        object = actor_json_to_model(ap_json, name, server)
        if object:
            if isinstance(object, User):
                return user_view(user=object, variant=7, user_id=user_id) if not recursive else object
            elif isinstance(object, Community):
                return community_view(community=object, variant=6, user_id=user_id) if not recursive else object

    # a post or a reply
    community = find_community(ap_json)
    # if community doesn't already exist, call this function recursively to create it
    if not community:
        locations = ['audience', 'cc', 'to']
        for location in locations:
            if location in ap_json:
                potential_id = ap_json[location]
                if isinstance(potential_id, str):
                    if not potential_id.startswith('https://www.w3.org') and not potential_id.endswith('/followers'):
                        potential_community = get_resolve_object(None, {"q": potential_id}, user_id, True)
                        if isinstance(potential_community, Community):
                            community = potential_community
                            break
                if isinstance(potential_id, list):
                    for c in potential_id:
                        if not c.startswith('https://www.w3.org') and not c.endswith('/followers'):
                            potential_community = get_resolve_object(None, {"q": c}, user_id, True)
                            if isinstance(potential_community, Community):
                                community = potential_community
                                break

        if not community and 'inReplyTo' in ap_json and ap_json['inReplyTo'] is not None:
            comment_being_replied_to = None
            post_being_replied_to = Post.get_by_ap_id(ap_json['inReplyTo'])
            if post_being_replied_to:
                community = post_being_replied_to.community
            else:
                comment_being_replied_to = PostReply.get_by_ap_id(ap_json['inReplyTo'])
                if comment_being_replied_to:
                    community = comment_being_replied_to.community
            # if parent doesn't already exist, call this function recursively to create it, and use parent's community
            if not post_being_replied_to and not comment_being_replied_to:
                object = get_resolve_object(None, {"q": ap_json['inReplyTo']}, user_id, True)
                if object:
                    community = object.community

        if not community:
            raise Exception('No object found.')

    # pretend this was Announced in, so an existing function can be re-used
    announce_id = f"https://{server}/activities/announce/{gibberish(15)}"
    object = create_resolved_object(query, ap_json, server, community, announce_id, False)
    # if object can't be created due to missing a parent post or reply, call this function recursively to create it.
    if not object:
        if 'inReplyTo' in ap_json and ap_json['inReplyTo'] is not None:
            get_resolve_object(None, {"q": ap_json['inReplyTo']}, user_id, True)
            object = create_resolved_object(query, ap_json, server, community, announce_id, False)

    if object:
        if isinstance(object, Post):
            return post_view(post=object, variant=5, user_id=user_id) if not recursive else object
        elif isinstance(object, PostReply):
            return reply_view(reply=object, variant=5, user_id=user_id) if not recursive else object

    # failed to resolve if here.
    raise Exception('No object found.')


def get_suggestion(data):
    query = data['q']
    result = []
    if query.startswith('@'):
        if 'post_id' in data:
            people_from_post = User.query.join(PostReply, PostReply.user_id == User.id).\
                filter(PostReply.post_id == data['post_id']).\
                filter(User.user_name.ilike(f'{query[1:]}%')).distinct()

            for person in people_from_post.all():
                person_text = person.lemmy_link()
                if person_text not in result:
                    result.append(person_text)

        other_people = User.query.filter(User.user_name.ilike(f'{query[1:]}%')).order_by(desc(User.reputation)).limit(7).all()
        for other_person in other_people:
            if len(result) >= 7:
                break
            person_text = other_person.lemmy_link()
            if person_text not in result:
                result.append(person_text)
        if len(result) < 7:
            other_people = User.query.filter(User.user_name.ilike(f'%{query[1:]}%')).order_by(
                desc(User.reputation)).limit(7).all()
            for other_person in other_people:
                if len(result) >= 7:
                    break
                person_text = other_person.lemmy_link()
                if person_text not in result:
                    result.append(person_text)
    elif query.startswith('!'):
        for community in Community.query.filter(Community.name.ilike(f'{query[1:]}%')).order_by(desc(Community.active_monthly)).limit(7).all():
            result.append(community.lemmy_link()[1:])
    return {'result': result}
