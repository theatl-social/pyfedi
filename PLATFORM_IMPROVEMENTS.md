# PyFedi/PeachPie Platform Improvements Plan

## Overview

This document outlines the platform improvements needed to enhance PyFedi/PeachPie's ActivityPub compatibility, performance, and maintainability. These improvements focus on functional enhancements rather than security fixes (which are covered in SECURITY_IMPROVEMENTS.md).

## Phase 1: Critical Vote Processing Fixes (Week 1-2)

### 1.1 Fix Inbound Vote Object Reference Parsing
**Problem**: Rigid parsing expects specific nesting patterns that vary across ActivityPub implementations

**Solution**: Implement flexible object reference extraction
- Create universal object ID extractor
- Handle Lemmy, Mastodon, and other formats
- Support both direct and announced activities

**Testing Requirements**:
- Test with various ActivityPub implementations
- Verify backwards compatibility
- Load test with mixed format votes

### 1.2 Implement Vote Suspense Queue
**Problem**: Votes for unknown objects are rejected instead of queued

**Solution**: Create pending vote system
- Database table for pending votes
- Celery tasks for retry logic
- Automatic resolution when objects arrive
- Configurable retry limits and timeouts

**Testing Requirements**:
- Test out-of-order activity handling
- Verify vote deduplication
- Test cleanup of stale votes

### 1.3 Standardize Outbound Vote Format
**Problem**: Non-standard 'audience' field may cause compatibility issues

**Solution**: Conditional formatting based on target instance
- Minimal format for unknown instances
- Include audience only for compatible software
- Remove unnecessary context from nested objects

**Testing Requirements**:
- Test with each major ActivityPub implementation
- Verify vote federation success rates
- Monitor for rejection patterns

## Phase 2: Performance & Async Operations (Week 2-3)

### 2.1 Async Announce Distribution
**Problem**: Synchronous HTTP calls to all followers block request processing

**Solution**: Queue-based distribution
- Move all announce operations to Celery
- Implement parallel sending with rate limiting
- Add circuit breakers for failing instances
- Track delivery success metrics

**Performance Targets**:
- < 100ms inbox response time
- Support 1000+ followers per community
- 99.9% eventual delivery rate

### 2.2 Async Actor Resolution
**Problem**: Synchronous actor fetching blocks activity processing

**Solution**: Cache-first architecture
- In-memory cache for hot actors
- Background fetch for unknown actors
- Graceful degradation when actors unavailable
- Periodic cache refresh for active actors

**Performance Targets**:
- 95% cache hit rate for active actors
- < 10ms actor lookup time (cached)
- No blocking on actor fetch

### 2.3 Add Fetch-on-Demand for Vote Objects
**Problem**: No attempt to fetch unknown objects when votes arrive

**Solution**: Intelligent object fetching
- Trigger fetch when votes arrive for unknown objects
- Rate limit fetches per instance
- Priority queue for popular objects
- Prevent fetch loops

**Performance Targets**:
- Successful resolution within 5 minutes
- No more than 10 fetches/minute per instance

## Phase 3: Code Refactoring (Week 4)

### 3.1 Break Up routes.py
**Problem**: 2800+ line file is unmaintainable

**Solution**: Logical separation into modules
```
app/activitypub/routes/
├── __init__.py       # Route registration
├── inbox.py          # Inbox handlers
├── actors.py         # Actor endpoints
├── activities.py     # Activity processors
├── collections.py    # Collection endpoints
└── nodeinfo.py       # Instance metadata
```

### 3.2 Extract Vote Processing Module
**Problem**: Vote logic scattered across multiple files

**Solution**: Centralized vote handling
- Single VoteProcessor class
- Consistent error handling
- Shared validation logic
- Easier unit testing

### 3.3 Implement Activity Processing Pipeline
**Problem**: Activity processing is monolithic and hard to extend

**Solution**: Pipeline architecture
- Pluggable validators
- Middleware for common operations
- Activity-specific handlers
- Consistent error propagation

## Phase 4: Federation Compatibility (Week 5)

### 4.1 Multi-Platform Testing Suite
- Automated tests against Lemmy, Mastodon, Misskey
- Compatibility matrix tracking
- Regular regression testing
- Performance benchmarking

### 4.2 Software Detection and Adaptation
- Detect instance software via NodeInfo
- Maintain compatibility profiles
- Adapt message format per platform
- Track success rates by software type

### 4.3 Federation Health Monitoring
- Real-time federation status dashboard
- Alert on federation failures
- Track vote success rates
- Monitor instance availability

## Phase 5: Developer Experience (Week 6)

### 5.1 Comprehensive Documentation
- ActivityPub implementation guide
- Federation troubleshooting guide
- API documentation
- Development setup guide

### 5.2 Development Tools
- Federation testing tools
- Activity inspector
- Signature verification tool
- Mock ActivityPub server for testing

### 5.3 Debugging Improvements
- Enhanced activity logging
- Request/response capture
- Federation trace tools
- Performance profiling

## Success Metrics

### Compatibility
- 95%+ vote success rate across platforms
- Support for top 10 ActivityPub implementations
- Zero breaking changes to existing federation

### Performance
- 10x improvement in inbox response time
- Support for 100K+ activities/hour
- Linear scaling with additional workers

### Reliability
- 99.9% uptime for federation endpoints
- < 0.1% activity loss rate
- Automatic recovery from failures

### Developer Productivity
- 50% reduction in debugging time
- 90% test coverage for federation code
- < 1 hour onboarding for new developers

## Risk Mitigation

1. **Feature Flags**: All new features behind flags
2. **Gradual Rollout**: Test on small instances first
3. **Rollback Plan**: One-command rollback capability
4. **Monitoring**: Comprehensive metrics and alerting
5. **Communication**: Notify large instances of changes

## Timeline Summary

- **Week 1-2**: Critical vote processing fixes
- **Week 2-3**: Performance improvements
- **Week 4**: Code refactoring
- **Week 5**: Federation compatibility
- **Week 6**: Developer experience

Total estimated time: 6 weeks with 2-3 developers

## Dependencies

- PostgreSQL with JSONB support
- Redis for caching and locks
- Celery for async processing
- Monitoring infrastructure (Prometheus/Grafana recommended)