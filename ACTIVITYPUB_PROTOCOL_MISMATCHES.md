# ActivityPub Protocol Mismatches Report

## Overview
PyFedi/PieFed has several ActivityPub implementation details that cause compatibility issues with other federated software, particularly Lemmy and Mastodon.

## Vote Processing Issues

### 1. Non-Standard 'audience' Field
**Issue**: PyFedi includes an 'audience' field in vote activities that other implementations don't expect.

**PyFedi sends**:
```json
{
  "@context": "https://www.w3.org/ns/activitystreams",
  "type": "Like",
  "actor": "https://pyfedi.example/u/user",
  "object": "https://lemmy.example/post/123",
  "audience": "https://pyfedi.example/c/community",
  "id": "https://pyfedi.example/activities/like/456"
}
```

**Lemmy expects**:
```json
{
  "@context": "https://www.w3.org/ns/activitystreams",
  "type": "Like",
  "actor": "https://lemmy.example/u/user",
  "object": "https://lemmy.example/post/123",
  "id": "https://lemmy.example/activities/like/789"
}
```

**Impact**: Remote instances may reject or ignore votes with unexpected fields.

### 2. Announce Wrapping of Votes
**Issue**: PyFedi wraps votes in Announce activities when distributing to followers.

**PyFedi's approach**:
```python
announce_activity_to_followers(liked.community, user, request_json, can_batch=True)
```

This creates:
```json
{
  "type": "Announce",
  "actor": "https://pyfedi.example/c/community",
  "object": {
    "type": "Like",
    "actor": "https://pyfedi.example/u/user",
    "object": "https://remote.example/post/123"
  }
}
```

**Problem**: 
- Lemmy expects direct Like/Dislike activities, not Announced votes
- The community actor announcing user votes is non-standard
- Creates confusion about the authoritative source of the vote

### 3. Vote Object Structure
**Issue**: PyFedi accepts votes where the object can be either a string (URL) or an object with an 'id' field, but may not handle all cases correctly.

**Valid formats PyFedi accepts**:
```json
// Format 1: Direct URL
"object": "https://example.com/post/123"

// Format 2: Object with ID
"object": {
  "id": "https://example.com/post/123",
  "type": "Page"
}

// Format 3: Announced vote with nested object
"object": {
  "object": "https://example.com/post/123"
}
```

**Issue**: Inconsistent handling and forwarding of these formats.

## Signature Validation Mismatches

### 1. Unsafe Fallbacks
**Issue**: PyFedi accepts unsigned activities in several cases:

1. **Fediseer Exception**: Accepts unsigned ChatMessages from Fediseer
2. **Object Reduction**: Accepts unsigned Create/Update by reducing to object ID
3. **Relay Tolerance**: Accepts activities with broken signatures from relays

**Security Impact**: Allows authentication bypass attacks.

### 2. Signature Requirements
**PyFedi's behavior**:
- Tries HTTP signature first
- Falls back to LD signature
- Falls back to unsigned acceptance (security hole)

**Lemmy's behavior**:
- Requires valid HTTP signature
- No unsigned fallbacks
- Rejects all unsigned activities

**Mastodon's behavior**:
- Always signs with HTTP signatures
- Expects HTTP signatures from others

## Missing Suspense Queue

**Issue**: PyFedi has no mechanism to hold votes for posts that haven't been received yet.

**Scenario**:
1. Remote user votes on a post
2. Vote arrives before the post
3. PyFedi rejects vote (can't find object)
4. Vote is lost permanently

**Lemmy's approach**: Queues activities referencing unknown objects for later processing.

## Actor Discovery Issues

**Issue**: When creating remote actors, PyFedi doesn't handle all ActivityPub actor types correctly.

**Supported**: Person, Service, Group
**Missing**: Application, Organization
**Impact**: Can't interact with some bot accounts or organizational actors

## Recommendations

### High Priority Fixes
1. **Remove 'audience' field** from outbound votes
2. **Send votes directly** without Announce wrapper
3. **Implement suspense queue** for out-of-order activities
4. **Remove unsigned activity acceptance** (match Lemmy's security model)

### Medium Priority  
1. **Standardize vote object handling** - always send as URL string
2. **Support all actor types** in actor discovery
3. **Add retry logic** for failed vote delivery

### Low Priority
1. **Add compatibility modes** for different implementations
2. **Implement activity validation** before forwarding
3. **Add metrics** for federation success rates

## Testing Recommendations

1. **Set up test federation** with Lemmy instance
2. **Monitor logs** for rejected activities  
3. **Use ActorPub.rocks** test suite
4. **Test vote federation** specifically:
   - Outbound votes to Lemmy posts
   - Inbound votes from Lemmy users
   - Vote updates/deletions
   - Vote forwarding in communities

## Summary

The main compatibility issues stem from:
1. Non-standard fields ('audience')
2. Unnecessary activity wrapping (Announce)
3. Security/compatibility trade-offs (unsigned activities)
4. Missing features (suspense queue)

Fixing these issues would significantly improve PyFedi's federation compatibility, particularly with Lemmy instances which have strict ActivityPub implementations.