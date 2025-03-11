from app.utils import authorise_api_user
from app.shared.upload import process_upload

def post_upload_image(auth, image_file=None):
    user_id = authorise_api_user(auth)
    url = process_upload(image_file)
    return {'url': url}
