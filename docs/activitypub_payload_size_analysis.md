# ActivityPub Payload Size Analysis

## Typical ActivityPub Payload Sizes

### 1. Standard Text Posts
- **Lemmy announce**: ~1.5KB (example measured)
- **Mastodon status**: 1-5KB typically
- **PeerTube video metadata**: 2-10KB
- **Article/Page objects**: 5-20KB with full content

### 2. Posts with Media References
ActivityPub objects don't contain actual media data, just URLs:
- Image posts: Add ~200-500 bytes per image URL
- Video posts: Add ~500-1KB for metadata
- Multiple attachments: Add ~300 bytes each

### 3. Large Content Scenarios
- **Long articles**: Up to 100KB for very long blog posts
- **Polls with many options**: Up to 20KB
- **Events with rich data**: Up to 50KB
- **Collections (followers, etc.)**: Can be paginated, typically <100KB per page

### 4. Edge Cases
- **Mastodon user profiles** with many fields: Up to 50KB
- **PeerTube channel** with extensive metadata: Up to 100KB
- **Mobilizon events** with complex data: Up to 200KB

## Real-World Data Points

### Mastodon
- Enforces a 1MB limit on incoming activities
- Most status updates are 1-5KB
- Profile updates rarely exceed 20KB

### Lemmy
- Typical post announcements: 1-3KB
- Comments: 1-5KB
- Community updates: 5-20KB

### PeerTube
- Video activity (not the video itself): 5-20KB
- Channel updates: 10-50KB

## Media Handling
**Important**: ActivityPub doesn't embed media directly. Instead:
- Images/videos are referenced by URL
- Media is fetched separately via HTTP
- This keeps ActivityPub payloads small

## Recommendations

### 10MB Limit Analysis
- **Pros**:
  - Covers 99.99% of legitimate ActivityPub traffic
  - Allows for future protocol extensions
  - Protects against malicious payloads
  - Matches or exceeds most implementations

- **Cons**:
  - Might be too generous (Mastodon uses 1MB)
  - Could allow memory exhaustion with many concurrent requests

### Alternative Limits to Consider
1. **1MB (Conservative)**: Matches Mastodon, covers all normal use cases
2. **5MB (Balanced)**: Allows headroom for edge cases
3. **10MB (Liberal)**: Current setting, very permissive

### Recommendation: 5MB
A 5MB limit would:
- Cover all legitimate ActivityPub traffic
- Provide 5x headroom over Mastodon's limit
- Reduce memory usage by 50% vs 10MB
- Still protect against OOM attacks

## Implementation Note
```python
# In config.py, consider:
MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 5 * 1024 * 1024))  # 5MB default
```

## Monitoring
Track actual payload sizes in production:
```sql
SELECT 
    content_length,
    COUNT(*) as count,
    parsed_json->>'type' as activity_type
FROM ap_request_body
WHERE content_length IS NOT NULL
GROUP BY content_length / 10000, activity_type
ORDER BY content_length;
```