WITH downvotes AS (
    SELECT user_id, author_id, created_at, 'post' AS kind, post_id AS item_id
    FROM post_vote
    WHERE effect < 0
      AND created_at > now() - interval '7 days'
      AND user_id <> author_id
    UNION ALL
    SELECT user_id, author_id, created_at, 'reply' AS kind, post_reply_id AS item_id
    FROM post_reply_vote
    WHERE effect < 0
      AND created_at > now() - interval '7 days'
      AND user_id <> author_id
),
windowed AS (
    SELECT user_id, author_id, created_at,
           count(*) OVER (
               PARTITION BY user_id, author_id
               ORDER BY created_at
               RANGE BETWEEN CURRENT ROW AND interval '3 minutes' FOLLOWING
           ) AS votes_in_3min
    FROM downvotes
)
SELECT w.user_id,
       voter.user_name  AS voter,
       voter.ap_domain  AS voter_domain,
       voter.ap_id      AS voter_ap_id,
       w.author_id,
       author.user_name AS author,
       author.ap_domain AS author_domain,
       max(w.votes_in_3min) AS max_downvotes_in_3min,
       min(w.created_at)    AS first_burst_start,
       count(*)             AS burst_windows
FROM windowed w
JOIN "user" voter  ON voter.id  = w.user_id
JOIN "user" author ON author.id = w.author_id
WHERE w.votes_in_3min >= 10 and not (author.bot_override is true or author.bot is true or author.banned is true or author.deleted is true)
GROUP BY w.user_id, voter.user_name, voter.ap_domain, voter.ap_id,
         w.author_id, author.user_name, author.ap_domain
ORDER BY max_downvotes_in_3min DESC, burst_windows DESC;