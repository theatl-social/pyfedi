#!/bin/bash

# Test script for PieFed API post reply pagination
# Tests cursor-based pagination with nested structure

BASE_URL="https://piefed.ngrok.app/api/alpha/post/replies"
POST_ID="381"
SORT="Hot"

echo "================================="
echo "PieFed API Pagination Test Suite"
echo "================================="
echo

# Test 1: Full list (no pagination)
echo "=== TEST 1: Full comment list (no pagination) ==="
curl -s "${BASE_URL}?post_id=${POST_ID}&sort=${SORT}" | jq '[.comments[] | .comment.id]'
echo

# Test 2: Basic pagination with limit=1
echo "=== TEST 2: Sequential pagination with limit=1 ==="
echo "Page 1:"
curl -s "${BASE_URL}?post_id=${POST_ID}&sort=${SORT}&limit=1" | jq '{count: (.comments | length), next: .next_page, ids: [.comments[] | .comment.id]}'
echo

echo "Page 2 (cursor=914):"
curl -s "${BASE_URL}?post_id=${POST_ID}&sort=${SORT}&limit=1&page=914" | jq '{count: (.comments | length), next: .next_page, ids: [.comments[] | .comment.id]}'
echo

echo "Page 3 (cursor=915):"
curl -s "${BASE_URL}?post_id=${POST_ID}&sort=${SORT}&limit=1&page=915" | jq '{count: (.comments | length), next: .next_page, ids: [.comments[] | .comment.id]}'
echo

echo "Page 4 (cursor=911):"
curl -s "${BASE_URL}?post_id=${POST_ID}&sort=${SORT}&limit=1&page=911" | jq '{count: (.comments | length), next: .next_page, ids: [.comments[] | .comment.id]}'
echo

echo "Page 5 (cursor=912):"
curl -s "${BASE_URL}?post_id=${POST_ID}&sort=${SORT}&limit=1&page=912" | jq '{count: (.comments | length), next: .next_page, ids: [.comments[] | .comment.id]}'
echo

# Test 3: Pagination with limit=2
echo "=== TEST 3: Branch-aware pagination with limit=2 ==="
echo "Page 1:"
curl -s "${BASE_URL}?post_id=${POST_ID}&sort=${SORT}&limit=2" | jq '{count: (.comments | length), next: .next_page, ids: [.comments[] | .comment.id]}'
echo

echo "Page 2 (cursor=915):"
curl -s "${BASE_URL}?post_id=${POST_ID}&sort=${SORT}&limit=2&page=915" | jq '{count: (.comments | length), next: .next_page, ids: [.comments[] | .comment.id]}'
echo

echo "Page 3 (cursor=911):"
curl -s "${BASE_URL}?post_id=${POST_ID}&sort=${SORT}&limit=2&page=911" | jq '{count: (.comments | length), next: .next_page, ids: [.comments[] | .comment.id]}'
echo

# Test 4: Nested structure verification
echo "=== TEST 4: Nested structure verification ==="
echo "Top-level comments with post/community fields:"
curl -s "${BASE_URL}?post_id=${POST_ID}&sort=${SORT}" | jq '.comments[] | {id: .comment.id, has_post: (has("post")), has_community: (has("community")), reply_count: (.replies | length)}'
echo

echo "Comment 915 with nested replies:"
curl -s "${BASE_URL}?post_id=${POST_ID}&sort=${SORT}" | jq '.comments[] | select(.comment.id == 915) | {id: .comment.id, has_post: (has("post")), has_community: (has("community")), reply_count: (.replies | length), child_structure: [.replies[] | {id: .comment.id, has_post: (has("post")), has_community: (has("community"))}]}'
echo

# Test 5: Max depth filtering
echo "=== TEST 5: Max depth filtering ==="
echo "With max_depth=1:"
curl -s "${BASE_URL}?post_id=${POST_ID}&sort=${SORT}&max_depth=1" | jq '{comment_count: (.comments | length), top_level_ids: [.comments[] | .comment.id]}'
echo

echo "With max_depth=2:"
curl -s "${BASE_URL}?post_id=${POST_ID}&sort=${SORT}&max_depth=2" | jq '{comment_count: (.comments | length), top_level_ids: [.comments[] | .comment.id]}'
echo

# Test 6: Large page size to verify complete branches
echo "=== TEST 6: Large page size (complete data) ==="
echo "All comments with limit=10:"
curl -s "${BASE_URL}?post_id=${POST_ID}&sort=${SORT}&limit=10" | jq '{comment_count: (.comments | length), next_page: .next_page, structure: [.comments[] | {id: .comment.id, reply_count: (.replies | length)}]}'
echo

echo "================================="
echo "Test suite completed!"
echo "================================="