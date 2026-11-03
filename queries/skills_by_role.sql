-- Share of postings in each role category that mention each of the overall
-- top 12 skills. Long format: one row per (role, skill).
WITH scope AS (
    SELECT * FROM current_postings
    WHERE (:it_only = 0 OR role_category <> 'other')
),
role_totals AS (
    SELECT role_category, COUNT(*) AS total
    FROM scope
    GROUP BY role_category
),
top_skills AS (
    SELECT ps.skill_id
    FROM scope
    JOIN posting_skills AS ps USING (posting_id)
    JOIN skills         AS s  USING (skill_id)
    WHERE s.category <> 'language'
    GROUP BY ps.skill_id
    ORDER BY COUNT(*) DESC, ps.skill_id
    LIMIT 12
)
SELECT
    rt.role_category,
    rt.total                                                     AS role_postings,
    s.skill_id,
    s.label,
    COUNT(ps.posting_id)                                         AS postings,
    ROUND(100.0 * COUNT(ps.posting_id) / rt.total, 1)            AS share_pct
FROM role_totals AS rt
CROSS JOIN top_skills AS t
JOIN skills AS s ON s.skill_id = t.skill_id
LEFT JOIN scope AS p
       ON p.role_category = rt.role_category
LEFT JOIN posting_skills AS ps
       ON ps.posting_id = p.posting_id AND ps.skill_id = t.skill_id
GROUP BY rt.role_category, rt.total, s.skill_id, s.label
ORDER BY rt.role_category, share_pct DESC, s.label;
