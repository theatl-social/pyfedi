# ActivityPub Implementation Coverage

## Supported Activity Types

### Implemented and Tested ✅

1. **Like** - Vote up on posts/comments
   - Handler: `_handle_like` in inbox.py
   - Test: `test_like_activity`

2. **Dislike** - Vote down on posts/comments
   - Handler: `_handle_dislike` in inbox.py
   - Test: `test_dislike_activity`

3. **Create** - Create posts, comments, notes, articles
   - Handler: `_handle_create` in inbox.py
   - Tests: `test_create_note_activity`, `test_create_article_activity`

4. **Update** - Update posts, comments, user profiles
   - Handler: `_handle_update` in inbox.py
   - Test: `test_update_activity`

5. **Delete** - Delete posts, comments, actors
   - Handler: `_handle_delete` in inbox.py
   - Test: `test_delete_activity`
   - Special case: Self-delete doesn't require signature

6. **Follow** - Follow users or communities
   - Handler: `_handle_follow` in inbox.py
   - Test: `test_follow_activity`

7. **Accept** - Accept follow requests
   - Handler: `_handle_accept` in inbox.py
   - Test: `test_accept_activity`

8. **Reject** - Reject follow requests
   - Handler: `_handle_reject` in inbox.py
   - Test: `test_reject_activity`

9. **Announce** - Share/boost posts
   - Handler: `_handle_announce` in inbox.py
   - Test: `test_announce_activity`

10. **Undo** - Undo likes, follows, etc.
    - Handler: `_handle_undo` in inbox.py
    - Tests: `test_undo_like_activity`, `test_undo_follow_activity`

11. **Flag** - Report content or users
    - Handler: `_handle_flag` in inbox.py
    - Test: `test_flag_activity`

12. **Add** - Add to collections (featured posts, etc.)
    - Handler: `_handle_add` in inbox.py
    - Test: `test_add_activity`

13. **Remove** - Remove from collections
    - Handler: `_handle_remove` in inbox.py
    - Test: `test_remove_activity`

14. **Block** - Block users or instances
    - Handler: `_handle_block` in inbox.py
    - Test: `test_block_activity`

### Not Yet Implemented ❌

15. **Move** - Move actors between instances
    - No handler found
    - No test found

## Object Types Supported

- **Note** - Short text posts
- **Article** - Long-form articles
- **Page** - Static pages
- **Question** - Polls
- **Comment** - Reply to posts
- **Person** - Individual users
- **Group** - Communities
- **Collection** - Lists of objects
- **OrderedCollection** - Ordered lists

## Federation Features

- ✅ HTTP Signatures
- ✅ JSON-LD support
- ✅ WebFinger
- ✅ NodeInfo
- ✅ Actor endpoints (inbox/outbox)
- ✅ Activity queuing with Redis Streams
- ✅ Relay support
- ✅ Remote object resolution

## Security Features

- ✅ Signature verification (except self-deletes)
- ✅ Actor validation
- ✅ URI validation
- ✅ Rate limiting
- ✅ Request logging

## Testing Coverage

- ✅ All implemented verbs have tests
- ✅ Invalid activity type handling
- ✅ Missing required fields handling
- ✅ Collection activities
- ✅ Nested activities
- ✅ Activity priorities

## Notes

1. The "Move" activity is not implemented but is rarely used in practice
2. All core ActivityPub verbs for social networking are fully implemented
3. Type annotations have been added to improve code safety
4. Redis Streams replaced Celery for better performance