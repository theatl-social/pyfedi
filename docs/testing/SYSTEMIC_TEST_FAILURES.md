# Systemic Test Failure Analysis

## Overview
Yes, there are clear systemic patterns causing the majority of test failures. Most failures stem from 3-4 root causes that affect many tests.

## Root Causes

### 1. **Database Schema Mismatches** (Causing ~207 ERROR states)

The models don't match the actual database schema created by migrations:

#### Instance Model Mismatches:
- Model has `online` column → Database doesn't have it
- Model has `last_successful_contact` → Database has `last_successful_send`
- Model has `trust_level` → Database doesn't have it

#### Site Model Mismatches (Fixed):
- Model had `registration_open` → Database has `registration_mode` ✅

**Pattern**: Models were updated but corresponding migrations weren't created or applied.

### 2. **Missing g.site Object** (Causing ~49 FAILED tests)

Many routes expect `g.site` to be populated:
```python
'publicKeyPem': g.site.public_key  # AttributeError: site
```

**Cause**: The `before_request` handler that sets `g.site` isn't running in tests or Site record doesn't exist.

### 3. **Import/Mock Mismatches** 

Tests try to mock functions that don't exist:
```python
AttributeError: <module 'app.activitypub.routes.inbox'> does not have the attribute 'verify_request'
```

**Cause**: Functions were moved/renamed but tests weren't updated.

### 4. **Empty Test Database**

Tests expect fixtures (User, Community, Instance) but `test_instance` fixture fails due to schema mismatch, cascading to all dependent tests.

## Impact Analysis

| Issue | Tests Affected | % of Failures |
|-------|---------------|---------------|
| Instance schema mismatch | ~207 | 67% |
| Missing g.site | ~49 | 16% |
| Import errors | ~30 | 10% |
| Other | ~24 | 7% |

## Solution Priority

### 1. Fix Instance Model (High Impact - 67% of failures)
Either:
- Update Instance model to match database schema
- OR create migration to add missing columns

### 2. Fix g.site Setup (Medium Impact - 16% of failures)
- Ensure Site record exists in test database
- Set up g.site in test fixtures

### 3. Update Test Mocks (Low Impact - 10% of failures)
- Find where functions moved to
- Update mock paths

## Quick Win
Fixing just the Instance model schema mismatch would resolve ~67% of all test failures!

## Verification
After fixing Instance model:
- ERROR count should drop from 207 to ~50
- Many dependent tests should start working
- Can then focus on the smaller issues