"""ActivityPub inbox/outbox processing tasks"""
from app.federation.tasks import task, Priority

# These are placeholder imports - the actual functions will be moved here
# For now, we'll import from the existing location
from app.activitypub.routes import process_inbox_request as _process_inbox_request
from app.activitypub.routes import process_delete_request as _process_delete_request


@task(name='process_inbox_request', priority=Priority.NORMAL)
def process_inbox_request(request_json, store_ap_json, request_id=None):
    """Process incoming ActivityPub requests"""
    return _process_inbox_request(request_json, store_ap_json, request_id)


@task(name='process_delete_request', priority=Priority.URGENT)
def process_delete_request(request_json, store_ap_json, request_id=None):
    """Process ActivityPub delete requests (account deletions)"""
    return _process_delete_request(request_json, store_ap_json, request_id)


# Export tasks
__all__ = ['process_inbox_request', 'process_delete_request']