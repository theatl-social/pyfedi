from app.shared.upload import process_upload
from app.utils import authorise_api_user


def post_upload_image(auth, image_file=None):
    authorise_api_user(auth)
    url = process_upload(image_file)
    return {"url": url}


def post_upload_community_image(auth, image_file=None):
    authorise_api_user(auth)
    url = process_upload(image_file, destination="communities")
    return {"url": url}


def post_upload_user_image(auth, image_file=None):
    authorise_api_user(auth)
    url = process_upload(image_file, destination="users")
    return {"url": url}
