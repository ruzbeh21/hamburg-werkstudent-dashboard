-- How often the top 10 skills appear together in the same posting.
-- The diagonal (skill_a = skill_b) is the skill's own posting count.
WITH scope AS (
    SELECT posting_id FROM current_postings
    WHERE (:it_only = 0 OR role_category <> 'other')
),
scoped_skills AS (
    SELECT ps.posting_id, ps.skill_id
    FROM posting_skills AS ps
    JOIN scope  USING (posting_id)
    JOIN skills AS s USING (skill_id)
    WHERE s.category <> 'language'
),
top10 AS (
    SELECT skill_id
    FROM scoped_skills
    GROUP BY skill_id
    ORDER BY COUNT(*) DESC, skill_id
    LIMIT 10
),
pairs AS (
    SELECT a.skill_id AS skill_a, b.skill_id AS skill_b, COUNT(*) AS postings
    FROM scoped_skills AS a
    JOIN scoped_skills AS b ON a.posting_id = b.posting_id
    GROUP BY a.skill_id, b.skill_id
)
SELECT
    a.skill_id                  AS skill_a,
    b.skill_id                  AS skill_b,
    COALESCE(p.postings, 0)     AS postings
FROM top10 AS a
CROSS JOIN top10 AS b
LEFT JOIN pairs AS p ON p.skill_a = a.skill_id AND p.skill_b = b.skill_id
ORDER BY a.skill_id, b.skill_id;
