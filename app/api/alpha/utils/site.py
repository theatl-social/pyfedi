from app.api.alpha.utils.validators import required, integer_expected, boolean_expected
from app.api.alpha.views import site_view, federated_instances_view, site_instance_chooser_view
from app.constants import SRC_API
from app.models import InstanceBlock
from app.shared.site import block_remote_instance, unblock_remote_instance
from app.utils import authorise_api_user


def get_site(auth):
    if auth:
        user = authorise_api_user(auth, return_type='model')
    else:
        user = None

    site_json = site_view(user)
    return site_json


def get_site_instance_chooser(auth):
    return site_instance_chooser_view()


def get_federated_instances(data):
    return federated_instances_view()


def post_site_block(auth, data):
    required(['instance_id', 'block'], data)
    integer_expected(['instance_id'], data)
    boolean_expected(['block'], data)

    instance_id = data['instance_id']
    block = data['block']

    user_id = block_remote_instance(instance_id, SRC_API, auth) if block else unblock_remote_instance(instance_id, SRC_API, auth)
    blocked = InstanceBlock.query.filter_by(user_id=user_id, instance_id=instance_id).first()
    block = True if blocked else False
    data = {
        "blocked": block
    }
    return data
