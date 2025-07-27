# ActivityPub Routes

This directory contains all ActivityPub protocol endpoints, refactored from the original monolithic routes.py file into focused, maintainable modules.

## Module Organization

Each module handles a specific aspect of the ActivityPub protocol:

### `webfinger.py`
- **Purpose**: Actor discovery using WebFinger (RFC 7033)
- **Endpoints**:
  - `/.well-known/webfinger` - Discover users and communities
  - `/.well-known/host-meta` - Host metadata for older clients
- **Key Features**: Supports both `acct:` URIs and HTTPS URLs

### `nodeinfo.py`
- **Purpose**: Server metadata and capabilities
- **Endpoints**:
  - `/.well-known/nodeinfo` - Discovery links
  - `/nodeinfo/2.0` - NodeInfo 2.0 format
  - `/nodeinfo/2.1` - NodeInfo 2.1 format
- **Key Features**: Usage statistics, software info, federation status

### `actors.py`
- **Purpose**: Actor profiles and collections
- **Endpoints**:
  - `/u/<actor>` - User profiles
  - `/c/<actor>` - Community profiles
  - `/u/<actor>/outbox` - User activities
  - `/c/<actor>/outbox` - Community posts
  - `/c/<actor>/followers` - Follower counts
  - `/c/<actor>/moderators` - Moderator lists
- **Key Features**: Multi-format support, privacy-preserving collections

### `inbox.py`
- **Purpose**: Receive incoming ActivityPub activities
- **Endpoints**:
  - `/inbox` - Shared inbox for all actors
  - `/site_inbox` - Instance-level inbox
  - `/u/<actor>/inbox` - User-specific inbox
  - `/c/<actor>/inbox` - Community-specific inbox
- **Key Features**: 
  - Signature verification
  - Multi-platform compatibility
  - Follow Accept/Reject format fixes
  - Activity routing

### `outbox.py`
- **Purpose**: Send outgoing activities
- **Functions**:
  - `send_activity()` - Queue single activity
  - `send_to_followers()` - Fan-out to followers
  - `create_*_activity()` - Activity builders
- **Key Features**: Redis Streams integration, batch sending

### `api.py`
- **Purpose**: Compatibility APIs for various platforms
- **Endpoints**:
  - `/api/v1/instance` - Mastodon-compatible
  - `/api/v1/instance/domain_blocks` - Block list
  - `/api/v3/site` - Lemmy-compatible
  - `/api/v3/federated_instances` - Federation info
- **Key Features**: Cross-platform compatibility

### `debug.py`
- **Purpose**: Development and debugging tools
- **Endpoints**:
  - `/testredis` - Redis connectivity test
  - `/debug/ap_requests` - Recent request list
  - `/debug/ap_request/<id>` - Request details
  - `/debug/ap_stats` - Processing statistics
- **Security**: Only available in debug mode

### `helpers.py`
- **Purpose**: Shared utilities and types
- **Key Functions**:
  - `format_follow_response()` - Multi-platform Follow responses
  - `log_ap_status()` - Request tracking
  - `store_request_body()` - Debug storage
  - `make_activitypub_response()` - Response formatting
- **Features**: Full type annotations, reusable components

## Design Principles

1. **Separation of Concerns**: Each module has a single, clear purpose
2. **Type Safety**: All functions use Python 3.13 type hints
3. **Documentation**: Comprehensive pydoc for all functions
4. **Compatibility**: Maintains support for multiple ActivityPub implementations
5. **Security**: Consistent signature verification and validation

## Adding New Routes

When adding new ActivityPub endpoints:

1. Choose the appropriate module based on functionality
2. Add full type annotations
3. Include comprehensive pydoc
4. Handle multi-platform compatibility
5. Add security checks (signatures, domain validation)
6. Update module documentation

## Testing

Each module can be tested independently:

```python
# Test WebFinger
curl -H "Accept: application/json" \
  https://example.com/.well-known/webfinger?resource=acct:user@example.com

# Test NodeInfo
curl https://example.com/nodeinfo/2.0

# Test Actor
curl -H "Accept: application/activity+json" \
  https://example.com/u/username
```

## Common Patterns

### Signature Verification
```python
if 'Signature' in request.headers:
    HttpSignature.verify_request(request, public_key)
```

### Multi-format Responses
```python
if is_activitypub_request(request):
    return make_activitypub_response(data)
else:
    return redirect(url_for('html_view'))
```

### Error Handling
```python
try:
    # Process activity
except ValidationError:
    return 'Bad Request', 400
except Exception as e:
    logger.error(f"Error: {e}")
    return 'Internal Server Error', 500
```