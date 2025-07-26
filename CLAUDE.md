# PyFedi/PeachPie Development Memory

## Current Status (2025-01-26)

### Branch: 20250126-critical-security-fixes
Working on critical security vulnerabilities identified in security analysis.

### Completed Analysis
1. **Vote Processing Issues**
   - Inbound votes fail due to rigid object parsing
   - No suspense queue for out-of-order activities
   - Outbound format includes non-standard 'audience' field
   - Complex Announce wrapping confuses other implementations

2. **Security Vulnerabilities Identified**
   - CRITICAL: RCE via unsafe JSON deserialization
   - CRITICAL: Authentication bypass via signature fallback
   - CRITICAL: SQL injection risks in raw queries
   - HIGH: DoS via unlimited actor creation
   - HIGH: Vote amplification attacks
   - HIGH: Insufficient URI validation
   - HIGH: Missing access control on Announces
   - HIGH: Insecure object references

3. **Performance Issues**
   - Synchronous HTTP calls block request processing
   - No async actor resolution
   - announce_activity_to_followers is synchronous

### Current Task Queue
1. Implement safe JSON parser with depth/size limits
2. Fix authentication bypass - remove unsafe fallbacks
3. Audit and fix all SQL injection vulnerabilities
4. Add rate limiting for actor creation
5. Implement vote deduplication
6. Add URI validation library
7. Make announce distribution async

### Key Findings
- Lemmy always signs activities (no exceptions)
- Mastodon always signs activities
- Some implementations (PeerTube, relays) may send unsigned
- Current PyFedi code accepts unsigned activities unsafely

### Implementation Strategy
- Feature flags for gradual rollout
- Comprehensive testing at each stage
- Monitor federation compatibility
- Keep changes modular for easy rollback

### Files Created
- PLATFORM_IMPROVEMENTS.md - Functional improvements plan
- SECURITY_IMPROVEMENTS.md - Security fixes overview  
- SECURITY_MITIGATION_DETAILS.md - Detailed implementation guide
- UPSTREAM_SECURITY_ANALYSIS.md - (in progress via subagent)

### Next Steps
1. Implement safe JSON parser
2. Fix signature verification
3. SQL injection audit and fixes
4. Deploy to test instance
5. Monitor metrics before wider rollout