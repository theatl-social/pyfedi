import random
from datetime import timedelta
from unicodedata import normalize

from flask import current_app

from app import cache, db
from app.models import Site, utcnow, Notification, UserRegistration, User
from app.utils import get_request


# Return a random string of 6 letter/digits.
def random_token(length=6) -> str:
    return "".join(
        [random.choice('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ') for x in range(length)])


def normalize_utf(username):
    return normalize('NFKC', username)


def ip2location(ip: str):
    """ city, region and country for the requester, using the ipinfo.io service """
    if ip is None or ip == '':
        return {}
    ip = '208.97.120.117' if ip == '127.0.0.1' else ip
    # test
    data = cache.get('ip_' + ip)
    if data is None:
        if not current_app.config['IPINFO_TOKEN']:
            return {}
        url = 'http://ipinfo.io/' + ip + '?token=' + current_app.config['IPINFO_TOKEN']
        response = get_request(url)
        if response.status_code == 200:
            data = response.json()
            cache.set('ip_' + ip, data, timeout=86400)
        else:
            return {}

    if 'postal' in data:
        postal = data['postal']
    else:
        postal = ''
    return {'city': data['city'], 'region': data['region'], 'country': data['country'], 'postal': postal,
            'timezone': data['timezone']}


def no_admins_logged_in_recently():
    a_week_ago = utcnow() - timedelta(days=7)
    for user in Site.admins():
        if user.last_seen > a_week_ago:
            return False

    for user in Site.staff():
        if user.last_seen > a_week_ago:
            return False

    return True


def check_if_ip_banned() -> bool:
    # Country based registration blocking
    ip_address_info = ip2location(ip_address())
    if ip_address_info and ip_address_info['country']:
        for country_code in get_setting('auto_decline_countries', '').split('\n'):
            if country_code and country_code.strip().upper() == ip_address_info['country'].upper():
                return True
    return False


def create_user_application(user: User, registration_answer: str):
    application = UserRegistration(user_id=user.id, answer='Signed in with Google')
    db.session.add(application)
    targets_data = {'application_id':application.id,'user_id':user.id}
    for admin in Site.admins():
        notify = Notification(title='New registration', url=f'/admin/approve_registrations?account={user.id}',
                              user_id=admin.id,
                              author_id=user.id, notif_type=NOTIF_REGISTRATION,
                              subtype='new_registration_for_approval',
                              targets=targets_data)
        admin.unread_notifications += 1
        db.session.add(notify)
        # todo: notify everyone with the "approve registrations" permission, instead of just all admins
    db.session.commit()

