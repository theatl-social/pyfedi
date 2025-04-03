from app.utils import gibberish, ensure_directory_exists

from pillow_heif import register_heif_opener
from PIL import Image, ImageOps
from flask import current_app

import os


def process_upload(image_file, destination='posts'):
    # should have errored earlier if no upload, but just to be paranoid
    if not image_file or image_file.filename == '':
        raise Exception('file not uploaded')

    allowed_extensions = ['.gif', '.jpg', '.jpeg', '.png', '.webp', '.heic', '.mpo', '.avif', '.svg']
    file_ext = os.path.splitext(image_file.filename)[1]
    if file_ext.lower() not in allowed_extensions:
        raise Exception('filetype not allowed')

    new_filename = gibberish(15)
    # set up the storage directory
    directory = 'app/static/media/' + destination + '/' + new_filename[0:2] + '/' + new_filename[2:4]
    ensure_directory_exists(directory)

    # save the file
    final_place = os.path.join(directory, new_filename + file_ext)
    image_file.seek(0)
    image_file.save(final_place)

    if file_ext.lower() == '.heic':
        register_heif_opener()
    if file_ext.lower() == '.avif':
        import pillow_avif

    Image.MAX_IMAGE_PIXELS = 89478485

    # limit full sized version to 2000px
    if not final_place.endswith('.svg'):
        img = Image.open(final_place)
        if '.' + img.format.lower() in allowed_extensions:
            img = ImageOps.exif_transpose(img)

            img.thumbnail((2000, 2000))
            img.save(final_place)

            url = f"https://{current_app.config['SERVER_NAME']}/{final_place.replace('app/', '')}"
        else:
            raise Exception('filetype not allowed')
    else:
        url = f"https://{current_app.config['SERVER_NAME']}/{final_place.replace('app/', '')}"

    if not url:
        raise Exception('unable to process upload')

    return url


