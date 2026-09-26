WITH v AS (
    SELECT user_id, author_id, effect FROM post_vote
    WHERE created_at >= NOW() - make_interval(days => :days)
      AND effect <> 0 AND author_id IS NOT NULL AND user_id <> author_id
    UNION ALL
    SELECT user_id, author_id, effect FROM post_reply_vote
    WHERE created_at >= NOW() - make_interval(days => :days)
      AND effect <> 0 AND author_id IS NOT NULL AND user_id <> author_id
),
pairs AS (
    SELECT user_id, author_id, COUNT(*) AS votes,
           COUNT(*) FILTER (WHERE effect > 0) AS ups,
           COUNT(*) FILTER (WHERE effect < 0) AS downs
    FROM v
    GROUP BY user_id, author_id
    HAVING COUNT(*) >= :min_votes
)
SELECT voter.user_name                          AS username,
       COALESCE(voter.ap_id, voter.user_name)   AS voter_label,
       COALESCE(target.ap_id, target.user_name) AS target_label,
       p.votes, p.ups, p.downs
FROM pairs p
JOIN "user" voter  ON voter.id  = p.user_id
JOIN "user" target ON target.id = p.author_id
WHERE LOWER(voter.user_name) = LOWER(target.user_name)
  AND voter.instance_id IS DISTINCT FROM target.instance_id
  AND (p.ups = 0 OR p.downs = 0)
  AND voter.deleted IS NOT TRUE AND target.deleted IS NOT TRUE
ORDER BY p.votes DESC
LIMIT 100