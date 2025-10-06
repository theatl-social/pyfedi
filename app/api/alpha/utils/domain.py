from app.constants import SRC_API
from app.shared.domain import block_domain, unblock_domain


def post_domain_block(auth, data):
    domain = data['domain']
    block = data['block']

    if block:
        block_domain(domain, SRC_API, auth)
        return True
    else:
        unblock_domain(domain, SRC_API, auth)
        return False
