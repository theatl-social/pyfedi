# Rate Limiting Guide

## Overview

PeachPie implements sophisticated per-destination rate limiting to:
- Prevent overwhelming remote instances
- Adapt to instance performance characteristics
- Respect remote instance capacity
- Maintain federation reliability

## Features

### 1. Multiple Rate Limit Types
Different activity types have different limits:
- **Activities**: General federation activities (100/min default)
- **Follows**: Follow/unfollow requests (20/5min default)
- **Votes**: Like/dislike activities (200/min default)
- **Media**: Media fetch requests (30/min default)
- **Global**: Overall per-instance limit (300/min default)

### 2. Adaptive Rate Limiting
The system automatically adjusts limits based on instance response times:
- Fast instances (< 0.5s): 125% of normal rate
- Normal instances: 100% rate
- Slow instances (> 2s): 75% rate
- Very slow instances (> 5s): 50% rate

### 3. Burst Allowance
Allows temporary bursts if recent usage is low:
- 20% burst allowance above limits
- Only if under 25% usage in recent half-window
- Prevents blocking legitimate traffic spikes

### 4. Sliding Window Algorithm
Uses Redis sorted sets for accurate rate limiting:
- Precise request counting
- No fixed window artifacts
- Automatic cleanup of old entries

## Configuration

### Environment Variables
```env
# Format: requests/seconds
RATE_LIMIT_ACTIVITIES=100/60       # 100 activities per minute
RATE_LIMIT_FOLLOWS=20/300          # 20 follows per 5 minutes
RATE_LIMIT_VOTES=200/60            # 200 votes per minute
RATE_LIMIT_MEDIA=30/60             # 30 media requests per minute
RATE_LIMIT_GLOBAL=300/60           # 300 total requests per minute
```

### Per-Instance Adjustments
Rate limits automatically adjust based on:
1. Response times
2. Error rates
3. Instance capacity

## Admin Interface

### Rate Limit Monitor (`/admin/rate-limits/rate-limits`)
- View all rate-limited destinations
- See current usage percentages
- Monitor configuration
- Live updates

### Features:
1. **Usage Visualization**: Progress bars show limit usage
2. **Auto-refresh**: Live monitoring every 10 seconds
3. **Reset Controls**: Clear limits for specific instances
4. **Configuration Display**: Current limits and windows

## Integration with Health Monitoring

Rate limiting works with health monitoring:
1. Healthy instances get full rate limits
2. Degraded instances get reduced limits
3. Circuit breaker prevents all requests to dead instances

## API Endpoints

### Get Rate Limit Status
```
GET /api/admin/rate-limits
```

Returns currently rate-limited destinations.

### Get Specific Instance Status
```
GET /api/admin/rate-limits?destinations=example.com,other.com
```

### Get Configuration
```
GET /api/admin/rate-limits/config
```

## Implementation Details

### Redis Keys
- `rate_limit:<type>:<destination>` - Request timestamps
- `rate_limit:adjustment:<destination>` - Adjustment factors
- `rate_limit:response_times:<destination>` - Response time history

### Error Handling
When rate limited:
1. Request is rejected with 429-like error
2. Retry-After header indicates wait time
3. Task is requeued with delay
4. Admin interface shows limited instances

### Performance Impact
- Minimal overhead (< 1ms per check)
- Redis operations are O(log N)
- Automatic cleanup prevents memory growth
- No locks or blocking operations

## Best Practices

### 1. Initial Configuration
Start with default limits and adjust based on:
- Your instance's capacity
- Federation partner requirements
- Observed traffic patterns

### 2. Monitoring
Regularly check:
- Rate limit dashboard
- Instance health status
- Federation error logs

### 3. Troubleshooting
If instances are frequently rate limited:
1. Check their health status
2. Review response times
3. Consider manual adjustment
4. Contact remote admin if needed

### 4. Emergency Controls
- Reset limits for specific instance
- Adjust configuration temporarily
- Use circuit breaker for problematic instances

## Integration Example

```python
from app.federation.rate_limiter import check_rate_limit

# Before sending activity
allowed, retry_after = check_rate_limit('example.com', 'Like')
if not allowed:
    # Queue for retry after retry_after seconds
    schedule_retry(retry_after)
else:
    # Send activity
    send_activity()
```

## Metrics and Monitoring

### Key Metrics
- Requests per minute by type
- Rate limit hit ratio
- Average retry delays
- Burst allowance usage

### Alerting Thresholds
- > 50% instances rate limited
- > 100 retry queue depth
- > 5s average response time

## Future Enhancements

1. **Machine Learning**: Predict optimal rates
2. **Negotiation**: Rate limit negotiation protocol
3. **Priorities**: Different limits for important activities
4. **Quotas**: Daily/monthly quotas for instances