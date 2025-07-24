import time
import httpx
from functools import wraps
from app.activitypub.util import find_liked_object, resolve_remote_post

# Retry decorator for ActivityPub actions that may return an unfound object
# Usage: decorate any function that performs ActivityPub actions and may return None or unfound

def retry_activitypub_action(max_retries=4, delay=2, allowed_statuses=(404, 410)):
    """
    Decorator to retry ActivityPub actions that may return an unfound object.
    Retries on HTTP 404/410 or None result.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = 0.5  # Set initial delay for exponential backoff
            for attempt in range(max_retries):
                result = func(*args, **kwargs)
                # If result is not None and not a 404/410, return
                if result is not None and not (hasattr(result, 'status_code') and result.status_code in allowed_statuses):
                    return result

                # Try to refetch missing object if possible
                ap_id = None
                # Try to extract ap_id from args/kwargs
                if 'request_json' in kwargs:
                    req_json = kwargs['request_json']
                    if 'object' in req_json:
                        ap_id = req_json['object']
                        if isinstance(ap_id, dict) and 'id' in ap_id:
                            ap_id = ap_id['id']
                        elif isinstance(ap_id, dict) and 'object' in ap_id and 'id' in ap_id['object']:
                            ap_id = ap_id['object']['id']
                elif len(args) > 2:
                    req_json = args[2]
                    if isinstance(req_json, dict) and 'object' in req_json:
                        ap_id = req_json['object']
                        if isinstance(ap_id, dict) and 'id' in ap_id:
                            ap_id = ap_id['id']
                        elif isinstance(ap_id, dict) and 'object' in ap_id and 'id' in ap_id['object']:
                            ap_id = ap_id['object']['id']

                # If ap_id is present and not found locally, try remote fetch
                if ap_id:
                    obj = find_liked_object(ap_id)
                    if obj is None:
                        # Attempt remote fetch
                        try:
                            resolve_remote_post(ap_id)
                        except Exception:
                            pass  # Ignore errors, will retry

                if attempt < max_retries - 1:
                    time.sleep(delay * (2 ** attempt))
            return None
        return wrapper
    return decorator
