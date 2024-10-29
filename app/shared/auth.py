from app import db
from app.auth.util import ip2location
from app.models import IpBan, User, utcnow
from app.utils import ip_address, user_ip_banned, user_cookie_banned, banned_ip_addresses, gibberish
from app.api.alpha.utils.validators import required, string_expected

from datetime import datetime

from flask import redirect, url_for, flash, request, make_response, session, Markup
from flask_babel import _

# would be in app/constants.py
SRC_WEB = 1
SRC_PUB = 2
SRC_API = 3


# function can be shared between WEB and API (only API calls it for now)

def log_user_in(input, src):
    if src == SRC_WEB:
        username = input.user_name.data
        password = input.password.data
        user = User.query.filter_by(user_name=username, ap_id=None).first()
    elif src == SRC_API:
        required(["username_or_email", "password"], input)
        string_expected(["username_or_email", "password"], input)

        username = input['username_or_email']
        password = input['password']
        user = User.query.filter_by(user_name=username, ap_id=None, deleted=False).one()
    else:
        return None

    if src == SRC_WEB:
        if user is None or user.deleted:
            flash(_('No account exists with that user name.'), 'error')
            return redirect(url_for('auth.login'))

    if not user.check_password(password):
        if src == SRC_WEB:
            if user.password_hash is None:
                message = Markup(_('Invalid password. Please <a href="/auth/reset_password_request">reset your password</a>.'))
                flash(message, 'error')
                return redirect(url_for('auth.login'))
            flash(_('Invalid password'))
            return redirect(url_for('auth.login'))
        elif src == SRC_API:
             raise Exception('incorrect_login')

    if user.id != 1 and (user.banned or user_ip_banned() or user_cookie_banned()):
        # Detect if a banned user tried to log in from a new IP address
        if user.banned and not user_ip_banned():
            # If so, ban their new IP address as well
            new_ip_ban = IpBan(ip_address=ip_address(), notes=user.user_name + ' used new IP address')
            db.session.add(new_ip_ban)
            db.session.commit()
            cache.delete_memoized(banned_ip_addresses)

            if src == SRC_WEB:
                flash(_('You have been banned.'), 'error')

                response = make_response(redirect(url_for('auth.login')))

                # Set a cookie so we have another way to track banned people
                response.set_cookie('sesion', '17489047567495', expires=datetime(year=2099, month=12, day=30))
                return response
            elif src == SRC_API:
                 raise Exception('incorrect_login')

    if src == SRC_WEB:
        if user.waiting_for_approval():
            return redirect(url_for('auth.please_wait'))
        login_user(user, remember=True)
        session['ui_language'] = user.interface_language

    user.last_seen = utcnow()
    user.ip_address = ip_address()
    ip_address_info = ip2location(user.ip_address)
    user.ip_address_country = ip_address_info['country'] if ip_address_info else user.ip_address_country
    db.session.commit()

    if src == SRC_WEB:
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            if len(user.communities()) == 0:
                next_page = url_for('topic.choose_topics')
            else:
                next_page = url_for('main.index')
        response = make_response(redirect(next_page))
        if input.low_bandwidth_mode.data:
            response.set_cookie('low_bandwidth', '1', expires=datetime(year=2099, month=12, day=30))
        else:
            response.set_cookie('low_bandwidth', '0', expires=datetime(year=2099, month=12, day=30))
        return response
    elif src == SRC_API:
        login_json = {
          'jwt': user.encode_jwt_token(),
          'registration_created': user.verified,
          'verify_email_sent': True
        }
        return login_json
