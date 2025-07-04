from datetime import datetime
from random import randint

from flask import (
    Markup,
    current_app,
    flash,
    g,
    make_response,
    redirect,
    request,
    session,
    url_for,
)
from flask_babel import _
from flask_login import current_user, login_user, logout_user
from sqlalchemy import func
from werkzeug.urls import url_parse

from app import cache, db, limiter, oauth
from app.auth import bp
from app.auth.forms import (
    LoginForm,
    RegisterByMastodonForm,
    RegistrationForm,
    ResetPasswordForm,
    ResetPasswordRequestForm,
)
from app.auth.util import (
    create_registration_application,
    get_country,
    notify_admins_of_registration,
    handle_abandoned_open_instance,
    process_registration_form,
    render_login_form,
    process_login,
    redirect_next_page,
    render_registration_form,
)
from app.email import (
    send_password_reset_email,
    send_registration_approved_email,
)
from app.ldap_utils import sync_user_to_ldap
from app.models import IpBan, User, UserRegistration, utcnow
from app.utils import (
    banned_ip_addresses,
    finalize_user_setup,
    get_setting,
    gibberish,
    ip_address,
    render_template,
    user_cookie_banned,
    user_ip_banned,
)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("100 per day;20 per 5 minutes", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect_next_page()

    form = LoginForm()
    if request.method == "POST" and form.validate_on_submit():
        return process_login(form)

    return render_login_form(form)


@bp.route('/logout')
def logout():
    logout_user()
    response = make_response(redirect(url_for('main.index')))
    response.set_cookie('low_bandwidth', '0', expires=datetime(year=2099, month=12, day=30))
    return response

@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("100 per day;20 per 5 minutes", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    handle_abandoned_open_instance()

    form = RegistrationForm()
    if request.method == "POST" and form.validate_on_submit():
        return process_registration_form(form)

    return render_registration_form(form)


@bp.route('/please_wait', methods=['GET'])
def please_wait():
    return render_template('auth/please_wait.html', title=_('Account under review'))


@bp.route('/check_email', methods=['GET'])
def check_email():
    return render_template('auth/check_email.html', title=_('Check your email'))


@bp.route('/reset_password_request', methods=['GET', 'POST'])
@limiter.limit("20 per day;10 per 5 minutes", methods=['POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        form.email.data = form.email.data.strip()
        if form.email.data.lower().startswith('postmaster@') or form.email.data.lower().startswith('abuse@') or \
                form.email.data.lower().startswith('noc@'):
            flash(_('Sorry, you cannot use that email address.'), 'error')
        else:
            user = User.query.filter(func.lower(User.email) == func.lower(form.email.data)).filter_by(ap_id=None,
                                                                                                      deleted=False).first()
            if user:
                send_password_reset_email(user)
                flash(_('Check your email for a link to reset your password.'))
                return redirect(url_for('auth.login'))
            else:
                flash(_('No account with that email address exists'), 'warning')
    return render_template('auth/reset_password_request.html',
                           title=_('Reset Password'), form=form)


@bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    user = User.verify_reset_password_token(token)
    if not user:
        return redirect(url_for('main.index'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash(_('Your password has been reset. Please use it to log in with user name of %(name)s.', name=user.user_name))
        return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html', form=form)


@bp.route('/verify_email/<token>')
def verify_email(token):
    if token != '':
        user = User.query.filter_by(verification_token=token).first()
        if user is not None:
            if user.banned:
                flash(_('You have been banned.'), 'error')
                return redirect(url_for('main.index'))
            if user.verified:  # guard against users double-clicking the link in the email
                flash(_('Thank you for verifying your email address.'))
                return redirect(url_for('auth.login'))
            user.verified = True

            # Update any pending application status from -1 to 0 when email is verified
            application = UserRegistration.query.filter_by(user_id=user.id, status=-1).first()
            if application:
                application.status = 0

                # Now notify admins since application is ready for review
                notify_admins_of_registration(application)

            db.session.commit()
            if not user.waiting_for_approval() and user.private_key is None:  # only finalize user set up if this is a brand new user. People can also end up doing this process when they change their email address in which case we DO NOT want to reset their keys, etc!
                finalize_user_setup(user)
            flash(_('Thank you for verifying your email address.'))
        else:
            flash(_('Email address validation failed.'), 'error')
            return redirect(url_for('main.index'))

        if user.waiting_for_approval():
            return redirect(url_for('auth.please_wait'))
        else:
            # Two things need to happen - email verification and (usually) admin approval.
            if g.site.registration_mode == 'RequireApplication':
                send_registration_approved_email(user)
            else:
                ...
                # send_welcome_email(user) #not written yet

            login_user(user, remember=True)
            if len(user.communities()) == 0:
                return redirect(url_for('auth.trump_musk'))
            else:
                return redirect(url_for('main.index'))


@bp.route('/validation_required')
def validation_required():
    return render_template('auth/validation_required.html')


@bp.route('/permission_denied')
def permission_denied():
    return render_template('auth/permission_denied.html')


@bp.route('/google_login')
def google_login():
    return oauth.google.authorize_redirect(redirect_uri=url_for('auth.google_authorize', _external=True))


@bp.route('/google_authorize')
def google_authorize():
    from app.shared.tasks import task_selector
    try:
        token = oauth.google.authorize_access_token()
    except Exception:
        current_app.logger.exception("Google OAuth error")
        flash(_('Login failed due to a problem with Google.'), 'error')
        return redirect(url_for('auth.login'))

    ip = ip_address()
    country = get_country(ip)
    # Country-based registration blocking
    if country != '':
        for country_code in get_setting('auto_decline_countries', '').split('\n'):
            if country_code and country_code.strip().upper() == country.upper():
                return render_template('generic_message.html', title=_('Application declined'),
                                       message=_('Sorry, we are not accepting registrations from your country.'))
    resp = oauth.google.get('oauth2/v2/userinfo', token=token)
    user_info = resp.json()
    google_id = user_info['id']
    email = user_info['email']
    name = user_info.get('name', '')

    # Try to find user by google_id first
    user = User.query.filter_by(google_oauth_id=google_id).first()

    # If not found, check by email and link
    if not user:
        user = User.query.filter_by(email=email).first()
        if user:
            user.google_oauth_id = google_id
        else:
            # Check if registrations are closed
            if g.site.registration_mode == 'Closed':
                flash(_('Account registrations are currently closed.'), 'error')
                return redirect(url_for('auth.login'))
            if user_ip_banned():
                return redirect(url_for('auth.please_wait'))

            user = User(user_name=find_new_username(email), title=name, email=email, verified=True,
                        verification_token='', instance_id=1, ip_address=ip_address(),
                        banned=user_ip_banned() or user_cookie_banned(), email_unread_sent=False,
                        referrer='', alt_user_name=gibberish(randint(8, 20)), google_oauth_id=google_id,
                        ip_address_country=country)
            db.session.add(user)
            db.session.commit()

            if g.site.registration_mode == 'RequireApplication' and g.site.application_question:
                application = create_registration_application(user, "Signed in with Google")
                db.session.commit()
                if get_setting('ban_check_servers', 'piefed.social'):
                    task_selector('check_application', application_id=application.id)
                return redirect(url_for('auth.please_wait'))
            else:
                # New user, no application required
                finalize_user_setup(user)
                login_user(user, remember=True)
                return redirect(url_for('auth.trump_musk'))
    else:
        if user.verified and not user.waiting_for_approval():
            finalize_user_setup(user)
            login_user(user, remember=True)
            return redirect(url_for('auth.trump_musk'))
        elif user.waiting_for_approval():
            return redirect(url_for('auth.please_wait'))
        else:
            return redirect(url_for('auth.check_email'))

    # user already exists - check if banned
    if user.id != 1 and (user.banned or user_ip_banned() or user_cookie_banned()):
        flash(_('You have been banned.'), 'error')

        response = make_response(redirect(url_for('auth.login')))
        # Detect if a banned user tried to log in from a new IP address
        if user.banned and not user_ip_banned():
            # If so, ban their new IP address as well
            new_ip_ban = IpBan(ip_address=ip, notes=user.user_name + ' used new IP address')
            db.session.add(new_ip_ban)
            db.session.commit()
            cache.delete_memoized(banned_ip_addresses)

        # Set a cookie so we have another way to track banned people
        response.set_cookie('sesion', '17489047567495', expires=datetime(year=2099, month=12, day=30))
        return response
    if user.waiting_for_approval():
        return redirect(url_for('auth.please_wait'))
    else:
        login_user(user, remember=True)
        session['ui_language'] = user.interface_language
        current_user.last_seen = utcnow()
        current_user.ip_address = ip
        current_user.ip_address_country = country if country != '' else current_user.ip_address_country
        db.session.commit()
        [limiter.limiter.clear(limit.limit, *limit.request_args) for limit in limiter.current_limits]
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            if len(current_user.communities()) == 0:
                next_page = url_for('auth.trump_musk')
            else:
                next_page = url_for('main.index')
        return redirect(next_page)


@bp.route("/mastodon_login")
def mastodon_login():
    redirect_uri = "urn:ietf:wg:oauth:2.0:oob"  # url_for('auth.mastodon_authorize', _external=True)
    return oauth.mastodon.authorize_redirect(redirect_uri=redirect_uri)


@bp.route("/mastodon_authorize", methods=['GET', 'POST'])
def mastodon_authorize():
    from app.shared.tasks import task_selector
    if not session.get("mastodon_token"):
        try:
            token = oauth.mastodon.authorize_access_token()
            session["mastodon_token"] = token
        except Exception as e:
            current_app.logger.exception(e)
            flash(_('Login failed due to a problem with Mastodon server.'), 'error')
            return redirect(url_for('auth.login'))
    else:
        token = session.get("mastodon_token")

    ip = ip_address()
    country = get_country(ip)
    # Country-based registration blocking
    if country != '':
        for country_code in get_setting('auto_decline_countries', '').split('\n'):
            if country_code and country_code.strip().upper() == country.upper():
                return render_template('generic_message.html', title=_('Application declined'),
                                       message=_('Sorry, we are not accepting registrations from your country.'))

    resp = oauth.mastodon.get('v1/accounts/verify_credentials', token=token)
    user_info = resp.json()
    mastodon_id = user_info['id']
    username = user_info.get('username', '')
    display_name = user_info.get("display_name", "")

    user = User.query.filter_by(mastodon_oauth_id=mastodon_id).first()
    if not user:
        # Check if registrations are closed
        if g.site.registration_mode == 'Closed':
            flash(_('Account registrations are currently closed.'), 'error')
            return redirect(url_for('auth.login'))
        if user_ip_banned():
            return redirect(url_for('auth.please_wait'))
        # if IP is not banned and there is no user just display form to fill additional data
        form = RegisterByMastodonForm()
        if request.method == "GET" or not form.validate_on_submit():
            return render_template(
                'auth/mastodon_authorize.html', form=form, user_info=user_info
            )
        # Note - get from form additional data
        email = form.email.data
        # password = form.password.data
        # get avatar also
        user = User(user_name=username, title=display_name, email=email, verified=True,
                    verification_token='', instance_id=1, ip_address=ip,
                    banned=user_ip_banned() or user_cookie_banned(), email_unread_sent=False,
                    referrer='', alt_user_name=gibberish(randint(8, 20)), mastodon_oauth_id=mastodon_id,
                    ip_address_country=country)
        # user.set_password(password)
        db.session.add(user)

        db.session.commit()
        if g.site.registration_mode == 'RequireApplication' and g.site.application_question:
            application = create_registration_application(user, "Signed in with Mastodon")
            db.session.commit()
            if get_setting('ban_check_servers', 'piefed.social'):
                task_selector('check_application', application_id=application.id)
            return redirect(url_for('auth.please_wait'))
    else:
        if user.verified and not user.waiting_for_approval():
            user.ip_address = ip
            user.ip_address_country = country if country != '' else user.ip_address_country
            finalize_user_setup(user)
            login_user(user, remember=True)
            return redirect(url_for('auth.trump_musk'))
        elif user.waiting_for_approval():
            return redirect(url_for('auth.please_wait'))
        else:
            return redirect(url_for('auth.check_email'))

    return redirect(url_for('auth.check_email'))


@bp.route('/discord_login')
def discord_login():
    return oauth.discord.authorize_redirect(redirect_uri=url_for('auth.discord_authorize', _external=True))


@bp.route('/discord_authorize')
def discord_authorize():
    from app.shared.tasks import task_selector
    try:
        token = oauth.discord.authorize_access_token()
    except Exception:
        current_app.logger.exception("Discord OAuth error")
        flash(_('Login failed due to a problem with Discord.'), 'error')
        return redirect(url_for('auth.login'))

    ip = ip_address()
    country = get_country(ip)
    # Country-based registration blocking
    if country != '':
        for country_code in get_setting('auto_decline_countries', '').split('\n'):
            if country_code and country_code.strip().upper() == country.upper():
                return render_template('generic_message.html', title=_('Application declined'),
                                       message=_('Sorry, we are not accepting registrations from your country.'))

    resp = oauth.discord.get('users/@me', token=token)
    user_info = resp.json()
    discord_id = user_info['id']
    email = user_info['email']
    username = user_info.get('username', '')

    # Try to find user by discord_id first
    user = User.query.filter_by(discord_oauth_id=discord_id).first()

    # If not found, check by email and link
    if not user:
        user = User.query.filter_by(email=email).first()
        if user:
            user.discord_oauth_id = discord_id
        else:
            # Check if registrations are closed
            if g.site.registration_mode == 'Closed':
                flash(_('Account registrations are currently closed.'), 'error')
                return redirect(url_for('auth.login'))
            if user_ip_banned():
                return redirect(url_for('auth.please_wait'))

            user = User(user_name=find_new_username(email), title=username, email=email, verified=True,
                        verification_token='', instance_id=1, ip_address=ip,
                        banned=user_ip_banned() or user_cookie_banned(), email_unread_sent=False,
                        referrer='', alt_user_name=gibberish(randint(8, 20)), discord_oauth_id=discord_id,
                        ip_address_country=country)
            db.session.add(user)
            db.session.commit()

            if g.site.registration_mode == 'RequireApplication' and g.site.application_question:
                application = create_registration_application(user, "Signed in with Discord")
                db.session.commit()
                if get_setting('ban_check_servers', 'piefed.social'):
                    task_selector('check_application', application_id=application.id)
                return redirect(url_for('auth.please_wait'))
            else:
                # New user, no application required
                finalize_user_setup(user)
                login_user(user, remember=True)
                return redirect(url_for('auth.trump_musk'))
    else:
        if user.verified and not user.waiting_for_approval():
            user.ip_address = ip
            user.ip_address_country = country if country != '' else user.ip_address_country
            finalize_user_setup(user)
            login_user(user, remember=True)
            return redirect(url_for('auth.trump_musk'))
        elif user.waiting_for_approval():
            return redirect(url_for('auth.please_wait'))
        else:
            return redirect(url_for('auth.check_email'))

    # user already exists - check if banned
    if user.id != 1 and (user.banned or user_ip_banned() or user_cookie_banned()):
        flash(_('You have been banned.'), 'error')

        response = make_response(redirect(url_for('auth.login')))
        # Detect if a banned user tried to log in from a new IP address
        if user.banned and not user_ip_banned():
            # If so, ban their new IP address as well
            new_ip_ban = IpBan(ip_address=ip, notes=user.user_name + ' used new IP address')
            db.session.add(new_ip_ban)
            db.session.commit()
            cache.delete_memoized(banned_ip_addresses)

        # Set a cookie so we have another way to track banned people
        response.set_cookie('sesion', '17489047567495', expires=datetime(year=2099, month=12, day=30))
        return response
    if user.waiting_for_approval():
        return redirect(url_for('auth.please_wait'))
    else:
        login_user(user, remember=True)
        session['ui_language'] = user.interface_language
        current_user.last_seen = utcnow()
        current_user.ip_address = ip
        current_user.ip_address_country = country if country != '' else current_user.ip_address_country
        db.session.commit()
        [limiter.limiter.clear(limit.limit, *limit.request_args) for limit in limiter.current_limits]
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            if len(current_user.communities()) == 0:
                next_page = url_for('auth.trump_musk')
            else:
                next_page = url_for('main.index')
        return redirect(next_page)


def find_new_username(email: str) -> str:
    email_parts = email.lower().split('@')
    original_email_part = email_parts[0]
    attempts = 0

    while attempts < 1000:
        existing_user = User.query.filter(User.user_name == email_parts[0], User.ap_id == None).first()
        if existing_user is None:
            return email_parts[0]
        else:
            email_parts[0] = original_email_part + str(randint(1, 1000))
            attempts += 1

    return gibberish(10)
