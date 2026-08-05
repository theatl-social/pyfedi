# Unlimited Votes and Public Profile Vote Totals

## Goal

Disable the daily vote quota for every vote path in this fork, while exposing
each profile's aggregate upvote and downvote totals to every visitor.

## Decisions

- `VOTE_QUOTA=0` means unlimited votes.
- An absent `VOTE_QUOTA` keeps the current default of `240` votes per day.
- The unlimited setting applies to local web votes, authenticated API votes,
  and inbound ActivityPub Like and Dislike activities.
- Profile totals are public to anonymous and authenticated visitors, for local
  and remote profiles alike.
- The public profile shows aggregate votes cast as `upvotes / downvotes` only.
  It does not expose voter identities, voter lists, IP addresses, referrers,
  reputation, or other admin-only information.
- The quota progress indicator is not rendered when quotas are disabled.

## Design

### Configuration

`config.py` already preserves an explicit zero because environment values are
strings: `"0"` is truthy before it is converted to an integer. This change
documents and implements the following configuration contract:

| `VOTE_QUOTA` environment value | Effective behavior |
| --- | --- |
| absent or empty | quota is 240 votes per day |
| positive integer | quota is that many votes per day |
| `0` | quota is disabled |

Negative and non-integer configuration is outside this change; existing
startup conversion behavior remains in place.

### Vote enforcement

All existing quota checks must use the same condition: only evaluate the
daily Redis count when `VOTE_QUOTA` is greater than zero. This applies to:

- `app/shared/post.py:vote_for_post` for browser and API post votes;
- `app/shared/reply.py:vote_for_reply` for browser and API reply votes; and
- `app/activitypub/routes.py` for inbound Like and Dislike activities.

The daily counter can continue to be recorded while quotas are disabled; it
is no longer used to reject a vote. This avoids changing vote bookkeeping and
allows an administrator to re-enable a positive quota without a migration.

### Profile rendering

`app/user/routes.py:show_profile` calculates the quota fraction only when the
viewer is authenticated and the configured quota is positive. Otherwise it
passes a falsey value to the template. This prevents division by zero and
suppresses quota UI in unlimited mode.

`app/templates/user/show_profile.html` renders `Votes: upvotes / downvotes`
without the current authenticated-admin condition. The existing admin-only
wrapper remains around reputation, referrer, IP/country, last-active, and
donor fields.

## Error Handling

Positive quotas preserve the current response behavior: local/API post and
reply paths abort with HTTP 429 after the existing threshold is reached;
inbound ActivityPub activities are ignored once over threshold. With
`VOTE_QUOTA=0`, none of those paths reject or ignore a vote for quota reasons.

## Verification

Add focused pytest coverage that exercises:

1. public profile rendering for an anonymous visitor, asserting aggregate
   vote totals are present and admin-only metadata remains absent;
2. post and reply vote handling under a zero quota when the Redis counter is
   already above the former limit; and
3. inbound ActivityPub Like and Dislike processing under the same zero-quota
   condition.

Run the new focused tests and the repository's field-consistency test using
the documented macOS-safe cache settings. No database migration, API contract
change, federation schema change, or new dependency is required.

## Non-goals

- Displaying individual voters publicly.
- Changing per-post or per-comment score display.
- Altering vote quota defaults for deployments that do not opt in with
  `VOTE_QUOTA=0`.
- Changing Redis retention or vote-counter key structure.
