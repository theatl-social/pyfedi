#!flask/bin/python
import os
from datetime import datetime

import arrow
from flask import session, g, json, request, current_app
from flask_babel import get_locale
from flask_login import current_user
from werkzeug.middleware.profiler import ProfilerMiddleware
from app import create_app, db, cli
from app.models import Site
from app.utils import gibberish, shorten_number, community_membership, getmtime, digits, user_access, ap_datetime, \
    can_create_post, can_upvote, can_downvote, current_theme, shorten_string, shorten_url, feed_membership, role_access, \
    in_sorted_list, first_paragraph, html_to_text, community_link_to_href, person_link_to_href, remove_images
from app.constants import *

app = create_app()


@app.context_processor
def app_context_processor():
    return dict(getmtime=getmtime, instance_domain=current_app.config['SERVER_NAME'], debug_mode=current_app.debug,
                arrow=arrow, locale=g.locale if hasattr(g, 'locale') else None,
                POST_TYPE_LINK=POST_TYPE_LINK, POST_TYPE_IMAGE=POST_TYPE_IMAGE,
                POST_TYPE_ARTICLE=POST_TYPE_ARTICLE, POST_TYPE_VIDEO=POST_TYPE_VIDEO, POST_TYPE_POLL=POST_TYPE_POLL,
                SUBSCRIPTION_MODERATOR=SUBSCRIPTION_MODERATOR, SUBSCRIPTION_MEMBER=SUBSCRIPTION_MEMBER,
                SUBSCRIPTION_OWNER=SUBSCRIPTION_OWNER, SUBSCRIPTION_PENDING=SUBSCRIPTION_PENDING)

with app.app_context():
    app.jinja_env.globals['len'] = len
    app.jinja_env.globals['digits'] = digits
    app.jinja_env.globals['str'] = str
    app.jinja_env.globals['shorten_number'] = shorten_number
    app.jinja_env.globals['community_membership'] = community_membership
    app.jinja_env.globals['feed_membership'] = feed_membership
    app.jinja_env.globals['json_loads'] = json.loads
    app.jinja_env.globals['user_access'] = user_access
    app.jinja_env.globals['role_access'] = role_access
    app.jinja_env.globals['ap_datetime'] = ap_datetime
    app.jinja_env.globals['can_create'] = can_create_post
    app.jinja_env.globals['can_upvote'] = can_upvote
    app.jinja_env.globals['can_downvote'] = can_downvote
    app.jinja_env.globals['in_sorted_list'] = in_sorted_list
    app.jinja_env.globals['theme'] = current_theme
    app.jinja_env.globals['file_exists'] = os.path.exists
    app.jinja_env.globals['first_paragraph'] = first_paragraph
    app.jinja_env.globals['html_to_text'] = html_to_text
    app.jinja_env.filters['community_links'] = community_link_to_href
    app.jinja_env.filters['person_links'] = person_link_to_href
    app.jinja_env.filters['shorten'] = shorten_string
    app.jinja_env.filters['shorten_url'] = shorten_url
    app.jinja_env.filters['remove_images'] = remove_images
    app.config['PROFILE'] = True
    app.wsgi_app = ProfilerMiddleware(app.wsgi_app, restrictions=[30])
    app.run(debug = True, host='127.0.0.1')



@app.before_request
def before_request():
    session['nonce'] = gibberish()
    g.locale = str(get_locale())
    if request.path != '/inbox' and not request.path.startswith(
            '/static/'):  # do not load g.site on shared inbox, to increase chance of duplicate detection working properly
        g.site = Site.query.get(1)
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        current_user.email_unread_sent = False
    else:
        if session.get('Referer') is None and \
                request.headers.get('Referer') is not None and \
                current_app.config['SERVER_NAME'] not in request.headers.get('Referer'):
            session['Referer'] = request.headers.get('Referer')


@app.after_request
def after_request(response):
    if 'auth/register' not in request.path:
        response.headers['Content-Security-Policy'] = f"script-src 'self' 'nonce-{session['nonce']}'"
        response.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains; preload'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if '/embed' not in request.path:
            response.headers['X-Frame-Options'] = 'DENY'
    return response
