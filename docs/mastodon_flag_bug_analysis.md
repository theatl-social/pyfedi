# "Intended for Mastodon" Flag Bug Analysis

## Issue
Lemmy posts are being incorrectly flagged as "Intended for Mastodon"

## Root Cause
In `app/activitypub/routes.py` lines 867-871, the code has flawed logic:

```python
if not 'id' in object or not 'type' in object or not 'actor' in object or not 'object' in object:
    if 'type' in object and (object['type'] == 'Page' or object['type'] == 'Note'):
        # Flags as "Intended for Mastodon"
```

## Why This Is Wrong

1. **The code expects ALL announced objects to have an 'object' field**
   - This is not a requirement in ActivityPub spec
   - Lemmy's Page objects don't have an 'object' field

2. **Incorrect assumption about Page/Note types**
   - The code assumes Page/Note without 'object' = Mastodon
   - Lemmy uses 'Page' type for posts/articles
   - Many ActivityPub implementations use Page/Note without nested 'object'

3. **The Lemmy post structure**:
   ```
   Announce {
     object: Page {
       id: "...",
       type: "Page", 
       actor: "...",
       // NO 'object' field - this is normal!
     }
   }
   ```

## Impact
All Lemmy posts (and potentially posts from other non-Mastodon ActivityPub servers) that use Page or Note types without an 'object' field are incorrectly ignored as "Intended for Mastodon".

## Recommended Fix
Remove or refine the check to not assume Page/Note objects require an 'object' field. The presence of 'id', 'type', and 'actor' should be sufficient for processing.