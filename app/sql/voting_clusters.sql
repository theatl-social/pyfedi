WITH raw AS (
    SELECT post_id * 2 AS item, user_id, SIGN(effect)::int AS dir
    FROM post_vote
    WHERE created_at >= NOW() - make_interval(days => :days) AND effect <> 0
    UNION ALL
    SELECT post_reply_id * 2 + 1, user_id, SIGN(effect)::int
    FROM post_reply_vote
    WHERE created_at >= NOW() - make_interval(days => :days) AND effect <> 0
),
item_n AS (
    SELECT item, COUNT(*) AS n FROM raw
    GROUP BY item HAVING COUNT(*) BETWEEN 2 AND :cap
),
rare AS (
    SELECT r.item, r.user_id, r.dir, i.n FROM raw r JOIN item_n i USING (item)
),
rare_c AS (
    SELECT rr.item, rr.user_id, rr.dir, po.community_id
    FROM rare rr JOIN post po ON po.id = rr.item / 2 WHERE MOD(rr.item, 2) = 0
    UNION ALL
    SELECT rr.item, rr.user_id, rr.dir, pr.community_id
    FROM rare rr JOIN post_reply pr ON pr.id = rr.item / 2 WHERE MOD(rr.item, 2) = 1
),
totals AS (
    SELECT user_id, COUNT(*) AS n, SUM(n) AS s_pop FROM rare GROUP BY user_id
),
universe AS (SELECT COUNT(*) AS v FROM rare),
pairs AS (
    SELECT a.user_id AS u1, b.user_id AS u2,
           COUNT(*) AS shared,
           COUNT(DISTINCT a.community_id) AS communities
    FROM rare_c a
    JOIN rare_c b ON b.item = a.item AND b.dir = a.dir AND b.user_id > a.user_id
    GROUP BY 1, 2
    HAVING COUNT(*) >= :min_shared AND COUNT(DISTINCT a.community_id) >= :min_communities
)
SELECT p.u1, p.u2, p.shared, p.communities,
       t1.n AS n1, t2.n AS n2, t1.s_pop AS s1, t2.s_pop AS s2,
       (SELECT v FROM universe) AS universe
FROM pairs p
JOIN totals t1 ON t1.user_id = p.u1
JOIN totals t2 ON t2.user_id = p.u2