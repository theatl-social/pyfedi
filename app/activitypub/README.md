# ActivityPub Module

This module implements the ActivityPub protocol for PyFedi, providing full federation capabilities with other ActivityPub-compatible platforms like Lemmy, Mastodon, PeerTube, and more.

## Module Structure

```
activitypub/
├── routes/              # HTTP endpoints organized by function
│   ├── webfinger.py    # Actor discovery (.well-known/webfinger)
│   ├── nodeinfo.py     # Server metadata endpoints
│   ├── actors.py       # User and community profiles
│   ├── inbox.py        # Receiving activities
│   ├── outbox.py       # Sending activities
│   ├── api.py          # Compatibility APIs
│   ├── debug.py        # Development debugging tools
│   └── helpers.py      # Shared utilities
├── signature.py         # HTTP signature verification/creation
├── util.py             # ActivityPub utilities
├── typed_util.py       # Fully typed utilities
├── find_object.py      # Object resolution
└── shared_inbox.py     # Shared inbox handling
```

## Key Features

### Multi-Platform Compatibility
- **Lemmy**: Full compatibility including Follow/Accept format fixes
- **Mastodon**: Person actors, status activities
- **PyFedi/PieFed**: Native support with extended features
- **PeerTube**: Video content support
- **Others**: Generic ActivityPub compliance

### Security
- HTTP signature verification on all incoming activities
- Domain verification to prevent spoofing
- Instance ban checking
- Safe JSON parsing with limits

### Type Safety
- Full Python 3.13 type annotations
- TypedDict for activity structures
- Comprehensive pydoc documentation
- IDE autocomplete support

## Endpoints

### Discovery
- `/.well-known/webfinger` - Actor discovery
- `/.well-known/nodeinfo` - Server capabilities
- `/.well-known/host-meta` - Legacy discovery

### Actor Endpoints
- `/u/<username>` - User profiles
- `/c/<community>` - Community profiles
- `/u/<username>/inbox` - User inbox
- `/c/<community>/inbox` - Community inbox

### Collections
- `/u/<username>/outbox` - User activities
- `/c/<community>/outbox` - Community posts
- `/c/<community>/followers` - Follower collection
- `/c/<community>/moderators` - Moderator list

### API Endpoints
- `/api/v1/instance` - Mastodon-compatible instance info
- `/api/v3/site` - Lemmy-compatible site info
- `/api/v3/federated_instances` - Federation status

## Activity Handling

### Incoming Activities
Activities are received through inbox endpoints and processed based on type:

- **Create**: New posts or comments
- **Update**: Edits to existing content
- **Delete**: Content removal
- **Follow**: Subscription requests
- **Accept/Reject**: Follow responses
- **Like/Dislike**: Voting
- **Announce**: Boosts/shares
- **Flag**: Reports

### Outgoing Activities
Activities are queued through the federation module for reliable delivery.

## Compatibility Fixes

### Follow Accept/Reject Format
Different platforms expect different response formats:

```python
# Lemmy/Mastodon format (simple)
{
    "type": "Accept",
    "object": "https://example.com/activities/follow/123"
}

# PyFedi format (detailed)
{
    "type": "Accept", 
    "object": {
        "type": "Follow",
        "id": "https://example.com/activities/follow/123",
        "actor": "...",
        "object": "..."
    }
}
```

The `format_follow_response()` function automatically selects the correct format based on the recipient's software.

## Usage Examples

### Sending an Activity
```python
from app.activitypub.routes.outbox import send_activity

await send_activity(
    activity={"type": "Create", "object": {...}},
    recipient_inbox="https://remote.site/inbox",
    sender_private_key=private_key,
    sender_key_id=key_id
)
```

### Verifying a Signature
```python
from app.activitypub.signature import HttpSignature

HttpSignature.verify_request(
    request,
    public_key,
    skip_date=True
)
```

## Security Considerations

1. **Always verify signatures** on incoming activities
2. **Check domain consistency** between actor and activity
3. **Validate JSON structure** before processing
4. **Rate limit** incoming requests
5. **Ban problematic instances** when necessary

## Debugging

Enable debug endpoints in development:
```python
# In config
ENABLE_DEBUG_ENDPOINTS = True
```

Access debug tools:
- `/debug/ap_requests` - View recent requests
- `/debug/ap_request/<id>` - Request details
- `/debug/federation_status` - Instance status

## Future Improvements

- [ ] Support for more activity types
- [ ] Enhanced media handling
- [ ] Relay support
- [ ] FEP implementations
- [ ] Performance optimizations