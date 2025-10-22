from flask_login import current_user

from app.shared.upload import process_upload, process_file_delete
from app.utils import authorise_api_user


def post_upload_image(auth, image_file=None):
    try:
        user_id = authorise_api_user(auth)
    except Exception:
        if current_user.is_authenticated:
            user_id = current_user.id
        else:
            raise Exception('incorrect_login')
    url = process_upload(image_file, user_id=user_id)
    return {'url': url}


def post_upload_community_image(auth, image_file=None):
    authorise_api_user(auth)
    url = process_upload(image_file, destination='communities')
    return {'url': url}


def post_upload_user_image(auth, image_file=None):
    authorise_api_user(auth)
    url = process_upload(image_file, destination='users')
    return {'url': url}


def post_image_delete(auth, data):
    try:
        user_id = authorise_api_user(auth)
    except Exception:
        if current_user.is_authenticated:
            user_id = current_user.id
        else:
            raise Exception('incorrect_login')
    process_file_delete(data['file'], user_id=user_id)
    return {'result': 'ok'}
