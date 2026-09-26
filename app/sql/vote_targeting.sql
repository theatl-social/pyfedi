WITH v AS (
    SELECT pv.user_id, pv.author_id, pv.effect, pv.created_at, po.community_id
    FROM post_vote pv
    JOIN post po ON po.id = pv.post_id
    WHERE pv.created_at >= NOW() - make_interval(days => :days)
      AND pv.effect <> 0 AND pv.author_id IS NOT NULL AND pv.user_id <> pv.author_id
    UNION ALL
    SELECT prv.user_id, prv.author_id, prv.effect, prv.created_at, pr.community_id
    FROM post_reply_vote prv
    JOIN post_reply pr ON pr.id = prv.post_reply_id
    WHERE prv.created_at >= NOW() - make_interval(days => :days)
      AND prv.effect <> 0 AND prv.author_id IS NOT NULL AND prv.user_id <> prv.author_id
),
totals AS (
    SELECT user_id, COUNT(*) AS total FROM v GROUP BY user_id
),
pairs AS (
    SELECT user_id, author_id,
           COUNT(*) AS votes,
           COUNT(*) FILTER (WHERE effect > 0) AS ups,
           COUNT(*) FILTER (WHERE effect < 0) AS downs,
           COUNT(DISTINCT community_id) AS communities,
           MIN(created_at) AS first_vote,
           MAX(created_at) AS last_vote,
           COUNT(*)::float
               / GREATEST(COUNT(DISTINCT date_trunc('minute', created_at)), 1) AS per_min
    FROM v
    GROUP BY user_id, author_id
    HAVING COUNT(*) >= :min_votes
)
SELECT COALESCE(voter.ap_id, voter.user_name)   AS voter_label,
       COALESCE(target.ap_id, target.user_name) AS target_label,
       p.votes, p.ups, p.downs, p.communities,
       ROUND(100.0 * p.votes / t.total)                  AS share_pct,
       EXTRACT(EPOCH FROM (p.last_vote - p.first_vote))  AS span_seconds,
       p.per_min
FROM pairs p
JOIN totals t      ON t.user_id = p.user_id
JOIN "user" voter  ON voter.id  = p.user_id
JOIN "user" target ON target.id = p.author_id
WHERE (p.ups = 0 OR p.downs = 0)                     -- never voted the other way
  AND p.votes::float / t.total >= :min_focus
  AND (p.communities >= :min_communities OR p.per_min >= :min_rate)
  AND voter.deleted IS NOT TRUE AND voter.banned IS NOT TRUE
  AND target.deleted IS NOT TRUE AND target.bot IS NOT TRUE
ORDER BY p.votes DESC
LIMIT 50