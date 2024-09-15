import random
from unicodedata import normalize

from flask import current_app

from app import cache
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
