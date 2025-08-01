# Federation Implementation Details

## ActivityPub Coverage

PyFedi implements a comprehensive set of ActivityPub features focused on federated social networking.

### Supported Activities (14/15)

✅ **Implemented**:
- Create, Update, Delete - Content management
- Like, Dislike - Voting system
- Follow, Accept, Reject - Social connections
- Announce - Content sharing/boosting
- Undo - Reversing actions
- Flag - Content reporting
- Add, Remove - Collection management
- Block - User/instance blocking

❌ **Not Implemented**:
- Move - Account migration (see rationale below)

### Supported Object Types

✅ **Content Objects**:
- Note (short posts), Article (long-form), Page (static), Question (polls)
- Comment (via Note with inReplyTo)

✅ **Actor Types**:
- Person, Group, Service, Application, Organization

✅ **Collections**:
- Collection, OrderedCollection with pagination support

✅ **Media**:
- Image, Video, Document, Audio attachments

### Design Decisions

#### Why Move Activity is Not Implemented

The Move activity for account migration was intentionally omitted because:

1. **Limited Adoption** - Only Mastodon fully supports it
2. **Implementation Complexity** - Requires:
   - Cryptographic proof of account ownership
   - Automated follower migration
   - Content redirection mechanisms
   - Complex verification flows
3. **Security Risks** - Potential for account hijacking if not perfectly implemented
4. **User Workaround Available** - Users can manually announce their new account

This is a pragmatic decision that focuses engineering effort on widely-used features.

#### Focus on Core Social Features

PyFedi prioritizes ActivityPub features commonly used in federated social media:
- Microblogging (Mastodon-compatible)
- Community discussions (Lemmy-compatible)
- Content voting and moderation
- Media sharing

Less common object types (Event, Place, Tombstone) are not implemented as they're rarely used in this context.

## Technical Implementation

### Type Safety

All ActivityPub handlers use Python 3.13 type annotations with:
- TypedDict for activity objects
- Proper validation of required fields
- Type-safe return values

### Security

- HTTP Signature verification on all incoming activities
- Exception: self-deletes (actor deleting themselves)
- URI validation to prevent SSRF
- Rate limiting on activity processing

### Performance

- Redis Streams for async task processing
- Batched activity delivery
- Caching of remote actors
- Efficient database queries with proper indexing

## Testing

Comprehensive test coverage includes:
- All implemented activity types
- Invalid activity handling
- Missing field validation
- Collection operations
- Nested activities
- Priority queue handling

See `/tests/test_activitypub_verbs_comprehensive.py` for full test suite.